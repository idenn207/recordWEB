# recordWEB TypeScript 버전

기존 Python(FastAPI) 앱을 NestJS + React로 다시 작성한 버전입니다. 설정/상태 JSON 파일 형식은 그대로라서
`json/` 폴더를 바꾸지 않고 읽습니다. 기존 Python 코드는 검증이 끝날 때까지 저장소에 남아 있습니다.

## 구조 (pnpm 모노레포)

```
apps/api   NestJS. config(설정·채널·쿠키 저장소) / chzzk·youtube(방송 상태 조회) /
           recorder(감시·녹화 루프, 후처리, 알림) / files / uploads(YouTube 업로드) / system
apps/web   Vite + React + Tailwind v4 + Headless UI, FSD 구조
           app / pages / widgets / features / entities / shared (위 계층만 아래 계층을 import)
```

녹화·후처리·다운로드는 `streamlink`, `yt-dlp`, `ffmpeg`를 subprocess로 실행합니다 (Python 라이브러리 의존 없음).

## 실행

```bash
pnpm install
pnpm build                 # web 빌드 후 api 빌드
pnpm start                 # http://localhost:5000 (config.json의 port, PORT 환경변수로 변경)

pnpm dev:api               # 개발: API (tsc watch)
pnpm dev:web               # 개발: Vite (5173, /api는 5000으로 프록시)
pnpm test                  # 단위 테스트 (api: vitest)
```

환경변수: `RECORDWEB_ROOT`(json/녹화 폴더 기준 경로, 기본 현재 폴더), `PORT`, `WEB_DIST`,
`FFMPEG` / `FFPROBE` / `STREAMLINK` / `YT_DLP` / `DENO`(바이너리 경로 지정).
Windows 개발 환경에서는 `dependent/` 안의 번들 바이너리를 자동으로 찾습니다(`RECORDWEB_BIN_ROOT`로 위치 변경).

## NAS 배포 (Docker)

소스를 NAS의 `/volume3/docker/recordweb-ts/`에 올린 뒤, root 권한으로 스크립트를 실행합니다.
녹화 중인 채널이 있으면 확인을 묻고, json 백업 → 이미지 빌드(기존 컨테이너 유지) → 교체 → 응답 확인 순서로 진행하며 롤백 명령을 출력합니다.

```bash
ssh -t nas-claude 'sudo sh /volume3/docker/recordweb-ts/docker/deploy-nas.sh'
```

수동으로 하려면 기존 컨테이너를 먼저 중지한 뒤 `docker compose -f docker-compose.ts.yml up -d --build`를 실행합니다.

기존과 같은 포트·볼륨(`/app/json`, `/app/chzzk`)을 씁니다. YouTube 업로드는 기존에 배치로 돌리던
`yt_token.json`, `yt_upload_state.json`을 `json/` 폴더에 두면 이어서 사용합니다(상태가 있어야 이미 올린 99개가 중복되지 않습니다).

### YouTube 재인증

YouTube 업로드 → 업로드 설정에서 **새 refresh token**을 입력하고 **재인증**을 누릅니다.
기존 `json/yt_token.json`의 client ID와 secret으로 Google에 유효성을 확인한 뒤 refresh token만 교체합니다.
실패하면 기존 파일을 유지하며, 성공하면 인증 오류를 해제하고 다음 업로드 스캔(기본 최대 5분)부터 자동으로 재개합니다.
새 토큰은 기존과 같은 OAuth 클라이언트에서 발급해야 합니다. 클라이언트가 달라졌거나 최초 등록이라면
아래 **인증 토큰 전체 JSON**에 `refresh_token`, `client_id`, `client_secret`, `token_uri`가 들어 있는 JSON을 등록합니다.
토큰 값은 화면에 다시 표시하지 않습니다. `POST /api/uploads/reauth`는 `{ "refresh_token": "새 값" }`을 받으며 성공 여부만 반환합니다.

Google 로그인과 OAuth 콜백을 통한 자동 재발급은 지원하지 않습니다. LAN HTTP 주소는 Google OAuth 콜백으로
등록할 수 없어 도메인·HTTPS 구성이 필요하며, 현재는 발급받은 토큰을 직접 등록하는 방식입니다.

## Python 버전과 달라진 점

- 제외: GPU 하드웨어 인코딩, 분할 녹화(overlap), `timemachine` 플러그인, 다시보기 다운로더, PyQt GUI, 앱 로그인/계정.
  후처리는 스트림 복사와 소프트웨어 재인코딩(libx264/libx265)만 지원합니다.
- 파일 관리자의 `fileManagerEnabled`는 더 이상 `loginMode`에 묶이지 않습니다. 설정에서 켜면 바로 동작합니다.
- 후처리에서 `fixed_` 접두사를 뗄 때 같은 이름이 이미 있으면 덮어쓰지 않고 `fixed_` 이름을 유지합니다.
- 서버가 종료될 때(컨테이너 중지 등) 녹화를 중지하고 후처리가 끝나기를 최대 25초 기다립니다.
