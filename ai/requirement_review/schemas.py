from pydantic import BaseModel, Field


class ScoreSet(BaseModel):
    accuracy: int = Field(ge=0, le=100)
    completeness: int = Field(ge=0, le=100)
    consistency: int = Field(ge=0, le=100)
    testability: int = Field(ge=0, le=100)


class ItemReview(BaseModel):
    req_code: str
    score: int = Field(ge=0, le=100)
    verdict: str
    findings: list[str] = Field(default_factory=list)
    recommendation: str = ""


class RevisedItem(BaseModel):
    req_code: str
    req_name: str
    description: str
    related_feature: str = ""
    input_output: str = ""
    acceptance_criteria: str = ""
    note: str = ""
    source: str = ""
    review_status: str = ""
    priority: str = "MEDIUM"
    difficulty: str = "중"
    category: str = ""
    category_2: str = ""


class RequirementReviewResult(BaseModel):
    scores: ScoreSet
    summary: str
    strengths: list[str] = Field(default_factory=list)
    critical_issues: list[str] = Field(default_factory=list)
    item_reviews: list[ItemReview] = Field(default_factory=list)
    revised_items: list[RevisedItem] = Field(min_length=1)
