# Plan: recordWEB NAS Docker 배포 (자동 스트리밍 녹화)

**Source**: 대화형 요청 (free-form, PRD 없음)
**Complexity**: Medium

## Summary
`recordWEB.py`(FastAPI 기반 웹 UI + 녹화 엔진)를 Synology NAS(DSM 7.3.2, Container Manager/Docker 24.0.2)에 Docker로 배포해, 로컬 PC 전원 상태와 무관하게 24시간 자동 스트리밍 녹화가 되도록 한다. 배포 설정(compose/Dockerfile/시크릿)은 `volume3`에, 실제 녹화 영상은 `volume1`에 저장한다. 설정 GUI는 이미 `recordWEB.py`의 웹 UI(`templates/`)가 제공하므로 별도 구축 불필요 — 컨테이너로 그대로 노출하면 요구사항을 충족한다.

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Docker 배포 위치 | `/volume3/docker/terab/` (기존 서비스) | `/volume3/docker/<project>/`에 compose+env+secrets 배치 |
| 데이터 볼륨 | `/volume1/storage/terab-files/` | `/volume1/storage/<project>-files/`에 대용량 데이터 저장 |
| 진입점 | `recordWEB.py:2562` `if __name__=="__main__"` | `uvicorn.Config(app, host="0.0.0.0", port=port)` — 이미 컨테이너 친화적 |
| OS 분기 | `module/data_manager.py` `getFFmpeg/getStreamlink/...` | `os.name=='nt'`면 `dependent/*.exe`, 아니면 `shutil.which()` — Linux는 PATH만 잡아주면 코드 수정 불필요 |
| 민감정보 제외 | `.gitignore` (이번 세션에 작성) | `json/` 전체가 시크릿/개인 상태 — 이미지에 굽지 않고 볼륨 마운트 |

## User Intent (참고 — free-form 대화 원문)
| ID | Constraint (user-stated) | Kind |
|---|---|---|
| UI1 | Docker 배포 설정/구성 파일은 volume3 사용 | constraint |
| UI2 | 영상 저장 경로는 volume1 사용 | constraint |
| UI3 | 폴더 명칭은 NAS에서 직접 확인한 기존 패턴을 따를 것 | direction |
| UI4 | 설정 가능한 GUI 지원 희망 | direction |
| UI5 | 측정 가능한 성공 지표 = 치지직 "아카네 리제" 스트리밍이 실제로 녹화된 파일로 확인되는 것 | constraint |

## Design Decisions
- 별도 GUI를 새로 만들지 않고 `recordWEB.py`의 기존 웹 UI(FastAPI+Jinja2, `templates/config.html`/`channels.html`/`cookies.html`)를 그대로 컨테이너로 노출한다. 이미 존재하는 기능을 재구현하지 않기 위함.
- `json/` 전체(설정+쿠키+로그인 시크릿)는 이미지에 포함하지 않고 `/volume3/docker/recordweb/json`에 바인드 마운트한다. 컨테이너 재생성/이미지 재빌드에도 자격증명·채널 목록이 유지되어야 하기 때문.
- 녹화 출력은 `channels.json`의 기존 `output_dir: "chzzk"` 값을 그대로 두고, 컨테이너 내부 `/app/chzzk`에 `/volume1/storage/recordweb-files/chzzk`를 바인드 마운트한다. `channels.json` 수정 없이 그대로 동작시키기 위함(`base_directory`는 프로젝트 루트 기준 상대경로로 계산됨 — `module/data_manager.py`).
- `dependent/aria2c`, `dependent/bgutil-pot`, `dependent/ffmpeg`, `dependent/streamlink`, `dependent/ytarchive`, `dependent/yt-dlp`(총 ~886MB Windows PE 바이너리)는 이미지에 포함하지 않는다. Dockerfile에서 Linux 네이티브 ffmpeg/aria2를 apt로, streamlink/yt-dlp를 pip로 설치해 `PATH`에 올리면 `shutil.which()` 분기가 그대로 동작한다.
- Docker Swarm(`terab`이 쓰는 방식)이 아니라 단일 호스트 `docker compose`로 배포한다. recordWEB은 단일 인스턴스면 충분하고, Swarm 스택에 편입시킬 이유가 없다.

## Files to Change
| File | Action | Why |
|---|---|---|
| `requirements.txt` | CREATE | fastapi, uvicorn[standard], jinja2, python-multipart, requests, httpx, aiohttp, psutil, cryptography, streamlink, yt-dlp (탐색된 의존성 목록 기반, PyQt6/pystray/pygetwindow 등 GUI 전용 패키지는 제외) |
| `Dockerfile` | CREATE | `python:3.11-slim` 베이스, `apt-get install -y ffmpeg aria2`, `pip install -r requirements.txt`, `WORKDIR /app`, `EXPOSE 5000`, `CMD ["python","recordWEB.py"]` |
| `.dockerignore` | CREATE | `chzzk/`, `dependent/aria2c` 등 Windows 바이너리, `json/`, `.git`, `__pycache__` 제외 — 이미지 빌드 컨텍스트 축소 |
| `docker-compose.yml` | CREATE | 이미지 빌드/실행 정의, `json`·`chzzk` 바인드 마운트, 포트 매핑, `restart: unless-stopped` |
| `json/config.json` (NAS 배포본만, git에는 없음) | UPDATE(배포시) | `enableTray: false`, `minimizeToTray*: false` — 컨테이너엔 트레이 아이콘 자체가 무의미 |
| (NAS) `/volume3/docker/recordweb/` | CREATE | compose 스택 배치 위치 |
| (NAS) `/volume1/storage/recordweb-files/chzzk` | CREATE | 녹화 영상 저장 위치 |

## Tasks

### Task 1: requirements.txt 작성
- **Action**: 탐색된 3rd-party 패키지 목록(fastapi, uvicorn, jinja2, python-multipart, requests, httpx, aiohttp, psutil, cryptography, streamlink, yt-dlp)을 버전 미고정으로 명시
- **Mirror**: `recordWEB.py`/`recordGUI.py`의 `install_missing_modules()` 런타임 자동설치 목록을 정적 파일로 대체(런타임 pip install은 컨테이너에서 비활성화)
- **Validate**: `pip install -r requirements.txt` 로컬 dry-run 또는 Docker 빌드 성공 여부로 확인

### Task 2: Dockerfile / .dockerignore 작성
- **Action**: Linux 네이티브 ffmpeg/aria2 설치 + Python 의존성 설치 + `recordWEB.py` 기본 CMD
- **Mirror**: `module/data_manager.py`의 `getFFmpeg()`/`getStreamlink()`/`getYtDlp()`/`getAria2c()` — `shutil.which()` 분기를 만족시키도록 PATH 보장
- **Validate**: `docker build -t recordweb .` 성공, `docker run --rm recordweb ffmpeg -version` / `streamlink --version` / `yt-dlp --version` 확인

### Task 3: docker-compose.yml 작성 및 볼륨 설계
- **Action**: `json`과 `chzzk` 바인드 마운트, `5000:5000` 포트, `restart: unless-stopped`
- **Mirror**: `/volume3/docker/terab/docker-stack.yml`의 서비스 정의 스타일(주석, 헬스체크 패턴)을 참고하되 Swarm이 아닌 compose 문법 사용
- **Validate**: `docker compose config` 로 문법 검증

### Task 4: NAS에 배포 디렉터리 준비 (sudo 필요, 1회성)
- **Action**: `/volume3/docker/recordweb/` 생성, 여기에 리포지토리 clone 또는 rsync, `/volume1/storage/recordweb-files/chzzk` 생성
- **Validate**: `ls -la` 로 두 경로 존재 및 소유권 확인

### Task 5: 기존 로컬 `json/` 자격증명(쿠키·로그인 등) NAS로 이전
- **Action**: 로컬 PC의 실제 `json/config.json`(트레이 옵션만 비활성화), `channels.json`, `cookie.json`, `login.json` 등을 `/volume3/docker/recordweb/json/`으로 안전하게 복사(scp, git 아님)
- **Validate**: NAS에서 `ls json/` 로 파일 존재 확인, 컨테이너 기동 후 웹 UI 로그인/채널 목록이 기존과 동일한지 확인

### Task 6: 이미지 빌드 및 기동
- **Action**: NAS에서 `sudo docker compose build && sudo docker compose up -d` (또는 GitHub Actions로 이미지 빌드 후 `docker compose pull`)
- **Validate**: `docker compose ps`, `docker compose logs -f` 로 정상 기동 및 채널 폴링 로그 확인

### Task 7: 성공 지표 검증 — "아카네 리제" 녹화 확인
- **Action**: `channels.json`에 이미 `아카네 리제`(chzzk, `record_enabled: true`)가 등록돼 있음을 재확인 → 컨테이너 기동 후 방송 시작 시점까지 대기(또는 방송 중이면 즉시) → `/volume1/storage/recordweb-files/chzzk/`에 `.ts` 파일이 생성되고 파일 크기가 지속적으로 증가하는지 확인
- **Validate**: `ls -la /volume1/storage/recordweb-files/chzzk/*아카네*` + 수 분 간격으로 재확인해 파일 크기 증가(=실시간 녹화 진행) 확인, 웹 UI(`/recording`)에서도 녹화 상태 "REC" 표시 확인

## Validation
```bash
# NAS (sudo 필요)
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f recordweb
ls -la /volume1/storage/recordweb-files/chzzk/
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Docker 소켓 권한(claude 계정 미가입) 문제 | 낮음 (sudo 확인 완료) | `sudo docker compose ...`로 실행, 또는 이후 NOPASSWD sudoers/docker 그룹 추가는 별도 논의 |
| ffmpeg/streamlink/yt-dlp Linux 빌드가 Windows용과 옵션/성능 차이 | 중간 | 최초 배포 후 recording 로그·파일 정상 여부로 검증(Task 7), 이상 시 `extra_ffmpeg_options` 조정 |
| PO-token/bgutil(YouTube 인증 강화) 기능은 `deno` 미설치 시 동작 안 함 | 낮음 (Chzzk 우선 검증) | 1차 배포는 Chzzk 성공 지표만 충족하면 되므로 deno는 후속 과제로 보류, 필요 시 Dockerfile에 deno 설치 단계 추가 |
| 126GB 기존 로컬 녹화본은 이번 배포 범위에 없음(신규 녹화만 NAS로) | — | 사용자가 별도로 원치 않는 한 기존 파일 마이그레이션은 이번 계획에서 제외 |

## Acceptance
- [ ] `docker compose up -d`로 NAS에서 recordWEB 컨테이너가 정상 기동
- [ ] 웹 UI(`http://<NAS-IP>:5000`)로 설정/채널 관리 가능 (GUI 요구사항 충족)
- [ ] `/volume1/storage/recordweb-files/chzzk/`에 "아카네 리제" 방송 녹화 파일이 생성되고 크기가 증가함 (성공 지표 충족)

## Codex Adversarial Review

<!-- placeholder: will be replaced by Phase 7.3 -->

