# users/tests.py

from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class UserMeTestCase(APITestCase):

    def setUp(self):
        # 💡 id="testuser" 대신 username을 전달합니다. (id는 Django가 1, 2, 3... 숫자로 자동 채움)
        self.user = User.objects.create_user(
            username="testuser",
            password="password128!"
        )
        self.client.force_authenticate(user=self.user)

    def test_patch_password_response_format(self):
        url = reverse('user-me')  # /api/v1/users/me/
        response = self.client.patch(
            url, {'password': 'newpassword128!'}, format='json'
        )

        # 1. 상태 코드 검증
        self.assertEqual(response.status_code, 200)

        # 2. 실제 반환된 JSON 키 구조 검증
        self.assertIn("message", response.data)
        self.assertEqual(
            response.data["message"], "비밀번호가 성공적으로 변경되었습니다."
        )