#meetings/serializers.py

###############################################################
# MeetingNoteSerializer: 
## 회의록 단건 조회 시 해당 회의록에서 파생된 기획서 목록(spec_documents)을 하위 배열로 함께 반환하도록 구성
# SpecDocumentSerializer: 
## 기획서 검토 상태(status_code)의 코드명과 검토자 이름을 쉽게 읽을 수 있도록 
## 읽기 전용 필드(status_info, reviewer_name)를 추가
# MeetingNoteCreateSerializer: 
## 회의록 생성 시 클라이언트로부터 필요한 입력값만 받아 깔끔하게 검증
###############################################################

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from meetings.models import MeetingNote, SpecDocument
from common.models import CommonCode

class CommonCodeSimpleSerializer(serializers.ModelSerializer):
    """
    상태/그룹 코드 단순 조회용 Serializer
    """
    class Meta:
        model = CommonCode
        fields = ['code_id', 'code_name']


class SpecDocumentSerializer(serializers.ModelSerializer):
    """
    기획서(SpecDocument) 조회 및 작성용 Serializer
    """
    # 프론트엔드 API 규격상 'id' 키 이름을 선호할 경우 source='pk' 매핑
    id = serializers.ReadOnlyField(source='pk')
    status_info = CommonCodeSimpleSerializer(source='status_code', read_only=True)
    reviewer_name = serializers.CharField(source='reviewer.username', read_only=True)

    class Meta:
        model = SpecDocument
        fields = [
            'id',             # source='pk' 매핑으로 안전하게 호출
            'spec_id',        # 실제 모델 PK 필드
            'meeting',
            'title',
            'overview',
            'problem_definition',
            'target_users',
            'key_features',
            'user_scenarios',
            'tech_stack',
            'final_decisions',
            'period_start',
            'period_end',
            'background',
            'target_scope',
            'status_code',
            'status_info',
            'reviewer',
            'reviewer_name',
            'review_comment',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'spec_id', 'created_at', 'updated_at']

    def create(self, validated_data):
        # status_code를 안 보내고 만들면(직접 작성) 항상 초안(DRAFT)에서 시작해야, 아직
        # 검토요청도 안 한 문서가 곧장 검토중/승인 상태로 잘못 보이는 일이 없다.
        # code_id는 CommonCode 전체에서 전역 유일해 REQSPEC_STATUS와 안 겹치도록 PROPOSAL_
        # 접두사로 시드했다(meetings/migrations/0005 참고) — views.py의 _proposal_status()와 동일 규칙.
        if not validated_data.get('status_code'):
            validated_data['status_code'] = CommonCode.objects.filter(
                group_id='PROPOSAL_STATUS', code_id='PROPOSAL_DRAFT'
            ).first()
        return super().create(validated_data)


class MeetingNoteSerializer(serializers.ModelSerializer):
    """
    회의록(MeetingNote) 목록 및 상세 조회용 Serializer
    관련된 기획서(spec_documents) 목록을 포함합니다.
    """
    # 프론트엔드 API 규격상 'id' 키 이름을 선호할 경우 source='pk' 매핑
    id = serializers.ReadOnlyField(source='pk')
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    spec_documents = SpecDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = MeetingNote
        fields = [
            'id',             # source='pk' 매핑
            'meeting_id',     # 실제 모델 PK 필드
            'project',
            'title',
            'content',
            'summary_content',
            'meeting_date',
            'attendees',
            'status',
            'status_display',
            'created_by',
            'created_by_name',
            'spec_documents',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'meeting_id', 'created_at', 'updated_at']


class MeetingNoteCreateSerializer(serializers.ModelSerializer):
    """
    회의록 신규 등록 전용 Serializer
    """
    class Meta:
        model = MeetingNote
        fields = ['project', 'title', 'content', 'meeting_date', 'attendees']