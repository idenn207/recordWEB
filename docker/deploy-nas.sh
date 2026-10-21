#!/bin/sh
# NAS에서 Python 컨테이너를 TypeScript 컨테이너로 교체한다. root 권한이 필요하다:
#   ssh -t nas-claude 'sudo sh /volume3/docker/recordweb-ts/docker/deploy-nas.sh'
#
# 순서: 녹화 중 확인 → json 백업 → 이미지 빌드(기존 컨테이너는 계속 동작) → 컨테이너 교체 → 확인.
# 빌드를 먼저 끝내므로 녹화가 끊기는 시간은 교체 구간(수십 초)뿐이다.
# 롤백: 이 스크립트가 끝에 출력하는 명령을 그대로 실행한다.
set -eu

DOCKER=/usr/local/bin/docker
NEW=/volume3/docker/recordweb-ts
OLD=/volume3/docker/recordweb
HOST=192.168.0.10:5080

cd "$NEW"
echo "[docker] $($DOCKER --version)"

echo "== 1. 지금 녹화 중인 채널"
N=$(curl -s -m 8 "http://$HOST/status" | grep -o '"recording":true' | wc -l | tr -d ' ')
echo "  녹화 중 ${N}개 (응답이 없으면 0으로 표시됩니다)"
if [ "$N" != "0" ] && [ "${FORCE:-}" != "1" ]; then
  echo "녹화 중인 채널이 있습니다. 교체하면 그 녹화가 끊깁니다."
  printf "그래도 교체할까요? (yes 입력) "
  read ANS
  [ "$ANS" = "yes" ] || { echo "중단했습니다. 컨테이너는 그대로입니다."; exit 1; }
fi

echo "== 2. json 백업"
BK="$OLD/json.bak-$(date +%Y%m%d-%H%M%S)"
cp -a "$OLD/json" "$BK"
echo "  $BK"

echo "== 3. 이미지 빌드 (기존 컨테이너는 계속 동작)"
# Dockerfile.ts 전용 ignore 파일은 BuildKit에서만 쓰이므로, 어느 빌더에서도 같게 동작하도록 .dockerignore로도 둔다.
cp Dockerfile.ts.dockerignore .dockerignore
DOCKER_BUILDKIT=1 $DOCKER build -f Dockerfile.ts -t recordweb-ts:latest .

echo "== 4. 컨테이너 교체"
if $DOCKER compose version >/dev/null 2>&1; then COMPOSE="$DOCKER compose"; else COMPOSE=docker-compose; fi
$DOCKER stop -t 60 recordweb
$DOCKER rename recordweb recordweb-py-old
$COMPOSE -f docker-compose.ts.yml up -d --no-build

echo "== 5. 확인"
OK=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 3
  if curl -s -m 5 -o /dev/null -w "%{http_code}" "http://$HOST/api/channels" | grep -q 200; then OK=1; break; fi
done
if [ "$OK" = "1" ]; then
  echo "  새 서버가 응답합니다: http://$HOST"
  $DOCKER logs --tail 5 recordweb 2>&1 | sed 's/^/  /'
  echo
  echo "정상 확인 후 옛 컨테이너 삭제: $DOCKER rm recordweb-py-old"
else
  echo "  !! 새 서버가 응답하지 않습니다. 로그:"
  $DOCKER logs --tail 30 recordweb 2>&1 | sed 's/^/  /'
fi
echo
echo "롤백: $DOCKER rm -f recordweb && $DOCKER rename recordweb-py-old recordweb && $DOCKER start recordweb"
