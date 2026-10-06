"""One process per employee watcher, controlled by that employee's Settings switch."""
import logging
import time
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from meetings.management.commands.watch_daily_meetings import Command as FolderWatcher, dated_folders, signature
from meetings.models import MeetingWatchSetting
from meetings.watch_control import validate_folder

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Internal service for one employee meeting-folder watcher.'

    def add_arguments(self, parser):
        parser.add_argument('control_id', type=int)
        parser.add_argument('token', type=uuid.UUID)

    def handle(self, *args, **options):
        control_id, token = options['control_id'], options['token']
        seen = {}
        watcher = FolderWatcher()
        # The web request commits the token shortly after spawning us.
        for _ in range(50):
            control = MeetingWatchSetting.objects.get(pk=control_id)
            if control.process_token == token:
                break
            time.sleep(0.1)
        else:
            return
        while True:
            close_old_connections()
            control = MeetingWatchSetting.objects.select_related('project', 'user').get(pk=control_id)
            if not control.enabled or control.process_token != token:
                break
            try:
                root = validate_folder(control.folder)
                if not control.project or not control.user or not control.user.is_active:
                    raise ValueError('프로젝트 또는 실행 계정을 확인하세요.')
            except ValueError as exc:
                logger.error('Meeting watch configuration failed for user %s: %s', control.user_id, exc)
                MeetingWatchSetting.objects.filter(pk=control_id, process_token=token).update(
                    enabled=False, last_error=str(exc), heartbeat_at=timezone.now())
                break
            now = time.monotonic()
            MeetingWatchSetting.objects.filter(pk=control_id, process_token=token).update(heartbeat_at=timezone.now())
            try:
                for folder in dated_folders(root):
                    current = signature(folder)
                    if not current:
                        continue
                    previous, since = seen.get(folder, (None, now))
                    if current != previous:
                        seen[folder] = (current, now)
                        continue
                    if now - since < 30:
                        continue
                    watcher._process(folder, {
                        'project_id': control.project_id,
                        'username': control.user.username,
                        'model': None,
                    })
            except Exception as exc:
                logger.exception('Meeting watch failed for user %s', control.user_id)
                self.stderr.write(f'회의록 감시 실패: {exc}')
                MeetingWatchSetting.objects.filter(pk=control_id, process_token=token).update(last_error=str(exc)[:1000])
            time.sleep(5)
        MeetingWatchSetting.objects.filter(pk=control_id, process_token=token).update(process_id=None, process_token=None)
        close_old_connections()
