import time
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone
from meetings.full_auto import run_full_auto_job
from meetings.models import FullAutoJob


class Command(BaseCommand):
    help = 'Process durable Full Auto jobs. Run separately from the web server.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process one pending job and exit')
        parser.add_argument('--recover-job', help='Requeue an interrupted RUNNING job UUID. Stop all workers first.')

    def handle(self, *args, **options):
        if options['recover_job']:
            changed = FullAutoJob.objects.filter(pk=options['recover_job'], status='RUNNING').update(
                status='PENDING', stage='중단된 작업 복구 대기', updated_at=timezone.now(),
            )
            if not changed:
                raise CommandError('RUNNING 상태의 작업을 찾을 수 없습니다.')
        self.stdout.write('Full Auto worker started')
        try:
            while True:
                close_old_connections()
                job_id = FullAutoJob.objects.filter(status='PENDING').order_by('created_at').values_list('pk', flat=True).first()
                if job_id:
                    run_full_auto_job(job_id)
                if options['once']:
                    return
                if not job_id:
                    time.sleep(2)
        except KeyboardInterrupt:
            self.stdout.write('Full Auto worker stopped')
        finally:
            close_old_connections()
