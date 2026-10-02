"""20-user, 80/20 read/write mixed workload with temporary per-user tasks."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import random, threading, time
import httpx
from django.contrib.auth import get_user_model
from django.db import connection
from tasks.models import TaskAssignment, TaskStatusCode


def run_stages(base, context, password, rows, logins, *, stage_users, stage_duration):
    assert stage_users == [20]
    cfg=connection.settings_dict
    assert cfg['HOST']=='127.0.0.1' and str(cfg['PORT'])=='3307' and cfg['NAME']=='heyzzabi_test'
    User=get_user_model(); users={i:User.objects.get(username=f'lt_small_{i:03}') for i in range(1,21)}
    source=TaskAssignment.objects.filter(task_no__startswith='LT-').first(); assert source
    tasks={}; expected={}; lock=threading.Lock(); begun=time.perf_counter()
    read_paths=['/api/dashboard/overview/','/api/projects/','/api/tasks/assignments/','/api/requirements/']
    try:
        for i,user in users.items():
            tasks[i]=TaskAssignment.objects.create(req_item=source.req_item, project=source.project,
                assigned_user=user, task_no=f'LT-MIXED-{i:03}', title=f'[LOADTEST mixed] {i:03}',
                description='mixed-start', status_code_id=TaskStatusCode.APPROVED, progress=0)
            expected[i]='mixed-start'
        with ExitStack() as stack:
            clients={}
            for i in users:
                c=stack.enter_context(httpx.Client(base_url=base,verify=context,trust_env=False,timeout=20))
                c.get('/api/users/csrf/').raise_for_status(); start=time.perf_counter()
                r=c.post('/api/users/login/',json={'username':users[i].username,'password':password},
                    headers={'X-CSRFToken':c.cookies.get('csrftoken'),'Referer':base+'/'})
                r.raise_for_status(); c.headers.update({'X-CSRFToken':c.cookies.get('csrftoken'),'Referer':base+'/'})
                clients[i]=c; logins.append({'role':'pm' if i<=4 else 'member','user':i,'status':r.status_code,'elapsed_ms':(time.perf_counter()-start)*1000})
            deadline=time.perf_counter()+stage_duration; initial=len(rows)
            def loop(i):
                rng=random.Random(20261002+i); seq=0
                while time.perf_counter()<deadline:
                    write=rng.random()<.20
                    if write:
                        seq+=1; value=f'mixed-{i}-{seq}'; path=f'/api/tasks/assignments/{tasks[i].pk}/'; method='PATCH'
                        started=time.perf_counter()
                        try:
                            r=clients[i].patch(path,json={'description':value}); status=r.status_code; size=len(r.content); valid=status==200; error='' if valid else f'status_{status}'
                            if valid: expected[i]=value
                        except httpx.HTTPError as exc: status=size=0; valid=False; error=type(exc).__name__
                    else:
                        path=rng.choice(read_paths); method='GET'; started=time.perf_counter()
                        try:
                            r=clients[i].get(path); status=r.status_code; size=len(r.content); valid=status==200; error='' if valid else f'status_{status}'
                        except httpx.HTTPError as exc: status=size=0; valid=False; error=type(exc).__name__
                    ended=time.perf_counter()
                    with lock: rows.append({'stage':20,'role':'pm' if i<=4 else 'member','user':i,'path':path,'phase':method,
                        'started_offset_s':started-begun,'completed_offset_s':ended-begun,'elapsed_ms':round((ended-started)*1000,3),
                        'status':status,'bytes':size,'valid':valid,'error':error})
                    time.sleep(max(0,min(rng.uniform(2,5),deadline-time.perf_counter())))
            with ThreadPoolExecutor(max_workers=20) as pool:
                for f in [pool.submit(loop,i) for i in users]: f.result()
            subset=rows[initial:]
        mismatches=[]
        for i,task in tasks.items():
            task.refresh_from_db()
            if task.description!=expected[i]: mismatches.append({'user':i,'expected':expected[i],'actual':task.description})
        return [{'users':20,'started_unix':time.time(),'elapsed_seconds_including_drain':time.perf_counter()-begun,
                 'requests':len(subset),'errors':sum(not r['valid'] for r in subset),'stopped_early':False,
                 'read_requests':sum(r['phase']=='GET' for r in subset),'write_requests':sum(r['phase']=='PATCH' for r in subset),
                 'integrity_mismatches':mismatches}]
    finally:
        TaskAssignment.objects.filter(pk__in=[t.pk for t in tasks.values()]).delete()

