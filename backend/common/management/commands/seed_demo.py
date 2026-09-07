# common/management/commands/seed_demo.py
"""
테스트용 더미 유저를 DB에 직접 주입한다. (datadump.json fixture 없이)

    python manage.py seed_demo                 # demo01~demo100, 비번 test1234!
    python manage.py seed_demo --count 30      # demo01~demo30
    python manage.py seed_demo --password pw!  # 비번 지정
    python manage.py seed_demo --reset         # demo* 유저/스킬/자격증 삭제 후 재생성

멱등이라 여러 번 실행해도 중복이 쌓이지 않는다.
공통코드(부서/직무/직급/권한/상태 + 스킬/자격증 코드)는 미리 있어야 한다.
없으면 안내 후 중단한다.
"""

import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from common.models import CommonCode
from users.models import UserCertification, UserSkill

User = get_user_model()

JOB  = ["BACKEND", "FRONTEND", "FULLSTACK", "DATA_ENGINEER", "DEVOPS",
        "PROJECT_MANAGER", "QA_ENGINEER", "UIUX_DESIGNER"]
DEPT = ["DEV_TEAM", "PLANNING_TEAM", "DESIGN_TEAM", "QA_TEAM", "HR_TEAM",
        "MARKETING_TEAM", "SALES_TEAM"]
POS  = ["STAFF", "SENIOR", "ASSISTANT", "MANAGER", "DEPUTY_GENERAL_MANAGER",
        "GENERAL_MANAGER", "DIRECTOR"]
STAT = ["ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE", "LEAVE"]

SURNAMES = list("김이박최정강조윤장임한오서신권황안송전홍유고문양손배백허남심노하곽")
GIVEN = ["지민", "서준", "도윤", "예은", "하준", "지우", "서연", "민준", "수아", "은우",
         "지호", "다은", "준서", "채원", "시우", "유진", "현우", "예린", "건우", "지아",
         "승현", "나윤", "준우", "서윤", "지훈", "하은", "태윤", "소율", "재민", "유나",
         "동현", "가은", "성민", "시연", "우진", "보람", "한결", "윤슬", "세아", "도현"]

PROJECTS = [
    "사내 협업 포털", "고객 CRM 고도화", "실시간 알림 시스템", "AI 문서요약 파이프라인",
    "결제 게이트웨이 연동", "모바일 앱 리뉴얼", "데이터 웨어하우스 구축", "관리자 대시보드 개편",
    "추천 엔진 v2", "SSO 인증 통합", "물류 트래킹 시스템", "챗봇 상담 자동화", "재고관리 최적화",
    "마케팅 자동화 플랫폼", "영상 스트리밍 서비스", "보안 감사 로그 시스템", "Kubernetes 마이그레이션",
    "레거시 API 현대화", "온보딩 자동화", "매출 리포트 BI", "실시간 채팅 서비스", "전자결재 시스템",
    "포인트/쿠폰 엔진", "검색 인프라 개편", "IoT 센서 모니터링",
]

# 직무별 스킬/자격증 코드 풀 (common_code.code_id 기준)
SKILL_POOL = {
    "BACKEND":         ["DJANGO", "SPRING", "FASTAPI", "NODEJS", "NESTJS", "PYTHON", "JAVA", "GO",
                        "TYPESCRIPT", "MYSQL", "POSTGRESQL", "REDIS", "REST_API", "GIT"],
    "FRONTEND":        ["REACT", "NEXTJS", "VUE", "ANGULAR", "HTML", "CSS", "TAILWIND_CSS",
                        "JAVASCRIPT", "TYPESCRIPT", "JEST", "CYPRESS", "GIT"],
    "FULLSTACK":       ["DJANGO", "SPRING", "NODEJS", "REACT", "NEXTJS", "VUE", "MYSQL",
                        "POSTGRESQL", "MONGODB", "TYPESCRIPT", "PYTHON", "GIT"],
    "DATA_ENGINEER":   ["PANDAS", "PYTORCH", "TENSORFLOW", "DATA_ANALYSIS", "SQL", "POSTGRESQL",
                        "MYSQL", "PYTHON", "AWS", "DOCKER", "LINUX"],
    "DEVOPS":          ["AWS", "AZURE", "GCP", "DOCKER", "KUBERNETES", "TERRAFORM", "CI_CD",
                        "LINUX", "REDIS", "GIT", "GO", "PYTHON"],
    "PROJECT_MANAGER": ["AGILE", "SCRUM", "JIRA", "GIT", "REST_API"],
    "QA_ENGINEER":     ["SELENIUM", "CYPRESS", "JEST", "GIT", "PYTHON", "REST_API", "GRAPHQL"],
    "UIUX_DESIGNER":   ["FIGMA", "SKETCH", "PROTOTYPING", "DESIGN_SYSTEM", "UX_RESEARCH",
                        "PHOTOSHOP", "ILLUSTRATOR", "HTML", "CSS", "GIT"],
}
CERT_POOL = {
    "BACKEND":         ["INFO_PROCESSING_ENGINEER", "INFO_PROCESSING_INDUSTRIAL_ENGINEER",
                        "SQLD", "SQLP", "OCJP"],
    "FRONTEND":        ["INFO_PROCESSING_ENGINEER", "ITQ", "COMPUTER_LITERACY_1", "COMPUTER_LITERACY_2"],
    "FULLSTACK":       ["INFO_PROCESSING_ENGINEER", "AWS_DEVELOPER_ASSOCIATE", "AWS_SOLUTIONS_ARCHITECT"],
    "DATA_ENGINEER":   ["ADSP", "BIG_DATA_ANALYST_ENGINEER", "SQLD", "SQLP"],
    "DEVOPS":          ["AWS_SOLUTIONS_ARCHITECT", "AWS_SYSOPS_ADMINISTRATOR", "AZURE_FUNDAMENTALS",
                        "GCP_ASSOCIATE_CLOUD_ENGINEER", "LINUX_MASTER", "CCNA", "NETWORK_ADMINISTRATOR"],
    "PROJECT_MANAGER": ["PMP", "ITQ", "COMPUTER_LITERACY_1"],
    "QA_ENGINEER":     ["INFO_PROCESSING_ENGINEER", "CISSP", "INFO_SECURITY_ENGINEER"],
    "UIUX_DESIGNER":   ["GTQ", "GTQI", "ITQ", "COMPUTER_LITERACY_2"],
}


class Command(BaseCommand):
    help = "테스트용 더미 유저(스킬·자격증·프로젝트 포함)를 DB에 직접 주입한다."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=100, help="생성할 유저 수 (demo01~)")
        parser.add_argument("--password", default="test1234!", help="공통 비밀번호")
        parser.add_argument("--reset", action="store_true", help="demo* 데이터 삭제 후 재생성")

    @transaction.atomic
    def handle(self, *args, **opts):
        count = opts["count"]
        password = opts["password"]

        # 0. 공통코드 존재 확인
        needed = set(JOB + DEPT + POS + ["EMPLOYEE", "TEAM_LEAD", "ADMIN"] + STAT)
        have = set(CommonCode.objects.filter(code_id__in=needed).values_list("code_id", flat=True))
        missing = needed - have
        if missing:
            self.stderr.write(self.style.ERROR(
                "공통코드가 없습니다: " + ", ".join(sorted(missing))[:200] +
                "\n먼저 공통코드를 시딩하세요 (seed_codes 또는 loaddata datadump.json)."
            ))
            return

        codes = {c.code_id: c for c in CommonCode.objects.all()}  # code_id -> CommonCode

        if opts["reset"]:
            qs = User.objects.filter(username__regex=r"^demo[0-9]+$")
            UserSkill.objects.filter(user__in=qs).delete()
            UserCertification.objects.filter(user__in=qs).delete()
            n, _ = qs.delete()
            self.stdout.write(f"기존 demo 데이터 삭제: {n} rows")

        skills_made = certs_made = 0

        for i in range(1, count + 1):
            uname = f"demo{i:02d}"
            emp_num = 100 + i
            rnd = random.Random(i)

            role = "ADMIN" if i % 25 == 0 else ("TEAM_LEAD" if i % 5 == 0 else "EMPLOYEE")
            is_admin = role == "ADMIN"
            job = JOB[i % len(JOB)]

            projs = ", ".join(rnd.sample(PROJECTS, rnd.randint(2, 4)))

            user, created = User.objects.get_or_create(
                username=uname, defaults={"email": f"{uname}@demo.io"}
            )
            user.email = f"{uname}@demo.io"
            user.last_name = SURNAMES[i % len(SURNAMES)]
            user.first_name = GIVEN[i % len(GIVEN)]
            user.emp_no = f"D{emp_num:04d}"
            user.phone = f"010-1000-{emp_num:04d}"
            user.dept_code = codes[DEPT[i % len(DEPT)]]
            user.job_role_code = codes[job]
            user.position_code = codes[POS[i % len(POS)]]
            user.role_code = codes[role]
            user.status_code = codes[STAT[i % len(STAT)]]
            user.past_projects = projs
            user.is_busy = (i % 3 == 0)
            user.is_active = True
            user.is_staff = is_admin
            user.is_superuser = is_admin
            user.set_password(password)          # 매 실행마다 비밀번호 재설정
            user.save()

            # 스킬 재생성 (직무 풀에서 3~5개)
            user.skills.all().delete()
            pool = [c for c in dict.fromkeys(SKILL_POOL[job]) if c in codes]
            for sc in rnd.sample(pool, min(len(pool), rnd.randint(3, 5))):
                UserSkill.objects.create(
                    user=user, skill_code=codes[sc], proficiency_level=rnd.randint(2, 5)
                )
                skills_made += 1

            # 자격증 재생성 (직무 풀에서 1~3개)
            user.certifications.all().delete()
            cpool = [c for c in dict.fromkeys(CERT_POOL[job]) if c in codes]
            for cc in rnd.sample(cpool, min(len(cpool), rnd.randint(1, 3))):
                UserCertification.objects.create(
                    user=user, cert_code=codes[cc],
                    acquired_date=f"202{rnd.randint(1, 5)}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}",
                )
                certs_made += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n완료: 유저 {count}명 / 스킬 {skills_made}건 / 자격증 {certs_made}건\n"
            f"로그인: username=demo01~demo{count:02d}, password={password}"
        ))
