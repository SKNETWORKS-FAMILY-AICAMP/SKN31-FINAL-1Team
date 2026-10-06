"""Import a dated local folder into the existing Full Auto pipeline."""
import json
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from meetings.daily_import import fingerprint, read_folder, summarize
from meetings.models import FullAutoJob, MeetingNote
from projects.models import PipelineHistory, Project


class Command(BaseCommand):
    help = 'Summarize all notes in a YYYYMMDD folder, then optionally queue Full Auto.'

    def add_arguments(self, parser):
        parser.add_argument('folder', type=Path)
        parser.add_argument('--project-id', type=int, required=True)
        parser.add_argument('--username', required=True)
        parser.add_argument('--apply', action='store_true', help='Register summary and queue Full Auto')
        parser.add_argument('--output-dir', type=Path, help='Summary destination; defaults to a sibling YYYYMMDD_summary folder')
        parser.add_argument('--model', default=None, help='Summary model; defaults to MEETING_SUMMARY_MODEL or gpt-5')

    def handle(self, *args, **options):
        try:
            day, sources = read_folder(options['folder'])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        project = Project.objects.filter(pk=options['project_id']).first()
        user = get_user_model().objects.filter(username=options['username'], is_active=True).first()
        if not project or not user:
            raise CommandError('활성 사용자와 프로젝트 ID를 확인하세요.')
        if project.owner_id and project.owner_id != user.pk and not user.is_staff:
            raise CommandError('프로젝트 소유자 또는 PM만 등록할 수 있습니다.')
        digest = fingerprint(sources)
        marker = f'[daily-import:{day:%Y%m%d}:{digest}]'
        existing = MeetingNote.objects.filter(project=project, content__contains=marker).first()
        if existing:
            self.stdout.write(f'이미 등록됨: meeting={existing.pk}, job={getattr(existing, "full_auto_job", None)}')
            return
        output_dir = options['output_dir'] or options['folder'].parent / f'{options["folder"].name}_summary'
        output = output_dir / '최종_회의록_요약본.md'
        manifest = output_dir / '최종_회의록_요약본.sources.json'
        if output.exists():
            if not options['apply']:
                raise CommandError(f'출력 파일이 이미 있습니다: {output}. 검토 후 --apply로 등록하세요.')
            try:
                data = json.loads(manifest.read_text(encoding='utf-8'))
                if data['fingerprint'] != digest:
                    raise ValueError('원본 파일이 요약 후 변경되었습니다.')
                content = output.read_text(encoding='utf-8')
                if marker not in content:
                    raise ValueError('요약본의 원본 식별 정보가 일치하지 않습니다.')
            except (OSError, ValueError, KeyError) as exc:
                raise CommandError(str(exc)) from exc
        else:
            model = options['model'] or os.environ.get('MEETING_SUMMARY_MODEL', '').strip() or 'gpt-5'
            try:
                summaries, final = summarize(sources, model)
            except Exception as exc:
                raise CommandError(f'요약 실패: {exc}') from exc
            if fingerprint(read_folder(options['folder'])[1]) != digest:
                raise CommandError('요약 중 원본 파일이 변경되었습니다. 다시 실행하세요.')
            source_list = '\n'.join(f'- {s.name} (SHA-256: {s.sha256})' for s in sources)
            content = f'# 최종 회의록 요약본 ({day:%Y-%m-%d})\n\n출처:\n{source_list}\n\n{final}\n\n{marker}\n'
            output_dir.mkdir(parents=True, exist_ok=True)
            output.write_text(content, encoding='utf-8')
            manifest.write_text(json.dumps({
                'fingerprint': digest,
                'sources': [{'filename': s.name, 'sha256': s.sha256, 'summary': summary}
                            for s, summary in zip(sources, summaries)]
            }, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(f'요약본 저장: {output} ({len(sources)}개 파일)')
        if not options['apply']:
            self.stdout.write('DB 등록 전입니다. 검토 후 --apply로 실행하세요.')
            return
        with transaction.atomic():
            if MeetingNote.objects.filter(project=project, content__contains=marker).exists():
                raise CommandError('같은 폴더의 회의록이 이미 등록되었습니다.')
            note = MeetingNote.objects.create(project=project, title=f'최종_회의록_요약본_{day:%Y%m%d}',
                                              content=content, meeting_date=timezone.make_aware(day), created_by=user)
            job = FullAutoJob.objects.create(note=note, created_by=user)
            PipelineHistory.objects.create(project=project, meeting=note, step_type='MEETING_REGISTERED',
                                           title=f'회의록 등록: {note.title}',
                                           description=f'{len(sources)}개 파일 통합, 작성자: {user.username}', actor=user)
        self.stdout.write(f'자동 실행 예약: meeting={note.pk}, job={job.pk}')
