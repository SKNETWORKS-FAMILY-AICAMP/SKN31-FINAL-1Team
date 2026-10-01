from django.test import SimpleTestCase

from requirement_draft.schemas import PlanDocument, RequirementItem
from requirements.views import _validate_ai_output_before_persist


class RequirementPersistenceQualityGateTests(SimpleTestCase):
    def setUp(self):
        self.plan = PlanDocument.model_validate(
            {
                "project_id": "102",
                "title": "ERP 연동",
                "goal": "ERP 업무를 자동화한다",
                "key_features": "ERP API 어댑터를 연동한다.",
                "requirements": [
                    {"id": "REQ-01", "content": "ERP API 어댑터 연동"}
                ],
            }
        )
        self.base_item = {
            "id": "FR-01-001",
            "category_1": "기능",
            "category_2": "ERP 연동",
            "title": "ERP API 요청",
            "description": "ERP API로 요청을 전달하고 결과를 반환한다.",
            "related_feature": "[key_features] ERP API 어댑터 연동",
            "input_output": "요청을 입력받아 ERP API 결과를 반환한다.",
            "acceptance_criteria": "요청 결과가 반환되는지 통합 테스트로 확인한다.",
            "note": "기획서 key_features 직접 근거",
            "type": "기능",
            "priority": "High",
            "source": "requirement_text",
            "review_status": "검토완료",
        }

    def make_item(self, **overrides):
        values = {**self.base_item, **overrides}
        return RequirementItem.model_validate(values)

    def test_valid_output_can_reach_persistence(self):
        _validate_ai_output_before_persist(self.plan, [self.make_item()])

    def test_invalid_output_is_blocked_before_persistence(self):
        item = self.make_item(acceptance_criteria="후속 확정 필요")

        with self.assertRaisesMessage(ValueError, "ACCEPTANCE_PLACEHOLDER"):
            _validate_ai_output_before_persist(self.plan, [item])
