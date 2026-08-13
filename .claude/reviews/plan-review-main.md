# Plan Review Panel — main

**Plan**: .claude/plans/nas-docker-deploy.plan.md · **Plan version**: sha256:5c88a0dc4e2804ddafe196931902c05279c2f29c1b23d406c94c813c269c957d
**Verdict**: divergent via multi-agent
**Quorum**: 0/3 required responses passed (4/4 responded) · 4/4 distinct roles
**Layers**: L1 converged · L2 fail (4/4 reviewers) · L3 not fired

## Findings

| Perspective | Severity | Claim | Evidence |
|---|---|---|---|
| security | CRITICAL | 인증 없는(loginMode=false) 웹 UI를 0.0.0.0:5000으로 그대로 노출 | recordWEB.py:376, json/config.json:31 |
| security | CRITICAL | GET /cookies가 인증 없이 cookie.json(NID_AUT/NID_SES)과 ytPoToken을 평문 렌더링 | recordWEB.py:1695-1701, templates/cookies.html:76,116 |
| security | HIGH | requireLogin이 RedirectResponse를 raise가 아니라 return — loginMode=true여도 /cookies 우회됨 | recordWEB.py:383, 1696 |
| architect | HIGH | install_missing_modules()가 무조건 실행되어 컨테이너 기동마다 네트워크 pip install 시도 (계획은 "비활성화"라 주장) | recordWEB.py:66, 32-38 |
| architect | HIGH | getDeno() 가드 없이 호출 → deno 미설치 시 sys.exit(1)로 프로세스 전체(진행 중 Chzzk 녹화 포함) 종료 | module/youtube_recorder.py:605, module/data_manager.py:1144 |
| invariant | HIGH | Risk 표가 deno 부재를 "기능 저하"로 오기술 — 실제로는 성공 지표(UI5)까지 죽이는 프로세스 종료 | module/youtube_recorder.py:605, data_manager.py:1140-1144 |
| invariant | HIGH | 런타임 pip install 비활성화 주장에 대응하는 코드 변경 없음 | recordWEB.py:66, 32-38, 59-60 |
| test | HIGH | install_missing_modules 비활성화 주장을 반증할 Validate 없음 | recordWEB.py:66 vs plan Task1 |
| test | HIGH | requirements.txt가 실제 import와 불일치하는지 검증하는 부팅 확인 없음 | recordWEB.py:33-38 vs plan Task2 |
| security | MEDIUM | requirements.txt에 werkzeug/itsdangerous 누락(비밀번호 해시/세션 서명) | recordWEB.py:27,89 |
| security | MEDIUM | NAS 측 시크릿 디렉터리 권한 요구사항 없음 | plan Task4/5 |
| architect | MEDIUM | .dockerignore가 dependent/plugin(Linux에서도 쓰이는 순수 파이썬)까지 함께 제외 | module/live_recorder.py:504-509 |
| invariant | MEDIUM | 자격증명 NAS 이전에 rollback/backup 경로 없음, 로컬 인스턴스 중지 단계 없음(이중 녹화 위험) | plan Tasks 5-7 |
| invariant | MEDIUM | 포트가 GUI에서 편집 가능한데 compose/Dockerfile은 5000 고정 | recordWEB.py:2566 vs plan EXPOSE/ports |
| invariant | MEDIUM | checkRequiredPaths는 출력만 하고 종료하지 않음; ffprobe/aria2c는 부팅이 아닌 첫 녹화 시 실패 | recordWEB.py:237-251, data_manager.py:1083,1125 |
| test | MEDIUM | 포트 5000 하드코딩 가정이 반증 불가(config.json 값 미검증) | recordWEB.py:2566,2466 |
| test | MEDIUM | 성공 지표 검증(Task7)이 사용자 설정 가능한 filenamePattern에 의존해 위음성 가능 | module/live_recorder.py:355-363 |
| test | MEDIUM | checkRequiredPaths 미종료로 인해 Task6 검증이 로그 확인에만 의존 | recordWEB.py:243-251 |
| architect | LOW | "Linux는 PATH만 잡으면 코드 수정 불필요" 주장이 저장소 전역 사실은 아님(GUI 전용 경로 한정 영향) | module/replay_download.py:21-31 |

## Refutation attempted

| Perspective | Verdict | What was attacked |
|---|---|---|
| architect | fail | install_missing_modules 무조건 실행 여부, getDeno 가드 존재 여부, dependent/plugin 제외 여부, OS 분기 단일 출처 주장 |
| security | fail | loginMode 기본값과 배포 시 복사 여부, /cookies 인증 우회, requireLogin의 return-vs-raise, requirements 목록과 실제 import 대조 |
| test | fail | 각 Validate 명령이 계획의 핵심 주장(런타임 pip install 비활성화, 포트 고정, 성공 지표 파일명 패턴)을 실제로 반증할 수 있는지 |
| invariant | fail | deno 실패 모드의 실제 영향 범위, rollback/backup 경로 존재 여부, 포트 앵커링, checkRequiredPaths의 실질적 강제력 |
