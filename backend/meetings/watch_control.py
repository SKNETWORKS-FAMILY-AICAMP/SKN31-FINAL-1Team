"""Start and inspect independent employee folder watchers."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction

from meetings.models import MeetingWatchSetting


def allowed_root():
    configured = os.environ.get('MEETING_WATCH_ALLOWED_ROOT', '').strip()
    return Path(configured).expanduser().resolve() if configured else None


def normalize_folder(value):
    """Accept an absolute backend path or a Windows C: path available through WSL."""
    raw = str(value or '').strip().strip('"')
    if os.name != 'nt' and len(raw) >= 3 and raw[1:3] == ':\\':
        raw = '/mnt/' + raw[0].lower() + '/' + raw[3:].replace('\\', '/')
    return Path(raw).expanduser().resolve() if raw else None


def validate_folder(value):
    folder = normalize_folder(value)
    root = allowed_root()
    if not root or not folder or not folder.is_dir() or not folder.is_relative_to(root):
        raise ValueError('감시 폴더는 백엔드가 접근할 수 있는 허용 경로 안의 폴더여야 합니다.')
    return folder


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        stat = Path(f'/proc/{pid}/stat')
        if stat.exists() and stat.read_text().split()[2] == 'Z':
            return False
        return True
    except (OSError, ValueError):
        return False


def ensure_process(control_id):
    """Launch only this employee's watcher when enabled."""
    with transaction.atomic():
        control = MeetingWatchSetting.objects.select_for_update().get(pk=control_id)
        if not control.enabled or alive(control.process_id):
            return control
        token = uuid.uuid4()
        log_path = settings.BASE_DIR / 'logs' / f'meeting_watch_{control_id}.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('ab') as log:
            process = subprocess.Popen(
                [sys.executable, str(settings.BASE_DIR / 'manage.py'), 'run_meeting_watch_service', str(control_id), str(token)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                cwd=settings.BASE_DIR, start_new_session=True, close_fds=True,
            )
        control.process_id = process.pid
        control.process_token = token
        control.last_error = ''
        control.save(update_fields=['process_id', 'process_token', 'last_error', 'updated_at'])
        return control
