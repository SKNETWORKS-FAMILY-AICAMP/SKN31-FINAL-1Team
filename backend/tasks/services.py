from django.contrib.auth import get_user_model
from specs.models import SpecDocument
from tasks.models import TaskAssignment

User = get_user_model()

def create_task_assignments_for_spec(spec_id: int):
    """
    기획서를 기반으로 '작업 중이 아닌(is_busy=False)' 사원들에게 업무를 자동 배분(추천 상태)하는 함수
    """
    try:
        spec = SpecDocument.objects.get(id=spec_id)
        
        # 1. 작업 중이지 않은 사원 목록 추출 (Role이 MEMBER인 사원)
        available_users = User.objects.filter(is_busy=False, role='MEMBER')
        
        if not available_users.exists():
            return {"status": "warning", "message": "현재 배분 가능한(idle) 사원이 없습니다."}
        
        # 2. 임시 업무 할당 레코드 생성 (예시 로직: 기획서 기반 작업 분할 및 순환 배정)
        # 실제 구현 시 LLM을 활용해 기획서 내용을 파싱하여 세부 Task로 나눌 수 있습니다.
        sample_tasks = [
            f"{spec.title} - 백엔드 API 개발",
            f"{spec.title} - 프론트엔드 UI 구현",
            f"{spec.title} - DB 및 연동 테스트"
        ]
        
        created_assignments = []
        user_count = available_users.count()
        
        for idx, task_title in enumerate(sample_tasks):
            assigned_user = available_users[idx % user_count]
            assignment = TaskAssignment.objects.create(
                spec=spec,
                assigned_user=assigned_user,
                task_title=task_title,
                task_description=f"[{spec.title}] 관련 세부 작업입니다.",
                status=TaskAssignment.Status.PENDING_APPROVAL
            )
            created_assignments.append(assignment)
            
        return {"status": "success", "count": len(created_assignments)}

    except SpecDocument.DoesNotExist:
        return {"status": "error", "message": "기획서를 찾을 수 없습니다."}