"""이미지 빌드 중 streamlink의 HTTPS 처리가 깨지지 않았는지 확인한다.

urllib3 2.8.0 + streamlink 조합은 모든 HTTPS 요청이
"Urllib3UtilUrlPercentReOverride has no attribute 'sub'" 로 실패한다 (녹화가 시작조차 안 됨).
요청 자체의 성공 여부(404 등)는 상관없고, 이 오류가 나면 빌드를 실패시킨다.
네트워크가 없는 빌드 환경에서는 연결 오류만 나므로 통과한다.
"""
import sys

from streamlink import Streamlink

try:
    Streamlink().http.get("https://api.chzzk.naver.com/service/v2/channels/healthcheck/live-detail", timeout=10)
except Exception as e:  # noqa: BLE001 - 어떤 응답이든 메시지만 본다
    if "Urllib3UtilUrlPercentReOverride" in str(e):
        sys.exit(f"streamlink HTTPS 처리가 깨졌습니다 (urllib3 호환성): {e}")
print("streamlink HTTPS check ok")
