# Plan: recordWEB NAS Docker 배포 (자동 스트리밍 녹화) — v3

**Source**: 대화형 요청 (free-form, PRD 없음)
**Complexity**: Medium
**Revision**: v1(4/4 fail, CRITICAL 2건) → v2(코드 수정에도 4/4 fail, CRITICAL 1건 신규) → v3: 라우트별 patch 대신 **네트워크 경계 자체를 차단**하는 구조적 방어로 전략 변경

## Summary
`recordWEB.py`(FastAPI 기반 웹 UI + 녹화 엔진)를 Synology NAS(DSM 7.3.2, Container Manager/Docker 24.0.2)에 Docker로 배포해, 로컬 PC 전원 상태와 무관하게 24시간 자동 스트리밍 녹화가 되도록 한다. 배포 설정(compose/Dockerfile/시크릿)은 `volume3`에, 실제 녹화 영상은 `volume1`에 저장한다.

**v3의 핵심 전환**: v1/v2 리뷰에서 `/config`(POST), `/api/config`, `/api/yt_potoken`(GET/POST), `/get_config` 등 애초에 `Depends(requireLogin)`이 붙지 않은 라우트가 계속 발견됐다(2라운드 연속, 매번 새로운 구멍). 45개 라우트를 전수 감사해 개별 patch하는 것은 시간 대비 리스크가 높고 "또 놓친 라우트"가 나올 가능성을 배제할 수 없다. 따라서 **컨테이너 포트를 애초에 LAN/WAN에 노출하지 않고 NAS 루프백(127.0.0.1)에만 바인딩**해, 앱 자체의 라우트별 인증 커버리지와 무관하게 "NAS에 SSH/로컬 접근 권한이 있는 사람만 UI에 도달 가능"이라는 하나의 경계로 위협을 좁힌다. 이는 원래 Windows 데스크톱 앱이 "내 PC에서만 열려있는 로컬 서버"였던 신뢰 모델과 동일하다. `requireLogin`의 실제 버그(raise 누락)는 그대로 수정해 두지만, 심층 방어 차원이며 배포의 1차 방어선은 아니다.

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Docker 배포 위치 | `/volume3/docker/terab/` (기존 서비스) | `/volume3/docker/<project>/`에 compose+env+secrets 배치 |
| 데이터 볼륨 | `/volume1/storage/terab-files/` | `/volume1/storage/<project>-files/`에 대용량 데이터 저장 |
| 진입점 | `recordWEB.py:2562` `if __name__=="__main__"` | `uvicorn.Config(app, host="0.0.0.0", port=port)` — 컨테이너 내부는 그대로 0.0.0.0, 외부 노출은 compose 포트 매핑에서 loopback으로 제한 |
| 예외 처리 | `recordWEB.py:343-351` `http_exception_handler` | `HTTPException(status_code=401)`만 `RedirectResponse('/login')`으로 변환하고 그 외 status_code는 헤더 없이 JSON으로 변환 — 401 외 코드로 리다이렉트를 시도하면 무력화됨 |
| 계정 부재 감지 | `module/data_manager.py:629-644` `loadAccount()` | `username`/`password`가 null이면 `None` 반환 → `/register`로 최초 계정 생성 유도 |
| 민감정보 제외 | `.gitignore` (이전 세션에 작성) | `json/` 전체가 시크릿/개인 상태 — 이미지에 굽지 않고 볼륨 마운트 |

## User Intent (참고 — free-form 대화 원문)
| ID | Constraint (user-stated) | Kind |
|---|---|---|
| UI1 | Docker 배포 설정/구성 파일은 volume3 사용 | constraint |
| UI2 | 영상 저장 경로는 volume1 사용 | constraint |
| UI3 | 폴더 명칭은 NAS에서 직접 확인한 기존 패턴을 따를 것 | direction |
| UI4 | 설정 가능한 GUI 지원 희망 | direction |
| UI5 | 측정 가능한 성공 지표 = 치지직 "아카네 리제" 스트리밍이 실제로 녹화된 파일로 확인되는 것 | constraint |
| UI6 | (2026-08-14) 리뷰 게이트가 CRITICAL을 이유로 2회 연속 차단한 뒤, 사용자가 "claude 판단으로 진행해줘"라고 위임 | direction |

## L2 리뷰(2라운드)에서 지적된 CRITICAL·HIGH와 그에 대한 대응
| 라운드 | 지적 | 조치 |
|---|---|---|
| v1 | (CRITICAL) `loginMode:false`가 그대로 배포되어 웹 UI가 인증 없이 노출 | 배포용 `config.json`은 `loginMode:true`로 강제(방어의 일부, 아래 참고) |
| v1 | (CRITICAL) `GET /cookies`가 인증 없이 세션 쿠키·PO 토큰을 평문 렌더링 | `requireLogin`의 raise 누락 버그 수정(아래 v2/v3 정정 포함) |
| v2 | (HIGH, 신규) 303+Location 방식은 전역 예외 핸들러가 401만 리다이렉트로 바꾸고 그 외 코드는 헤더를 버려서 무력화됨 | `requireLogin`을 `HTTPException(status_code=401)`만 raise하도록 정정 — 기존에 이미 검증된 401→redirect 경로(343-351행)를 재사용 |
| v2 | (CRITICAL, 신규) `/config`(POST) 등 애초에 `Depends(requireLogin)` 자체가 없는 라우트가 다수 존재 — 라우트 단위 patch로는 커버리지를 보장 못함 | **전략 전환**: 라우트 patch를 더 이상 추가하지 않고, compose 포트 게시를 `127.0.0.1:5000:5000`으로 제한해 NAS 외부에서 도달 자체가 불가능하게 만듦(Design Decisions 참고) |
| v2 | (HIGH) `/register` 무인증 선착순 — 컨테이너 기동 시점과 관리자 등록 시점 사이 레이스 | 루프백 바인딩으로 애초에 외부에서 도달 불가 → 레이스의 공격자 모수가 "NAS에 로그인 가능한 사람"으로 좁혀짐(=이미 sudo 비밀번호를 아는 신뢰 당사자) |
| v2 | (MEDIUM) `login.json`의 `secret_key`를 회전 없이 그대로 NAS로 이전 — 로컬에 남은 값으로 세션 위조 가능 | Task 5에서 NAS 배포본 `login.json`은 **새 `secret_key`로 재생성**(로컬 값 재사용 안 함) |
| v1 | (HIGH) `getDeno()` 무가드 호출 → 미설치 시 `sys.exit(1)`로 전체 프로세스 종료 | Dockerfile에서 `denoland/deno` 공식 이미지 바이너리를 멀티스테이지 `COPY`로 항상 포함 |
| v1/v2 | (HIGH) `install_missing_modules()`가 매 기동 시 네트워크 pip install 시도 | requirements.txt를 실제 목록과 1:1 일치(`pystray`/`pillow`/`py-cpuinfo` 포함) |
| v2 | (HIGH) Task1 Validate가 `docker build` 로그를 보라고 했지만 해당 print는 `docker run`(CMD 실행) 시점에만 출력됨 | Validate를 `docker compose up` 로그 확인으로 정정 |
| v1 | (MEDIUM) `dependent/plugin`이 `.dockerignore`로 함께 제외될 뻔함 | `dependent/plugin/`, `dependent/img/`는 명시적으로 keep |
| v1 | (MEDIUM) 성공 지표 검증이 파일명 패턴에 의존 | mtime/크기 증가 확인을 주 검증으로, 파일명 grep은 보조 수단 |
| v1 | (MEDIUM) 자격증명 NAS 이전에 rollback/백업, 로컬 인스턴스 중지 단계 없음 | Task 5 로컬 백업, Task 6 로컬 프로세스 중지 단계 추가 |

## Design Decisions
- 별도 GUI를 새로 만들지 않고 `recordWEB.py`의 기존 웹 UI를 그대로 컨테이너로 노출한다.
- **네트워크 경계**: `docker-compose.yml`의 포트 게시를 `127.0.0.1:5000:5000`으로 고정한다(0.0.0.0 아님). NAS 밖에서는 이 포트에 도달할 수 없다. 접근이 필요하면 `ssh -L 5000:localhost:5000 nas-claude` 로 로컬 포트포워딩해서 사용한다. LAN 전체 공개나 라우터 포트포워딩은 이번 계획 범위에서 하지 않는다 — 하려면 애플리케이션의 라우트별 인증 커버리지를 별도로 전수 감사해야 하므로 후속 과제로 분리한다.
- `requireLogin`은 여전히 `loginMode:true` + `HTTPException(401)`로 수정해 둔다(심층 방어). 배포본 `config.json`도 `loginMode:true`로 설정한다.
- `json/` 전체는 이미지에 포함하지 않고 `/volume3/docker/recordweb/json`에 바인드 마운트한다.
- 녹화 출력은 `channels.json`의 기존 `output_dir: "chzzk"`를 그대로 두고, 컨테이너 내부 `/app/chzzk`에 `/volume1/storage/recordweb-files/chzzk`를 바인드 마운트한다.
- `dependent/aria2c`, `dependent/bgutil-pot`, `dependent/ffmpeg`, `dependent/streamlink`, `dependent/ytarchive`, `dependent/yt-dlp`(Windows PE 바이너리)는 이미지에 포함하지 않고, Linux 네이티브 ffmpeg/aria2(apt)·streamlink/yt-dlp(pip)로 대체한다. `dependent/plugin`, `dependent/img`는 유지한다.
- deno는 `denoland/deno` 공식 이미지에서 바이너리만 멀티스테이지로 복사해 항상 포함시킨다.
- Docker Swarm이 아니라 단일 호스트 `docker compose`로 배포한다.
- NAS 배포본 `login.json`의 `secret_key`는 로컬 값을 재사용하지 않고 새로 생성한다.

## Files to Change
| File | Action | Why |
|---|---|---|
| `recordWEB.py` | **UPDATE (이미 적용됨)** | `requireLogin`(383행 부근)이 `HTTPException(401)`을 raise하도록 수정 — 기존 예외 핸들러(343-351행)가 401만 redirect로 바꾸는 동작을 그대로 재사용 |
| `requirements.txt` | CREATE | `install_missing_modules()` 목록과 정확히 일치(fastapi, uvicorn, aiohttp, jinja2, werkzeug, itsdangerous, python-multipart, starlette, psutil, cryptography, requests, httpx, pystray, pillow, py-cpuinfo) + streamlink, yt-dlp |
| `Dockerfile` | CREATE | `python:3.11-slim`, `apt-get install -y ffmpeg aria2`, `denoland/deno` 이미지에서 바이너리 COPY, `pip install -r requirements.txt`, `WORKDIR /app`, `EXPOSE 5000`, `CMD ["python","recordWEB.py"]` |
| `.dockerignore` | CREATE | `chzzk/`, `dependent/{aria2c,bgutil-pot,ffmpeg,streamlink,ytarchive,yt-dlp}/`, `json/`, `.git`, `__pycache__` 제외. `dependent/plugin/`, `dependent/img/`는 keep |
| `docker-compose.yml` | CREATE | 이미지 빌드/실행, `json`·`chzzk` 바인드 마운트, **`127.0.0.1:5000:5000`**, `restart: unless-stopped` |
| `json/config.json` | UPDATE(배포시, 배포본에만 적용·git에는 미반영) | `enableTray:false`, `minimizeToTray*:false`, `loginMode:true`, `port:5000` |
| `json/login.json` | UPDATE(배포시, 배포본에만 적용) | `secret_key`를 새로 생성해 로컬 값과 분리 |
| (NAS) `/volume3/docker/recordweb/` | CREATE | compose 스택 배치 위치 |
| (NAS) `/volume1/storage/recordweb-files/chzzk` | CREATE | 녹화 영상 저장 위치 |

## Tasks

### Task 0: `requireLogin` 인증 우회 버그 수정 (완료)
- **Action**: `recordWEB.py`의 `requireLogin`에서 리다이렉트 경로를 `HTTPException(status_code=401, detail="Login required")` raise로 통일(기존 401→redirect 전역 핸들러 재사용)
- **Validate**: 배포 후 세션 없는 상태에서 `GET /cookies` 요청 시 `/login`으로 리다이렉트되는지 확인(심층 방어 검증 — 1차 방어선은 Task 3의 loopback 바인딩)

### Task 1: requirements.txt 작성
- **Action**: `install_missing_modules()` 목록(pystray/pillow/py-cpuinfo 포함)과 1:1 일치 + streamlink, yt-dlp 추가
- **Validate**: `docker compose up` 최초 기동 로그에서 `모든 필수 모듈이 이미 설치되어 있습니다` 메시지 확인(=네트워크 pip install 미발생). *(build 시점이 아니라 CMD 실행 시점에 출력되므로 `docker build` 로그가 아닌 `up`/`run` 로그를 봐야 함)*

### Task 2: Dockerfile / .dockerignore 작성
- **Action**: ffmpeg/aria2(apt) + deno(멀티스테이지 COPY) + Python 의존성 설치
- **Validate**: `docker build -t recordweb .` 성공, `docker run --rm recordweb sh -c "ffmpeg -version && streamlink --version && yt-dlp --version && deno --version"`

### Task 3: docker-compose.yml 작성 — 포트를 루프백에만 게시
- **Action**: `json`/`chzzk` 바인드 마운트, **`127.0.0.1:5000:5000`**(0.0.0.0 아님), `restart: unless-stopped`
- **Validate**: `docker compose config`로 문법 확인, 기동 후 NAS 자체에서만 `curl localhost:5000`이 응답하고 다른 기기의 LAN IP 접근은 연결이 거부되는지 확인

### Task 4: NAS 배포 디렉터리 준비 (sudo 필요, 1회성)
- **Action**: `/volume3/docker/recordweb/` 생성 후 리포지토리 clone, `/volume1/storage/recordweb-files/chzzk` 생성
- **Validate**: `ls -la` 로 두 경로 존재 및 권한 확인(0700, claude 소유)

### Task 5: 로컬 자격증명 백업 및 NAS 이전 (secret_key 재생성)
- **Action**: 로컬 `json/` 전체를 우선 로컬 백업 후, `config.json`(트레이/로그인/포트 조정), `channels.json`, `cookie.json`을 `/volume3/docker/recordweb/json/`으로 scp 이전. `login.json`은 그대로 복사하지 않고 `secret_key`만 새로 생성해서 저장(`username`/`password`는 null 유지 → 최초 `/register` 필요)
- **Validate**: NAS `ls json/`로 파일 확인, `login.json`의 `secret_key`가 로컬 원본과 다른지 확인

### Task 6: 로컬 인스턴스 중지 → 이미지 빌드 및 기동 → 관리자 계정 생성(SSH 터널)
- **Action**: (a) 로컬 PC의 recordWEB 프로세스 종료(이중 녹화 방지) → (b) NAS에서 `sudo docker compose build && sudo docker compose up -d` → (c) `ssh -L 5000:localhost:5000 nas-claude`로 터널을 연 뒤 `http://localhost:5000/register`로 관리자 계정 생성
- **Validate**: `docker compose ps`, `docker compose logs -f`로 정상 기동 확인. `config.json`의 실제 `port` 값과 compose 포트 매핑 일치 확인. SSH 터널 없이 NAS의 LAN IP:5000으로 접근 시도 시 연결이 거부되는지 확인(loopback 바인딩 검증)

### Task 7: 성공 지표 검증 — "아카네 리제" 녹화 확인
- **Action**: `channels.json`에 `아카네 리제`(chzzk, `record_enabled:true`) 등록 확인 → 방송 시작 대기/즉시 확인 → `/volume1/storage/recordweb-files/chzzk/`에 새 파일 생성 확인
- **Validate**: 파일명 grep은 보조 수단으로만 사용하고, 주 검증은 `ls -la --time-style=full-iso /volume1/storage/recordweb-files/chzzk/ | sort` 를 수 분 간격으로 재실행해 대상 파일의 mtime과 크기가 계속 증가하는지 확인. SSH 터널을 통해 웹 UI `/recording`에서도 "REC" 상태 확인

## Validation
```bash
# NAS (sudo 필요)
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f recordweb   # "모든 필수 모듈이 이미 설치되어 있습니다" 확인
# 루프백 바인딩 검증: NAS 자신에게서는 응답, 외부 IP로는 미노출
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/
ls -la /volume1/storage/recordweb-files/chzzk/
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Docker 소켓 권한(claude 계정 미가입) | 낮음 (sudo 확인 완료) | `sudo docker compose ...` |
| ffmpeg/streamlink/yt-dlp Linux 빌드가 Windows용과 옵션/성능 차이 | 중간 | Task 7 검증으로 확인, 이상 시 `extra_ffmpeg_options` 조정 |
| loopback 바인딩으로 인해 다른 기기(휴대폰 등)에서 바로 웹 UI 접속 불가 — UI4(설정 GUI) 요구를 충족하되 편의성은 SSH 터널이 필요한 수준으로 제한됨 | 확정(설계상 트레이드오프) | 이번 계획의 성공 기준(UI4/UI5)은 "GUI로 설정 가능 + 녹화 확인 가능"이며 둘 다 SSH 터널로 충족됨. LAN 전체 공개가 필요하면 라우트 전수 인증 감사를 별도 후속 과제로 진행 |
| 126GB 기존 로컬 녹화본은 이번 배포 범위에 없음(신규 녹화만 NAS로) | — | 사용자가 별도로 원치 않는 한 마이그레이션은 이번 계획에서 제외 |

## Acceptance
- [ ] `docker compose up -d`로 NAS에서 recordWEB 컨테이너가 정상 기동
- [ ] 포트가 127.0.0.1에만 게시되어 SSH 터널 없이는 외부에서 도달 불가함을 확인
- [ ] SSH 터널을 통해 웹 UI로 설정/채널 관리 가능 (GUI 요구사항 충족)
- [ ] `/volume1/storage/recordweb-files/chzzk/`에 "아카네 리제" 방송 녹화 파일이 생성되고 크기가 증가함 (성공 지표 충족)

## Codex Adversarial Review

<!-- placeholder: will be replaced by Phase 7.3 -->
