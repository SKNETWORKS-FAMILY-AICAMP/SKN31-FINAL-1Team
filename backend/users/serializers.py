# users/serializers.py

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


def normalize_password(value: str) -> str:
    """
    비밀번호 정규화 및 검증 함수
    - 앞뒤 공백 제거
    - Django 기본 비밀번호 정책 검증 (길이, 유사성, 흔한 비밀번호 등)
    """
    if not value:
        raise serializers.ValidationError("비밀번호는 필수 입력 항목입니다.")
    
    # 1. 앞뒤 공백 제거 (필요에 따라 적용)
    normalized = value.strip()
    
    if len(normalized) < 8:
        raise serializers.ValidationError("비밀번호는 최소 8자 이상이어야 합니다.")
        
    # 2. Django 설정(settings.py)에 정의된 비밀번호 유효성 검사 규칙 적용
    try:
        validate_password(normalized)
    except Exception as e:
        raise serializers.ValidationError(list(e.messages))
        
    return normalized


class RegisterSerializer(serializers.ModelSerializer):
    """회원가입 전용."""

    id = serializers.CharField(required=True, allow_blank=False, max_length=50)
    username = serializers.CharField(required=True, allow_blank=False, max_length=50)

    # write_only=True: 클라이언트 응답(JSON)에 비밀번호 노출을 방지함
    password = serializers.CharField(write_only=True, min_length=8, max_length=255)

    class Meta:
        model = User
        fields = ['id', 'username', 'password']

    def validate_password(self, value):
        # 회원가입 시에도 normalize_password 함수 적용
        return normalize_password(value)

    def create(self, validated_data):
        # create_user 메서드가 내부적으로 set_password()를 호출하여 해싱 저장함
        return User.objects.create_user(
            id=validated_data['id'],
            username=validated_data['username'],
            password=validated_data['password'],
        )


class UserSerializer(serializers.ModelSerializer):
    """유저 정보 조회 전용."""
    class Meta:
        model = User
        fields = ['id', 'username', 'role', 'is_busy']
        read_only_fields = ['id']


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    본인 정보 수정. 현재는 비밀번호만 변경 전용.
    """
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('password',)

    def validate_password(self, value):
        return normalize_password(value)

    def update(self, instance, validated_data):
        """
        비밀번호 수정 시 평문으로 저장되지 않도록 set_password() 호출
        """
        password = validated_data.get('password')
        if password:
            instance.set_password(password)
            instance.save()
        return instance