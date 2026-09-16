from pydantic import BaseModel, Field


class ScoreSet(BaseModel):
    accuracy: int = Field(ge=0, le=100, description="회의록 사실과의 일치도")
    completeness: int = Field(ge=0, le=100, description="회의에서 논의한 내용의 포함 정도")
    consistency: int = Field(ge=0, le=100, description="문서 내부 모순이 없는 정도")
    traceability: int = Field(ge=0, le=100, description="주장에 회의록 근거가 있는 정도")


class SectionReview(BaseModel):
    section_key: str
    section_title: str
    score: int = Field(ge=0, le=100)
    verdict: str = Field(description="pass | needs_improvement | critical")
    evidence: list[str] = Field(default_factory=list, description="회의록에서 그대로 찾을 수 있는 짧은 근거")
    findings: list[str] = Field(default_factory=list)
    recommendation: str = ""


class RevisedDocument(BaseModel):
    overview: str
    problem_definition: str
    goals: str
    target_users: str
    key_features: str
    tech_stack: str
    final_decisions: str


class PlanReviewResult(BaseModel):
    scores: ScoreSet
    summary: str
    strengths: list[str] = Field(default_factory=list)
    critical_issues: list[str] = Field(default_factory=list)
    section_reviews: list[SectionReview]
    revised_document: RevisedDocument

