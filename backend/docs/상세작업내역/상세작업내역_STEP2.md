# 단계별 상세 작업 내역 (Detailed Tasks)

### STEP 2: 사용자 인증 및 회원 관리 (Auth Module)
* **작업일 : 2026-08-24**

* **커스텀 유저 모델(Custom User Model) 구현**
  * `AbstractUser` 상속받아 커스텀 유저 모델 정의 (이메일 기반 로그인 지원)
  * Django에서 DB 마이그레이션(makemigrations)을 실행하기 전에 반드시 유저 모델을 먼저 커스텀 모델로 설정해두어야 함.
    * users/models.py 파일 코드 작성
    * config/settings.py에 Custom User 모델 지정
    ```
    AUTH_USER_MODEL = 'users.User'
    ```
    * 초기 DB 마이그레이션 실행
    ```
    터미널에서 아래 코드를 순차적으로 실행 
    1) python manage.py makemigrations
    2) python manage.py migrate
    ```

  * 산출물: `users/models.py`
---
* **작업일 : 2026-08-24**

* **JWT 인증 & 사용자 관리 REST API 구현**

  * config/setting.py 파일 하단에 코드 추가
    ```
    REST_FRAMEWORK = {
    # 1. API 문서화 설정 (drf-spectacular)
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    
    # 2. 사용자 인증 설정 (Simple JWT)
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    
    # (선택) 기본 접근 권한 설정 (예: 인증된 사용자만 접근 가능)
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    }
    ```
    
  * Access Token (단기) & Refresh Token (장기) 발급 및 재발급 엔드포인트 구현
  * 주요 엔드포인트: `/api/v1/users/access/`, `/api/v1/users/refresh/`

  * -> 실제 프론트엔드나 Postman에서 호출할 회원가입/로그인 뷰(View) 및 URL 연결
    * users/serializers.py 작성 (회원가입 및 유저 정보 직렬화):
      * 회원가입용 RegisterSerializer 작성 (비밀번호 해싱 처리)
      * 유저 정보 조회용 UserSerializer 작성
      * 비밀번호 수정용 UserUpdateSerializer 작성
      
    * users/views.py 작성 (회원가입, 내 정보 조회 뷰 구현):
    * users/urls.py 생성 및 작성 (인증 관련 라우팅 설정)
      * SimpleJWT 제공 뷰 연동 (TokenObtainPairView, TokenRefreshView)
      * 회원가입 API endpoint (/api/v1/users/register/)
      * 내 정보 조회 API endpoint (/api/v1/users/me/)
    * config/urls.py 연결  
      `path('api/v1/auth/', include('users.urls')),` 추가
  * 서버 연결 확인해보기
    * 터미널에서 `python manage.py runserver` 명령어를 실행
    * 웹에서 `http://127.0.0.1:8000/api/v1/users/` 접속해서 화면가입 API 화면 확인해보기
    * DRF(Django REST Framework)의 Browsable API 기능 덕분에 브라우저 상에 JSON 데이터를 보낼 수 있는 폼(Form) 인터페이스가 나타납니다
* **인가(Permission) 설정**
  * `AllowAny`: 회원가입, 로그인, 토큰 재발급 엔드포인트 적용
  * `IsAuthenticated`: 내 정보 조회(`/api/v1/users/me/`) API에 적용하여 비인가 접근 차단 -> 로그인된 유저만 챗봇 기능에 접근하도록 제한

  * **적용된 인가(Permission) 설정 내역**
    1) **로그인 불필요 (누구나 접근 가능 - `AllowAny`)**:

      * **회원가입 (`/api/v1/auth/register/`)**: 계정이 없는 방문자가 접근해야 하므로 `permission_classes = [AllowAny]`로 열려 있습니다.

      * **로그인 (`/api/v1/auth/login/`) & 토큰 재발급 (`/api/v1/auth/refresh/`)**: SimpleJWT 기본 제공 뷰로, 로그인 전 토큰 발급을 위해 누구나 접근 가능합니다.

    2) **로그인 필수 (인증된 유저만 접근 가능 - `IsAuthenticated`)**:

      * **내 정보 조회 (`/api/v1/auth/me/`)**: `permission_classes = [IsAuthenticated]`가 적용되어 있어, HTTP Header에 유효한 JWT Access Token(`Authorization: Bearer <토큰>`)을 실어 보내지 않으면 `401 Unauthorized` 에러를 반환하며 접근이 차단됩니다.

* **Swagger UI 연결 (drf-spectacular)**
  * 웹 브라우저에서 모든 API 목록을 한눈에 보고 직접 테스트해 볼 수 있도록 Swagger 문서화를 연결

  * config/settings.py 수정
    * REST_FRAMEWORK 설정 부분에 DEFAULT_SCHEMA_CLASS를 추가  
    `'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',`
    
    * drf-spectacular가 OpenAPI 버전 및 기본 메타데이터를 정상적으로 생성할 수 있도록 config/settings.py 하단에 아래 설정을 추가
    ```
    # Swagger / drf-spectacular 상세 설정 추가
    SPECTACULAR_SETTINGS = {
    'TITLE': 'Chatbot Service API',
    'DESCRIPTION': 'Django 기반 AI 챗봇 백엔드 API 문서입니다.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    }
    ```

  * config/urls.py 수정
    * Swagger UI를 제공하는 URL을 추가
    ```
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

    # Swagger API 문서 관련 URL
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    ```

  * 웹 연결 확인해보기
    * 회원가입, 로그인, 토큰 재발급, 내 정보 조회 API가 깔끔하게 명세된 Swagger UI 화면이 뜨는지 확인
    * 터미널에서 `python manage.py runserver` 명령어를 실행(서버 연결돼있으면 ctrl + c로 종료한다음 재시작.)
    * 웹에서 `http://127.0.0.1:8000/api/v1/docs/` 접속 -> Chatbot Service API.yaml 파일 다운로드 됨.