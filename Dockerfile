# deno는 yt-dlp의 외부 JS 런타임(PO token 등)에 쓰인다. denoland의 공식
# "bin" 이미지는 /deno 바이너리 하나만 담은 scratch 이미지라 멀티스테이지
# COPY로 가져오는 게 apt/curl 설치보다 가볍고 재현 가능하다.
FROM denoland/deno:bin AS deno

FROM python:3.11-slim-bookworm

# ffmpeg: 녹화/트랜스코딩. aria2: replay 다운로드(module/replay_download.py는
# Windows 하드코딩이라 이 배포 경로에서는 안 쓰이지만, module/data_manager.py의
# getAria2c()가 Linux에서 shutil.which("aria2c")를 찾으므로 설치해 둔다.
# tzdata: 베이스 이미지엔 시간대 데이터가 없어서 time.localtime()이 항상 UTC로
# 계산된다(파일 관리자 화면의 mtime 표시가 실제 NAS 시각과 어긋나던 원인) — 설치 후
# Asia/Seoul로 고정한다.
ENV TZ=Asia/Seoul
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        aria2 \
        ca-certificates \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deno /deno /usr/local/bin/deno

WORKDIR /app

# requirements.txt만 먼저 복사해 의존성 레이어를 캐싱한다 — 코드만 바뀐
# 재빌드에서 pip install을 반복하지 않는다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "recordWEB.py"]
