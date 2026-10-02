"""Bounded local task update and lost-update probe; restores synthetic task fields."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time
from django.contrib.auth import get_user_model
from django.db import connection
from tasks.models import TaskAssignment
import httpx


def run_stages(base, context, password, rows, logins, **kwargs):
    cfg = connection.settings_dict
    assert cfg['NAME'] == 'heyzzabi_test' and str(cfg['PORT']) == '3307'
    clients, tasks, snapshots = [], [], []
    started = time.perf_counter()
    mismatches = []
    try:
        for n in range(1, 21):
            user = get_user_model().objects.get(username=f'lt_small_{n:03}')
            candidates = TaskAssignment.objects.filter(task_no__startswith='LT-', assigned_user__username__startswith='lt_small_').exclude(is_task_header=True).exclude(status_code_id='BACKLOG').exclude(pk__in=tasks)
            if not user.is_staff:
                candidates = candidates.filter(assigned_user=user)
            task = candidates.first()
            assert task is not None
            snapshots.append({'id': task.pk, 'progress': task.progress,
                              'status_code_id': task.status_code_id, 'description': task.description})
            tasks.append(task.pk)
            client = httpx.Client(base_url=base, verify=context, trust_env=False, timeout=30)
            clients.append(client)
            client.get('/api/users/csrf/').raise_for_status()
            response = client.post('/api/users/login/', json={'username': user.username, 'password': password},
                                   headers={'X-CSRFToken': client.cookies.get('csrftoken'), 'Referer': base+'/'})
            response.raise_for_status()
            client.headers.update({'X-CSRFToken': client.cookies.get('csrftoken'), 'Referer': base+'/'})
            logins.append({'role': 'pm' if user.is_staff else 'member', 'status': response.status_code})

        def request(index, payload, phase, barrier=None, target=None):
            if barrier:
                barrier.wait(timeout=30)
            t = time.perf_counter()
            path = f'/api/tasks/assignments/{target or tasks[index]}/'
            status, valid, error, size = 0, False, '', 0
            try:
                response = clients[index].patch(path, json=payload)
                status, size = response.status_code, len(response.content)
                valid = status == 200 and all(response.json().get(k) == v for k, v in payload.items())
                if not valid:
                    error = 'status_or_body_mismatch'
            except httpx.HTTPError as exc:
                error = type(exc).__name__
            end = time.perf_counter()
            rows.append({'stage': 20, 'role': 'pm' if index < 4 else 'member', 'user': index+1,
                         'path': path, 'phase': phase, 'elapsed_ms': round((end-t)*1000, 3),
                         'started_offset_s': t-started, 'completed_offset_s': end-started,
                         'status': status, 'bytes': size, 'valid': valid, 'error': error})

        measured = time.time()
        clock = time.perf_counter()
        with ThreadPoolExecutor(max_workers=20) as pool:
            for round_ in range(10):
                barrier = threading.Barrier(20)
                value = 10 + round_
                futures = [pool.submit(request, i, {'progress': value, 'status_code': snapshots[i]['status_code_id']}, 'isolated', barrier) for i in range(20)]
                for f in futures:
                    f.result()
                for pk in tasks:
                    if TaskAssignment.objects.get(pk=pk).progress != value:
                        mismatches.append({'phase': 'isolated', 'id': pk, 'round': round_})
            # Separate clients update disjoint fields on one task at the same time.
            for round_ in range(20):
                barrier = threading.Barrier(2)
                desc = f'[LOADTEST concurrent edit {round_}]'
                value = 30 + round_
                futures = [pool.submit(request, 0, {'progress': value, 'status_code': snapshots[0]['status_code_id']}, 'collision', barrier),
                           pool.submit(request, 1, {'description': desc, 'status_code': snapshots[0]['status_code_id']}, 'collision', barrier, tasks[0])]
                for f in futures:
                    f.result()
                task = TaskAssignment.objects.get(pk=tasks[0])
                if task.progress != value or task.description != desc:
                    mismatches.append({'phase': 'collision', 'round': round_,
                                       'progress_matches': task.progress == value,
                                       'description_matches': task.description == desc})
        elapsed = time.perf_counter()-clock
        return [{'users': 20, 'started_unix': measured, 'elapsed_seconds_including_drain': elapsed,
                 'requests': len(rows), 'errors': sum(not x['valid'] for x in rows),
                 'stopped_early': False, 'integrity_mismatches': mismatches,
                 'isolated_rounds': 10, 'collision_rounds': 20}]
    finally:
        for snapshot in snapshots:
            pk = snapshot['id']
            TaskAssignment.objects.filter(pk=pk).update(**{k: v for k, v in snapshot.items() if k != 'id'})
        for client in clients:
            client.close()
        assert all(TaskAssignment.objects.filter(pk=s['id'], progress=s['progress'], status_code_id=s['status_code_id'], description=s['description']).exists() for s in snapshots), 'Restoration mismatch'
