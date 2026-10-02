"""Task status permissions, side effects, and cross-endpoint concurrency probe."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import httpx
from django.contrib.auth import get_user_model
from django.db import connection
from notifications.models import Notification
from projects.models import PipelineHistory
from tasks.models import TaskAssignment, TaskStatusCode


def run_stages(base, context, password, rows, logins, **kwargs):
    cfg = connection.settings_dict
    assert cfg['NAME'] == 'heyzzabi_test' and str(cfg['PORT']) == '3307'
    users = get_user_model()
    owner = users.objects.get(username='lt_small_005')
    outsider = users.objects.get(username='lt_small_006')
    pm = users.objects.get(username='lt_small_001')
    task = (TaskAssignment.objects.filter(task_no__startswith='LT-', assigned_user=owner)
            .exclude(is_task_header=True).exclude(status_code_id=TaskStatusCode.BACKLOG).first())
    assert task
    snapshot = {name: getattr(task, name) for name in
                ['status_code_id', 'progress', 'description', 'reject_reason', 'assigned_user_id']}
    busy = {u.pk: u.is_busy for u in [owner, outsider, pm]}
    notification_start = Notification.objects.order_by('-pk').values_list('pk', flat=True).first() or 0
    history_start = PipelineHistory.objects.order_by('-pk').values_list('pk', flat=True).first() or 0
    clients = {}
    started = time.perf_counter()
    mismatches = []

    def login(label, user):
        c = httpx.Client(base_url=base, verify=context, trust_env=False, timeout=30)
        c.get('/api/users/csrf/').raise_for_status()
        response = c.post('/api/users/login/', json={'username': user.username, 'password': password},
                          headers={'X-CSRFToken': c.cookies.get('csrftoken'), 'Referer': base+'/'})
        response.raise_for_status()
        c.headers.update({'X-CSRFToken': c.cookies.get('csrftoken'), 'Referer': base+'/'})
        clients[label] = c
        logins.append({'role': label, 'status': response.status_code})

    def call(label, path, payload, phase, expected, barrier=None):
        if barrier:
            barrier.wait(timeout=30)
        begin = time.perf_counter()
        error = ''
        try:
            response = clients[label].patch(path, json=payload)
            status = response.status_code
            valid = status == expected
            size = len(response.content)
            if not valid:
                error = f'expected_{expected}_got_{status}'
        except httpx.HTTPError as exc:
            status, size, valid, error = 0, 0, False, type(exc).__name__
        end = time.perf_counter()
        rows.append({'stage': 3, 'role': label, 'user': label, 'path': path, 'phase': phase,
                     'elapsed_ms': round((end-begin)*1000, 3), 'started_offset_s': begin-started,
                     'completed_offset_s': end-started, 'status': status, 'bytes': size,
                     'valid': valid, 'error': error})
        return status

    detail = f'/api/tasks/assignments/{task.pk}/'
    status_path = f'/api/tasks/assignments/{task.pk}/status/'
    try:
        login('owner', owner); login('outsider', outsider); login('pm', pm)
        call('outsider', status_path, {'status_code': TaskStatusCode.IN_PROGRESS}, 'permission', 403)
        call('outsider', detail, {'description': 'forbidden'}, 'permission', 404)
        call('owner', status_path, {'status_code': TaskStatusCode.REJECTED}, 'validation', 400)

        # Disjoint writes through detail and status endpoints must both survive.
        for round_ in range(20):
            TaskAssignment.objects.filter(pk=task.pk).update(
                status_code_id=TaskStatusCode.PENDING_APPROVAL, progress=0,
                description=snapshot['description'], reject_reason=None)
            barrier = threading.Barrier(2)
            marker = f'[LOADTEST status cross {round_}]'
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(call, 'owner', status_path,
                                {'status_code': TaskStatusCode.IN_PROGRESS}, 'cross_endpoint', 200, barrier),
                    pool.submit(call, 'pm', detail, {'description': marker},
                                'cross_endpoint', 200, barrier),
                ]
                for future in futures: future.result()
            current = TaskAssignment.objects.get(pk=task.pk)
            if current.status_code_id != TaskStatusCode.IN_PROGRESS or current.description != marker:
                mismatches.append({'phase': 'cross_endpoint', 'round': round_,
                                   'status': current.status_code_id,
                                   'description': current.description,
                                   'status_matches': current.status_code_id == TaskStatusCode.IN_PROGRESS,
                                   'description_matches': current.description == marker})

        # Two identical transitions should create one notification and one history row.
        TaskAssignment.objects.filter(pk=task.pk).update(status_code_id=TaskStatusCode.PENDING_APPROVAL)
        before_n = Notification.objects.filter(pk__gt=notification_start).count()
        before_h = PipelineHistory.objects.filter(pk__gt=history_start).count()
        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(call, label, status_path,
                                   {'status_code': TaskStatusCode.APPROVED},
                                   'duplicate_transition', 200, barrier)
                       for label in ['owner', 'pm']]
            for future in futures: future.result()
        added_n = Notification.objects.filter(pk__gt=notification_start).count() - before_n
        added_h = PipelineHistory.objects.filter(pk__gt=history_start).count() - before_h
        if added_n != 1 or added_h != 1:
            mismatches.append({'phase': 'duplicate_transition',
                               'notifications': added_n, 'histories': added_h})

        return [{'users': 3, 'started_unix': time.time(),
                 'elapsed_seconds_including_drain': time.perf_counter()-started,
                 'requests': len(rows), 'errors': sum(not x['valid'] for x in rows),
                 'stopped_early': False, 'integrity_mismatches': mismatches,
                 'cross_endpoint_rounds': 20, 'duplicate_transition_rounds': 1}]
    finally:
        TaskAssignment.objects.filter(pk=task.pk).update(**snapshot)
        for pk, value in busy.items(): users.objects.filter(pk=pk).update(is_busy=value)
        Notification.objects.filter(pk__gt=notification_start).delete()
        PipelineHistory.objects.filter(pk__gt=history_start).delete()
        for client in clients.values(): client.close()
        restored = TaskAssignment.objects.get(pk=task.pk)
        assert all(getattr(restored, key) == value for key, value in snapshot.items())
