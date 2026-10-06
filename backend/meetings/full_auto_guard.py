from rest_framework.exceptions import APIException, ValidationError
from meetings.models import FullAutoJob, SpecDocument


class FullAutoConflict(APIException):
    status_code = 409
    default_detail = '자동 실행 중인 문서입니다. 완료 후 수정해주세요.'


class FullAutoProtectedMixin:
    """Prevent manual mutation of documents owned by an unfinished pipeline."""
    full_auto_target = 'spec'

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return
        try:
            self.check_full_auto(request, kwargs)
        except (ValueError, TypeError):
            raise ValidationError('문서 ID는 정수여야 합니다.')

    def check_full_auto(self, request, kwargs):
        target = self.full_auto_target
        if target == 'note':
            note_id = kwargs.get('pk')
        elif target == 'item':
            from requirements.models import RequirementItem, RequirementDefinition
            if kwargs.get('pk'):
                note_id = RequirementItem.objects.filter(pk=kwargs['pk']).values_list('req_def__spec__meeting_id', flat=True).first()
            else:
                note_id = RequirementDefinition.objects.filter(pk=request.data.get('req_def')).values_list('spec__meeting_id', flat=True).first()
        else:
            spec_id = kwargs.get('spec_id') or kwargs.get('pk') or request.data.get('spec') or request.data.get('spec_id')
            note_id = SpecDocument.objects.filter(pk=spec_id).values_list('meeting_id', flat=True).first()
            if request.data.get('req_def_id'):
                from requirements.models import RequirementDefinition
                note_id = RequirementDefinition.objects.filter(pk=request.data['req_def_id']).values_list('spec__meeting_id', flat=True).first()
            if not note_id:
                note_id = request.data.get('meeting')
        if note_id and FullAutoJob.objects.filter(note_id=note_id, status__in=['PENDING', 'RUNNING', 'ERROR']).exists():
            raise FullAutoConflict()
