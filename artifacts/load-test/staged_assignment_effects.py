"""Local-only, bounded reassignment and completion side-effect checks."""
import time

import httpx
from django.contrib.auth import get_user_model
from django.db import connection
from notifications.models import Notification
from projects.models import PipelineHistory
from tasks.models import TaskAssignment, TaskStatusCode


def run_stages(base, context, password, rows, logins, **kwargs):
    cfg = connection.settings_dict
    assert cfg['HOST'] == '127.0.0.1' and str(cfg['PORT']) == '3307' and cfg['NAME'] == 'heyzzabi_test'
    users = get_user_model()
    pm = users.objects.get(username='lt_small_001')
    owner = users.objects.get(username='lt_small_005')
    candidate = users.objects.get(username='lt_small_006')
    assert not TaskAssignment.objects.filter(assigned_user=pm).exists(), 'Dedicated completion account has other tasks'
    source = TaskAssignment.objects.filter(task_no__startswith='LT-', assigned_user=owner).first()
    assert source is not None
    snapshot_busy = {u.pk: u.is_busy for u in (pm, owner, candidate)}
    notification_start = Notification.objects.order_by('-pk').values_list('pk', flat=True).first() or 0
    history_start = PipelineHistory.objects.order_by('-pk').values_list('pk', flat=True).first() or 0
    clients, tasks, checks = {}, [], []
    begun = time.perf_counter()

    def login(label, user):
        c = httpx.Client(base_url=base, verify=context, trust_env=False, timeout=30)
        c.get('/api/users/csrf/').raise_for_status()
        response = c.post('/api/users/login/', json={'username': user.username, 'password': password},
                          headers={'X-CSRFToken': c.cookies.get('csrftoken'), 'Referer': base+'/'})
        response.raise_for_status()
        c.headers.update({'X-CSRFToken': c.cookies.get('csrftoken'), 'Referer': base+'/'})
        clients[label] = c
        logins.append({'role': label, 'status': response.status_code})

    def call(label, pk, path, payload, phase, expected):
        start = time.perf_counter()
        status, size, error = 0, 0, ''
        try:
            response = clients[label].patch(f'/api/tasks/assignments/{pk}/{path}', json=payload)
            status, size = response.status_code, len(response.content)
        except httpx.HTTPError as exc:
            error = type(exc).__name__
        end = time.perf_counter()
        valid = status == expected
        if not valid and not error: error = f'expected_{expected}_got_{status}'
        rows.append({'stage': 3, 'role': label, 'user': label, 'path': f'/api/tasks/assignments/{pk}/{path}',
                     'phase': phase, 'elapsed_ms': round((end-start)*1000, 3),
                     'started_offset_s': start-begun, 'completed_offset_s': end-begun,
                     'status': status, 'bytes': size, 'valid': valid, 'error': error})
        return status

    def check(name, passed, detail=''):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    try:
        # Create only two identifiable synthetic tasks; remove them in finally.
        for suffix, assignee in [('REASSIGN', owner), ('COMPLETE', pm)]:
            task = TaskAssignment.objects.create(
                req_item=source.req_item, project=source.project,
                assigned_user=assignee, task_no=f'LT-EFFECT-{suffix}',
                title=f'[LOADTEST effects] {suffix}', description='temporary test task',
                status_code_id=TaskStatusCode.PENDING_APPROVAL, progress=0)
            tasks.append(task)
        a, b = tasks
        login('pm', pm); login('owner', owner); login('candidate', candidate)

        assert TaskAssignment.objects.filter(assigned_user=owner).exclude(pk=a.pk).exclude(
            status_code_id=TaskStatusCode.COMPLETED).exists()
        users.objects.filter(pk=owner.pk).update(is_busy=True)

        call('owner', a.pk, 'status/', {'assigned_user_id': candidate.pk}, 'non_pm_reassign', 403)
        check('non_pm_reassign_unchanged', TaskAssignment.objects.get(pk=a.pk).assigned_user_id == owner.pk)
        call('pm', a.pk, 'status/', {'assigned_user_id': candidate.pk}, 'pm_reassign', 200)
        a.refresh_from_db()
        check('pm_reassign_target', a.assigned_user_id == candidate.pk)
        check('new_assignee_busy', users.objects.get(pk=candidate.pk).is_busy)
        check('old_assignee_still_busy_with_other_tasks', users.objects.get(pk=owner.pk).is_busy)
        count = Notification.objects.filter(pk__gt=notification_start, user=candidate).count()
        check('one_reassignment_notification', count == 1, f'count={count}')
        call('pm', a.pk, 'status/', {'assigned_user_id': candidate.pk}, 'same_assignee_retry', 200)
        count = Notification.objects.filter(pk__gt=notification_start, user=candidate).count()
        check('no_duplicate_reassignment_notification', count == 1, f'count={count}')
        call('pm', a.pk, 'status/', {'status_code': TaskStatusCode.APPROVED}, 'approve_before_lock', 200)
        call('pm', a.pk, 'status/', {'assigned_user_id': owner.pk}, 'approved_reassign_block', 403)
        check('approved_reassign_unchanged', TaskAssignment.objects.get(pk=a.pk).assigned_user_id == candidate.pk)

        users.objects.filter(pk=pm.pk).update(is_busy=True)
        call('pm', b.pk, 'status/', {'status_code': TaskStatusCode.COMPLETED}, 'complete_only_task', 200)
        b.refresh_from_db()
        check('completion_status_progress', b.status_code_id == TaskStatusCode.COMPLETED and b.progress == 100,
              f'status={b.status_code_id},progress={b.progress}')
        check('completion_clears_busy_without_other_tasks', not users.objects.get(pk=pm.pk).is_busy)
        n = Notification.objects.filter(pk__gt=notification_start, user=pm).count()
        h = PipelineHistory.objects.filter(pk__gt=history_start, task=b).count()
        check('completion_notification_and_history', n == 1 and h == 1, f'notifications={n},histories={h}')
        call('pm', b.pk, 'status/', {'status_code': TaskStatusCode.COMPLETED}, 'completion_retry', 200)
        n2 = Notification.objects.filter(pk__gt=notification_start, user=pm).count()
        h2 = PipelineHistory.objects.filter(pk__gt=history_start, task=b).count()
        check('no_duplicate_completion_side_effects', n2 == 1 and h2 == 1,
              f'notifications={n2},histories={h2}')
        call('pm', b.pk, 'status/', {'assigned_user_id': candidate.pk}, 'completed_reassign_block', 403)
        check('completed_reassign_unchanged', TaskAssignment.objects.get(pk=b.pk).assigned_user_id == pm.pk)

        return [{'users': 3, 'started_unix': time.time(),
                 'elapsed_seconds_including_drain': time.perf_counter()-begun,
                 'requests': len(rows), 'errors': sum(not row['valid'] for row in rows),
                 'stopped_early': False, 'checks': checks,
                 'integrity_mismatches': [item for item in checks if not item['passed']]}]
    finally:
        for client in clients.values(): client.close()
        PipelineHistory.objects.filter(pk__gt=history_start, task__in=tasks).delete()
        Notification.objects.filter(pk__gt=notification_start,
                                    user_id__in=[pm.pk, owner.pk, candidate.pk],
                                    message__contains='[LOADTEST effects]').delete()
        for task in tasks: TaskAssignment.objects.filter(pk=task.pk).delete()
        for pk, value in snapshot_busy.items(): users.objects.filter(pk=pk).update(is_busy=value)
        assert not TaskAssignment.objects.filter(pk__in=[task.pk for task in tasks]).exists()
        assert all(users.objects.get(pk=pk).is_busy == value for pk, value in snapshot_busy.items())
