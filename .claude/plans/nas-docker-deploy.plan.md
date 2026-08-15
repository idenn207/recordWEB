# Plan: recordWEB NAS Docker 배포 (자동 스트리밍 녹화) — v14

**Source**: 대화형 요청 (free-form, PRD 없음)
**Complexity**: Medium
**Revision**: v1~v7은 앱 레벨 로그인(`loginMode`)을 라우터 전역으로 강제하는 방향으로 다섯 라운드 넘게 반복 수정됐다. v8에서 사용자가 전제를 정정했다 — 개인 로컬 NAS이고 공유기가 WAN 접근을 차단하므로 앱 레벨 로그인을 강제하지 않고 네트워크 경계(LAN IP 게시)만 쓰기로 했다. v8→v9→v10→v11은 "특정 경로로 위험한 값이 켜지는 것을 막는" 패치를 반복했고, 매 라운드 L2 패널이 막지 못한 다른 경로를 찾아냈다: v10에서 `requireLogin`을 상수화(loginMode 자체를 무의미하게 만듦) → v11에서 그 직후 발견된 CRITICAL(파일 관리자 라우트 10개 중 9개가 `fileManagerEnabled`를 아예 확인 안 함)을 `requireFileManagerEnabled` 게이트로 수정 → **곧바로 L2 패널이 그 게이트의 우회로를 발견**: `POST /api/save_config`가 정규화 없이 요청 바디를 그대로 `app.state.config`에 반영해, `fileManagerEnabled`-`loginMode` 커플링(원래 `loadConfig()`에만 있던 규칙)을 건너뛰고 새 게이트를 곧바로 무력화할 수 있었다. **v12는 이 정규화를 `saveConfig()` 자체로 옮겨** `loadConfig()`/`saveConfig()` 어느 경로로 쓰든 동일한 규칙이 적용되게 했다 — 라우트별로 커플링을 개별 구현하는 대신 저장 계층 하나에서 강제한다. 아래 "v12 변경 사항" 참고.

## Summary
`recordWEB.py`(FastAPI 기반 웹 UI + 녹화 엔진)를 Synology NAS(DSM 7.3.2, Container Manager/Docker 24.0.2)에 Docker로 배포해, 로컬 PC 전원 상태와 무관하게 24시간 자동 스트리밍 녹화가 되도록 한다. 배포 설정(compose/Dockerfile/시크릿)은 `volume3`에, 실제 녹화 영상은 `volume1`에 저장한다. 접근 통제는 애플리케이션 로그인이 아니라 **네트워크 경계(포트를 NAS의 LAN IP에만 게시)** 하나로 한다.

## v8 변경 사항 — 앱 레벨 로그인 제거, 네트워크 경계로 전환

- v5에서 추가했던 라우터 전역 강제(`app.router.dependencies.append(Depends(enforceLoginGlobally))`, `_PUBLIC_PATHS`, `enforceLoginGlobally`)를 **제거했다**(recordWEB.py). 이게 v1~v7 전체 소동의 근원이었던 "새 라우트를 빠뜨리면 인증도 빠진다"는 구조 자체를 없앤다.
- 개별 라우트에 남아있는 기존 `Depends(requireLogin)`(40여 곳)은 **건드리지 않았다** — `requireLogin`은 `config.get('loginMode', False)`가 거짓이면 무조건 통과하는 no-op이고(recordWEB.py:380-391), 배포본 `config.json`에서 `loginMode`를 켜지 않는 한 이미 사실상 "로그인 없음" 상태다. 40여 개 라우트 시그니처를 일일이 고치는 건 이번 목표(로그인 안 씀) 대비 불필요하게 스케일이 큰 작업이라 하지 않았다.
- `http_exception_handler`의 401 분기(v7에서 Sec-Fetch-Mode 기반으로 개선)는 도달하지 않는 죽은 경로가 됐지만, 만약을 대비해 302 리다이렉트로 단순화해 남겨뒀다(구 307의 메서드/바디 보존 버그는 여전히 고쳐진 채로 유지). loginMode는 v9에서도 여전히 항상 False이므로 이 분기는 실질적으로 도달하지 않는다.
- v7에서 만든 `tools/verify_auth_coverage.py`(전역 인증 커버리지 증명 스크립트)는 검증 대상 자체가 없어져 **삭제했다**.
- 네트워크 경계를 `127.0.0.1`(loopback, SSH 터널 필요)에서 **NAS의 LAN IP(`192.168.0.10`)에만 게시**로 바꿨다 — 같은 LAN의 어떤 기기에서도 SSH 터널 없이 직접 접근 가능. `0.0.0.0`(전체 공개)은 여전히 쓰지 않는다.

## v9 변경 사항 (패치 시도, v10에서 근본 원인 해결로 대체됨)
v8이 남긴 두 개의 loginMode fail-closed 패치(`loadConfig()`의 손상 시 강제 True, `POST /config`의 필드 부재 시 값 유지)를 되돌렸다. 인용 오류(`recordWEB.py:397-408` → 실제 `380-391`), curl 명령 무효 URL(`NAS_IP`/`NAS_PORT` 변수로 수정), Risk 표의 파일 관리자 노출 서술 정정, LAN IP 고정 여부 확인(Task 4) 추가도 이 라운드에서 반영됐다 — 이 항목들은 v10에서도 유효하게 남아 있다.

## v10 변경 사항 — 패치를 멈추고 근본 원인 제거 (L2 패널이 v9의 패치도 반증)

v9의 되돌리기(config 손상 트리거 제거)로는 부족했다 — L2 패널(4/4 fail)이 **더 직접적인 경로**를 찾았다: `loginMode`는 인증 없는 `POST /config` 폼 필드로 누구나 즉시 켤 수 있고(`recordWEB.py:2376` `"loginMode": toBool(loginMode)`, `saveConfig()`가 계정 존재 여부 확인보다 먼저 실행됨), 켜지는 순간 계정이 없는 상태(Task 5가 `login.json`을 이전하지 않으므로)이므로 v9이 "해소했다"고 주장한 바로 그 두 가지 결과(영구 락아웃, 무가드 `POST /register`를 통한 계정 선점)가 config 손상 없이도 그대로 재현된다.

**[HIGH, 근본 원인 해결]** `loginMode`가 "외부에서 값을 바꿀 수 있는 신뢰 경계"라는 구조 자체가 문제였다 — 이 값에 이르는 경로를 하나씩 막는 patch-whack-a-mole은 v6→v7→v8→v9에서 반복해서 실패했다. `requireLogin`(recordWEB.py:380-391 부근)을 **`config.get('loginMode', ...)`를 아예 읽지 않고 무조건 `True`를 반환**하도록 바꿨다. 이제 `loginMode`가 파일에서 어떤 값을 갖든, `POST /config`로 무엇을 켜든 인증 동작에 아무 영향이 없다 — `config.html`의 로그인 모드 토글은 저장은 되지만 효과가 없는 죽은 UI가 된다(의도된 트레이드오프: 토글 UI를 지우는 것도 가능하지만 이번 스코프를 더 키우지 않기 위해 남겨뒀다). 로컬에서 `loginMode: True`로 세팅한 가짜 요청으로 `requireLogin`이 여전히 `True`를 반환하는지 직접 실행해 확인했다.

이 변경으로 v6~v9에서 반복됐던 "loginMode가 어떻게든 True가 되면"류의 위협 전체가 전제부터 성립하지 않게 됐다 — 더 이상 그 값을 읽는 코드가 없다. (단, `loginMode`는 여전히 파일에 남고 `/`, `/register` 등 UI 분기와 `fileManagerEnabled` 계산에는 쓰인다 — "인증 동작"에만 영향이 없다는 뜻이었고, v11 findings가 정확히 그 `fileManagerEnabled` 연결 지점에서 다른 문제를 찾았다.)

## v11 변경 사항 — 파일 관리자가 애초에 fileManagerEnabled를 검사하지 않던 CRITICAL 수정

architect/security 두 리뷰어가 독립적으로 같은 결함에 도달했다: Risk 표가 "`loginMode:False`면 `fileManagerEnabled`가 항상 False로 강제되므로 파일 관리자는 노출 범위에서 제외"라고 적었는데, 이건 **`fileManagerEnabled` 값이 무엇이든 애초에 그 값을 확인하는 라우트가 `/api/files/roots` 하나뿐이었기 때문에** 틀린 완화였다. `/api/files/usage`, `/list`, `/ls`, `/disk-usage`, `/download`, `/mkdir`, `/rename`, `/move`, `/delete`, `/streamcopy` — 파일을 실제로 읽고 쓰고 지우는 라우트 전부가 `Depends(requireLogin)`만 거쳤고, v10에서 그게 상수 `True`가 되면서 사실상 항상 열려 있었다. 기본 `fileManagerMode`가 `"blacklist"`라 `buildAllowedRoots`가 `["*"]`(전체 허용)를 반환하고 Linux 시스템 경로 블랙리스트에는 `/app`, `/volume1`, `/volume3`가 없어서, LAN의 아무 기기나 `GET /api/files/download?path=/app/json/login.json`으로 시크릿을 읽거나 `POST /api/files/delete`로 **UI5 성공 지표인 녹화 영상 전체를 삭제**할 수 있었다(CRITICAL — 데이터 손실).

**수정**: `recordWEB.py`에 `requireFileManagerEnabled` 의존성을 새로 만들어(`request.app.state.config.get("fileManagerEnabled", False)`가 거짓이면 403) 위 10개 라우트 전부에 `Depends(requireLogin)`과 나란히 추가했다. 기본 설정에서 `fileManagerEnabled`는 `False`이므로(module/data_manager.py 기본값, 이번 배포도 별도로 켜지 않음) 이 배포에서는 파일 관리자 라우트 전체가 기본적으로 닫힌다. `fileManagerEnabled`는 여전히 `POST /config`로 켤 수 있지만(UI7이 이미 받아들인 "같은 LAN은 신뢰 경계" 트레이드오프 안에 있음), 로컬에서 `fileManagerEnabled=False`/`True` 양쪽을 흉내낸 요청으로 403/통과가 실제로 갈리는지 직접 실행해 확인했다.

## v12 변경 사항 — saveConfig()에 정규화 강제 (v11 게이트의 우회로 차단)

L2 패널(architect는 pass, security/test/invariant fail)이 v11의 `requireFileManagerEnabled` 게이트 자체는 올바르게 배선됐음을 확인했지만(10개 라우트 전부에 실제로 붙어 있음), 그 게이트가 읽는 `app.state.config`를 **정규화 없이 직접 갱신하는 두 번째 쓰기 경로**를 찾아냈다: `POST /api/save_config`(및 `/api/save_youtube_po_token`)는 `saveConfig(body)`를 호출하는데, 기존 `saveConfig()`는 디스크의 기존 값과 요청 바디를 `{**disk, **data}`로 그대로 병합해 썼다 — `loadConfig()`에만 있던 "`loginMode`가 꺼져 있으면 `fileManagerEnabled`도 강제로 꺼짐" 같은 정규화 규칙이 전혀 적용되지 않았다. 즉 `POST /api/save_config {"loginMode": true, "fileManagerEnabled": true}` 한 번으로 v11의 게이트를 곧바로 열 수 있었다(**CRITICAL** 재현).

**수정**: `module/data_manager.py`에서 `loadConfig()`의 정규화 로직(기본값 병합, 타입 보정, `fileManagerEnabled`↔`loginMode` 커플링 등)을 `_normalizeConfig(data)`라는 공용 함수로 뽑아냈다. `loadConfig()`는 이제 `_normalizeConfig(readJsonSafe(...))`를 호출하는 얇은 래퍼이고, `saveConfig(data)`도 디스크값과 병합한 뒤 **저장 직전에 같은 `_normalizeConfig()`를 통과**시킨다. 이제 config를 쓰는 경로가 몇 개든(`/config`, `/api/save_config`, `/api/save_youtube_po_token`, 앞으로 추가될 라우트) 정규화 규칙이 한 곳(저장 계층)에서 강제된다 — v11까지처럼 라우트마다 커플링을 개별 구현하거나 빠뜨릴 걱정이 없다. 로컬에서 `saveConfig({"fileManagerEnabled": True})`(loginMode 없이)를 직접 호출해 결과가 `False`로 강제되는지 확인했다.

**주의(정직하게 남겨두는 잔여 위험)**: 이 정규화는 "한 필드만 몰래 켜는" 우회를 막을 뿐, `POST /api/save_config`가 `{"loginMode": true, "fileManagerEnabled": true}`를 **함께** 보내는 것 자체는 막지 않는다 — `loginMode`도 이 배포에서는 인증적 의미가 없는 값이라(v10) 그 자체가 진짜 방어선이 아니다. 이 배포의 실제 방어선은 애초부터 애플리케이션 레벨이 아니라 네트워크 경계(LAN IP 게시, UI7)이며, `fileManagerEnabled`는 "기본값은 닫혀 있고, LAN 내부에서 의도적으로 켤 수 있다"는 정도의 보호만 제공한다는 걸 Risk 표에 명확히 했다.

## v13 변경 사항 — POST /config가 saveConfig()의 정규화된 반환값을 버리던 HIGH 수정

v12까지 저장 계층(`_normalizeConfig`)에 정규화를 몰아넣었지만, L2 패널(architect/test fail, security는 pass하되 관련 finding 제출)이 그 강제가 **in-memory 상태(`app.state.config`, 게이트가 실제로 읽는 값)까지는 미치지 않는 경로**를 찾아냈다: `POST /config` 핸들러(recordWEB.py:2422 부근)가 `saveConfig(new_config)`는 호출하면서도 그 반환값(정규화됨)을 버리고, 자신이 폼에서 직접 만든 `new_config`(비정규화 raw dict)를 그대로 `request.app.state.config`에 대입하고 있었다. 지금 당장 뚫리지 않은 건 이 라우트가 `effective_fm_enabled = toBool(loginMode) and toBool(fileManagerEnabled)`(recordWEB.py:2232 부근)라는 **커플링을 자체적으로 한 번 더 구현**해뒀기 때문이었는데, 이는 정확히 v12가 "없앴다"고 주장한 "라우트마다 커플링을 개별 구현"하는 패턴이 여전히 남아 있다는 뜻이었다 — 그 중복 구현이 나중에 어긋나거나(예: 새 필드 추가 시 한쪽만 갱신) `saveConfig()`가 디스크 쓰기 실패로 예외 경로를 타 비정규화 원본을 반환하면, 어떤 경고도 없이 다시 CRITICAL이 재현될 수 있었다.

**수정**: `request.app.state.config = new_config`를 `request.app.state.config = saveConfig(new_config)`로 바꿔 `POST /config`도 `POST /api/save_config`(이미 반환값을 쓰고 있었음)와 동일하게 `saveConfig()`가 실제로 반환한 정규화 결과를 상태에 반영하도록 했다. 이제 정규화 지점은 이름 그대로 하나이며, 어느 라우트도 개별적으로 커플링을 다시 구현할 필요가 없다.

**세션 예산 소진 — 이 수정은 자동 L2 재검증을 받지 못했다(v13 당시).** 다음 세션에서 v13을 그대로 L2 패널에 올렸고(4/4 fail, invariant **CRITICAL**), 아래 "v14 변경 사항"에서 그 CRITICAL을 닫았다.

## v14 변경 사항 — saveConfig() 예외 경로가 비정규화 원본을 반환하던 CRITICAL 수정

v13을 L2 패널(architect/security/test/invariant 4개 독립 에이전트)에 올렸더니 **4/4 fail**, invariant 리뷰어는 **CRITICAL**로 판정했다: `saveConfig()`(module/data_manager.py:895-912)는 `_normalizeConfig()`를 `try` 블록 **안에서** 호출하고 있었고, `writeJsonSafe()`가 디스크 쓰기 실패로 예외를 던지면 `except` 분기가 **정규화를 거치지 않은 raw `data`를 그대로 반환**했다. v13이 `POST /config`를 `request.app.state.config = saveConfig(new_config)`로 고쳐 반환값을 신뢰하게 만든 게 바로 이 반환값이었으므로, `/volume3` 바인드 마운트가 read-only이거나 디스크가 가득 차는 등 쓰기 실패가 발생하는 순간, 인증 없는 `POST /api/save_config {"fileManagerEnabled": true}` 한 번으로 v11/v12가 막으려던 CRITICAL(파일 관리자 무인증 노출)이 그대로 재현됐다 — architect/security/test 세 리뷰어가 독립적으로 같은 결함을 지적했다.

**수정**: `_normalizeConfig({**disk, **(data or {})})` 호출을 `try` 블록 **밖으로** 옮겼다. 이제 디스크 쓰기가 성공하든 실패하든 `saveConfig()`는 항상 정규화된 `merged` 값을 반환한다(`readJsonSafe()`는 이미 내부적으로 예외를 삼키므로 밖으로 옮겨도 안전). 쓰기 실패는 여전히 로그만 남기고 넘어가지만(v13까지의 fail-open 정책 유지, UI7 "네트워크 경계만 쓴다" 트레이드오프와 일관), in-memory 상태(`app.state.config`, 게이트가 실제로 읽는 값)는 디스크 쓰기 성공 여부와 무관하게 항상 `fileManagerEnabled`↔`loginMode` 커플링이 적용된 값이 된다. 부수 효과로 invariant 리뷰어가 지적한 두 번째 문제(쓰기 실패 시 요청 바디의 posted 키만 살아남고 나머지 config 키가 사라지던 것)도 함께 해소됐다 — 이제 실패 시에도 `merged`(디스크 값 + posted 값의 병합·정규화 결과)가 반환된다.

## 게이트 상태 (v14, 2026-08-14)
v6 자동 리뷰 미완료 → v7 L1+L2 divergent(HIGH 4건) → v8(로그인 제거 지시, v7 패치 오판) L2 4/4 fail → v9(패치 원복) L2 4/4 fail(직접 토글 경로) → v10(근본 원인 제거: requireLogin 상수화) L2 4/4 fail(**CRITICAL**: 파일 관리자 무방비) → v11(requireFileManagerEnabled 추가) L2 fail(**CRITICAL**: saveConfig 우회) → v12(saveConfig 정규화 강제) L2 fail(**HIGH**: POST /config가 정규화된 반환값을 안 씀) → v13(반환값 사용으로 수정) L2 4/4 fail(**CRITICAL**: saveConfig 예외 경로가 비정규화 원본 반환) → v14(정규화를 try 밖으로 이동). 전체 findings는 `.claude/reviews/plan-review-nas-docker-deploy.md`에 누적 기록. v14은 아직 자동 L2 재검증 전이다.

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Docker 배포 위치 | `/volume3/docker/terab/` (기존 서비스) | `/volume3/docker/<project>/`에 compose+env+secrets 배치 |
| 데이터 볼륨 | `/volume1/storage/terab-files/` | `/volume1/storage/<project>-files/`에 대용량 데이터 저장 |
| 진입점 | `recordWEB.py` 함수 `runUvicorn`(uvicorn 설정) / `if __name__=="__main__"` 블록(실행 트리거) | `uvicorn.Config(app, host="0.0.0.0", port=port)` — 컨테이너 내부는 그대로 0.0.0.0, 외부 노출은 compose 포트 매핑에서 LAN IP로 제한 |
| 계정 부재 감지 | `module/data_manager.py` `loadAccount()` | 이번 배포에서는 사용하지 않음(로그인 미사용) — 참고용으로만 유지 |
| 민감정보 제외 | `.gitignore` (이전 세션에 작성) | `json/` 전체가 시크릿/개인 상태 — 이미지에 굽지 않고 볼륨 마운트 |

## User Intent (참고 — free-form 대화 원문)
| ID | Constraint (user-stated) | Kind |
|---|---|---|
| UI1 | Docker 배포 설정/구성 파일은 volume3 사용 | constraint |
| UI2 | 영상 저장 경로는 volume1 사용 | constraint |
| UI3 | 폴더 명칭은 NAS에서 직접 확인한 기존 패턴을 따를 것 | direction |
| UI4 | 설정 가능한 GUI 지원 희망 | direction |
| UI5 | 측정 가능한 성공 지표 = 치지직 "아카네 리제" 스트리밍이 실제로 녹화된 파일로 확인되는 것 | constraint |
| UI6 | (v6 이전) 리뷰 게이트가 CRITICAL/HIGH를 이유로 4라운드 연속 차단한 뒤, 사용자가 "claude 판단으로 진행해줘"라고 위임 | direction |
| UI7 | (v8) 외부에 공유하지 않는 개인 로컬 NAS이고 공유기가 WAN 접근을 차단하므로, 앱 레벨 로그인을 만들지 말 것 — 네트워크 경계(IP 제한)만으로 충분 | constraint |
| UI8 | (v8) 포트는 loopback이 아니라 NAS의 LAN IP(192.168.0.10)에만 게시 — 다른 LAN 기기에서 SSH 터널 없이 직접 접근 가능해야 함 | constraint |
| UI9 | (v8) "굳이 스케일이 늘어나는 작업을 할 필요는 없을 것 같아" — 40여 개 라우트의 `Depends(requireLogin)` 시그니처를 일일이 제거하는 등 불필요하게 큰 리팩터링은 하지 말 것 | direction |

## 라운드별 지적과 대응 요약 (v1~v7, 참고용 — v8에서 인증 자체를 제거하며 대부분 무의미해짐)
| 라운드 | 핵심 지적 | 조치 |
|---|---|---|
| v12 (L2 패널) | HIGH: `POST /config`가 `saveConfig()`의 정규화된 반환값을 버리고 raw dict를 `app.state.config`에 직접 대입 — 저장 계층 강제가 in-memory 상태에 안 미침 | **v13: 반환값 사용으로 수정(세션 예산 소진으로 자동 재검증 미완료)** |
| v11 (L2 패널) | **CRITICAL**: `POST /api/save_config`가 정규화 없이 body를 그대로 `app.state.config`에 반영해 v11 게이트를 한 번의 호출로 우회 가능 | v12: 정규화를 `saveConfig()` 자체로 이동, 모든 쓰기 경로에 강제 |
| v10 (L2 패널, 4/4 fail) | **CRITICAL**: 파일 관리자 라우트 10개 중 9개가 애초에 `fileManagerEnabled`를 확인한 적 없음 — `requireLogin`이 상수화되면서 무인증으로 임의 파일 읽기/삭제(녹화본 전량 삭제 포함) 가능 | v11: `requireFileManagerEnabled` 의존성 신설, 해당 라우트 전부에 추가 (→ v12에서 우회로 추가 차단) |
| v9 (L2 패널, 4/4 fail) | HIGH: config 손상 트리거를 없애도, 무인증 `POST /config`로 loginMode를 직접 켤 수 있는 더 직접적인 경로가 남아 있어 동일한 락아웃/계정탈취가 재현됨 | v10: patch-whack-a-mole을 멈추고 `requireLogin`이 loginMode를 아예 읽지 않도록 근본 수정 |
| v8 (L2 패널, 4/4 fail) | HIGH: v7의 loginMode fail-closed 패치가 "login.json 미이전" 결정과 결합해 영구 락아웃/무인증 계정 탈취를 만듦 | v9: 두 패치 모두 원복(loadConfig, POST /config) — 이후 v10에서 더 근본적으로 해결됨 |
| v8 (L2 패널) | MEDIUM: Risk 표가 "파일 관리 포함 전체 노출"이라 서술했으나 loginMode:False면 fileManagerEnabled도 항상 False | v9: Risk 서술 정정, `/cookies` 평문 노출을 별도 행으로 분리 |
| v8 (L2 패널) | MEDIUM: LAN IP(192.168.0.10) 고정 여부 미확인 — DHCP면 재부팅 시 배포가 깨짐 | v9: Task 4에 고정 IP 확인 추가 |
| v8 (L2 패널) | MEDIUM: Validation의 curl 대상이 무효한 URL 프로즈였음 | v9: `NAS_IP`/`NAS_PORT` 셸 변수로 수정 |
| v8 (L2 패널) | LOW: `requireLogin` 인용 라인 오류(397-408 vs 실제 380-391) | v9: 정정 |
| v7 → v8 | (사용자 지시) 개인 로컬 NAS이므로 앱 레벨 로그인 자체가 불필요 | 라우터 전역 강제 제거, 네트워크 경계(LAN IP 게시)로 전환 |
| v6 (L2 패널, 4/4 응답 중 3 fail) | HIGH: 401 리다이렉트가 307이라 POST/PUT/DELETE 메서드·바디 보존됨 | v7에서 수정, v9에서도 유지(도달하지 않지만 무해) |
| v6 (L2 패널) | HIGH: 인증 커버리지 주장이 실행 가능한 검증 없이 grep에만 의존 | v7에서 검증 스크립트 작성 → v8에서 대상 소멸로 삭제 |
| v6 (L2 패널) | HIGH: config.json 손상 시 인증 게이트 전체 fail-open | v7에서 수정 → v9에서 원복(무해가 아니었음, 위 참고) |
| v6 (L2 패널) | HIGH: `POST /config`가 필드 부재 시 loginMode를 조용히 끔 | v7에서 수정 → v9에서 원복(무해가 아니었음, 위 참고) |
| v1~v5 | 무인증 라우트가 라운드마다 새로 발견됨 → 결국 라우터 전역 강제로 구조 전환 | v8에서 "인증 자체를 안 씀"으로 문제가 소멸 |
| v3 | MEDIUM: deno COPY 대상 PATH 미명시, PID 1 zombie reap 부재 | Dockerfile에서 `/usr/local/bin/deno`로 명시 COPY, compose에 `init: true` |
| v1 | HIGH: `getDeno()` 무가드 호출로 프로세스 전체 종료 위험 | `denoland/deno` 이미지에서 바이너리 상시 포함 |
| v1/v2 | HIGH: `install_missing_modules()` 매 기동 네트워크 pip install | requirements.txt를 실제 목록과 1:1 일치 |
| v1 | MEDIUM: `dependent/plugin` 오제외 위험, 성공 지표가 파일명 패턴 의존, rollback/로컬중지 단계 부재 | `.dockerignore`에서 명시적 keep, mtime 기반 검증으로 보강 |

## Design Decisions
- 별도 GUI를 새로 만들지 않고 `recordWEB.py`의 기존 웹 UI를 그대로 컨테이너로 노출한다.
- **인증 없음**: 앱 레벨 로그인을 강제하지 않는다(UI7). 개별 라우트의 기존 `Depends(requireLogin)`은 `loginMode`가 꺼져 있으면 no-op이므로 그대로 두되, 라우터 전역 강제(v5에서 추가)는 제거했다.
- **네트워크 경계(유일한 접근 통제)**: `docker-compose.yml`의 포트 게시를 NAS의 LAN IP `192.168.0.10`의 5000번 포트로 고정한다(host `192.168.0.10`, container `5000`, `0.0.0.0` 아님). 같은 LAN의 다른 기기는 `http://192.168.0.10 (포트 5000)`으로 SSH 터널 없이 직접 접근 가능. 라우터/방화벽이 WAN→LAN 접근을 차단한다는 전제(UI7)에 의존한다.
- `json/` 전체는 이미지에 포함하지 않고 `/volume3/docker/recordweb/json`에 바인드 마운트한다.
- 녹화 출력은 `channels.json`의 기존 `output_dir: "chzzk"`를 그대로 두고, 컨테이너 내부 `/app/chzzk`에 `/volume1/storage/recordweb-files/chzzk`를 바인드 마운트한다.
- `dependent/aria2c`, `dependent/bgutil-pot`, `dependent/ffmpeg`, `dependent/streamlink`, `dependent/ytarchive`, `dependent/yt-dlp`(Windows PE 바이너리)는 이미지에 포함하지 않고, Linux 네이티브 ffmpeg/aria2(apt)·streamlink/yt-dlp(pip)로 대체한다. `dependent/plugin`, `dependent/img`는 유지한다.
- deno는 `denoland/deno` 공식 이미지에서 바이너리만 `/usr/local/bin/deno`로 멀티스테이지 복사한다.
- Docker Swarm이 아니라 단일 호스트 `docker compose`로 배포한다.

## Files to Change
| File | Action | Why |
|---|---|---|
| `recordWEB.py` | **UPDATE (이미 적용됨, v8+v9+v10+v11+v13)** | (v8) 라우터 전역 인증 강제 제거, 401 예외 핸들러는 단순화한 302 리다이렉트로 유지(도달 안 함). (v9) `POST /config`의 loginMode 필드-부재-시-현재값-유지 패치를 원복. (v10) `requireLogin`이 `config.get('loginMode', ...)`를 아예 읽지 않고 무조건 `True`를 반환하도록 변경. (v11) `requireFileManagerEnabled` 의존성 신설, `/api/files/*` 10개 라우트에 추가. **(v13) `POST /config`가 `saveConfig()` 반환값을 쓰도록 수정 — 세션 예산 소진으로 자동 재검증 미완료** |
| `module/data_manager.py` | **UPDATE (이미 적용됨, v9+v12)** | (v9) `loadConfig()`의 config.json 손상 시 loginMode를 True로 강제하던 v7 fail-closed 패치를 되돌림. **(v12)** `loadConfig()`의 정규화 로직을 `_normalizeConfig()` 공용 함수로 분리해 `saveConfig()`도 저장 전 동일하게 통과하도록 변경 — `POST /api/save_config` 등 saveConfig를 직접 호출하는 경로가 정규화를 우회하지 못하게 함 |
| `requirements.txt` | CREATE | `install_missing_modules()` 목록과 정확히 일치(fastapi, uvicorn, aiohttp, jinja2, werkzeug, itsdangerous, python-multipart, starlette, psutil, cryptography, requests, httpx, pystray, pillow, py-cpuinfo) + streamlink, yt-dlp |
| `Dockerfile` | CREATE | `python:3.11-slim`, `apt-get install -y ffmpeg aria2`, `denoland/deno` 이미지에서 바이너리를 `/usr/local/bin/deno`로 COPY, `pip install -r requirements.txt`, `WORKDIR /app`, `EXPOSE 5000`, `CMD ["python","recordWEB.py"]` |
| `.dockerignore` | CREATE | `chzzk/`, `dependent/{aria2c,bgutil-pot,ffmpeg,streamlink,ytarchive,yt-dlp}/`, `json/`, `.git`, `__pycache__` 제외. `dependent/plugin/`, `dependent/img/`는 keep |
| `docker-compose.yml` | CREATE | 이미지 빌드/실행, `json`·`chzzk` 바인드 마운트, **192.168.0.10의 5000번 포트로 게시(host 192.168.0.10, container 5000)**, `restart: unless-stopped`, `init: true`(PID 1 zombie reap) |
| `json/config.json` | UPDATE(배포시, 배포본에만 적용·git에는 미반영) | `enableTray:false`, `minimizeToTray*:false`, `port:5000` (`loginMode`는 기본값 False 그대로 — 명시적으로 켜지 않음) |
| (NAS) `/volume3/docker/recordweb/` | CREATE | compose 스택 배치 위치 |
| (NAS) `/volume1/storage/recordweb-files/chzzk` | CREATE | 녹화 영상 저장 위치 |

## Tasks

### Task 0: 앱 레벨 인증을 구조적으로 무력화 (완료)
- **Action**: (a, v8) 라우터 전역 강제(`app.router.dependencies.append(Depends(enforceLoginGlobally))` 및 관련 `_PUBLIC_PATHS`/`enforceLoginGlobally`)를 제거. (b, v9) `module/data_manager.py`의 `loadConfig()` fail-closed 패치와 `recordWEB.py`의 `POST /config` loginMode-보존 패치를 원복. (c, v10, 근본 수정) `requireLogin`이 `loginMode` 값을 아예 읽지 않고 무조건 `True`를 반환하도록 변경. (d, v11) 신설한 `requireFileManagerEnabled` 의존성을 `/api/files/{usage,list,ls,disk-usage,download,mkdir,rename,move,delete,streamcopy}` 10개 라우트에 `Depends(requireLogin)`과 나란히 추가 — `fileManagerEnabled=False`(기본값)면 403. (e, v12) `module/data_manager.py`의 `loadConfig()` 정규화 로직을 `_normalizeConfig()`로 분리해 `saveConfig()`도 저장 전 동일하게 통과하도록 변경. **(f, v13)** `POST /config`가 `saveConfig()`의 반환값을 버리고 raw `new_config`를 `app.state.config`에 직접 대입하던 것을 반환값 사용으로 수정 — (e)의 저장 계층 강제가 in-memory 상태에도 실제로 적용되게 함
- **Validate**: (실행됨, 결과 확인 완료)
  ```bash
  # (a) 전역 강제가 제거됐는지 확인
  grep -n "app.router.dependencies.append\|enforceLoginGlobally" recordWEB.py
  # → 아무 결과도 없어야 함(주석 텍스트 제외)

  # (c, v10) loginMode를 True로 세팅한 가짜 요청에도 requireLogin이 True를
  # 반환하는지 직접 실행 — "loginMode가 어떻게든 True가 되면"류의 위협 전체가
  # 더 이상 성립하지 않음을 증명 (config 손상, 무인증 POST /config 토글 등
  # loginMode에 이르는 경로가 몇 개든 상관없음)
  python -c "
import asyncio, recordWEB as rw
class FakeApp:
    class state: config = {'loginMode': True}
class FakeReq:
    app = FakeApp()
    session = {}
result = asyncio.run(rw.requireLogin(FakeReq()))
assert result is True, f'FAIL: loginMode=True인데도 requireLogin이 {result} 반환'
print('OK: loginMode 값과 무관하게 requireLogin은 항상 True')
"

  # (d, v11) 파일 관리자 라우트가 fileManagerEnabled를 실제로 확인하는지 검증 —
  # False면 403, True면 통과. 10개 라우트 각각을 실행하는 대신 공유 의존성
  # 함수 자체를 검증(모든 라우트가 이 동일 함수를 Depends로 쓰므로 충분)
  python -c "
import asyncio, recordWEB as rw
from fastapi import HTTPException
class FakeApp:
    class state: config = {'fileManagerEnabled': False}
class FakeReq:
    app = FakeApp()
try:
    asyncio.run(rw.requireFileManagerEnabled(FakeReq()))
    raise SystemExit('FAIL: fileManagerEnabled=False인데 403이 발생하지 않음')
except HTTPException as e:
    assert e.status_code == 403
FakeApp.state.config = {'fileManagerEnabled': True}
assert asyncio.run(rw.requireFileManagerEnabled(FakeReq())) is True
print('OK: fileManagerEnabled=False→403, True→통과')
"

  # (e, v12) saveConfig()가 정규화를 거치는지 확인 — fileManagerEnabled만
  # 단독으로 저장 요청해도 loginMode와의 커플링 때문에 False로 강제되는지
  # 직접 실행 (POST /api/save_config 같은 saveConfig 직접 호출 경로가
  # 정규화를 우회하지 못함을 증명)
  python -c "
import module.data_manager as dm, tempfile, os
tmp = tempfile.mkdtemp(); p = os.path.join(tmp, 'config.json')
dm.CONFIG_PATH = p
result = dm.saveConfig({'fileManagerEnabled': True})
assert result['fileManagerEnabled'] is False, f'FAIL: 정규화 우회됨 — {result[\"fileManagerEnabled\"]}'
print('OK: saveConfig가 정규화를 거쳐 fileManagerEnabled를 loginMode와 커플링함')
"

  # import 시점 확인. 주의: import는 부작용이 없지 않다 — loadAccount()가
  # secret_key 없으면 새로 생성해 json/login.json에 쓴다(recordWEB.py:332-339,
  # 이 플랜과 무관한 SessionMiddleware용 기존 동작). 로컬 개발 json/ 디렉터리에서
  # 실행하면 그 파일이 생성/갱신될 수 있음을 인지하고 실행한다.
  python -c "import recordWEB"
  ```

### Task 1: requirements.txt 작성
- **Action**: `install_missing_modules()` 목록(pystray/pillow/py-cpuinfo 포함)과 1:1 일치 + streamlink, yt-dlp 추가
- **Validate**: `docker compose up` 최초 기동 로그에서 `모든 필수 모듈이 이미 설치되어 있습니다` 메시지 확인(build 시점이 아니라 CMD 실행 시점에 출력되므로 `up`/`run` 로그를 봐야 함)

### Task 2: Dockerfile / .dockerignore 작성
- **Action**: ffmpeg/aria2(apt) + deno(멀티스테이지 COPY, `/usr/local/bin/deno`) + Python 의존성 설치
- **Validate**: `docker build -t recordweb .` 성공, `docker run --rm recordweb sh -c "ffmpeg -version && streamlink --version && yt-dlp --version && deno --version"`

### Task 3: docker-compose.yml 작성 — 포트를 NAS의 LAN IP에만 게시
- **Action**: `json`/`chzzk` 바인드 마운트, **192.168.0.10의 5000번 포트로 게시(host 192.168.0.10, container 5000)**(0.0.0.0 아님), `restart: unless-stopped`, `init: true`
- **Validate**: `docker compose config`로 문법 확인, 기동 후 같은 LAN의 다른 기기에서 `NAS_IP=192.168.0.10; curl http://$NAS_IP:5000`이 응답하고, 공유기 밖(WAN)에서는 도달 불가함을 확인(라우터 포트포워딩이 걸려 있지 않은지 사전 확인)

### Task 4: NAS 배포 디렉터리 준비 (sudo 필요, 1회성) + LAN IP 고정 확인
- **Action**: `/volume3/docker/recordweb/` 생성 후 리포지토리 clone, `/volume1/storage/recordweb-files/chzzk` 생성. **(v9 추가)** `192.168.0.10`이 NAS에 정적으로 할당돼 있는지, 또는 공유기에서 이 NAS의 MAC 주소로 DHCP 예약이 걸려 있는지 확인 — 유동 할당이면 재부팅 시 IP가 바뀌어 compose 포트 바인딩이 실패하고 24시간 자동 녹화가 조용히 끊길 수 있다
- **Validate**: `ls -la` 로 두 경로 존재 및 권한 확인(0700, claude 소유). DSM 제어판(네트워크 인터페이스 설정) 또는 공유기 관리 화면에서 `192.168.0.10`이 이 NAS에 고정/예약돼 있음을 확인

### Task 5: 로컬 설정 백업 및 NAS 이전
- **Action**: 로컬 `json/` 전체를 우선 로컬 백업 후, `config.json`(트레이/포트 조정), `channels.json`, `cookie.json`을 `/volume3/docker/recordweb/json/`으로 scp 이전. `login.json`은 로그인 미사용이므로 이전하지 않아도 됨(SessionMiddleware용 secret_key는 최초 기동 시 자동 생성됨)
- **Validate**: NAS `ls json/`로 파일 확인

### Task 6: 로컬 인스턴스 중지 → 이미지 빌드 및 기동
- **Action**: (a) 로컬 PC의 recordWEB 프로세스 종료(이중 녹화 방지) → (b) NAS에서 `sudo docker compose build && sudo docker compose up -d` → (c) 같은 LAN의 브라우저에서 `192.168.0.10`의 5000번 포트로 바로 접속해 웹 UI 확인
- **Validate**: `docker compose ps`, `docker compose logs -f`로 정상 기동 확인. `config.json`의 실제 `port` 값과 compose 포트 매핑 일치 확인. 공유기 밖(모바일 데이터 등 WAN)에서 접근 시도 시 도달 불가함을 확인

### Task 7: 성공 지표 검증 — "아카네 리제" 녹화 확인
- **Action**: `channels.json`에 `아카네 리제`(chzzk, `record_enabled:true`) 등록 확인 → 방송 시작 대기/즉시 확인 → `/volume1/storage/recordweb-files/chzzk/`에 새 파일 생성 확인
- **Validate**: 파일명 grep은 보조 수단으로만 사용하고, 주 검증은 `ls -la --time-style=full-iso /volume1/storage/recordweb-files/chzzk/ | sort` 를 수 분 간격으로 재실행해 대상 파일의 mtime과 크기가 계속 증가하는지 확인. LAN 브라우저로 웹 UI `/recording`에서도 "REC" 상태 확인

## Validation
```bash
# 로컬 — 전역 인증 강제 제거 + loginMode fail-closed 원복 확인 (v9)
grep -n "app.router.dependencies.append\|enforceLoginGlobally" recordWEB.py
python -c "import recordWEB"

# NAS (sudo 필요)
NAS_IP=192.168.0.10
NAS_PORT=5000
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f recordweb   # "모든 필수 모듈이 이미 설치되어 있습니다" 확인
curl -s -o /dev/null -w "%{http_code}\n" "http://$NAS_IP:$NAS_PORT/"
ls -la /volume1/storage/recordweb-files/chzzk/
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Docker 소켓 권한(claude 계정 미가입) | 낮음 (sudo 확인 완료) | `sudo docker compose ...` |
| ffmpeg/streamlink/yt-dlp Linux 빌드가 Windows용과 옵션/성능 차이 | 중간 | Task 7 검증으로 확인, 이상 시 `extra_ffmpeg_options` 조정 |
| **앱 레벨 인증이 없으므로 같은 LAN에 있는 누구나(다른 사람의 기기, IoT 기기 침해 등) 녹화 제어·채널 관리·설정 변경에 무제한 접근 가능. 파일 관리자(`/api/files/*`)는 기본값(`fileManagerEnabled:False`)에서는 닫혀 있지만, LAN의 아무 기기나 `POST /config` 또는 `POST /api/save_config`로 의도적으로 켤 수 있다 — "기본은 닫힘, 켜는 것도 무인증"이며 다른 설정 변경과 동일한 LAN 신뢰 경계 안에 있다는 뜻이지 "구조적으로 열 수 없다"는 뜻이 아니다** (v11: 파일 관리자 라우트들이 애초에 이 플래그를 확인하지 않던 CRITICAL 수정. v12: 그 게이트를 우회하던 `saveConfig()` 미정규화 CRITICAL 추가 수정 — 자세한 내용은 "v11/v12 변경 사항") | 낮음(가정 — 개인 로컬망, 신뢰 기기만 존재) | 사용자가 명시적으로 선택한 트레이드오프(UI7). LAN 자체가 신뢰 경계라는 전제. 신뢰할 수 없는 기기가 LAN에 들어올 가능성이 생기면(방문객 Wi-Fi 공유 등) 재검토 필요 |
| **`GET /cookies`가 치지직/유튜브 세션 쿠키를 평문으로 반환하며 이것도 무인증 대상이다 — LAN의 아무 기기나 계정 쿠키를 탈취 가능** (v9: security 리뷰어 지적으로 별도 행 분리) | 낮음(가정 동일) | 위와 같은 트레이드오프. 쿠키 탈취 시 스트리밍 플랫폼 계정 세션이 도용될 수 있음을 인지 |
| 공유기 설정이 바뀌어 포트포워딩/UPnP로 5000번이 실수로 WAN에 노출되면 인증 없이 전체 기능이 인터넷에 열림 | 낮음 | Task 3/6 검증에서 WAN 도달 불가를 매 배포 시 확인. 공유기 UPnP를 비활성화해두는 것을 권장(계획 범위 밖, 별도 확인 필요) |
| `192.168.0.10`이 NAS에 유동 할당(DHCP)이면 재부팅/임대 갱신 시 IP가 바뀌어 compose 포트 바인딩이 실패, 24시간 자동 녹화가 조용히 멈춤 (v9: architect 리뷰어 지적) | 낮음 | Task 4에서 고정 IP/DHCP 예약 여부 사전 확인 |
| **(v13, 미수정 잔여 위험)** `fileManagerMode`를 `"whitelist"`로, `fileManagerRoots`를 `["/"]`로 함께 설정하면(다중 필드 조작 필요) `_normalizeConfig`가 `POST /config`가 쓰는 시스템 경로 차단 필터(`_normalizeAllowedRoots`)를 적용하지 않아 `ensureInRoots`의 화이트리스트 분기에서 사실상 전체 파일시스템이 허용됨(블랙리스트 모드보다 넓은 노출) | 낮음(다중 필드 동시 조작 필요, LAN 신뢰 경계 안) | 이미 받아들인 LAN 트레이드오프(UI7) 범주 내. 코드 수정은 세션 예산 소진으로 다음 라운드로 미룸 |
| **(v13, 미수정 잔여 위험)** `docker-compose.yml`에 NAS의 LAN IP(`192.168.0.10`)와 절대 경로(`/volume1/...`, `/volume3/...`)가 하드코딩되어 git에 커밋됨 | 낮음 | 개인 리포지토리이고 LAN 대역 자체가 민감정보는 아니라고 판단. 공개 저장소로 옮길 경우 재검토 필요 |
| 126GB 기존 로컬 녹화본은 이번 배포 범위에 없음(신규 녹화만 NAS로) | — | 사용자가 별도로 원치 않는 한 마이그레이션은 이번 계획에서 제외 |
| **(v14, 미수정 잔여 위험 — L2 패널 security 리뷰어 HIGH)** 앱에 CSRF/Host-header 방어가 전혀 없다(`SessionMiddleware`만 있고 `TrustedHostMiddleware`나 CSRF 토큰 없음). `POST /config`는 `Form` 필드를 받아 CORS 프리플라이트가 필요 없는 "simple request"이고 `POST /api/stop_all_recording`은 바디도 필요 없어서, LAN 안의 브라우저가 악성/광고 페이지를 열기만 해도 숨겨진 auto-submit 폼으로 `loginMode`/`fileManagerEnabled`를 켜거나 녹화를 중지시킬 수 있다 — "LAN이 곧 신뢰 경계"(UI7) 전제가 "LAN 안의 브라우저"까지는 방어하지 못함을 의미 | 낮음(가정 — 신뢰 기기만 LAN에 존재, 방문객 Wi-Fi 없음) | 배포/테스트를 우선하기 위해 이번 라운드에서는 의도적으로 미수정 — 사용자 승인. Origin/Referer 검증 또는 CSRF 토큰 추가를 후속 작업으로 트래킹 |

## Acceptance
- [ ] `docker compose up -d`로 NAS에서 recordWEB 컨테이너가 정상 기동
- [ ] `grep -n "app.router.dependencies.append\|enforceLoginGlobally" recordWEB.py`가 빈 결과(주석 제외) — 전역 인증 강제가 제거됐음을 확인
- [ ] **(v10)** `loginMode: True`인 상태를 흉내낸 요청에도 `requireLogin`이 `True`를 반환하는지 확인(Task 0 검증 스크립트) — loginMode 값 자체가 인증 동작에 영향을 주지 않음을 증명
- [ ] **(v11)** `fileManagerEnabled=False`에서 `requireFileManagerEnabled`가 403을 반환하는지 확인(Task 0 검증 스크립트) — 배포본 기본 설정에서 `/api/files/*` 전체가 닫혀 있음을 증명
- [ ] **(v12)** `saveConfig({"fileManagerEnabled": True})`(loginMode 없이)를 직접 호출해도 결과가 `False`로 강제되는지 확인(Task 0 검증 스크립트) — `POST /api/save_config` 같은 saveConfig 직접 호출 경로가 정규화를 우회하지 못함을 증명
- [ ] `192.168.0.10`이 NAS에 고정/DHCP 예약돼 있음을 DSM 또는 공유기 설정에서 확인 (v9)
- [ ] 같은 LAN의 다른 기기 브라우저에서 `192.168.0.10`의 5000번 포트로 SSH 터널 없이 직접 접속 가능(GUI 요구사항 충족)
- [ ] 공유기 밖(WAN, 예: 모바일 데이터)에서는 `192.168.0.10`의 5000번 포트에 도달 불가함을 확인
- [ ] `/volume1/storage/recordweb-files/chzzk/`에 "아카네 리제" 방송 녹화 파일이 생성되고 크기가 증가함 (성공 지표 충족)

## Codex Adversarial Review

<!-- placeholder: will be replaced by Phase 5.2 L2 패널 -->
