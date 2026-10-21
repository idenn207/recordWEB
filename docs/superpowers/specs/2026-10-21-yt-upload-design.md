# YouTube 자동 업로드 설계

작성일: 2026-10-21 / 상태: 검토 대기

## 범위와 분해

원래 요청은 두 기능이다: (1) X 스페이스 녹음, (2) YouTube 자동 업로드. 서로 독립된 서브시스템이라 사이클을 나눈다.

- **이 문서: YouTube 업로드.** 대상은 Chzzk 녹화본만이다. 기존 NAS 배치 스크립트(`/volume3/docker/yt-upload/upload.py`)를 recordWEB 앱 안으로 옮긴다.
- **다음 사이클: X 스페이스 녹음.** 프로필 등록, 라이브 스페이스 감지, master URL 해석, 녹음을 다룬다. `json/xchannels.json`(`users`에 `@핸들` 10개, `recheckInterval` 120)과 `xcookie.txt`가 이미 있으니 그 설정을 이어받는 방향으로 별도 브레인스토밍을 한다.

## 합의한 요구사항

- 업로드 대상은 Chzzk 녹화본만이다.
- 트리거는 자동과 수동 둘 다 지원한다.
  - 자동: 채널별로 켜고 끈다.
  - 수동: 웹 UI에서 파일을 골라 큐에 넣는다.
- 앱은 NAS의 Docker 컨테이너(`recordweb`)에서 24시간 돌고 있으며, 업로더도 같은 컨테이너 안에서 동작한다.
- 성공 기준: 사람이 `sudo`로 스크립트를 돌리거나 `docker exec`를 쓰지 않아도, 녹화가 끝난 파일이 설정대로 YouTube에 올라가고 상태를 웹에서 볼 수 있다. 앱이 재시작돼도 이어서 올린다.

## 현재 스크립트에서 가져오는 것

| 항목 | 내용 |
|---|---|
| 인증 | `yt_token.json`(refresh_token, client_id, client_secret, token_uri)으로 access token 갱신. `invalid_grant`는 치명 오류로 취급해 업로드 전체를 멈춘다. |
| 업로드 | resumable 세션. 세션 URL을 상태 파일에 저장하고, 재시작하면 서버가 받은 offset을 조회해 이어 올린다. 세션이 404/410이면 처음부터 다시 만든다. |
| 한도 | 세션 생성은 락 하나로 직렬화한다. 429 또는 quota 오류가 나면 전체를 1시간 대기시킨다(실패한 insert도 할당량을 쓰기 때문). |
| 길이 상한 | 12시간(여유 10분 제외 `12h-600s`)을 넘으면 `-c copy`로 N등분하고, 원본은 `_over12h/`로 옮긴다. 제목에는 `(1부)`, `(2부)`가 붙는다. |
| 속도 제한 | 전체 전송 속도를 `rate_mbps`로 제한한다. |
| 상태 | 파일명을 키로 `session`, `video_id`, `privacy`, `playlisted`를 저장한다. 기존 `state.json` 99건과 호환되는 스키마를 유지한다. |

## 결정 사항 (모두 추천안 기준)

1. **구조: 앱 내장 모듈 + 주기 스캔 워커.** 별도 사이드카 컨테이너와 후처리 콜백 방식은 채택하지 않는다.
   - 사이드카는 `/app/json`, `/app/chzzk` 볼륨을 한 번 더 공유하고 UI와 상태를 주고받는 IPC가 필요해서 비용이 크다.
   - 후처리 콜백은 `copyStream`이 최종 경로를 반환하지 않고 `live_recorder.py`가 3천 줄이라 결합도가 높다.
   - 스캔 워커는 앱이 재시작돼도 놓친 파일을 다음 스캔에서 주워 오므로 멱등적이다.
2. **자동 업로드 시작 시점 기준 `auto_since`.** 이 날짜(녹화일, 파일명의 `[YYYY-MM-DD]`) 이후 파일만 자동 대상이다. 기능을 켠 날을 기본값으로 둔다. 9월 26일 이후 밀린 파일은 자동으로 쏟아붓지 않고, 수동 선택으로 원하는 것만 올린다. 지금 스크립트의 `BEFORE` 상수와 같은 역할을 설정값으로 바꾼 것이다.
3. **채널별 설정은 `channels.json`에 둔다.** 새 필드는 `yt_auto_upload`(bool, 기본 false)와 `yt_playlist_id`(문자열, 빈 값이면 재생목록 추가 안 함) 둘뿐이다. 코드에 박힌 스트리머명→재생목록 사전은 이 필드로 이전한다.
4. **전역 설정은 `json/yt_upload.json`에 둔다.** 항목은 `pool`(기본 3), `rate_mbps`(기본 120), `max_sec`, `default_privacy`(기본 `unlisted`), `description`, `tags`, `scan_interval_sec`(기본 300), `auto_since`다. 동시 업로드 수는 원래 10이었지만, 녹화와 같은 NAS 회선과 CPU를 쓰므로 기본값을 낮췄다.
5. **인증은 토큰 파일 방식 그대로.** 앱 안에 OAuth 동의 화면 흐름은 만들지 않는다. 설정 화면에서 `yt_token.json` 내용을 붙여 넣거나 올리면 `/app/json`에 저장한다. 앱이 인증 만료를 감지하면 UI 배너로 알리고 기존 `sendTelegram`으로도 알린다.
6. **파일 선택 규칙.**
   - 확장자가 `.ts` 또는 `.mp4`인 파일이다.
   - 이름이 `_`로 시작하는 폴더(`_over12h`, 휴지통 등)는 건너뛴다.
   - 같은 이름의 `fixed_` 파일과 일반 파일이 둘 다 있으면 `fixed_`만 올린다.
   - 녹화 중이거나 후처리 중인 파일은 제외한다. 기존 `file_manager.busyFilePaths`/`isLocked`를 쓴다.
   - 마지막 수정 후 5분이 지나야(`mtime` 안정) 대상이 된다.
7. **업로드 중인 파일 보호.** 파일 관리자의 삭제, 이름 변경, 이동 API가 업로드 중 파일을 잠금 상태로 취급하도록 `isLocked` 입력에 업로드 중 경로를 합친다.

## 구성 요소

- `module/yt_uploader.py`: 토큰 갱신, resumable 업로드, 분할, 제목 생성. 동기 I/O를 `asyncio.to_thread`로 감싼다. HTTP는 이미 의존성에 있는 `httpx`를 쓴다.
- `module/yt_queue.py`: 상태 파일 관리(`writeJsonSafe`로 원자적 저장과 `.bak` 복구), 스캔 워커, 큐 소비자(`pool` 개), 한도 대기 게이트, 진행률 집계.
- `recordWEB.py`: 앱 시작 시 워커를 띄우고 종료 시 정리한다. 아래 엔드포인트와 화면을 추가한다.
  - `GET /uploads`: 업로드 큐 화면
  - `GET /api/yt/queue`: 큐 상태 조회
  - `POST /api/yt/enqueue`: 수동 큐 추가
  - `POST /api/yt/cancel`: 취소
  - `POST /api/yt/retry`: 재시도
  - `GET`/`POST /api/yt/settings`: 전역 설정과 토큰 저장
- `templates/files.html`: 행 메뉴에 "YouTube 업로드"를 추가하고, 업로드 완료 파일에는 영상 링크 배지를 보여 준다.
- `templates/channels.html` 및 채널 편집 다이얼로그: `yt_auto_upload` 토글과 `yt_playlist_id` 입력.
- `templates/uploads.html`, 설정 화면: `DESIGN.md`와 `PRODUCT.md`의 어두운 테마, 한글 우선, 상태 한눈에 보이기 원칙을 따른다.

## 데이터 흐름

1. 워커가 `scan_interval_sec`마다 채널의 `output_dir`을 훑어 선택 규칙에 맞는 파일 후보를 만든다.
2. 후보 중 해당 채널의 `yt_auto_upload`가 켜져 있고 녹화일이 `auto_since` 이후인 것만 자동으로 큐에 들어간다. 수동 큐 추가는 이 필터를 건너뛴다.
3. 소비자가 파일 하나를 맡아 12시간 초과면 분할하고, 세션 생성, 이어받기 PUT, 재생목록 추가 순으로 진행한다.
4. 모든 단계가 끝나면 상태에 `video_id`와 `playlisted`를 기록한다. 재생목록 추가만 실패한 파일은 다음 사이클에서 재생목록 단계만 다시 한다.

## 오류 처리

- 인증 만료(`invalid_grant`): 큐 전체 중단, UI 배너, 텔레그램 알림. 토큰을 새로 저장하면 재개한다.
- quota 및 429: 1시간 게이트. 큐 화면에 "한도 대기, HH:MM까지"를 표시한다.
- 일시 오류: 30초에서 시작해 최대 30분까지 지수 백오프로 재시도한다.
- 원본 파일이 중간에 사라졌거나 크기가 바뀌었으면 세션을 버리고 다음 스캔에서 다시 판단한다.
- 상태 파일이 깨지면 `.bak`에서 복구한다. 복구해도 이미 올린 영상이 큐에 다시 들어가지 않도록, `video_id`가 없는 항목만 재업로드 대상이 된다.

## 마이그레이션과 배포

- 기존 `/volume3/docker/yt-upload/state.json`(99건 전부 완료)을 `/app/json/yt_upload_state.json`으로 복사해 기존 업로드가 중복되지 않게 한다.
- `yt_token.json`도 같은 방식으로 `/app/json`에 옮긴다. 이 파일은 시크릿이므로 저장소에 넣지 않고, `.gitignore`와 `.dockerignore`에 `json/`이 이미 제외돼 있는지 구현 시 확인한다.
- `docker-compose.yml`의 `json` 볼륨이 이미 `/app/json`에 매핑돼 있어 compose 변경은 필요 없다.
- 기존 `/volume3/docker/yt-upload/`는 백업으로 남겨 두고 더는 실행하지 않는다.

## 테스트

- 단위: 제목 생성(`title_of`, 100자 제한, 분할 접미사), 파일 선택 규칙, `auto_since` 필터, 상태 스키마와 기존 `state.json` 로드.
- 통합: 가짜 resumable 서버로 세션 생성, 308 이어받기, 404 재시작, 429 게이트를 검증한다.
- 수동: 작은 테스트 파일을 `unlisted`로 실제 업로드해 재생목록 추가까지 확인한다.

## 구현 전 확인할 것

- NAS의 실제 `config.json`에서 `removeFixedPrefix`, `moveAfterProcessing`, `deleteAfterPostProcessing` 값을 확인한다. 최종 파일명과 위치가 선택 규칙과 맞는지 판단하는 근거다.
- 현재 YouTube API 프로젝트의 일일 할당량. 기본값이면 영상 몇 개만 올려도 한도에 닿으므로, 이전에 증설했는지가 처리량을 좌우한다.
- OAuth 동의 화면이 "테스트" 상태인지. 테스트 상태면 refresh token이 7일마다 만료된다. 현재 토큰이 9월 26일부터 10월 1일까지 쓰였으므로 게시 상태일 가능성이 높지만 확인이 필요하다.
