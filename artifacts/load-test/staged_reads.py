"""Closed-model read workload for http_baseline.py --staged.

All users have individual authenticated HTTP sessions. Login and warmup are
excluded from measured requests. Deterministic per-user random streams select
weighted endpoints and 2–5 second think times. No AI or domain writes.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import random
import threading
import time

import httpx


def run_stages(base, context, password, rows, logins, *, stage_users, stage_duration):
    paths = ['/api/dashboard/overview/', '/api/projects/', '/api/tasks/assignments/',
             '/api/meetings/notes/', '/api/meetings/specs/', '/api/requirements/',
             '/api/notifications/']
    weights = [25, 20, 20, 10, 10, 10, 5]
    stages = []
    lock = threading.Lock()
    with ExitStack() as stack:
        clients = {}
        for i in range(1, 21):
            client = stack.enter_context(httpx.Client(
                base_url=base, verify=context, trust_env=False, timeout=15))
            client.get('/api/users/csrf/').raise_for_status()
            start = time.perf_counter()
            response = client.post('/api/users/login/',
                                   json={'username': f'lt_small_{i:03}', 'password': password},
                                   headers={'X-CSRFToken': client.cookies.get('csrftoken'),
                                            'Referer': base+'/'})
            logins.append({'role': 'pm' if i <= 4 else 'member', 'user': i,
                           'status': response.status_code,
                           'elapsed_ms': (time.perf_counter()-start)*1000})
            response.raise_for_status()
            assert client.cookies.get('access_token')
            clients[i] = client
        for i in [1, 5]:
            for path in paths:
                clients[i].get(path).raise_for_status()
        print('20 user sessions and per-role warmup ready.', flush=True)
        for count in stage_users:
            if count < 5 or count > 20 or count % 5:
                raise ValueError('Stage users must be one of 5, 10, 15, 20.')
            selected = list(range(1, count//5+1)) + list(range(5, 5+count-count//5))
            stage_stop = threading.Event()
            start_unix = time.time()
            start = time.perf_counter()
            deadline = start+stage_duration
            initial_rows = len(rows)

            def user_loop(i):
                rng = random.Random(20261001+count*100+i)
                stage_stop.wait(rng.uniform(0, 2))
                while time.perf_counter() < deadline and not stage_stop.is_set():
                    path = rng.choices(paths, weights=weights, k=1)[0]
                    started = time.perf_counter()
                    status, size, valid, error = 0, 0, False, ''
                    try:
                        response = clients[i].get(path)
                        status, size = response.status_code, len(response.content)
                        valid = status == 200 and isinstance(response.json(), (dict, list))
                        if not valid:
                            error = 'unexpected_status_or_json'
                    except (httpx.HTTPError, ValueError) as exc:
                        error = type(exc).__name__
                    finished = time.perf_counter()
                    row = {'stage': count, 'role': 'pm' if i <= 4 else 'member',
                           'user': i, 'path': path,
                           'started_offset_s': round(started-start, 6),
                           'completed_offset_s': round(finished-start, 6),
                           'elapsed_ms': round((finished-started)*1000, 3),
                           'status': status, 'bytes': size, 'valid': valid, 'error': error}
                    with lock:
                        rows.append(row)
                        recent = rows[initial_rows:]
                        if len(recent) >= 20 and sum(not r['valid'] for r in recent)/len(recent) > .05:
                            stage_stop.set()
                    stage_stop.wait(max(0, min(rng.uniform(2, 5), deadline-time.perf_counter())))

            print(f'Stage {count} users starting ({stage_duration} seconds).', flush=True)
            with ThreadPoolExecutor(max_workers=count) as pool:
                futures = [pool.submit(user_loop, i) for i in selected]
                for future in futures:
                    future.result()
            duration = time.perf_counter()-start
            subset = rows[initial_rows:]
            stages.append({'users': count, 'started_unix': start_unix,
                           'elapsed_seconds_including_drain': duration,
                           'requests': len(subset), 'errors': sum(not r['valid'] for r in subset),
                           'stopped_early': stage_stop.is_set()})
            print(f'Stage {count} finished: {len(subset)} requests, '
                  f'{stages[-1]["errors"]} errors.', flush=True)
            if stage_stop.is_set():
                raise RuntimeError('Stopped: error rate above 5% after at least 20 requests')
    return stages
