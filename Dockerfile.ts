# TypeScript 버전(NestJS + React) 이미지. 기존 Python 이미지(Dockerfile)와 별개로 빌드한다:
#   docker build -f Dockerfile.ts -t recordweb-ts:latest .
# 녹화/후처리는 streamlink, yt-dlp, ffmpeg 바이너리를 subprocess로 부르므로 이미지에 같이 넣는다.

FROM denoland/deno:bin AS deno

FROM node:24-bookworm-slim AS build
RUN corepack enable
WORKDIR /src
# 의존성 레이어 캐시: manifest만 먼저 복사
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY apps/api/package.json apps/api/
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile
COPY apps apps
RUN pnpm build \
    && pnpm --filter api --prod deploy --legacy /out/api

FROM node:24-bookworm-slim
# ffmpeg: 후처리/분할, python venv: streamlink + yt-dlp, tzdata: 파일 mtime을 NAS 시각(KST)으로 표시
ENV TZ=Asia/Seoul
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg python3 python3-venv ca-certificates tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && python3 -m venv /opt/py \
    && /opt/py/bin/pip install --no-cache-dir streamlink==8.5.0 yt-dlp \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/py/bin:$PATH
# deno는 yt-dlp의 외부 JS 런타임(PO token 등)에 쓰인다.
COPY --from=deno /deno /usr/local/bin/deno

WORKDIR /app
COPY --from=build /out/api /app
COPY --from=build /src/apps/web/dist /app/web-dist
ENV RECORDWEB_ROOT=/app WEB_DIST=/app/web-dist NODE_ENV=production

EXPOSE 5000
# 서버가 SIGTERM을 받으면 녹화 중인 프로세스를 정리하도록 init이 신호를 전달한다(compose의 init: true).
CMD ["node", "dist/main.js"]
