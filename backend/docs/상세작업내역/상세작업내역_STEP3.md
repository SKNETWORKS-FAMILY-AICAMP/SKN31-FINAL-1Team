### STEP 3: 공통코드(Common Code) 모듈 설계 및 DB 마이그레이션
* **작업일 : 2026-08-26**

* **`common` 앱 및 공통코드 모델 구현**
  * `python manage.py startapp common` 실행 및 `config/settings.py`의 `INSTALLED_APPS`에 등록
  * DB 담당자 스키마 설계에 맞춘 `common/models.py` 내 모델 작성
  * 코드 관리와 데이터 확장의 용이성을 위해 CommonCodeGroup(공통 코드 그룹)과 CommonCode(상세 코드)의 2단계 구조로 구성

```python
from django.db import models

class CommonCodeGroup(models.Model):
    """
    공통 코드 그룹 (대분류)
    예: USER_ROLE(권한), REQ_PRIORITY(우선순위), TASK_STATUS(진행상태) 등
    """
    group_code = models.CharField(
        max_length=50, 
        primary_key=True, 
        verbose_name="코드 그룹 ID"
    )
    group_name = models.CharField(
        max_length=100, 
        verbose_name="코드 그룹명"
    )
    description = models.TextField(
        null=True, 
        blank=True, 
        verbose_name="설명"
    )
    is_active = models.BooleanField(
        default=True, 
        verbose_name="사용 여부"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="생성 일시"
    )

    class Meta:
        db_table = "common_code_group"
        verbose_name = "공통 코드 그룹"
        verbose_name_plural = "공통 코드 그룹 목록"

    def __str__(self):
        return f"[{self.group_code}] {self.group_name}"


class CommonCode(models.Model):
    """
    공통 코드 상세 (중/소분류)
    예: REQ_PRIORITY 하위 -> HIGH(상), MEDIUM(중), LOW(하)
    """
    code_id = models.CharField(
        max_length=50, 
        primary_key=True, 
        verbose_name="코드 ID"
    )
    group = models.ForeignKey(
        CommonCodeGroup, 
        on_delete=models.CASCADE, 
        related_name="codes", 
        db_column="group_code", 
        verbose_name="코드 그룹"
    )
    code_name = models.CharField(
        max_length=100, 
        verbose_name="코드명"
    )
    sort_order = models.IntegerField(
        default=0, 
        verbose_name="정렬 순서"
    )
    is_active = models.BooleanField(
        default=True, 
        verbose_name="사용 여부"
    )
    description = models.TextField(
        null=True, 
        blank=True, 
        verbose_name="설명"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="생성 일시"
    )

    class Meta:
        db_table = "common_code"
        ordering = ["group", "sort_order"]
        verbose_name = "공통 코드"
        verbose_name_plural = "공통 코드 목록"

    def __str__(self):
        return f"[{self.group_id}] {self.code_id} - {self.code_name}"
```

* **DB 마이그레이션**
  * 마이그레이션 명령 실행:
    ```bash
    python manage.py makemigrations common
    python manage.py migrate
    ```

* **엑셀 데이터 주입**
  * Django의 Custom Management Command 방식을 구현
  * 이 방식을 사용하면 python manage.py load_codes 명령어 한 줄로 엑셀 데이터 130건을 한 번에 DB에 파싱하여 반영할 수 있음
  * common 하위 디렉토리 생성 후 seed_codes.py 파일 내 모델 작성
    ```text
      common/
        ├── management/
        │    ├── __init__.py
        │    └── commands/
        │         ├── __init__.py
        │         └── seed_codes.py
    ```
  * 커스텀 명령어 실행
    ```bash
    python manage.py seed_codes
    ```

* **`project` 앱 및 모델 구현**
  * `python manage.py startapp project` 실행 및 `config/settings.py`의 `INSTALLED_APPS`에 등록
  * DB 담당자 스키마 설계에 맞춘 `project/models.py` 내 모델 작성
  * 이 모델은 프로젝트 기본 정보(Project)와 프론트엔드 /history 페이지에 대응하는 파이프라인 전체 이력(PipelineHistory)을 관리

* **`requirements` 앱 및 모델 구현**
  * `python manage.py startapp requirements` 실행 및 `config/settings.py`의 `INSTALLED_APPS`에 등록
  * DB 담당자 스키마 설계에 맞춘 `requirements/models.py` 내 모델 작성
  * 이 모델은 파이프라인 2단계 산출물인 요구사항 정의서 헤더(RequirementDefinition) 및 세부 요구사항 항목(RequirementItem)을 정의

* **모든 주요 앱(common, users, meetings, requirements, tasks, projects)의 Serializer 구축**