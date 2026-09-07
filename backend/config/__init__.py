# config/__init__.py
#
# requirements.txt는 mysqlclient(MySQLdb)를 기준으로 하지만, 이건 시스템 라이브러리
# (libmysqlclient-dev)가 필요해서 sudo 권한 없이는 설치가 안 되는 환경이 있다(WSL 등).
# pymysql은 순수 Python 드라이버라 pip install만으로 설치되고, 아래처럼 MySQLdb인 척
# 등록해두면 Django의 django.db.backends.mysql이 코드 수정 없이 그대로 동작한다.
# mysqlclient가 이미 설치돼 있으면(팀 표준 환경) 이 shim은 아무 영향이 없다 — pymysql이
# 없으면 import 자체가 조용히 스킵된다.
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass
