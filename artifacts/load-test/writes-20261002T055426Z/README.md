# 과제 동시 수정 변경 유실 보완 후 재시험

2026-10-02, 로컬 heyzzabi_test, Gunicorn 1 worker / gthread 2 threads, 직접 HTTPS.

## 변경과 결과

상세 수정은 transaction.atomic 안에서 과제 행을 select_for_update로 조회한다. 첫 수정이 저장될 때까지 다음 수정이 대기하고 최신 필드를 읽도록 했다. 일반 조회 queryset에는 잠금을 적용하지 않는다.

| 검사 | 요청 | HTTP/본문 오류 | p95 ms | 최종 저장 불일치 |
|---|---:|---:|---:|---:|
| 서로 다른 과제 20건 × 10회 | 200 | 0 | 261.420 | 0 |
| 동일 과제 두 필드 수정 × 20회 | 40 | 0 | 40.184 | 0 |

- 최초 실행에서는 경합 20회 모두 변경 유실, 재시험에서는 0회다.
- 테스트 대상 필드를 복원하고 DB 재조회로 검증했다.
- 상태 변경 API에도 동일 과제 행 잠금을 추가했으나 이 재시험은 상세 PATCH만 대상으로 한다. 상태 전이·상태 API 간 교차 경합·담당자 재배정·알림 정합성은 후속 검사 대상이다.
- 약 3.6초의 정해진 요청 수 검사다. 장시간 쓰기 부하, 문서 승인·확정, AI, 운영 배포 경로는 포함하지 않았다.
- 같은 필드의 상충 변경은 별도의 충돌 정책이 필요하다. 이번 검사는 서로 다른 필드의 변경 보존을 검증한다.

원시 증적: requests.csv, manifest.json, summary.json, resources.csv, server.log. 도구: ../staged_writes.py.

재현: `/home/playdata/my-project/.venv/bin/python artifacts/load-test/http_baseline.py --writes`

실행 시 PM은 합성 과제, 일반 계정은 본인 합성 과제를 대상으로 하며 끝나면 원래 필드를 복원한다. 테스트 중 사용자 작업이 없는 전용 로컬 DB에서 실행해야 한다.
