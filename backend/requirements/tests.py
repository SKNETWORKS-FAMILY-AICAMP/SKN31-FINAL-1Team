from django.test import SimpleTestCase

from requirements.views import _parse_feature_lines


class FeatureLineParsingTests(SimpleTestCase):
    def test_generated_feature_html_is_split_into_individual_features(self):
        raw = (
            "<p><strong>스타일 태깅</strong></p>"
            "<p>상품 이미지에 표준 스타일 태그를 부여한다.</p>"
            "<p><strong>트렌드 분석</strong></p>"
            "<p>사용자 반응을 기반으로 트렌드를 분석한다.</p>"
            "<p><strong>PM 확인 사항</strong></p><ul><li>범위 확인</li></ul>"
        )

        self.assertEqual(
            _parse_feature_lines(raw),
            [
                "스타일 태깅: 상품 이미지에 표준 스타일 태그를 부여한다.",
                "트렌드 분석: 사용자 반응을 기반으로 트렌드를 분석한다.",
            ],
        )
