# 과제 조회 개선 후 20명·60초 재시험

2026-10-02, 로컬 MySQL heyzzabi_test, 프로젝트 50개·과제 2,000개.
Gunicorn 1 worker / 2 threads, DEBUG=False, 직접 HTTPS. PM 20%·일반 80%, 사용자 대기 2~5초. 로그인·예열은 제외했다.

| 지표 | 개선 전 | 개선 후 |
|---|---:|---:|
| 요청 수 | 271 | 325 |
| 오류 | 0 | 0 |
| RPS | 4.49 | 5.392 |
| 평균 ms | 949.620 | 193.099 |
| 전체 p95 ms | 3341.249 | 575.287 |
| 전체 p99 ms | 3760.780 | 726.394 |
| 최대 ms | 5346.372 | 775.092 |
| PM 과제 목록 p95 ms | 5346.372 (16건) | 726.394 (18건) |

백분위는 nearest-rank. 모든 측정 요청의 최대값이 1초 미만이며, 이번 단회 실행에서 잠정 조회 지연·오류율 기준을 충족했다. 같은 장비의 서버·발생기 및 60초 단회 결과로 운영 용량을 판정하지 않는다. 실행 날짜·캐시·환경 상태 차이를 포함하며 지연 변화 전체를 코드 수정만의 효과로 단정하지 않는다.

과제 목록/상세 queryset에 original_assigned_user, project, difficulty_code, git_status_code를 select_related로 추가했다. PM SQL 계측은 2,002개 → 2개, 내부 평균 1,671.498ms → 290.454ms였다. 응답 크기는 2,061,681bytes로 유지된다.

25개 과제의 기존/최적화 queryset 직렬화 내용 일치, 일반 사용자 본인 업무 목록·다른 담당자 필터 우회 방지·본인 상세 200·타인 상세 404를 확인했다. 프론트는 전체 배열을 사용하므로 페이지네이션은 후속 검토가 필요하다.

원시 증적: requests.csv, resources.csv, manifest.json, summary.json, server.log. 쿼리 증적: ../query-profile/task-optimized-20261002/profile.json. 비교 대상: ../stages-20261001T051929Z/.

재현: `LOADTEST_STAGES=20 LOADTEST_STAGE_SECONDS=60 /home/playdata/my-project/.venv/bin/python artifacts/load-test/http_baseline.py --staged`

다음 단계는 동일 확장 데이터에서 20명·5분 3회 반복 검증이다. 최종 보고서 갱신은 아직 수행하지 않았다.
