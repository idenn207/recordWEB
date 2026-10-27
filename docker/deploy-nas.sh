#!/bin/sh
# NAS 배포. root 권한이 필요하다:
#   ssh -t nas-claude 'sudo sh /volume3/docker/recordweb-ts/docker/deploy-nas.sh [app|recorder|all]'
#
#   app      (기본) 웹+업로더만 교체한다. 녹화는 끊기지 않는다.
#   recorder 녹화기만 교체한다. 녹화 중이면 확인을 묻는다 (FORCE=1이면 묻지 않는다).
#   all      둘 다. 기존 단일 컨테이너(recordweb)에서 처음 옮길 때도 이걸 쓴다.
#
# 순서: json 백업 → 이미지 빌드(기존 컨테이너는 계속 동작) → 컨테이너 교체 → 응답 확인.
set -eu

DOCKER=/usr/local/bin/docker
NEW=/volume3/docker/recordweb-ts
HOST=192.168.0.10:5080
TARGET=${1:-app}
case "$TARGET" in app|recorder|all) ;; *) echo "사용법: $0 [app|recorder|all]"; exit 2 ;; esac

cd "$NEW"
echo "[docker] $($DOCKER --version)"

# 기존 단일 컨테이너가 남아 있으면 둘로 갈아타야 한다 (같은 포트를 쓴다)
OLD=$($DOCKER ps -aq -f name='^recordweb$' || true)
[ -n "$OLD" ] && TARGET=all

if [ "$TARGET" != "app" ]; then
  echo "== 지금 녹화 중인 채널"
  N=$(curl -s -m 8 "http://$HOST/api/channels" | grep -o '"state":"recording"' | wc -l | tr -d ' ')
  echo "  녹화 중 ${N}개 (응답이 없으면 0으로 표시됩니다)"
  if [ "$N" != "0" ] && [ "${FORCE:-}" != "1" ]; then
    echo "녹화 중인 채널이 있습니다. 녹화기를 교체하면 그 녹화가 끊깁니다."
    printf "그래도 교체할까요? (yes 입력) "
    read ANS
    [ "$ANS" = "yes" ] || { echo "중단했습니다. 컨테이너는 그대로입니다."; exit 1; }
  fi
fi

echo "== json 백업"
BK="/volume3/docker/recordweb/json.bak-$(date +%Y%m%d-%H%M%S)"
cp -a /volume3/docker/recordweb/json "$BK"
echo "  $BK"

mkdir -p /volume1/storage/recordweb-files/xspaces  # X 스페이스 녹음 폴더 (compose 볼륨)
echo "== 이미지 빌드 (기존 컨테이너는 계속 동작)"
# NAS의 Docker에는 buildx가 없어 기본(레거시) 빌더를 쓴다. 이 빌더는 Dockerfile.ts.dockerignore를 읽지 않으므로 .dockerignore로 복사한다.
cp Dockerfile.ts.dockerignore .dockerignore
# 롤백용으로 지금 이미지를 prev 태그로 남겨 둔다
if $DOCKER image inspect recordweb-ts:latest >/dev/null 2>&1; then $DOCKER tag recordweb-ts:latest recordweb-ts:prev; fi
DOCKER_BUILDKIT=0 $DOCKER build -f Dockerfile.ts -t recordweb-ts:latest .

echo "== 컨테이너 교체 ($TARGET)"
if $DOCKER compose version >/dev/null 2>&1; then COMPOSE="$DOCKER compose"; else COMPOSE=docker-compose; fi
if [ -n "$OLD" ]; then $DOCKER stop -t 60 recordweb; $DOCKER rm recordweb; fi
case "$TARGET" in
  all) SERVICES="recorder app" ;;
  *) SERVICES="$TARGET" ;;
esac
# --no-deps: app만 올릴 때 recorder를 건드리지 않는다
$COMPOSE -f docker-compose.ts.yml up -d --no-build --no-deps $SERVICES

echo "== 확인"
OK=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 3
  if curl -s -m 5 -o /dev/null -w "%{http_code}" "http://$HOST/api/channels" | grep -q 200; then OK=1; break; fi
done
if [ "$OK" = "1" ]; then
  echo "  서버가 응답합니다: http://$HOST"
else
  echo "  !! 응답하지 않습니다. 로그:"
  for s in $SERVICES; do $DOCKER logs --tail 30 recordweb-$s 2>&1 | sed "s/^/  [$s] /"; done
fi
echo
echo "롤백(직전 이미지): $DOCKER tag recordweb-ts:prev recordweb-ts:latest && cd $NEW && $COMPOSE -f docker-compose.ts.yml up -d --no-build --no-deps --force-recreate $SERVICES"
