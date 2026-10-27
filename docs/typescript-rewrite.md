# recordWEB TypeScript 버전

기존 Python(FastAPI) 앱을 NestJS + React로 다시 작성한 버전입니다. 설정/상태 JSON 파일 형식은 그대로라서
`json/` 폴더를 바꾸지 않고 읽습니다. 기존 Python 코드와 PyQt/웹 GUI는 제거했습니다(git 이력에 남아 있습니다).

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

같은 이미지를 두 컨테이너로 띄웁니다. `ROLE` 환경변수로 역할을 정합니다(없으면 한 프로세스에 전부, 개발용).

| 컨테이너 | ROLE | 하는 일 |
|---|---|---|
| `recordweb-recorder` | `recorder` | 녹화/후처리, 채널 API. 포트를 게시하지 않음 |
| `recordweb-app` | `app` | 웹(5080), YouTube 업로드, 파일 관리, 설정. 채널/녹화 API는 recorder로 프록시 |

웹/업로더를 고쳐 배포해도 녹화는 끊기지 않습니다. JSON 파일의 쓰기 주체는 하나입니다:
`channels.json`은 recorder, `config.json`·쿠키·`yt_*`는 app이 씁니다. 상대가 쓴 파일은 mtime이 바뀌면 다시 읽습니다.
app은 5초마다 recorder에 녹화 중인 파일 목록을 물어 업로드/파일 작업에서 피합니다.

소스를 NAS의 `/volume3/docker/recordweb-ts/`에 올린 뒤, root 권한으로 스크립트를 실행합니다.
json 백업 → 이미지 빌드(기존 컨테이너 유지) → 교체 → 응답 확인 순서로 진행하며 롤백 명령을 출력합니다.

```bash
ssh -t nas-claude 'sudo sh /volume3/docker/recordweb-ts/docker/deploy-nas.sh'            # app만 (기본, 녹화 유지)
ssh -t nas-claude 'sudo sh /volume3/docker/recordweb-ts/docker/deploy-nas.sh recorder'    # 녹화기만 (녹화 중이면 확인)
ssh -t nas-claude 'sudo sh /volume3/docker/recordweb-ts/docker/deploy-nas.sh all'
```

기존 단일 컨테이너(`recordweb`)가 남아 있으면 스크립트가 자동으로 `all`로 바꿔 둘로 갈아탑니다(이때 한 번 녹화가 끊깁니다).
recorder와 app 사이의 API(`/api/recorder/busy`, `/api/channels`, `/api/recording`)를 바꿀 때는 둘 다 배포하세요.

기존과 같은 포트·볼륨(`/app/json`, `/app/chzzk`)을 씁니다. YouTube 업로드는 기존에 배치로 돌리던
`yt_token.json`, `yt_upload_state.json`을 `json/` 폴더에 두면 이어서 사용합니다(상태가 있어야 이미 올린 99개가 중복되지 않습니다).

### YouTube 재인증

YouTube 업로드 → 업로드 설정에서 **새 refresh token**을 입력하고 **재인증**을 누릅니다.
기존 `json/yt_token.json`의 client ID와 secret으로 Google에 유효성을 확인한 뒤 refresh token만 교체합니다.
실패하면 기존 파일을 유지하며, 성공하면 인증 오류를 해제하고 다음 업로드 스캔(기본 최대 5분)부터 자동으로 재개합니다.
새 토큰은 기존과 같은 OAuth 클라이언트에서 발급해야 합니다. 클라이언트가 달라졌거나 최초 등록이라면
아래 **인증 토큰 전체 JSON**에 `refresh_token`, `client_id`, `client_secret`, `token_uri`가 들어 있는 JSON을 등록합니다.
토큰 값은 화면에 다시 표시하지 않습니다. `POST /api/uploads/reauth`는 `{ "refresh_token": "새 값" }`을 받으며 성공 여부만 반환합니다.

웹 화면에서 Google 로그인으로 이동하는 기능은 없습니다. 기존 데스크톱 OAuth 클라이언트는 아래 PC용 도구로
재인증할 수 있습니다. NAS의 LAN HTTP 주소를 Google 콜백으로 등록할 필요가 없습니다.

#### 기존 데스크톱 클라이언트로 PC에서 로그인

Windows PC에서 프로젝트 루트의 **`youtube_reauth.bat`를 더블클릭**합니다.
처음 실행할 때만 Python 인증 라이브러리를 `tools/.venv/`에 설치합니다(Python 3.10 이상 필요).
기존 `json/yt_token.json`의 client ID·secret을 읽고, 기본 브라우저에서 Google 로그인·권한 동의 화면을 엽니다.
업로드할 계정과 YouTube 채널을 선택하면 이 PC의 임시 `127.0.0.1` 콜백으로 돌아와 인증을 완료합니다.
원본은 유지하고 결과를 `json/yt_token.reauthenticated.json`에 저장한 뒤,
`http://192.168.0.10:5080/api/uploads/reauth`로 새 refresh token만 전송하여 NAS에 등록합니다.
SSH 터널·외부 포트 개방·NAS 재시작은 필요 없습니다.

인증만 하고 NAS에 직접 등록하려면:

```powershell
tools\.venv\Scripts\python.exe tools\youtube_reauth.py
```

기존 JSON 경로나 NAS 주소를 지정하려면:

```powershell
tools\.venv\Scripts\python.exe tools\youtube_reauth.py --client-file json\yt_token.json --nas-url http://192.168.0.10:5080
```

Google Cloud에서 받은 `installed` 형식의 데스크톱 클라이언트 JSON도 `--client-file`로 지정할 수 있습니다.
NAS 등록에 실패해도 결과 JSON은 남으므로 업로드 설정의 **인증 토큰 전체 JSON**에 등록할 수 있습니다.
라이브러리는 OAuth state와 PKCE를 처리하며, 인증 대기는 최대 10분입니다. 토큰·secret은 콘솔에 출력하지 않습니다.

## Python 버전과 달라진 점

- 제외: GPU 하드웨어 인코딩, 분할 녹화(overlap), `timemachine` 플러그인, 다시보기 다운로더, PyQt GUI, 앱 로그인/계정.
  후처리는 스트림 복사와 소프트웨어 재인코딩(libx264/libx265)만 지원합니다.
- 파일 관리자의 `fileManagerEnabled`는 더 이상 `loginMode`에 묶이지 않습니다. 설정에서 켜면 바로 동작합니다.
- 후처리에서 `fixed_` 접두사를 뗄 때 같은 이름이 이미 있으면 덮어쓰지 않고 `fixed_` 이름을 유지합니다.
- 서버가 종료될 때(컨테이너 중지 등) 녹화를 중지하고 후처리가 끝나기를 최대 25초 기다립니다.
