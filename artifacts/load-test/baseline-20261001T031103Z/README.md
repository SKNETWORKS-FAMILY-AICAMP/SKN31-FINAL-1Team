# 단일 사용자 로컬 HTTPS 기준 측정

- 실행: 2026-10-01 12:11 KST, 실행 ID 20261001T031103Z
- Gunicorn 26.1.0: 워커 1개, gthread 2개, DEBUG=False. 임시 인증서를 신뢰한 HTTPS 연결.
- MySQL 8.4.11 / heyzzabi_test. 총 사용자 123명(테스트 20명 포함), 프로젝트 10개, 업무 200개.
- PM 및 일반 사용자를 차례로 실행. 동시에 진행 중인 요청 1개. 각 API 예열 2건 제외 후 측정 20건, 요청 사이 0.1초 대기.
- 측정 조회 340건: HTTP 200 및 JSON 객체/배열 검증 340건, 예상 밖 오류 0건.
- 로그인 각 1건 성공: PM 166.8ms, 일반 사용자 161.8ms. 로그인 표본으로 백분위 판정하지 않음.
- 일반 사용자의 PM 전용 분석 접근은 예상한 403 확인. 위 340건에서 제외.
- 백분위는 nearest-rank 방식. API별 표본 20건이므로 p95는 탐색적 참고값.

| 권한 | API | 평균(ms) | p95(ms) | 최대(ms) |
|---|---|---:|---:|---:|
| pm | /api/users/me/ | 17.4 | 20.0 | 20.4 |
| pm | /api/dashboard/overview/ | 37.1 | 39.7 | 40.3 |
| pm | /api/projects/ | 24.1 | 26.6 | 26.6 |
| pm | /api/tasks/assignments/ | 195.1 | 212.8 | 260.0 |
| pm | /api/meetings/notes/ | 44.1 | 47.4 | 64.6 |
| pm | /api/meetings/specs/ | 16.3 | 19.2 | 19.6 |
| pm | /api/requirements/ | 64.9 | 66.5 | 72.4 |
| pm | /api/notifications/ | 14.8 | 18.0 | 18.6 |
| pm | /api/dashboard/analytics/ | 33.8 | 36.2 | 37.7 |
| member | /api/users/me/ | 16.8 | 19.8 | 20.1 |
| member | /api/dashboard/overview/ | 36.7 | 40.6 | 66.5 |
| member | /api/projects/ | 23.5 | 25.5 | 30.8 |
| member | /api/tasks/assignments/ | 31.0 | 42.3 | 53.2 |
| member | /api/meetings/notes/ | 49.4 | 70.2 | 133.6 |
| member | /api/meetings/specs/ | 15.5 | 18.2 | 19.6 |
| member | /api/requirements/ | 63.7 | 66.2 | 66.2 |
| member | /api/notifications/ | 15.1 | 17.6 | 18.1 |

## 해석 및 한계

- 모든 API의 단일 사용자 p95는 잠정 조회 기준 1초 미만. 목표 동시 부하 통과를 의미하지 않음.
- PM 업무 목록이 가장 느림(p95 212.8ms). 다음 단계에서 사용자 수 증가와 함께 응답 크기·쿼리 부하 확인.
- 서버 RSS 합계 최대 약 230.6MiB(마스터+워커 합산; 공유 메모리 중복 가능). DB 컨테이너 자원은 미측정.
- Vercel·nginx·AWS 네트워크 제외. 서버와 부하 발생기가 같은 장비를 사용함.
- 단일 회차이며 5분 지속 기준 측정이나 3회 반복을 수행하지 않음. 쓰기·AI·폴링·토큰 갱신·동시 부하 미수행.
- 임시 서버는 측정 종료 후 자동 종료. 기존 .env와 서비스 코드는 변경하지 않음.

## 재현

프로젝트 루트에서:

```bash
/home/playdata/my-project/.venv/bin/python artifacts/load-test/http_baseline.py
```

로컬 DB 대상 및 테스트 데이터가 준비되어 있어야 한다. 기본 테스트 비밀번호를 바꿨다면 LOADTEST_PASSWORD를 지정한다.
requests.csv, logins.csv, resources.csv, manifest.json, summary.json에 원시값과 실행 조건을 저장했다.
