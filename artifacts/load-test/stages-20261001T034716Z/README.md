# 일반 조회 API 단계별 부하 탐색 결과

실행 ID: 20261001T034716Z

- 로컬 MySQL 8.4.11, 프로젝트 10개·업무 200개·사용자 총 123명.
- Gunicorn 1 worker / gthread 2 threads, DEBUG=False, 직접 HTTPS. AWS·Vercel·nginx 제외.
- 단계: 20명, 각 300초. 단계별 PM 20%·일반 80%, 계정/쿠키 개별 사용.
- 사용자별 요청 간 2~5초 대기, 시작 지연 0~2초. 폐쇄형 사용자 모델이며 동시 사용자 수가 동시 요청 수를 뜻하지 않음.
- 조회 비중: 대시보드 25%, 프로젝트 20%, 업무 20%, 회의록/기획서/요구사항 각 10%, 알림 5%.
- 20계정 사전 로그인과 역할별 각 경로 1회 예열은 아래 통계에서 제외. AI·도메인 쓰기·갱신·폴링 미수행.
- 정상 판정: HTTP 200 및 JSON 객체/배열 확인. 전체 업무 내용의 의미 검증은 별도.

| 사용자 | 요청 | 오류 | 실측 RPS | 평균 ms | p95 ms | p99 ms | 최대 ms | 최대 진행 중 요청 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 1691 | 0 | 5.64 | 47.63 | 111.541 | 242.062 | 410.224 | 3 |

## API·권한별 상세

| 사용자 | 권한 | 경로 | 표본 | 오류 | p95 ms |
|---:|---|---|---:|---:|---:|
| 20 | member | /api/meetings/notes/ | 120 | 0 | 73.188 |
| 20 | member | /api/projects/ | 276 | 0 | 40.336 |
| 20 | member | /api/dashboard/overview/ | 333 | 0 | 64.085 |
| 20 | pm | /api/tasks/assignments/ | 69 | 0 | 332.846 |
| 20 | member | /api/meetings/specs/ | 143 | 0 | 25.198 |
| 20 | pm | /api/projects/ | 62 | 0 | 38.13 |
| 20 | member | /api/tasks/assignments/ | 263 | 0 | 54.792 |
| 20 | pm | /api/dashboard/overview/ | 80 | 0 | 59.438 |
| 20 | pm | /api/notifications/ | 18 | 0 | 30.762 |
| 20 | member | /api/requirements/ | 153 | 0 | 111.319 |
| 20 | member | /api/notifications/ | 68 | 0 | 23.646 |
| 20 | pm | /api/meetings/specs/ | 29 | 0 | 21.034 |
| 20 | pm | /api/requirements/ | 38 | 0 | 194.798 |
| 20 | pm | /api/meetings/notes/ | 39 | 0 | 64.42 |

## 해석과 한계

- 이 실행은 20명·5분 반복 검증의 3회차다. 총 3회 비교는 ../repeat-summary-20u-5m/README.md에 기록했다. 최대 처리 용량·운영 SLA 통과를 판단하지 않는다.
- RPS는 단계 요청 수 / 실제 경과시간(마지막 요청 완료 대기 포함). 대기시간을 포함한 사용자 행동의 처리량이며 서버 최대 처리량이 아니다.
- p95/p99는 nearest-rank. 특히 권한·경로별 적은 표본의 백분위는 참고값이다. 단계 전체 백분위와 경로별 백분위를 구분한다.
- 서버 CPU는 마스터·워커 CPU 시간 증가량 / 경과시간으로 계산한 1코어 기준 비율. RSS는 프로세스 합산으로 공유 메모리를 중복 계산할 수 있다.
- MySQL 컨테이너 CPU·DB 연결·쿼리·잠금은 미측정. 서버와 발생기가 같은 장비를 공유한다.
- 기존 단일 사용자 측정과 요청 비율·대기시간이 달라 전체 평균의 단순 비율 비교는 하지 않는다.
- 실행 후 임시 서버 종료. AWS 접속·외부 AI 호출·기존 업무 데이터 수정 없음(테스트 로그인 세션 업데이트만 발생).

## 재현

```bash
LOADTEST_STAGES=20 LOADTEST_STAGE_SECONDS=300 /home/playdata/my-project/.venv/bin/python artifacts/load-test/http_baseline.py --staged
```
