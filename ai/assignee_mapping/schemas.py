"""
assignee_mapping/schemas.py

컨텍스트 설계 요약
  - 입력: 사원 원본 데이터 — User + UserSkill + UserCertification, SQL 조회
          (User.past_projects(TEXT, 경력기술서 원문)만 비구조화 데이터 — 나머지는
          이미 구조화되어 있어 LLM이 관여할 필요가 없다)
  - 정적 참고자료: few-shot(경력기술서 원문 → 유사 경험 태그 추출 패턴)
  - Tools: 없음
  - 출력: A2-3(assignee_recommend)의 get_project_members() 자리를 그대로
          대신하는 EmployeeFitnessProfile 목록 — assignee_recommend/rule_filter.py의
          schedule_assignments()가 기대하는 필드명과 1:1로 맞춰, A2-3 쪽 코드는
          전혀 수정하지 않아도 되게 한다.
"""

from typing import List

from pydantic import BaseModel, Field


class RawEmployeeProfile(BaseModel):
    """
    User + UserSkill + UserCertification 조회 결과 1인분.
    실제 '사원 테이블 User' 컬럼 기준 — id, employee_no, past_projects만 사용하고
    email/password/slack_email/github_email/role_code_id 등 배정 적합성과 무관한
    컬럼은 여기 담지 않는다.
    """

    employee_id: str = Field(..., description="User.id (UUID, PK)")
    employee_no: str = Field(..., description="User.employee_no — 사람이 읽는 사번")
    name: str = Field(..., description="User.name")
    skills: List[str] = Field(
        default_factory=list,
        description="UserSkill 조회 결과(skill_code_id → CommonCode.code_name) — 이미 구조화됨, LLM 필요 없음",
    )
    certifications: List[str] = Field(
        default_factory=list,
        description="UserCertification 조회 결과 — 이미 구조화됨, LLM 필요 없음",
    )
    career_history_text: str = Field(
        "",
        description="User.past_projects 원문 그대로. 이 필드만 LLM이 해석할 대상이다.",
    )
    # 가용시간(용량)은 User 테이블에 저장하지 않는다 — task.estimated_hours를 assignee_id
    # 기준으로 SUM해서 "현재 부하"를 실시간으로 구하는 게 정확하고, 별도 필드를 매번
    # 갱신할 필요도 없다. 이 계산은 순수 SQL 집계라 LLM이 필요 없어 이 에이전트가
    # 아니라 A2-3(assignee_recommend)의 책임으로 옮겼다 — rule_filter.py 참고.


class ExtractedExperienceTags(BaseModel):
    """LLM의 유일한 작업 — career_history_text에서 유사 경험을 짧은 태그로 추출."""

    tags: List[str] = Field(
        ...,
        description="경력기술서 원문에 실제로 언급된 프로젝트/업무만 짧은 태그로 추출하라. "
        "원문에 없는 경험을 지어내지 마라. 언급된 게 없으면 빈 리스트를 반환하라.",
    )


class EmployeeFitnessProfile(BaseModel):
    """
    이 에이전트의 최종 출력 1인분. assignee_recommend/rule_filter.py의
    schedule_assignments()가 소비하는 members 리스트 항목과 필드명이 동일하다
    (skills, certifications, past_similar_tasks, employee_id). 현재 부하(가용시간)는
    여기 없다 — A2-3이 실행 시점에 task 테이블에서 직접 SQL로 조회한다(rule_filter.py 참고).
    """

    employee_id: str
    skills: List[str] = Field(..., description="RawEmployeeProfile.skills를 코드가 그대로 복사 — LLM 관여 없음")
    certifications: List[str] = Field(
        default_factory=list,
        description="RawEmployeeProfile.certifications를 코드가 그대로 복사 — LLM 관여 없음. "
        "A2-3에서 가산점으로 반영된다(rule_filter._fit_score 참고).",
    )
    past_similar_tasks: List[str] = Field(..., description="= ExtractedExperienceTags.tags (LLM이 만든 값)")


class EmployeeFitnessProfileList(BaseModel):
    profiles: List[EmployeeFitnessProfile] = Field(default_factory=list)
