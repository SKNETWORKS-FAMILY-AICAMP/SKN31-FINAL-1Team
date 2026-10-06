"""Checkpointed orchestration. Run through `manage.py run_full_auto_worker`."""
import logging
from django.db import transaction
from django.utils import timezone
from common.models import CommonCode
from meetings.models import FullAutoJob, SpecDocument
from meetings.services import run_meeting_analysis
from projects.models import PipelineHistory

logger = logging.getLogger(__name__)


def run_full_auto_job(job_id):
    # Conditional UPDATE claims a queued job once, including with multiple workers.
    if not FullAutoJob.objects.filter(pk=job_id, status='PENDING').update(
        status='RUNNING', error_message='', updated_at=timezone.now()
    ):
        return False
    job = FullAutoJob.objects.select_related('note', 'created_by').get(pk=job_id)

    def stage(label):
        FullAutoJob.objects.filter(pk=job_id).update(stage=label[:100], updated_at=timezone.now())

    def history(kind, title):
        if job.note.project_id:
            PipelineHistory.objects.create(
                project_id=job.note.project_id, meeting=job.note, spec_id=job.spec_id,
                requirement_id=job.requirement_id, actor=job.created_by,
                step_type=kind, title=title,
                description='Full Auto: 회의록 작성자가 선택한 자동 실행 정책으로 처리',
            )

    try:
        # Recheck authorization after queueing (the account may have changed).
        if not job.created_by or not job.created_by.is_active:
            raise ValueError('자동 실행을 요청한 계정의 활성 상태를 확인해주세요.')
        if not job.spec_id:
            stage('1/4 기획서 생성')
            output = run_meeting_analysis(job.note_id, job.created_by_id, on_stage=stage)
            if output.get('status') != 'success':
                raise ValueError(output.get('message') or '기획서 생성 실패')
            spec = SpecDocument.objects.get(pk=output['created_spec']['id'], meeting=job.note)
            job.spec = spec
            job.save(update_fields=['spec', 'updated_at'])

        if job.spec.status_code_id != 'PROPOSAL_APPROVED':
            spec = job.spec
            with transaction.atomic():
                spec.status_code = CommonCode.objects.get(pk='PROPOSAL_APPROVED')
                spec.reviewer = None  # Never attribute a human review to automation.
                spec.review_comment = 'Full Auto 정책에 따른 자동 승인'
                spec.save(update_fields=['status_code', 'reviewer', 'review_comment', 'updated_at'])
                job.spec = spec
                job.save(update_fields=['spec', 'updated_at'])
                history('SPEC_GENERATED', '기획서 자동 승인')

        if not job.requirement_id:
            from requirements.views import process_ai_requirement_extraction
            stage('2/4 요구사항 정의서 생성')
            req = process_ai_requirement_extraction(job.spec, job.created_by, on_stage=stage)
            if not req.items.exists():
                raise ValueError('생성된 요구사항이 없습니다.')
            with transaction.atomic():
                req.status_code = CommonCode.objects.get(pk='APPROVED')
                req.save(update_fields=['status_code', 'updated_at'])
                job.requirement = req
                job.save(update_fields=['requirement', 'updated_at'])
                history('REQ_AI_GENERATED', '요구사항 정의서 자동 생성')
                history('REQ_DEFINED', '요구사항 정의서 자동 승인')

        from tasks.services import generate_task_suggestions, confirm_task_assignments
        if job.task_result is None:
            stage('3/4 업무 생성 및 담당자 추천')
            output = generate_task_suggestions(job.spec_id, on_stage=stage)
            if output.get('status') != 'success':
                raise ValueError(output.get('message') or '업무 배분 생성 실패')
            if output.get('req_def_id') != job.requirement_id:
                raise ValueError('요구사항 버전이 변경되어 자동 실행을 중단했습니다.')
            with transaction.atomic():
                job.task_result = output
                job.save(update_fields=['task_result', 'updated_at'])
                history('TASK_AI_SUGGESTED', '업무 배분 자동 추천')

        stage('4/4 업무 배분 확정')
        suggestions = job.task_result.get('suggestions') or []
        assignments = [item for item in suggestions if not item.get('is_task_header')]
        if not assignments or any(item.get('assignee_id') is None for item in assignments):
            raise ValueError('미배정 업무가 있습니다. 인력 정보를 보완한 뒤 재시도해주세요.')
        codes = set(job.requirement.items.values_list('req_code', flat=True))
        if any(item.get('source_req_id') not in codes for item in assignments):
            raise ValueError('업무의 원본 요구사항을 찾을 수 없습니다.')
        # Assignment persistence and SUCCESS are one transaction: retry cannot
        # commit the same final assignment twice after a worker interruption.
        with transaction.atomic():
            locked = FullAutoJob.objects.select_for_update().get(pk=job_id)
            if locked.status != 'RUNNING':
                raise ValueError('작업 상태가 변경되었습니다.')
            result = confirm_task_assignments(job.requirement_id, suggestions)
            if result.get('status') != 'success' or result.get('created_count') != len(assignments):
                raise ValueError(result.get('message') or '업무 저장 건수가 일치하지 않습니다.')
            history('TASK_ASSIGNED', '업무 배분 자동 확정')
            locked.status = 'SUCCESS'
            locked.stage = '업무 배분 완료'
            locked.result = dict(result, spec_id=job.spec_id, req_def_id=job.requirement_id)
            locked.save(update_fields=['status', 'stage', 'result', 'updated_at'])
    except Exception as exc:
        logger.exception('Full Auto failed: %s', job_id)
        FullAutoJob.objects.filter(pk=job_id).update(
            status='ERROR', error_message=str(exc), updated_at=timezone.now(),
        )
    return True
