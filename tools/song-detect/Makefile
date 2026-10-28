# 상시 점검 (harness/check.py). 종료코드 0 통과 / 1 게이트 실패 / 2 점검 오류
PY ?= python
check:
	$(PY) harness/check.py
check-fast:
	$(PY) harness/check.py --fast
accept:
	$(PY) harness/check.py --accept
.PHONY: check check-fast accept
