### STEP 2: 사용자 인증 및 회원 관리 (Auth Module)
* **작업일 : 2026-08-24**

* **커스텀 유저 모델(Custom User Model) 구현**
  * `AbstractUser` 상속받아 커스텀 유저 모델 정의 (이메일 기반 로그인 지원)
  * Django에서 DB 마이그레이션(makemigrations)을 실행하기 전에 반드시 유저 모델을 먼저 커스텀 모델로 설정해두어야 함.
    * users/models.py 파일 코드 작성
    * config/settings.py에 Custom User 모델 지정
    ```python
    AUTH_USER_MODEL = 'users.User'
    ```
    * 초기 DB 마이그레이션 실행
    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```

  * 산출물: `users/models.py`

---

* **작업일 : 2026-08-24**

* **JWT 인증 & 사용자 관리 REST API 구현**

  * config/settings.py 파일 하단에 코드 추가
    ```python
    REST_FRAMEWORK = {
        # 1. API 문서화 설정 (drf-spectacular)
        'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
        
        # 2. 사용자 인증 설정 (Simple JWT)
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'rest_framework_simplejwt.authentication.JWTAuthentication',
        ),
        
        # 기본 접근 권한 설정 (인증된 사용자만 접근 가능)
        'DEFAULT_PERMISSION_CLASSES': (
            'rest_framework.permissions.IsAuthenticated',
        ),
    }
    ```
    
  * Access Token (단기) & Refresh Token (장기) 발급 및 재발급 엔드포인트 구현
  * 주요 엔드포인트: `/api/v1/users/register/`, `/api/v1/users/login/`, `/api/v1/users/refresh/`, `/api/v1/users/me/`

  * 프론트엔드/Postman용 회원가입 및 로그인 뷰(View) 구현
    * `users/serializers.py` 작성 (RegisterSerializer, UserSerializer, UserUpdateSerializer)
    * `users/views.py` 작성 (회원가입, 내 정보 조회 뷰 구현)
    * `users/urls.py` 작성 및 `config/urls.py`에 연결 (`path('api/v1/users/', include('users.urls'))`)

* **인가(Permission) 설정**
  * `AllowAny`: 회원가입, 로그인, 토큰 재발급 엔드포인트 적용
  * `IsAuthenticated`: 내 정보 조회(`/api/v1/users/me/`) API에 적용하여 비인가 접근 차단

* **Swagger UI 연결 (drf-spectacular)**
  * config/settings.py 수정 (`SPECTACULAR_SETTINGS` 추가)
  * config/urls.py 수정 (`/api/v1/schema/`, `/api/v1/swagger/`, `/api/v1/redoc/` 연결)
