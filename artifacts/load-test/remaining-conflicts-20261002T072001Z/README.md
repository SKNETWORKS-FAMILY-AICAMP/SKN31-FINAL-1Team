# 남은 경합 검사

2026-10-02, 로컬 `heyzzabi_test`, Gunicorn 1 worker / gthread 2 threads, 직접 HTTPS 조건이다. 퇴사 처리된 담당자의 승인 과제 재배정, 같은 담당자의 두 과제 동시 완료, 같은 요구사항 정의서의 동시 과제 확정을 검사했다.

- 5개 요청의 기대 HTTP 상태 오류 0건, 전체 p95 88.921ms였다.
- 퇴사자 승인 과제는 PM이 새 담당자에게 재배정할 수 있었다.
- 두 과제 동시 완료 뒤 두 과제 모두 `DONE`·100%였고 마지막 미완료 과제가 없어 `is_busy=False`가 됐다.
- 동일 확정 요청 2건 뒤 최종 과제는 중복 없이 정확히 2건, 모두 `PENDING_APPROVAL`이었다.
- 임시 과제·요구사항 정의서·항목을 삭제하고 퇴사일과 `is_busy`를 시작값으로 복원했다.

표본이 작은 경합 기능 검사이며 처리 용량 근거로 사용하지 않는다. 상세 값은 `manifest.json`, `requests.csv`, `summary.json`, `server.log`에 있다.
