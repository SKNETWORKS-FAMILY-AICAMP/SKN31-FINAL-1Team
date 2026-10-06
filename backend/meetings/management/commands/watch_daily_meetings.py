"""Poll local dated folders and run the complete meeting-to-assignment pipeline."""
import time
from datetime import datetime
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from meetings.daily_import import fingerprint, read_folder
from meetings.full_auto import run_full_auto_job
from meetings.models import MeetingNote, FullAutoJob
from projects.models import Project
from django.contrib.auth import get_user_model


def dated_folders(root: Path) -> list[Path]:
    if not root.is_dir():
        raise CommandError(f'감시 폴더가 없습니다: {root}')
    try:
        datetime.strptime(root.name, '%Y%m%d')
        return [root]
    except ValueError:
        pass
    folders = []
    for folder in root.iterdir():
        if folder.is_dir():
            try:
                datetime.strptime(folder.name, '%Y%m%d')
                folders.append(folder)
            except ValueError:
                continue
    return sorted(folders)


def signature(folder: Path):
    """A cheap snapshot for copy settling; actual deduplication uses content hashes."""
    files = sorted((p for p in folder.iterdir() if p.is_file() and not p.name.startswith('~$')),
                   key=lambda p: p.name)
    return tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in files)


class Command(BaseCommand):
    help = 'Watch YYYYMMDD folders and automatically summarize, register, and assign work.'

    def add_arguments(self, parser):
        parser.add_argument('root', type=Path, help='One YYYYMMDD folder or its parent')
        parser.add_argument('--project-id', type=int, required=True)
        parser.add_argument('--username', required=True)
        parser.add_argument('--poll-seconds', type=float, default=5)
        parser.add_argument('--settle-seconds', type=float, default=30)
        parser.add_argument('--model', default=None)
        parser.add_argument('--once', action='store_true', help='Scan settled folders once and exit')

    def handle(self, *args, **options):
        if options['poll_seconds'] <= 0 or options['settle_seconds'] < 0:
            raise CommandError('poll-seconds는 양수, settle-seconds는 0 이상이어야 합니다.')
        project = Project.objects.filter(pk=options['project_id']).first()
        user = get_user_model().objects.filter(username=options['username'], is_active=True).first()
        if not project or not user:
            raise CommandError('활성 사용자와 프로젝트 ID를 확인하세요.')
        if project.owner_id and project.owner_id != user.pk and not user.is_staff:
            raise CommandError('프로젝트 소유자 또는 PM만 실행할 수 있습니다.')
        root = options['root'].expanduser().resolve()
        dated_folders(root)
        seen = {}
        self.stdout.write(f'회의록 폴더 감시 시작: {root}')
        try:
            while True:
                close_old_connections()
                now = time.monotonic()
                folders = dated_folders(root)
                for folder in folders:
                    try:
                        current = signature(folder)
                        if not current:
                            continue
                        previous, since = seen.get(folder, (None, now))
                        if current != previous:
                            seen[folder] = (current, now)
                            if not options['once']:
                                continue
                        elif not options['once'] and now - since < options['settle_seconds']:
                            continue
                        # A single scan cannot prove that a copy has settled, so --once is
                        # intended for scheduled runs after files have already arrived.
                        self._process(folder, options)
                    except (OSError, ValueError, CommandError) as exc:
                        self.stderr.write(f'{folder}: {exc}')
                if options['once']:
                    return
                time.sleep(options['poll_seconds'])
        except KeyboardInterrupt:
            self.stdout.write('회의록 폴더 감시 종료')
        finally:
            close_old_connections()

    def _process(self, folder: Path, options):
        day, sources = read_folder(folder)
        digest = fingerprint(sources)
        marker = f'[daily-import:{day:%Y%m%d}:{digest}]'
        project_id = options['project_id']
        note = MeetingNote.objects.filter(project_id=project_id, content__contains=marker).first()
        if note is None:
            # Every content version has its own immutable output. A new file therefore
            # creates a new summary while restart of the watcher reuses the same version.
            output_dir = folder.parent / f'{folder.name}_summary' / digest[:16]
            call_command('import_daily_meetings', folder, project_id=project_id,
                         username=options['username'], apply=True, output_dir=output_dir,
                         model=options['model'])
            note = MeetingNote.objects.get(project_id=project_id, content__contains=marker)
            self.stdout.write(f'회의록 {note.pk}: {len(sources)}개 파일 통합 완료')
        job = FullAutoJob.objects.get(note=note)
        if job.status == 'PENDING':
            run_full_auto_job(job.pk)
            job.refresh_from_db()
            self.stdout.write(f'자동 실행 {job.status}: meeting={note.pk}, job={job.pk}')
            if job.status == 'ERROR':
                self.stderr.write(job.error_message)
