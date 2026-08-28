from rest_framework import generics
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from common.models import CommonCode
from common.serializers import CommonCodeSerializer


@extend_schema(
    tags=['0단계 - 공통 메타데이터'],
    summary='공통 코드 목록 조회',
    description='시스템 전체에서 사용되는 공통 코드(부서, 직급, 상태 등) 목록을 조회합니다. `group_code` 쿼리 파라미터를 통해 특정 그룹 코드만 필터링할 수 있습니다.',
    parameters=[
        OpenApiParameter(
            name='group_code',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            description='필터링할 공통 코드 그룹 (예: DEPT, POSITION, STATUS)'
        )
    ],
    responses={
        200: CommonCodeSerializer(many=True)
    }
)
class CommonCodeListView(generics.ListAPIView):
    """
    공통 코드 목록 조회 API
    GET /api/common/codes/?group_code=DEPT
    """
    serializer_class = CommonCodeSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = CommonCode.objects.all()
        group_code = self.request.query_params.get('group_code', None)
        if group_code:
            queryset = queryset.filter(group_code=group_code)
        return queryset