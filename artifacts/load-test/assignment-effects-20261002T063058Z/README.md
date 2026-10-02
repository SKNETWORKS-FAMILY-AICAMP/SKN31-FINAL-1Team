# 담당자 재배정·완료 부수 효과 최초 검사

로컬 합성 과제 2건을 임시 생성해 8개의 HTTP 요청과 12개 DB 정합성 항목을 검사했다. 요청의 기대 상태 오류는 0건, 정합성 항목 1개가 실패했다.

실패 항목은 `old_assignee_still_busy_with_other_tasks`이다. 기존 합성 계정의 `is_busy`가 시작 전부터 `False`였으므로 “재배정 후에도 True 유지”를 확인할 전제 조건이 없었다. 애플리케이션 결함으로 판정하지 않고 테스트 준비 조건 오류로 분류한다. 대상 계정 상태와 임시 과제·알림·히스토리는 정리했다.

원시 자료: `manifest.json`의 `checks`, `requests.csv`, `server.log`. 유효한 재시험: `../assignment-effects-20261002T063146Z/README.md`.
