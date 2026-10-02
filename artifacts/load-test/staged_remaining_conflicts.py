"""Bounded retired-reassignment, concurrent completion, and confirm probes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import time

import httpx
from django.contrib.auth import get_user_model
from django.db import connection
from requirements.models import RequirementDefinition, RequirementItem
from tasks.models import TaskAssignment, TaskStatusCode


def run_stages(base, context, password, rows, logins, **kwargs):
    cfg = connection.settings_dict
    assert cfg['HOST'] == '127.0.0.1' and str(cfg['PORT']) == '3307' and cfg['NAME'] == 'heyzzabi_test'
    User = get_user_model()
    pm = User.objects.get(username='lt_small_001')
    owner = User.objects.get(username='lt_small_005')
    candidate = User.objects.get(username='lt_small_006')
    source = TaskAssignment.objects.filter(task_no__startswith='LT-', assigned_user=owner).select_related('req_item__req_def').first()
    assert source and not TaskAssignment.objects.filter(assigned_user=pm).exists()
    busy = {u.pk: u.is_busy for u in (pm, owner, candidate)}
    owner_resign = owner.resign_date
    made_tasks, clients, checks = [], [], []
    temp_def = temp_item = None
    begun = time.perf_counter()

    def login(label):
        c = httpx.Client(base_url=base, verify=context, trust_env=False, timeout=30)
        c.get('/api/users/csrf/').raise_for_status()
        r = c.post('/api/users/login/', json={'username': pm.username, 'password': password},
                   headers={'X-CSRFToken': c.cookies.get('csrftoken'), 'Referer': base+'/'})
        r.raise_for_status(); c.headers.update({'X-CSRFToken': c.cookies.get('csrftoken'), 'Referer': base+'/'})
        clients.append(c); logins.append({'role': label, 'status': r.status_code})
        return c

    def record(label, path, started, response, expected=200):
        ended = time.perf_counter(); valid = response.status_code == expected
        rows.append({'stage': 3, 'role': label, 'user': label, 'path': path, 'phase': label,
                     'elapsed_ms': round((ended-started)*1000, 3), 'started_offset_s': started-begun,
                     'completed_offset_s': ended-begun, 'status': response.status_code,
                     'bytes': len(response.content), 'valid': valid,
                     'error': '' if valid else f'expected_{expected}_got_{response.status_code}'})
        return response

    def check(name, passed, detail=''):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    try:
        c1, c2 = login('pm_a'), login('pm_b')
        retired = TaskAssignment.objects.create(req_item=source.req_item, project=source.project,
            assigned_user=owner, task_no='LT-REMAIN-RETIRED', title='[LOADTEST] retired reassignment',
            status_code_id=TaskStatusCode.APPROVED, progress=10)
        done_a = TaskAssignment.objects.create(req_item=source.req_item, project=source.project,
            assigned_user=pm, task_no='LT-REMAIN-DONE-A', title='[LOADTEST] concurrent done A',
            status_code_id=TaskStatusCode.IN_PROGRESS, progress=50)
        done_b = TaskAssignment.objects.create(req_item=source.req_item, project=source.project,
            assigned_user=pm, task_no='LT-REMAIN-DONE-B', title='[LOADTEST] concurrent done B',
            status_code_id=TaskStatusCode.IN_PROGRESS, progress=50)
        made_tasks += [retired, done_a, done_b]

        User.objects.filter(pk=owner.pk).update(resign_date=date.today())
        started=time.perf_counter(); r=c1.patch(f'/api/tasks/assignments/{retired.pk}/status/', json={'assigned_user_id': candidate.pk})
        record('retired_reassign', f'/api/tasks/assignments/{retired.pk}/status/', started, r)
        retired.refresh_from_db(); check('retired_locked_task_reassigned', retired.assigned_user_id == candidate.pk)

        User.objects.filter(pk=pm.pk).update(is_busy=True)
        def complete(pair):
            client, task = pair; started=time.perf_counter()
            r=client.patch(f'/api/tasks/assignments/{task.pk}/status/', json={'status_code': TaskStatusCode.COMPLETED})
            return task, started, r
        with ThreadPoolExecutor(max_workers=2) as pool:
            completed=list(pool.map(complete, [(c1, done_a), (c2, done_b)]))
        for task, started, r in completed:
            record('concurrent_complete', f'/api/tasks/assignments/{task.pk}/status/', started, r)
        done_a.refresh_from_db(); done_b.refresh_from_db(); pm.refresh_from_db()
        check('both_tasks_done', all(t.status_code_id == TaskStatusCode.COMPLETED and t.progress == 100 for t in (done_a, done_b)))
        check('busy_cleared_after_last_completion', not pm.is_busy, f'is_busy={pm.is_busy}')

        temp_def = RequirementDefinition.objects.create(spec=source.req_item.req_def.spec,
            project=source.project, title='[LOADTEST] concurrent confirmation', status_code_id='APPROVED', created_by=pm)
        temp_item = RequirementItem.objects.create(req_def=temp_def, req_code='LT-CONFIRM-1',
            req_name='temporary', description='temporary', order=1)
        assignments=[{'unit_id':'A','source_req_id':temp_item.req_code,'assignee_id':candidate.pk,
                      'title':'[LOADTEST] confirm A','description':'temporary','estimated_hours':1},
                     {'unit_id':'B','source_req_id':temp_item.req_code,'assignee_id':candidate.pk,
                      'title':'[LOADTEST] confirm B','description':'temporary','estimated_hours':1}]
        path=f'/api/requirements/{temp_def.spec_id}/confirm-tasks/'
        def confirm(client):
            started=time.perf_counter(); r=client.post(path, json={'req_def_id':temp_def.pk,'assignments':assignments})
            return started, r
        with ThreadPoolExecutor(max_workers=2) as pool:
            confirmed=list(pool.map(confirm, (c1,c2)))
        for started, r in confirmed: record('concurrent_confirm', path, started, r)
        final=TaskAssignment.objects.filter(req_item__req_def=temp_def)
        check('confirm_exactly_two_tasks', final.count() == 2, f'count={final.count()}')
        check('confirm_unique_task_numbers', final.values('task_no').distinct().count() == 2)
        check('confirm_all_pending', not final.exclude(status_code_id=TaskStatusCode.PENDING_APPROVAL).exists())

        return [{'users':2, 'started_unix':time.time(), 'elapsed_seconds_including_drain':time.perf_counter()-begun,
                 'requests':len(rows), 'errors':sum(not x['valid'] for x in rows), 'stopped_early':False,
                 'checks':checks, 'integrity_mismatches':[x for x in checks if not x['passed']]}]
    finally:
        for c in clients: c.close()
        if temp_def: RequirementDefinition.objects.filter(pk=temp_def.pk).delete()
        TaskAssignment.objects.filter(pk__in=[x.pk for x in made_tasks]).delete()
        User.objects.filter(pk=owner.pk).update(resign_date=owner_resign)
        for pk, value in busy.items(): User.objects.filter(pk=pk).update(is_busy=value)
