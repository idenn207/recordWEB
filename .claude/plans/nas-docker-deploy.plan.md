# Plan: recordWEB NAS Docker 배포 (자동 스트리밍 녹화) — v5

**Source**: 대화형 요청 (free-form, PRD 없음)
**Complexity**: Medium
**Revision**: v1~v4는 라우트 단위로 인증을 opt-in 추가하는 방식이었고, 매 라운드 리뷰에서 "또 다른 무인증 라우트"가 새로 발견됐다(v2: 다수, v3: 4개, v4: 4개 더). v5는 **라우터 레벨 전역 의존성**으로 구조 자체를 바꿔 이 whack-a-mole을 구조적으로 종료한다.

## Summary
`recordWEB.py`(FastAPI 기반 웹 UI + 녹화 엔진)를 Synology NAS(DSM 7.3.2, Container Manager/Docker 24.0.2)에 Docker로 배포해, 로컬 PC 전원 상태와 무관하게 24시간 자동 스트리밍 녹화가 되도록 한다. 배포 설정(compose/Dockerfile/시크릿)은 `volume3`에, 실제 녹화 영상은 `volume1`에 저장한다.

## v5의 핵심 변경 — 라우트별 opt-in에서 라우터 전역 강제로
FastAPI는 `APIRouter.add_api_route()` 호출 시점에 `self.dependencies`(라우터 레벨 기본 의존성 목록)를 복사해 각 라우트에 결합한다(`current_dependencies = self.dependencies.copy()`, 로컬 FastAPI 0.136.1 소스로 직접 확인). 즉 **이 리스트에 추가한 시점 이후 등록되는 모든 라우트는 자동으로 그 의존성을 상속**하며, 라우트 데코레이터마다 개별적으로 `Depends(requireLogin)`을 붙이고 빠뜨리는 실수가 구조적으로 불가능해진다.

`recordWEB.py`에서 `requireLogin` 정의 직후(404행)에 다음을 추가했다:
```python
_PUBLIC_PATHS = {"/", "/login", "/register", "/logout"}

async def enforceLoginGlobally(request: Request):
    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith("/static/"):
        return True
    return await requireLogin(request)

app.router.dependencies.append(Depends(enforceLoginGlobally))
```
파일 내 모든 `@app.get/post/put/delete` 데코레이터는 778행 이후에 있음을 grep으로 확인했다(47개 전부, 404행보다 뒤) — 즉 이 시점 이후 등록되는 라우트가 정확히 전체 라우트 집합과 일치한다. `/`, `/login`, `/register`, `/logout`, `/static/*`만 명시적으로 예외 처리했고, `/`는 `index()` 핸들러가 이미 내부적으로 loginMode/세션을 검사해 비로그인 시 제한된 화면만 보여주므로 이중 보호가 불필요하다.

루프백 바인딩(v3에서 도입)은 심층 방어로 그대로 유지한다.

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Docker 배포 위치 | `/volume3/docker/terab/` (기존 서비스) | `/volume3/docker/<project>/`에 compose+env+secrets 배치 |
| 데이터 볼륨 | `/volume1/storage/terab-files/` | `/volume1/storage/<project>-files/`에 대용량 데이터 저장 |
| 진입점 | `recordWEB.py` 함수 `runUvicorn`(uvicorn 설정) / `if __name__=="__main__"` 블록(실행 트리거) | `uvicorn.Config(app, host="0.0.0.0", port=port)` — 컨테이너 내부는 그대로 0.0.0.0, 외부 노출은 compose 포트 매핑에서 loopback으로 제한 |
| 예외 처리 | `recordWEB.py` `http_exception_handler` | `HTTPException(status_code=401)`만 `RedirectResponse('/login')`으로 변환 — `requireLogin`은 이 401 경로만 사용 |
| 계정 부재 감지 | `module/data_manager.py` `loadAccount()` | `username`/`password`가 null이면 `None` 반환 → `/register`로 최초 계정 생성 유도 |
| 라우터 전역 의존성 | FastAPI `APIRouter.add_api_route()` (`self.dependencies.copy()`) | 등록 시점 이후 모든 라우트가 상속 — v5의 구조적 인증 강제가 여기에 근거 |
| 민감정보 제외 | `.gitignore` (이전 세션에 작성) | `json/` 전체가 시크릿/개인 상태 — 이미지에 굽지 않고 볼륨 마운트 |

## User Intent (참고 — free-form 대화 원문)
| ID | Constraint (user-stated) | Kind |
|---|---|---|
| UI1 | Docker 배포 설정/구성 파일은 volume3 사용 | constraint |
| UI2 | 영상 저장 경로는 volume1 사용 | constraint |
| UI3 | 폴더 명칭은 NAS에서 직접 확인한 기존 패턴을 따를 것 | direction |
| UI4 | 설정 가능한 GUI 지원 희망 | direction |
| UI5 | 측정 가능한 성공 지표 = 치지직 "아카네 리제" 스트리밍이 실제로 녹화된 파일로 확인되는 것 | constraint |
| UI6 | (2026-08-14) 리뷰 게이트가 CRITICAL/HIGH를 이유로 4라운드 연속 차단한 뒤, 사용자가 "claude 판단으로 진행해줘"라고 위임 | direction |

## 라운드별 지적과 대응 요약
| 라운드 | 핵심 지적 | 조치 |
|---|---|---|
| v1 | CRITICAL: `loginMode:false` 배포 + `/cookies` 평문 쿠키 노출 | `loginMode:true` 강제, `requireLogin` raise 버그 수정 |
| v2 | CRITICAL: 303+Location이 전역 예외 핸들러에 의해 무력화, 다수 라우트가 애초에 무인증 | `requireLogin`을 401 경로로 정정, 루프백 바인딩으로 전략 전환(v3) |
| v3 | HIGH: architect가 재확정한 무인증 라우트 4개(`/api/config`, `/get_config`, `/api/yt_potoken` GET/POST) | 4개 라우트에 개별 patch(v4) |
| v4 | HIGH: 그마저도 완결이 아니었음 — `/status`, `/api/sys_metrics`, `/updateAccount`, `/user_info` 등 추가로 무인증 확인. 라우트별 opt-in 구조 자체가 신뢰할 수 없다는 지적 | **v5: 라우터 레벨 전역 `Depends`로 구조 전환** — 새 라우트가 추가돼도 명시적으로 예외 처리하지 않는 한 자동으로 인증이 걸림 |
| v3 | MEDIUM: deno COPY 대상 PATH 미명시, PID 1 zombie reap 부재 | Dockerfile에서 `/usr/local/bin/deno`로 명시 COPY, compose에 `init: true` |
| v1 | HIGH: `getDeno()` 무가드 호출로 프로세스 전체 종료 위험 | `denoland/deno` 이미지에서 바이너리 상시 포함 |
| v1/v2 | HIGH: `install_missing_modules()` 매 기동 네트워크 pip install | requirements.txt를 실제 목록과 1:1 일치 |
| v2 | HIGH: Task1 Validate 시점 오류(build vs run) | `docker compose up` 로그 확인으로 정정 |
| v1 | MEDIUM: `dependent/plugin` 오제외 위험, 성공 지표가 파일명 패턴 의존, rollback/로컬중지 단계 부재 | `.dockerignore`에서 명시적 keep, mtime 기반 검증으로 보강, Task 5/6에 백업·중지 단계 추가 |

## Design Decisions
- 별도 GUI를 새로 만들지 않고 `recordWEB.py`의 기존 웹 UI를 그대로 컨테이너로 노출한다.
- **인증**: 라우터 전역 `Depends(enforceLoginGlobally)`로 구조적으로 강제한다(위 "v5의 핵심 변경" 참고). 개별 라우트의 기존 `Depends(requireLogin)`은 중복이지만 해가 없으므로 그대로 둔다.
- **네트워크 경계(심층 방어)**: `docker-compose.yml`의 포트 게시를 127.0.0.1의 5000번 포트로 게시(host 127.0.0.1, container 5000)으로 고정한다(0.0.0.0 아님). 접근이 필요하면 `ssh -L 5000:localhost:5000 nas-claude`로 로컬 포트포워딩한다.
- 배포본 `config.json`은 `loginMode:true`로 설정한다.
- `json/` 전체는 이미지에 포함하지 않고 `/volume3/docker/recordweb/json`에 바인드 마운트한다.
- 녹화 출력은 `channels.json`의 기존 `output_dir: "chzzk"`를 그대로 두고, 컨테이너 내부 `/app/chzzk`에 `/volume1/storage/recordweb-files/chzzk`를 바인드 마운트한다.
- `dependent/aria2c`, `dependent/bgutil-pot`, `dependent/ffmpeg`, `dependent/streamlink`, `dependent/ytarchive`, `dependent/yt-dlp`(Windows PE 바이너리)는 이미지에 포함하지 않고, Linux 네이티브 ffmpeg/aria2(apt)·streamlink/yt-dlp(pip)로 대체한다. `dependent/plugin`, `dependent/img`는 유지한다.
- deno는 `denoland/deno` 공식 이미지에서 바이너리만 `/usr/local/bin/deno`로 멀티스테이지 복사한다.
- Docker Swarm이 아니라 단일 호스트 `docker compose`로 배포한다.
- NAS 배포본 `login.json`의 `secret_key`는 로컬 값을 재사용하지 않고 새로 생성한다(계정 등록 후부터 유효해지는 값이며, 등록 전에는 세션이 존재하지 않아 무의미하지만 등록 이후 세션 위조 방지를 위해 유지).

## Files to Change
| File | Action | Why |
|---|---|---|
| `recordWEB.py` | **UPDATE (이미 적용됨)** | (1) `requireLogin`이 `HTTPException(401)`을 raise하도록 수정. (2) `requireLogin` 정의 직후 `enforceLoginGlobally` + `app.router.dependencies.append(...)`로 라우터 전역 인증 강제 추가(모든 47개 라우트가 자동 적용 대상, `/`, `/login`, `/register`, `/logout`, `/static/*`만 예외) |
| `requirements.txt` | CREATE | `install_missing_modules()` 목록과 정확히 일치(fastapi, uvicorn, aiohttp, jinja2, werkzeug, itsdangerous, python-multipart, starlette, psutil, cryptography, requests, httpx, pystray, pillow, py-cpuinfo) + streamlink, yt-dlp |
| `Dockerfile` | CREATE | `python:3.11-slim`, `apt-get install -y ffmpeg aria2`, `denoland/deno` 이미지에서 바이너리를 `/usr/local/bin/deno`로 COPY, `pip install -r requirements.txt`, `WORKDIR /app`, `EXPOSE 5000`, `CMD ["python","recordWEB.py"]` |
| `.dockerignore` | CREATE | `chzzk/`, `dependent/{aria2c,bgutil-pot,ffmpeg,streamlink,ytarchive,yt-dlp}/`, `json/`, `.git`, `__pycache__` 제외. `dependent/plugin/`, `dependent/img/`는 keep |
| `docker-compose.yml` | CREATE | 이미지 빌드/실행, `json`·`chzzk` 바인드 마운트, **127.0.0.1의 5000번 포트로 게시(host 127.0.0.1, container 5000)**, `restart: unless-stopped`, `init: true`(PID 1 zombie reap) |
| `json/config.json` | UPDATE(배포시, 배포본에만 적용·git에는 미반영) | `enableTray:false`, `minimizeToTray*:false`, `loginMode:true`, `port:5000` |
| `json/login.json` | UPDATE(배포시, 배포본에만 적용) | `secret_key`를 새로 생성해 로컬 값과 분리 |
| (NAS) `/volume3/docker/recordweb/` | CREATE | compose 스택 배치 위치 |
| (NAS) `/volume1/storage/recordweb-files/chzzk` | CREATE | 녹화 영상 저장 위치 |

## Tasks

### Task 0: 인증을 라우터 전역 의존성으로 구조화 (완료)
- **Action**: (1) `requireLogin`이 `HTTPException(401)` raise. (2) `app.router.dependencies.append(Depends(enforceLoginGlobally))`를 라우트 등록보다 앞선 위치(404행)에 추가 — 이후 등록되는 전체 47개 라우트에 자동 적용
- **Validate**: (기계적, 실행 없이 정적 검증 가능)
  ```bash
  # 1) app.router.dependencies.append(...) 위치 확인
  grep -n "app.router.dependencies.append" recordWEB.py
  # 2) 모든 라우트 데코레이터가 그 뒤에 있는지 확인 (숫자 비교로 "빠진 라우트 없음"을 기계적으로 증명)
  grep -n "^@app\.\(get\|post\|put\|delete\)" recordWEB.py | awk -F: '{print $1}' | sort -n | head -1
  # → 최소 라인 번호가 append 라인보다 커야 함(현재: append=404, 최소 라우트=778)
  ```
  배포 후에는 심층 방어로 세션 없는 상태에서 `GET /status`, `GET /api/sys_metrics`, `GET /user_info`, `GET /cookies` 등 임의 표본 라우트가 401/리다이렉트로 막히는지도 확인한다.

### Task 1: requirements.txt 작성
- **Action**: `install_missing_modules()` 목록(pystray/pillow/py-cpuinfo 포함)과 1:1 일치 + streamlink, yt-dlp 추가
- **Validate**: `docker compose up` 최초 기동 로그에서 `모든 필수 모듈이 이미 설치되어 있습니다` 메시지 확인(build 시점이 아니라 CMD 실행 시점에 출력되므로 `up`/`run` 로그를 봐야 함)

### Task 2: Dockerfile / .dockerignore 작성
- **Action**: ffmpeg/aria2(apt) + deno(멀티스테이지 COPY, `/usr/local/bin/deno`) + Python 의존성 설치
- **Validate**: `docker build -t recordweb .` 성공, `docker run --rm recordweb sh -c "ffmpeg -version && streamlink --version && yt-dlp --version && deno --version"`

### Task 3: docker-compose.yml 작성 — 포트를 루프백에만 게시
- **Action**: `json`/`chzzk` 바인드 마운트, **127.0.0.1의 5000번 포트로 게시(host 127.0.0.1, container 5000)**(0.0.0.0 아님), `restart: unless-stopped`, `init: true`
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
# 로컬(정적 검증) — 라우터 전역 인증 커버리지 증명
grep -n "app.router.dependencies.append" recordWEB.py
grep -n "^@app\.\(get\|post\|put\|delete\)" recordWEB.py | awk -F: '{print $1}' | sort -n | head -1

# NAS (sudo 필요)
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f recordweb   # "모든 필수 모듈이 이미 설치되어 있습니다" 확인
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5000/
ls -la /volume1/storage/recordweb-files/chzzk/
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Docker 소켓 권한(claude 계정 미가입) | 낮음 (sudo 확인 완료) | `sudo docker compose ...` |
| ffmpeg/streamlink/yt-dlp Linux 빌드가 Windows용과 옵션/성능 차이 | 중간 | Task 7 검증으로 확인, 이상 시 `extra_ffmpeg_options` 조정 |
| 라우터 전역 의존성이 `/static/*` 외의 향후 새 public 경로(예: 헬스체크 엔드포인트)를 잊고 `_PUBLIC_PATHS`에 추가하지 않으면 그 라우트도 인증이 걸림 | 낮음 | 이는 "과소허용" 방향의 실패이므로 보안상 안전한 방향의 실패(막혀서 못 쓰는 것이 뚫려서 새는 것보다 낫다). 필요 시 `_PUBLIC_PATHS`에 추가 |
| loopback 바인딩으로 다른 기기에서 SSH 터널 없이 웹 UI 접속 불가 | 확정(설계상 트레이드오프) | UI4/UI5 성공 기준은 SSH 터널로 충족 가능. LAN 전체 공개가 필요하면 후속 과제 |
| 126GB 기존 로컬 녹화본은 이번 배포 범위에 없음(신규 녹화만 NAS로) | — | 사용자가 별도로 원치 않는 한 마이그레이션은 이번 계획에서 제외 |

## Acceptance
- [ ] `docker compose up -d`로 NAS에서 recordWEB 컨테이너가 정상 기동
- [ ] 정적 검증(`app.router.dependencies.append`가 모든 라우트 데코레이터보다 앞선 라인)으로 인증 커버리지가 전체 라우트에 미침을 확인
- [ ] 포트가 127.0.0.1에만 게시되어 SSH 터널 없이는 외부에서 도달 불가함을 확인
- [ ] SSH 터널을 통해 웹 UI로 설정/채널 관리 가능 (GUI 요구사항 충족)
- [ ] `/volume1/storage/recordweb-files/chzzk/`에 "아카네 리제" 방송 녹화 파일이 생성되고 크기가 증가함 (성공 지표 충족)

## Codex Adversarial Review

<!-- placeholder: will be replaced by Phase 7.3 -->
