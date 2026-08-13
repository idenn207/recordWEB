# Plan: recordWEB NAS Docker 배포 (자동 스트리밍 녹화) — v2

**Source**: 대화형 요청 (free-form, PRD 없음)
**Complexity**: Medium
**Revision**: v1의 mccp:plan L2 리뷰 패널(4/4 fail, CRITICAL 2건 포함)을 반영해 재작성

## Summary
`recordWEB.py`(FastAPI 기반 웹 UI + 녹화 엔진)를 Synology NAS(DSM 7.3.2, Container Manager/Docker 24.0.2)에 Docker로 배포해, 로컬 PC 전원 상태와 무관하게 24시간 자동 스트리밍 녹화가 되도록 한다. 배포 설정(compose/Dockerfile/시크릿)은 `volume3`에, 실제 녹화 영상은 `volume1`에 저장한다. 설정 GUI는 이미 `recordWEB.py`의 웹 UI(`templates/`)가 제공하므로 별도 구축 불필요.

v2에서는 L2 리뷰가 지적한 CRITICAL 인증 우회 버그를 애플리케이션 코드 레벨에서 수정하고, 배포 시 로그인을 강제하며, deno/의존성 관련 프로세스 종료 위험을 제거한다.

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Docker 배포 위치 | `/volume3/docker/terab/` (기존 서비스) | `/volume3/docker/<project>/`에 compose+env+secrets 배치 |
| 데이터 볼륨 | `/volume1/storage/terab-files/` | `/volume1/storage/<project>-files/`에 대용량 데이터 저장 |
| 진입점 | `recordWEB.py:2562` `if __name__=="__main__"` | `uvicorn.Config(app, host="0.0.0.0", port=port)` — 이미 컨테이너 친화적 |
| OS 분기 | `module/data_manager.py` `getFFmpeg/getStreamlink/...` | `os.name=='nt'`면 `dependent/*.exe`, 아니면 `shutil.which()` |
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
| UI6 | (2026-08-14) 리뷰 게이트가 CRITICAL을 이유로 차단한 뒤, 사용자가 "claude 판단으로 진행해줘"라고 위임 | direction |

## Codex/L2 리뷰에서 지적된 CRITICAL·HIGH와 그에 대한 대응
| 지적 | 조치 |
|---|---|
| (CRITICAL) `loginMode:false`가 그대로 배포되어 웹 UI가 인증 없이 노출 | 배포용 `config.json`은 `loginMode:true`로 강제. 최초 기동 후 `/register`에서 관리자 계정 생성을 배포 절차의 필수 단계로 명시(Task 6) |
| (CRITICAL) `GET /cookies`가 인증 없이 세션 쿠키·PO 토큰을 평문 렌더링 | 근본 원인(`requireLogin`이 redirect를 raise 대신 return)을 **코드로 직접 수정**(`recordWEB.py:383`, 이미 적용됨). 이제 `Depends(requireLogin)`이 붙은 모든 라우트(=`/cookies` 포함)가 비로그인 요청을 `HTTPException(303)`으로 실제 차단함 |
| (HIGH) `requireLogin`이 loginMode=true여도 우회됨 | 위 코드 수정으로 해결 |
| (HIGH) `getDeno()` 무가드 호출 → 미설치 시 `sys.exit(1)`로 전체 프로세스(진행 중 Chzzk 녹화 포함) 종료 | Dockerfile에서 `denoland/deno` 공식 이미지의 바이너리를 멀티스테이지 `COPY`로 포함시켜 애초에 deno가 항상 존재하도록 함(코드 미변경, 리스크 자체를 제거) |
| (HIGH) `install_missing_modules()`가 매 기동 시 네트워크 pip install 시도 (일부 패키지가 requirements.txt에서 누락돼 매번 트리거됨) | requirements.txt를 `install_missing_modules()`의 실제 목록과 **1:1로 정확히 일치**시켜(`pystray`/`pillow`/`py-cpuinfo` 포함) `pip show`가 전부 "이미 설치됨"으로 판정하게 만듦 → 컨테이너 기동 시 네트워크 pip install이 실질적으로 발생하지 않음 |
| (MEDIUM) requirements.txt에 werkzeug/itsdangerous 누락 | 위와 동일하게 정확한 목록에 포함 |
| (MEDIUM) `dependent/plugin`(Linux에서도 쓰이는 순수 파이썬)이 `.dockerignore`로 함께 제외될 뻔함 | `.dockerignore`에서 `dependent/plugin/`과 `dependent/img/`는 명시적으로 keep, Windows 바이너리 하위 폴더만 제외 |
| (MEDIUM) 포트 5000 하드코딩 vs 실제로는 `config.json`의 `port` 값을 읽음 | 배포 시 `config.json.port`를 5000으로 고정하고, Task 6 Validate에서 실제 값을 읽어 compose 포트 매핑과 일치하는지 확인하는 단계 추가 |
| (MEDIUM) 성공 지표 검증이 파일명 패턴에 의존 | Task 7 Validate를 디렉터리 mtime/파일 개수 증가 확인으로 보강(파일명 grep은 보조 수단으로만 사용) |
| (MEDIUM) 자격증명 NAS 이전에 rollback/백업, 로컬 인스턴스 중지 단계 없음 | Task 5에 로컬 `json/` 백업 단계와, Task 6에 "로컬 PC의 recordWEB 프로세스 중지" 단계를 명시적으로 추가(같은 계정으로 이중 녹화 방지) |

## Design Decisions
- 별도 GUI를 새로 만들지 않고 `recordWEB.py`의 기존 웹 UI를 그대로 컨테이너로 노출한다.
- `json/` 전체는 이미지에 포함하지 않고 `/volume3/docker/recordweb/json`에 바인드 마운트한다.
- 녹화 출력은 `channels.json`의 기존 `output_dir: "chzzk"`를 그대로 두고, 컨테이너 내부 `/app/chzzk`에 `/volume1/storage/recordweb-files/chzzk`를 바인드 마운트한다.
- `dependent/aria2c`, `dependent/bgutil-pot`, `dependent/ffmpeg`, `dependent/streamlink`, `dependent/ytarchive`, `dependent/yt-dlp`(Windows PE 바이너리)는 이미지에 포함하지 않고, Linux 네이티브 ffmpeg/aria2(apt)·streamlink/yt-dlp(pip)로 대체한다. `dependent/plugin`, `dependent/img`는 유지한다.
- deno는 `denoland/deno` 공식 이미지에서 바이너리만 멀티스테이지로 복사해 항상 포함시킨다(설치 스크립트 curl-pipe 방식 대신, 재현 가능하고 검증된 바이너리 복사).
- Docker Swarm이 아니라 단일 호스트 `docker compose`로 배포한다.
- **보안**: 배포본 `config.json`은 `loginMode:true`로 강제하고, `requireLogin`의 raise 누락 버그를 코드에서 수정했다(이미 적용). 최초 관리자 계정 생성(`/register`)을 배포 절차의 필수 단계로 둔다.

## Files to Change
| File | Action | Why |
|---|---|---|
| `recordWEB.py` | **UPDATE (이미 적용됨)** | `requireLogin`(383행)이 redirect를 raise하도록 수정 — CRITICAL 인증 우회 수정 |
| `requirements.txt` | CREATE | `install_missing_modules()` 목록과 정확히 일치(fastapi, uvicorn, aiohttp, jinja2, werkzeug, itsdangerous, python-multipart, starlette, psutil, cryptography, requests, httpx, pystray, pillow, py-cpuinfo) + streamlink, yt-dlp |
| `Dockerfile` | CREATE | `python:3.11-slim`, `apt-get install -y ffmpeg aria2`, `denoland/deno` 이미지에서 바이너리 COPY, `pip install -r requirements.txt`, `WORKDIR /app`, `EXPOSE 5000`, `CMD ["python","recordWEB.py"]` |
| `.dockerignore` | CREATE | `chzzk/`, `dependent/{aria2c,bgutil-pot,ffmpeg,streamlink,ytarchive,yt-dlp}/`, `json/`, `.git`, `__pycache__` 제외. `dependent/plugin/`, `dependent/img/`는 keep |
| `docker-compose.yml` | CREATE | 이미지 빌드/실행, `json`·`chzzk` 바인드 마운트, `5000:5000`, `restart: unless-stopped` |
| `json/config.json` | UPDATE(배포시, 배포본에만 적용·git에는 미반영) | `enableTray:false`, `minimizeToTray*:false`, `loginMode:true`, `port:5000` |
| (NAS) `/volume3/docker/recordweb/` | CREATE | compose 스택 배치 위치 |
| (NAS) `/volume1/storage/recordweb-files/chzzk` | CREATE | 녹화 영상 저장 위치 |

## Tasks

### Task 0: `requireLogin` 인증 우회 버그 수정 (완료)
- **Action**: `recordWEB.py:383`에서 `return RedirectResponse(...)` → `raise HTTPException(status_code=303, headers={"Location": "/login"})`로 변경
- **Validate**: `loginMode:true` + 세션 없는 상태에서 `GET /cookies` 요청 시 303으로 `/login`으로 리다이렉트되는지 확인 (배포 후 curl로 재확인)

### Task 1: requirements.txt 작성
- **Action**: `install_missing_modules()` 목록(pystray/pillow/py-cpuinfo 포함)과 1:1 일치 + streamlink, yt-dlp 추가
- **Validate**: `docker build` 로그에서 `모든 필수 모듈이 이미 설치되어 있습니다` 메시지 확인(=네트워크 pip install 미발생)

### Task 2: Dockerfile / .dockerignore 작성
- **Action**: ffmpeg/aria2(apt) + deno(멀티스테이지 COPY) + Python 의존성 설치
- **Validate**: `docker build -t recordweb .` 성공, `docker run --rm recordweb sh -c "ffmpeg -version && streamlink --version && yt-dlp --version && deno --version"`

### Task 3: docker-compose.yml 작성
- **Action**: `json`/`chzzk` 바인드 마운트, `5000:5000`, `restart: unless-stopped`
- **Validate**: `docker compose config`

### Task 4: NAS 배포 디렉터리 준비 (sudo 필요, 1회성)
- **Action**: `/volume3/docker/recordweb/` 생성 후 리포지토리 clone, `/volume1/storage/recordweb-files/chzzk` 생성
- **Validate**: `ls -la` 로 두 경로 존재 및 권한 확인(0700, claude 소유)

### Task 5: 로컬 자격증명 백업 및 NAS 이전
- **Action**: 로컬 `json/` 전체를 우선 로컬 백업 후, `config.json`(트레이/로그인/포트 조정), `channels.json`, `cookie.json`, `login.json`을 `/volume3/docker/recordweb/json/`으로 scp 이전
- **Validate**: NAS `ls json/`로 파일 확인, 디렉터리 권한 확인

### Task 6: 로컬 인스턴스 중지 → 이미지 빌드 및 기동 → 관리자 계정 생성
- **Action**: (a) 로컬 PC의 recordWEB 프로세스 종료(이중 녹화 방지) → (b) NAS에서 `sudo docker compose build && sudo docker compose up -d` → (c) `http://<NAS-IP>:5000/register`로 접속해 관리자 계정 생성
- **Validate**: `docker compose ps`, `docker compose logs -f`로 정상 기동 확인. `config.json`의 실제 `port` 값과 compose 포트 매핑 일치 확인. 로그인 없이 `/cookies` 접근 시 리다이렉트되는지 확인

### Task 7: 성공 지표 검증 — "아카네 리제" 녹화 확인
- **Action**: `channels.json`에 `아카네 리제`(chzzk, `record_enabled:true`) 등록 확인 → 방송 시작 대기/즉시 확인 → `/volume1/storage/recordweb-files/chzzk/`에 새 파일 생성 확인
- **Validate**: 파일명 grep은 보조 수단으로만 사용하고, 주 검증은 `ls -la --time-style=full-iso /volume1/storage/recordweb-files/chzzk/ | sort` 를 수 분 간격으로 재실행해 대상 파일의 mtime과 크기가 계속 증가하는지 확인. 웹 UI `/recording`에서 "REC" 상태 확인

## Validation
```bash
# NAS (sudo 필요)
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f recordweb
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://localhost:5000/cookies   # 303 /login 기대
ls -la /volume1/storage/recordweb-files/chzzk/
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Docker 소켓 권한(claude 계정 미가입) | 낮음 (sudo 확인 완료) | `sudo docker compose ...` |
| ffmpeg/streamlink/yt-dlp Linux 빌드가 Windows용과 옵션/성능 차이 | 중간 | Task 7 검증으로 확인, 이상 시 `extra_ffmpeg_options` 조정 |
| `requireLogin` 수정이 다른 세션 기반 라우트에 예기치 못한 영향 | 낮음 | HTTPException(303)은 FastAPI 기본 예외 핸들러가 그대로 Location 헤더를 전달 — GET 라우트 특성상 세션 미들웨어 동작에 영향 없음. 배포 후 로그인/로그아웃/보호된 페이지 왕복 테스트로 확인 |
| 126GB 기존 로컬 녹화본은 이번 배포 범위에 없음(신규 녹화만 NAS로) | — | 사용자가 별도로 원치 않는 한 마이그레이션은 이번 계획에서 제외 |

## Acceptance
- [ ] `docker compose up -d`로 NAS에서 recordWEB 컨테이너가 정상 기동
- [ ] `loginMode:true` + 관리자 계정 생성 완료, 비로그인 상태로 `/cookies` 접근 시 `/login`으로 리다이렉트됨(303)
- [ ] `/volume1/storage/recordweb-files/chzzk/`에 "아카네 리제" 방송 녹화 파일이 생성되고 크기가 증가함 (성공 지표 충족)

## Codex Adversarial Review

<!-- placeholder: will be replaced by Phase 7.3 -->
