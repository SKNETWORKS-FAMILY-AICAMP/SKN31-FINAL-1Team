"""Local single-user HTTPS baseline. Starts and always stops its own Gunicorn.

Run with the project parent virtualenv. No AI calls, no writes except login session
bookkeeping. A temporary self-signed certificate is explicitly trusted by httpx.
"""
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

import httpx
import psutil
import ssl

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
PORT = 18084
BASE = f'https://127.0.0.1:{PORT}'
SAMPLES = 20
PAUSE = 0.1


def main():
    mixed = '--mixed' in sys.argv
    remaining_conflicts = '--remaining-conflicts' in sys.argv
    assignment_effects = '--assignment-effects' in sys.argv
    status_writes = '--status-writes' in sys.argv
    writes = '--writes' in sys.argv or status_writes or assignment_effects or remaining_conflicts or mixed
    staged = '--staged' in sys.argv or writes
    os.environ.update(DJANGO_SETTINGS_MODULE='config.settings', DEBUG='False',
                      ALLOWED_HOSTS='127.0.0.1,localhost')
    sys.path.insert(0, str(BACKEND))
    import django
    django.setup()
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from django.contrib.auth import get_user_model
    from projects.models import Project
    from tasks.models import TaskAssignment
    cfg = connection.settings_dict
    if not (cfg['HOST'] == '127.0.0.1' and str(cfg['PORT']) == '3307'
            and cfg['NAME'] == 'heyzzabi_test'):
        raise RuntimeError('Refusing non-local database target')
    executor = MigrationExecutor(connection)
    assert not executor.migration_plan(executor.loader.graph.leaf_nodes())
    with connection.cursor() as cursor:
        cursor.execute('SELECT VERSION()')
        mysql_version = cursor.fetchone()[0]
    users = get_user_model()
    counts = {'all_users': users.objects.count(),
              'test_users': users.objects.filter(username__startswith='lt_small_').count(),
              'projects': Project.objects.count(), 'tasks': TaskAssignment.objects.count()}
    assert counts['test_users'] == 20 and counts['tasks'] >= 200
    connection.close()
    with socket.socket() as check:
        # Match Gunicorn's reuse policy so TIME_WAIT from a completed run
        # does not block the next run; an active listener still fails bind.
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        check.bind(('127.0.0.1', PORT))

    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'artifacts/load-test' / f'{"mixed" if mixed else "remaining-conflicts" if remaining_conflicts else "assignment-effects" if assignment_effects else "status-writes" if status_writes else "writes" if writes else "stages" if staged else "baseline"}-{run_id}'
    out.mkdir()
    env = os.environ.copy()
    password = env.get('LOADTEST_PASSWORD', 'LocalLoad2026!')
    rows, resources, logins = [], [], []
    stop = threading.Event()
    server = None
    manifest = {
        'run_id': run_id, 'status': 'running', 'base_url': BASE,
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'python': sys.version.split()[0], 'mysql': mysql_version,
        'database': 'heyzzabi_test', 'counts': counts, 'debug': False,
        'web_server': 'Gunicorn: 1 worker, gthread, 2 threads',
        'samples_per_endpoint_per_role': SAMPLES, 'warmup_requests_per_endpoint': 2,
        'concurrency': 1, 'pause_seconds': PAUSE,
        'limitations': ['Local server and generator share host; Docker MySQL on same machine',
                        'Direct HTTPS; excludes Vercel and nginx',
                        '20 samples per endpoint; tail estimates exploratory',
                        'Read-only workload plus login session updates; no AI calls',
                        'Resource samples exclude MySQL container and are not DB profiling'],
    }
    if staged:
        stage_users = [int(value) for value in os.environ.get('LOADTEST_STAGES', '5,10,20').split(',')]
        stage_duration = int(os.environ.get('LOADTEST_STAGE_SECONDS', '60'))
        manifest.pop('samples_per_endpoint_per_role')
        manifest.pop('pause_seconds')
        manifest.update(concurrency=stage_users, duration_per_stage_seconds=stage_duration,
                        think_time_seconds=[2, 5], model='closed user model; read-only',
                        role_ratio='20% PM, 80% member', seed=20261001,
                        warmup_requests_per_endpoint='one per role before stages',
                        endpoint_weights={'overview': 25, 'projects': 20, 'tasks': 20,
                                          'notes': 10, 'specs': 10, 'requirements': 10,
                                          'notifications': 5})
        manifest['limitations'][2] = f'One {stage_duration}-second run per stage; per-endpoint sample sizes vary'
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2))
    try:
        with tempfile.TemporaryDirectory(prefix='heyzzabi-baseline-') as temp, (out/'server.log').open('w') as log:
            cert, key = Path(temp)/'cert.pem', Path(temp)/'key.pem'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-keyout', str(key), '-out', str(cert), '-days', '1',
                            '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1'],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            server = subprocess.Popen([
                sys.executable, '-m', 'gunicorn', 'config.wsgi:application',
                '--bind', f'127.0.0.1:{PORT}', '--workers', '1', '--worker-class', 'gthread',
                '--threads', '2', '--timeout', '60', '--certfile', str(cert), '--keyfile', str(key),
            ], cwd=BACKEND, env=env, stdout=log, stderr=log)
            context = ssl.create_default_context(cafile=str(cert))
            with httpx.Client(base_url=BASE, verify=context, trust_env=False, timeout=10) as probe:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError('Gunicorn exited; see server.log')
                    try:
                        if probe.get('/api/users/csrf/').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError('Server readiness timeout')

            def monitor():
                while not stop.wait(1):
                    try:
                        processes = [psutil.Process(server.pid)]
                        processes += processes[0].children(recursive=True)
                        resources.append({'unix_time': time.time(),
                                          'server_rss_bytes': sum(p.memory_info().rss for p in processes),
                                          'server_threads': sum(p.num_threads() for p in processes),
                                          'server_cpu_seconds': sum(sum(p.cpu_times()[:2]) for p in processes),
                                          'generator_rss_bytes': psutil.Process().memory_info().rss})
                    except psutil.Error:
                        pass
            watcher = threading.Thread(target=monitor, daemon=True)
            watcher.start()
            if staged:
                if writes:
                    if mixed:
                        from staged_mixed import run_stages
                        manifest.update(model='20-user closed mixed read/write model', role_ratio='20% PM, 80% member',
                                        endpoint_weights={'reads':80,'task_description_patch':20},
                                        limitations=['Local HTTPS; server and generator share host; no AI calls'],
                                        restoration='Twenty temporary tasks removed after final-value verification')
                    elif remaining_conflicts:
                        from staged_remaining_conflicts import run_stages
                        manifest.update(model='bounded remaining conflict probe',
                                        limitations=['Local HTTPS; temporary records; no AI calls'],
                                        scenario='retired reassignment, concurrent completion, concurrent confirmation',
                                        restoration='Temporary tasks/definition removed; resign and busy fields restored')
                    elif assignment_effects:
                        from staged_assignment_effects import run_stages
                        manifest.update(model='bounded assignment/completion side-effect probe',
                                        limitations=['Local HTTPS; synthetic temporary tasks; no AI or confirmations'],
                                        scenario='permission, reassignment, locked reassignment, completion, notification and busy state',
                                        restoration='Temporary tasks and related notifications/histories removed; user busy flags restored')
                    elif status_writes:
                        from staged_status_writes import run_stages
                        manifest.update(
                            model='bounded task status/detail concurrency probe',
                            limitations=['Local HTTPS; same host server and generator',
                                         'One synthetic task and three accounts; no AI or confirmations'],
                            scenario='20 status/detail collisions; duplicate transition; permission and validation',
                            restoration='Task, user busy flags, notifications and pipeline history restored in finally')
                    else:
                        from staged_writes import run_stages
                        manifest.update(model='bounded concurrent task PATCH',
                                        limitations=['Local HTTPS; same host server and generator',
                                                     'Task progress/description updates only; no AI or confirmations'],
                                        scenario='20 isolated task edits; 20 paired same-task edits',
                                        restoration='Selected synthetic task fields restored in finally')
                else:
                    from staged_reads import run_stages
                manifest['stages'] = run_stages(
                    BASE, context, password, rows, logins,
                    stage_users=stage_users, stage_duration=stage_duration,
                )
            paths = ['/api/users/me/', '/api/dashboard/overview/', '/api/projects/',
                     '/api/tasks/assignments/', '/api/meetings/notes/', '/api/meetings/specs/',
                     '/api/requirements/', '/api/notifications/']
            for role, username in ([] if staged else [('pm', 'lt_small_001'), ('member', 'lt_small_005')]):
                with httpx.Client(base_url=BASE, verify=context, trust_env=False, timeout=30) as client:
                    client.get('/api/users/csrf/').raise_for_status()
                    token = client.cookies.get('csrftoken')
                    started = time.perf_counter()
                    response = client.post('/api/users/login/',
                                           json={'username': username, 'password': password},
                                           headers={'X-CSRFToken': token, 'Referer': BASE+'/'})
                    logins.append({'role': role, 'status': response.status_code,
                                   'elapsed_ms': (time.perf_counter()-started)*1000})
                    response.raise_for_status()
                    assert client.cookies.get('access_token'), 'Missing auth cookie'
                    if role == 'member':
                        assert client.get('/api/dashboard/analytics/').status_code == 403
                    role_paths = paths + (['/api/dashboard/analytics/'] if role == 'pm' else [])
                    for path in role_paths:
                        for _ in range(2):
                            client.get(path).raise_for_status()
                        for index in range(SAMPLES):
                            start = time.perf_counter()
                            response = client.get(path)
                            elapsed = (time.perf_counter()-start)*1000
                            valid = response.status_code == 200
                            if valid:
                                valid = isinstance(response.json(), (dict, list))
                            rows.append({'role': role, 'path': path, 'sample': index+1,
                                         'elapsed_ms': round(elapsed, 3), 'status': response.status_code,
                                         'bytes': len(response.content), 'valid': valid})
                            if not valid:
                                raise RuntimeError(f'Invalid response: {role} {path} {response.status_code}')
                            time.sleep(PAUSE)
                        print(f'{role} {path}: {SAMPLES} samples complete', flush=True)
            stop.set()
            watcher.join(timeout=2)
            manifest['status'] = 'complete'
    finally:
        stop.set()
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        if manifest['status'] != 'complete':
            manifest['status'] = 'failed'
        for name, data in [('requests', rows), ('resources', resources), ('logins', logins)]:
            if data:
                with (out/f'{name}.csv').open('w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=list(data[0]))
                    writer.writeheader()
                    writer.writerows(data)
        manifest['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (out/'manifest.json').write_text(json.dumps(manifest, indent=2))
    summary = []
    for stage, role, path in dict.fromkeys((r.get('stage', 1), r['role'], r['path']) for r in rows):
        subset = [r for r in rows if r.get('stage', 1)==stage and r['role']==role and r['path']==path]
        values = sorted(r['elapsed_ms'] for r in subset)
        summary.append({'stage': stage, 'role': role, 'path': path, 'n': len(values),
                        'errors': sum(not r['valid'] for r in subset),
                        'mean_ms': round(sum(values)/len(values), 3),
                        'p50_ms': values[math.ceil(len(values)*.5)-1],
                        'p95_ms': values[math.ceil(len(values)*.95)-1], 'max_ms': values[-1]})
    (out/'summary.json').write_text(json.dumps(summary, indent=2))
    print('RESULT:', out, flush=True)


if __name__ == '__main__':
    main()
