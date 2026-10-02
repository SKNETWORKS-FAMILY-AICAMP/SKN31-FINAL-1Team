# 담당자 재배정·완료 부수 효과 재시험

2026-10-02, 로컬 `heyzzabi_test`, Gunicorn 1 worker / gthread 2 threads, 직접 HTTPS. 합성 과제 2건과 PM·일반 계정 3개를 사용했다. 다른 미완료 과제가 있는 기존 담당자의 `is_busy=True`를 시작 조건으로 설정했다.

- 요청 8건의 기대 상태 오류 0건, DB 정합성 항목 12개 모두 통과. 전체 요청 p95 23.839ms. 요청 수가 적어 용량·안정적 백분위 근거로 사용하지 않는다.
- 일반 계정 재배정 403, PM 재배정 200, 같은 담당자로 재요청 200. 새 담당자의 `is_busy=True`, 기존 담당자의 다른 미완료 과제에 따른 `is_busy=True`, 재배정 알림 1건을 확인했다.
- 승인된 과제 및 완료된 과제의 일반 재배정은 각각 403, 담당자는 변경되지 않았다.
- 다른 과제가 없는 PM 담당 과제의 완료는 상태 `DONE`, 진행률 100%, `is_busy=False`로 저장됐다. 알림·파이프라인 히스토리는 각각 1건이고 완료 재요청 뒤에도 증가하지 않았다.
- 테스트용 과제 2건과 생성한 알림·히스토리를 삭제하고 세 계정의 `is_busy`를 시작 값으로 되돌렸다. 테스트 로그인 세션과 자동 갱신 시각은 복원 대상으로 삼지 않았다.

이 검사는 짧은 기능·부수 효과 검사다. 퇴사자 재배정 예외, 여러 과제의 동시 완료 경합, 문서 승인·확정, 장시간 쓰기 부하는 별도 검증 대상이다.

원시 증적: `manifest.json`의 `checks`, `requests.csv`, `summary.json`, `resources.csv`, `server.log`. 재현: `/home/playdata/my-project/.venv/bin/python artifacts/load-test/http_baseline.py --assignment-effects`.
