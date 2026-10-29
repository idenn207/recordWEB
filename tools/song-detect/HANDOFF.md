# 라이브 노래 클립 추출 프로토타입 - 인계 문서 (2026-10-25 기준)

다음 세션은 이 문서와 메모리(`project_live_song_clip_detection.md`)를 먼저 읽고 시작한다.
범위: 정확한 라이브 클립 추출만. 유튜브 업로드와 녹화기/NAS 변경은 지금 범위 밖이다. NAS에는 아무것도 배포하지 않았다.
작업 규칙: 코드는 ponytail 방식(가장 작은 변경), 새 기능은 기존 파일을 고치지 않고 별도 파일로 분리, 단계마다 커밋.

## 1. 목표와 판단 기준

- 녹화본(수 시간~10시간)에서 스트리머가 MR/AR에 맞춰 직접 부른 라이브 노래만 클립으로 만든다. 음원 재생, 같이 보기, 다른 사람의 노래, 연습, 중도 포기는 제외한다.
- 오탐이 미탐보다 훨씬 나쁘다. 미탐은 다시보기에서 수기로 찾을 수 있다.
- 곡 길이: 하한 90초, 상한 6분(보통 5분 이내). 1절만 부른 곡(약 90~110초)은 클립 대상이 아니지만 짧은 랩(72~98초)은 정상 클립이라 길이만으로 구분할 수 없다.
- 듀엣/싱크룸/(w.)/같이 부르는 곡은 정당한 클립이다(예외).

## 2. 구현된 것 (tools/song-detect/, 폴더 구조는 12번 참고)

핵심 파이프라인(detect, refine, finalize, snap, scene*, route, practice, singer, vod, labels, eval_blind, test_*, Dockerfile, `paths.py`)은 이 폴더 바로 아래, 보조 스크립트는 `datasets/`(수집·색인·일괄 실행), `review/`(블라인드 검토 클립·보고), `experiments/`(평가·실험)에 있다. 하위 폴더 스크립트는 상위 폴더를 sys.path 에 넣어 core 를 import 하며, 항상 cwd = tools/song-detect 에서 실행한다. 아래 표의 파일명은 위 구분대로 폴더를 붙여 읽는다. `paths.py`: DATA(`data/`)와 CACHE(`cache/`) 상수와 `cache_of(wav, ext)`(탐지 중간 결과 위치 `cache/detect/<이름><ext>`).

파이프라인 순서: `detect.py` -> `refine.py` -> `scene.py`/`scene_dataset.py` -> `route.py`

| 파일 | 역할 |
|---|---|
| `detect.py` | 1단계 YAMNet(0.5초 간격 Speech/Music) 후보 -> 2단계 Demucs 보컬 스템 비율(5초 창) -> 노래창 -> 구간. 말소리가 낀 15초 이상 비노래 블록에서 곡 분리, 90~360초, Music 연속 구간으로 경계 확장, 겹치는 조각 병합. GPU가 있으면 GPU, 없으면 CPU 프로세스 풀(후보 단위 병렬). 중간 결과 캐시(`cache/detect/<이름>.scores.npy`, `.vocal.json`) |
| `refine.py` | 경계 재분석: 시작/끝 주변을 0.1초 간격 YAMNet으로 다시 돌려 Music이 가장 가파르게 오르내리는 지점으로 보정(bias_start=0.3, bias_end=1.6) |
| `scene.py` | 장면 게이트: 키프레임 48x27 회색 썸네일을 라이브 장면 기준 프레임과 비교(거리). 읽기 실패 시 빈 배열(= 통과시키지 않음) |
| `route.py` | 3단계 라우팅 auto/review/drop. 임계값 scene_ok 0.075, scene_drop 0.18, 길이 125~340초. `test_route.py` 통과 |
| `scene_dataset.py`, `vod.py` | 다시보기 데이터셋에 장면 게이트+라우팅 적용(같은 채널 다른 날짜의 길이 대응 구간을 기준으로 사용 - 아래 5번 한계 참고) |
| `fetch_vod.py`, `vod_index.py`, `run_dataset.sh` | 치지직 다시보기 수집(오디오 전용 m4a, 평균 7MB/s 상한, 연결 4개), 재생목록과 날짜 대조 색인, 일괄 탐지 드라이버 |
| `blind.py`, `blind_vod.py`, `rename_blind.py`, `cut_clips.py` | 블라인드 검토 클립 생성. 파일명 `YYMMDD_(스트리머_)HHMMSS-HHMMSS__ID` |
| `evaluate_refs.py`, `boundary_stats.py`, `dataset_eval.py`, `locate_refs.py`, `evaluate.py` | 평가: 나나 정답 위치 대조, 경계 오차 통계, 약한 라벨(길이) 데이터셋 평가, 정답 클립 위치 찾기 |
| `Dockerfile` | CPU 이미지 `song-detect`, GPU 이미지 `song-detect-gpu`(`--build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu124`), `test_detect.py`는 도커 안에서 실행 |
| `hum.py` | 곡 직전 안정 유성음(허밍) 검출 실험. 허밍 곡 2개 중 1개만 찾음(미완성) |

### 실행 방법

```
# 탐지 (GPU): vocal_thr=0.2 로 고정한 설정. data 와 cache 를 둘 다 마운트하고 paths.py 도 마운트한다(이미지를 다시 빌드하지 않을 때)
MSYS_NO_PATHCONV=1 docker run --rm --gpus all -v "$PWD/data:/work/data" -v "$PWD/cache:/work/cache" -v "$PWD/paths.py:/work/paths.py" -v "$PWD/detect.py:/work/detect.py" song-detect-gpu data/vod/<번호>.wav vocal_thr=0.2 --out=cache/exp8/<번호>.segments.json
# 경계 재분석 -> 장면/라우팅 -> 평가 -> 검토 클립
python scene_dataset.py cache/exp8r cache/exp9 ; python experiments/dataset_eval.py cache/exp9 ; python review/blind_vod.py cache/exp9 data/review/blind5
# 테스트
python test_route.py ; MSYS_NO_PATHCONV=1 docker run --rm --entrypoint python -v "$PWD/test_detect.py:/work/test_detect.py" -v "$PWD/detect.py:/work/detect.py" -v "$PWD/paths.py:/work/paths.py" song-detect test_detect.py
```
주의: git bash 에서 도커 -v 를 쓰는 명령은 반드시 `MSYS_NO_PATHCONV=1` 을 앞에 붙인다(없으면 경로가 변환돼 `detect.py;C`, `data;C` 같은 빈 폴더가 생긴다). 프로세스를 끌 때 명령줄 패턴이 자기 셸을 매칭하지 않게 한다(과거에 셸이 종료됨). 대량 다운로드는 `fetch_vod.py`의 속도 상한과 낮은 우선순위를 유지한다(메모리 `feedback_bulk_download_network_etiquette.md`).

## 3. 검증 결과

- 나나(10-06, 10-16, 위치까지 확인한 정답 21곡): 곡 분리와 병합 규칙 후 10-06은 12곡 중 11곡 적중, 쪼개짐·합쳐짐 해소(Adele, 자우림, 4:00 A.M.). 10-16은 랩 2곡 미탐(vocal_thr=0.2 기준), 같이 보기 9개는 장면 게이트로 제거.
- 독립 검증(파라미터 고정 후): 후야 10-19 재생목록 11곡이 탐지와 일대일 대응(길이 기준), 마시로 10-23 17곡 중 16곡 대응. 마시로 콘서트 5개와 후야 케로로 따라 부르기 1개는 장면 거리 0.080~0.116으로 라이브(<=0.07)와 분리됨(같은 채널 기준일 때).
- 곡 사이 경계 신호: 말소리가 낀 15초 이상 비노래 블록(10초로 나누면 랩 곡이 잘못 쪼개져 15초로 정함).
- 경계 재분석: 끝 경계 +-1초 이내 36%->55%(조정), 14%->57%(시험).
- 성능: YAMNet 1시간 8초. 병목은 Demucs. GPU(RTX 4070 Ti)는 CPU 병렬 대비 약 11배, KEEP 결과 동일.
- 다시보기 데이터셋: 25방송(149시간) 중 24방송 수집(시부키 10-18 8.5시간은 401 인증 필요로 제외). 오디오 단독 기준선은 재생목록 클립 44개 중 32개 대응, 탐지 102개.

## 4. 데이터 위치 (모두 .gitignore, data 약 42GB + cache 약 0.6GB)

- `data/` = 원본, 정답, 라벨만. `data/vod/<videoNo>.wav`(16kHz mono 오디오), `data/vod/legacy/`(NAS 녹화본과 구버전 수집분, 12번), `data/samples/user/`(사용자가 자른 정답 클립), `data/samples/clips/`, `data/review/blind*/`(블라인드 검토 세트: mp4, review.csv, key.json), `data/vods*.json`(스트리머/날짜/클립 길이 색인), `data/playlist*.json`, `data/refs*.json`(나나 정답 위치 등), `data/labels.json`, `data/vod_*.txt`
- `cache/` = 다시 만들 수 있는 것 전부. `cache/detect/<이름>.{scores.npy,vocal.json,segments.json}`(탐지 중간 결과), `cache/exp8`(탐지), `exp8r`(경계 재분석 후), `exp9`(장면+라우팅), `exp10/10r/10s`, `exp11/11r/11s/11f`, `exp_singer`, `scene_pool.npz/json`, `blind5_kf.npz`, `frames`, `.torch`(TORCH_HOME), `logs/`, `_tmp_check/`
- 나나 정답: `data/refs.json`(클립 위치), 블라인드 `data/review/blind2`~`blind4`(검토 완료), 검토 대기 클립 `data/review/blind5`(24개와 `review.csv`)
- 원본 영상은 치지직에서 날짜/제목으로 다시 받을 수 있다(`datasets/fetch_vod.py`).

## 5. 알려진 한계와 미해결 문제

1. 약한 라벨 평가의 신뢰도: 클립 길이(+-15%)로 짝지으면 탐지가 많은 방송(리코 10-20: 클립 1개에 탐지 17개)에서 우연히 맞는다. 이 짝으로 기준 프레임을 만들면 방송 시작 대기 화면(장면 거리 0.010)이 섞여 오염된다. 자동 등급 6개 중 5개가 그 대기 화면이었다. 이 데이터셋의 자동 등급 정밀도 수치는 신뢰하면 안 된다. 기준 프레임은 사용자가 승인한 클립에서만 만든다.
2. 못 거르는 오탐: 연습(MR/원곡 반복, 완주 없음), 중도 포기, 1절곡, 원곡 틀고 따라 부르기(장면이 같을 때), 같은 화면의 영상 시청.
3. 경계: 곡 직전 사운드체크/가사 체크가 앞에 붙고, 허밍/한마디 도입부가 YAMNet에 말도 노래도 아닌 소리라 놓친다(10-06 N33). 곡이 연달아 붙은 곳의 시작 오차가 크다.
4. 다인 곡(듀엣/싱크룸) 판별 수단이 없다.
5. 일반화: 정답 위치가 있는 건 나나 1채널뿐. 힙합/허밍/일본곡 외 다양성은 부족하다. 임계값(0.2, 0.075, 15초, 6분)은 소수 채널로 정했다.
6. 장면 게이트는 새 채널에서 기준이 없다 -> 전부 review. 일부 다시보기는 144p 영상이 CDN에서 응답을 멈춘다(읽기 실패는 review 처리).
7. `hum.py`는 실험 단계. 후야 10-19는 같은 날짜 VOD 2개(1.48h/3.98h)라 탐지가 중복될 수 있다.

## 6. 다음 개발 (우선순위순)

0. (완료, 8번 참고) blind5 채점. 다음은 8번의 새 부정 유형 대응.
1. 평가 하네스 정비: 승인 클립만으로 기준 프레임 구성(대기 화면 오염 제거), 방송/스트리머 단위 분할(leave-one-streamer-out), 부정 예시 라벨(같이 보기/따라 부르기/콘서트/연습/중도 포기/1절) 컬럼 추가, mir_eval boundary hit rate(+-0.5, 3초), 신뢰구간.
2. 다중 참조 장면 게이트 확장: 라이브/같이 보기/콘서트 군집을 승인 기반으로 누적, 채널별 임계값, 애매하면 review. 새 채널은 review 전용으로 시작.
3. 가수 프로필 게이트: Demucs 보컬 스템 + ECAPA 임베딩, 채널별 확정 곡 10~20개로 프로필. 낮으면 "다인 의심"으로 review(타인 음원은 0.5 이하, 라이브끼리 0.68~0.88로 측정된 바 있음, 듀엣은 미측정).
4. 경계 개선: 시작 경계의 곡 직전 사운드체크/가사 체크 제거, 허밍/한마디 도입부 처리(pYIN, 시작은 MR 시작 기준 고정 리드인 가설), 사용자 정답 클립으로 리드인 분포 측정, 연달아 붙은 곡의 시작 오차.
5. 연습/중도 포기/1절 판별: 참조 곡 정렬(DTW)로 완주율, 반복 시작 탐지, 90~125초는 review 유지.
6. 원곡 지문(audfprint류)을 거부 신호로만 사용(MR 라이브 오거부 위험, 음원 확보와 저작권 비용). 후순위.
7. 비용: Demucs 설정 경량화(overlap 0.25->0.1, shifts), NAS CPU 실측. ONNX/INT8은 후순위.
8. 나중에: 제목/카테고리/태그 변경 이력 로거(녹화기+NAS 배포 필요, 소급 불가라 시작이 빠를수록 좋음), 유튜브 업로드(비공개 기본, 쿼터 확인 - 문서마다 1 unit/일 100회 vs 1600 unit 상충, 콘솔에서 확인), 증거 카드/영상 ID 원장/롤백/감사 로그/드리프트 감시, 앱 통합과 채널별 토글.

## 7. 조사 보고서 요약 (Claude+Codex 워크플로우, 신규 수치는 우리 데이터로 측정한 값이 아님)

- 근거가 확인되지 않아 제외한 인용: AES 2020 live/studio 분류 논문, CtrSVDD의 EER 수치, SigLIP 2의 10-shot 우위 등.
- 필수 기능 체크리스트: 증거 카드, 비공개 기본 업로드+승인 후 공개, 영상 ID 원장과 일괄 회수, 중복 방지 키(원본+구간+모델 버전), 쿼터 계측, 드리프트 감시와 auto 자동 중지, 새 채널은 review 전용 시작, 검토 UX(시작/중간/끝 재생, 경계 조정).
- 정답 60곡에서 오류 0건이어도 오류율 상한은 약 4.9%(95% 단측)라 "오탐 0"을 안전의 증거로 읽지 않는다.

## 8. blind5 검토 결과 (2026-10-24, 사용자 라벨 반영: data/blind5/review.csv)

- 24개 중 라이브 8(V11 V12 V13 V14 V15 V16 V21 V22), 오탐 16. 전체 정밀도 33%.
- auto 6개: 라이브 3(V12 V13 V22, 장면 0.059~0.073), 오탐 3(V07 V08 V17, 장면 0.010 = 방송 대기 화면에 곡만 틀어둠). 5번 한계 1번이 현실로 확인됨. 대응: `route.py`에 scene < 0.03 이면 review(정지 화면 의심) 추가, 테스트 통과. 근거가 6개뿐이라 임계값은 잠정.
- review 18개: 라이브 5(V11 V14 V15 V16 V21), 오탐 13. 장면 게이트 없이는 review가 사실상 채점 불가 수준(새 채널/읽기 실패).
- 오탐 유형: 커버곡/타 스트리머 클립 같이보기 10(V01 V02 V03 V04 V05 V06 V09 V10 V20 V24, 화면에 영상을 띄움), 대기 화면에 곡 재생 4(V07 V08 V17 V18, 리코 커버곡 포함), 게임 OST 1(V19), 리듬게임 1(V23).
- 경계(라이브 8개 중 V21 제외 7개): 시작 오차 -4~+2초(전부 +-2초 허용 근처), 끝 오차 -11.9, -5.0, +0.3, +0.9, +1.2, +1.5, +7.6. 끝이 일찍 잘린 경우(V14 랩 -11.9, V15 음악적 종료 -5.0)가 늦은 경우보다 나쁨. V21은 앞에 사운드체크/인트로 연습 77초, 뒤 55초가 붙어 병합 실패.

### 새 도메인 규칙 (사용자)
- 해당 방송 스트리머 본인의 라이브만 클립. 타 스트리머의 라이브를 같이보기로 틀어도 제외한다(각 방송에서 이미 클립이 있어 중복). 다인 곡(듀엣/싱크룸)은 보통 한 방송에서만 진행하므로 중복이 안 생긴다. 제목 키워드: (w.), 같이, 합방 추가.
- 커버곡 같이보기: 유튜브에 올린 편집 영상을 화면에 띄움. 게임 OST: 게임 화면이 계속 움직이면 90%는 OST(멈춰 있으면 라이브 가능성이 있으나 클립 불필요).
- 대기 화면(방송 시작 대기, 자리 비움)에 곡만 틀어두는 경우는 오탐.
- 경계: 시작/끝 +2초 여유는 허용. 단 말하던 중간에서 시작/끝나면 안 되고, 음성이 없는 구간(+1.7, +0.6, +2.4 같은)에서 시작/끝나게 맞춘다. 종료는 MR 종료가 아니라 음악적 종료(강제 종료 후 애드립은 제외)일 수 있다.
- 토아 10-24 싱크룸 방송은 여러 사람의 라이브 클립이 섞인 테스트 자료(토아 목소리가 아닌 것 포함): 아직 미사용.

### 다음
1. 라벨을 부정 예시로 쓰는 평가 하네스(6번 1항)와, 승인 클립(V11~V16 V22 등)만으로 만든 기준 프레임.
2. 같이보기 판별: 화면에 영상 창이 크게 뜬 레이아웃 탐지(장면 거리 대신 승인된 같이보기 프레임 군집).
3. 경계 후처리: 끝이 일찍 잘리는 문제(랩, 음악적 종료)와 +-2초 내 무음 지점 스냅.

## 9. 후속 작업 결과 (2026-10-24, 워크플로우 wf_ebd5e696)

수치는 모두 blind5 24개(라이브 8, 스트리머 7명) 기준이며 임계값이 같은 표본으로 정해져 낙관적이다. 독립 검증은 blind6 라벨이 필요하다.
- 평가 하네스 `labels.py`, `eval_blind.py`: `python eval_blind.py blind5`. 현재 route 기준 auto 3/3 정밀도(리코 한 명뿐이라 스트리머 단위 분할에서는 일반화 근거 없음), review 5/21, auto+review 재현율 8/8. 경계: 시작 +-2초 적중 5/7, 끝 4/7, 끝이 일찍 잘림 2/7. 새 라벨은 `labels.py` 의 add 로 추가.
- 다중 참조 장면 `scene_multi.py`, `scene_new.py`, route.py 연결: 스트리머 단위 분할에서 오탐 15개 중 14개를 drop(같이보기 11, 대기 화면 3), 오탐이 live 로 통과 0건, 라이브 7개 중 5개 재현(2개 review). live 판정이어도 auto 금지(review 만). 임계값(5.0, 0.10, 40.0)은 22개 표본에서 정한 값이고 motion 이 가장 불안하다. 같이보기 V24 는 못 거름.
- 경계 `snap.py`(`python snap.py evaltable`, `selftest`): 끝 음악 절벽을 뒤 15초까지 찾아 늘리고 무음 지점으로 스냅. 끝 오차 최대 11.9초 -> 1.2초, 7개 모두 +-2초 이내. 같은 7개로 정하고 평가해 독립 검증 아님. 시작이 3~4초 이른 V11/V16(MR 인트로)은 그대로. V21 앞 연습 제거(trim_front)는 시험만, 끝 +55초는 미해결. 아직 파이프라인(detect/refine 다음)에 연결하지 않음.
- 신규 표본: 토아 10-24 싱크룸 + 6방송(3.7GB)을 data/exp10 -> exp10r -> exp10s 로 처리, 검토 클립 `data/blind6`(30개, key.json, review.csv, README.txt). 토아 14개는 장면 기준이 1개뿐이라 전부 drop(싱크룸 화면이 달라서)이지만 과차단 확인용으로 일부러 포함. V05 V10 V29 는 방송 0초 부근이라 대기 화면 가능성. 랑 10-19 는 6시간에 탐지 0개(미탐 미확인). 제목에 (w./같이/합방 인 방송은 없었음. `detect.py` vocal_ratio 에 파일 끝 넘는 후보를 막는 1줄 수정.

### 다음
1. 사용자가 data/blind6/review.csv 라벨 -> `python eval_blind.py blind6` 로 독립 평가(특히 snap, scene_multi 임계값 검증, 토아 싱크룸 drop 이 과차단인지).
2. 결과로 snap.py 를 detect/refine 흐름에 연결, scene_multi 기준 풀을 승인 클립으로 확장.
3. 남은 로드맵: 가수 프로필 게이트(다인 곡), 연습/중도 포기/1절 판별, 시작 경계 MR 인트로.

## 10. blind6 결과 (사용자, 2026-10-24) - 라이브 여부만 판정

- 30개 중 라이브 27, 오탐 3(V05 V10 V29, 전부 방송 시작 0~3초 대기시간 음원). 사용자 피로가 커서 **사람 검수 라운드를 더 요청하지 않는다.** 정답 근거는 사람이 검수한 라이브 클립 유튜브 재생목록(오탐보다 이쪽에 과적합하는 편이 낫다)과 이미 받은 라벨로 한정한다.
- 신규 규칙(사용자): 방송 시작 후 앞 5분은 대기시간(노래를 틀어둠, 재시작해도 0~3분 대기). 클립 대상 제외. `route.py` 에 start < 300초 이면 drop 추가(테스트 통과). 근거: blind5+6 에서 대기 오탐 7개 전부 start < 300초 이고 라이브 35개는 전부 start >= 594초라 임계값 300은 사용자 규칙이지 표본 맞춤이 아니다.
- 현재 route 로 blind6: auto 1/1, review 12/12 정확, drop 17개 중 14개가 실제 라이브(토아 싱크룸 14개 전부 장면 거리 0.28~0.31로 drop). 즉 오탐은 0이지만 라이브 재현율 48%. 토아 싱크룸 화면이 기준 프레임(blind5 토아 1개)과 달라 생긴 과차단. 사용자가 승인한 blind6 토아 라이브 14개의 키프레임을 같은 채널 기준에 추가하면 해소될 가능성이 크다(미구현, 오탐이 없다는 점에서 미탐 쪽 오류라 우선순위 낮음).
- 경계: 사용자가 말한 라이브 시작 V08 12초, V15 15초, V22 10초(클립 내 상대초). 우리 탐지는 20초 시작이라 5~10초 늦게 시작(앞부분이 잘림). blind5 에서는 오히려 3~4초 빨랐다. 시작 오차가 +-로 흩어져 있어 `snap.py` 시작 규칙(앞 2초만 봄)은 한계. 곡 앞부분 잘림이 더 나쁘므로 다음에 시작 경계를 MR/Music 상승 기준으로 재검토. 이 3개를 labels.py blind6 에 user 시작값으로 기록.
- 다음(사람 검수 없이): (1) 토아 라이브 14개 키프레임을 기준 풀에 추가해 재평가 (2) 시작 경계가 늦은 사례를 data/exp10r 파형으로 분석 (3) 유튜브 재생목록 정답과 길이/위치 대조를 늘리는 쪽으로 평가 (4) snap.py 를 파이프라인에 연결.

## 11. 어려운 표본 후속 작업 결과 (2026-10-25, 워크플로우 wf_2cae0484)

수치는 blind5+6(54개, 라이브 35) 등 소수 표본 기준이며 임계값은 낙관적이다.
- 장면 기준 풀 `scene_pool.py`(data/scene_pool.npz, 50클립 1337프레임), `scene_new.py` 가 이를 사용. 방송 단위 분할(엄격)에서 오탐 통과 0, auto+review 재현율 57%. 토아 싱크룸 14개 과차단은 같은 방송의 승인 클립이 풀에 1개라도 있으면 해소(prev1 분할 94%). 새 방송의 첫 곡은 여전히 drop 될 수 있음. 스트리머 단위 분할에서는 기준이 없어 전부 review(오탐 1개가 review 까지 도달: 마시로 커버 같이보기 V24).
- 시작 경계 `snap.py lead_start`: 곡 앞 10초에서 무음/말 끊김을 거슬러 올라가 첫 소리-1초에 시작(말 중간 금지, 늘린 구간의 Singing+Music 평균 0.25 미만이면 늘리지 않음). 토아 V08/V15/V22 앞잘림 +8/+5/+10초 -> -1.5/-1.6/+1.8초. 나나 18곡에서는 시작 변화 없음, 끝 쪽 소폭 악화(적중 13->11). `finalize.py` 가 detect->refine->finalize->scene->route 순서로 연결(멱등, 범위 이탈 시 원래 경계 유지, 결과 data/exp11f).
- 연습 `practice.py` rep_near(첫 12초 크로마의 +-150초 최대 유사도, >0.55 이면 review 전용): 라이브 85개 중 1개 걸림, 연습 1개 걸림, 중도 포기 2건은 못 잡음. 근거 표본이 부정 3개뿐이라 일반화 불가. 완주/끝 음량/페이드는 분리 안 돼 폐기. route 에는 연결하지 않음. 길이 125초 미만 review 규칙이 안전망.
- 가수 프로필 `singer.py`(ECAPA): 엄격 분할 AUC 0.50 = 효과 없음. route 연결 금지.
- 어려운 표본 `mk_vods11.py`, `run_hard.sh`, `scene_hard.py`, `hard_report.py`: 게임 방송 6개 추가 수집(exp11/exp11r/exp11s). 힙합 랩 41~72초는 90초 하한 때문에 구조적 미탐(재생목록 우사기 랩 3개). 스타크래프트 9개는 전부 watch/대기시간으로 drop(OST 의심). 리듬게임/OST 신규 표본은 없음. 마시로 마크 방송은 정답 16/16 후보 확보(전부 review, 채널 기준 없음 -> auto 불가).
- 다음: (1) 사용자 검수 7건(data/blind7/ASK.md)의 답으로 auto 임계 0.075, 포기/연습 규칙, 경계 가드 방향 결정 (2) 랩 하한(90초) 완화 검토 (3) finalize 를 일괄 실행 스크립트(run_dataset.sh)에 편입.

## 12. 폴더 정리 (2026-10-25) - 이전 경로 -> 새 경로

삭제 없이 이동만 했다. 이동 전후 data 파일 수 844개, 45,615,890,636바이트로 일치(같은 드라이브 rename). 코드는 `git mv`(커밋 전 상태).

코드:

| 이전 | 새 위치 |
|---|---|
| fetch_vod, vod_index, fetch_audio, mk_vods10, mk_vods11, run_all/run_dataset/run_hard/run_new.sh | `datasets/` |
| blind, blind_new, blind_vod, cut_clips, rename_blind, hard_report | `review/` |
| hum, evaluate, evaluate_refs, locate_refs, boundary_stats, dataset_eval | `experiments/` |
| (신규) | `paths.py` (DATA, CACHE, cache_of) |

데이터:

| 이전 | 새 위치 |
|---|---|
| `data/_samples/`, `data/clips/` | `data/samples/user/`, `data/samples/clips/` |
| `data/blind`, `blind2`~`blind7` | `data/review/blind*` |
| `data/20*.wav` (12개), `data/_vod/*` | `data/vod/legacy/` |
| `data/20*.{scores.npy,vocal.json,segments.json}`, `data/vod/*.{scores.npy,vocal.json}` | `cache/detect/` |
| `data/exp*`, `exp_singer`, `frames`, `ref`, `v1`, `_singer_probe`, `.torch`, `.ecapa` | `cache/` 같은 이름 |
| `data/scene_pool.npz/json`, `data/blind5/_kf.npz` | `cache/scene_pool.*`, `cache/blind5_kf.npz` |
| `data/*.log`, `exp11s_report.txt` | `cache/logs/` |
| `data/vods*.json`, `playlist*.json`, `refs*.json`, `labels.json`, `vod_*.txt` | 그대로 `data/` |

코드 쪽 변경: detect.py 캐시와 기본 출력은 `cache_of`, 장면 기준 풀과 키프레임은 `cache/`, 세트 폴더는 `data/review/<세트>`, 도커는 `-v data -v cache -v paths.py` 마운트와 `TORCH_HOME=/work/cache/.torch`. 명령줄 인자로 받는 segments 폴더(`exp8r` 등)는 이제 `cache/exp8r` 처럼 쓴다. 검증: `test_route.py`, `snap.py selftest`, `finalize.py selftest`, `eval_blind.py blind5 blind6`(경계 5/7, 4/7, 2/7 등 9번과 동일), GPU 도커 detect.py 캐시 히트(결과가 cache/exp8 과 동일)와 캐시 미스(cache/detect 에 생성).

### 중복 후보 (사용자가 지울지 결정, 지우지 않았음)
`data/vod/legacy/` 의 NAS 녹화 wav 와 `data/vod/` 의 다시보기 wav 를 Music 점수 시계열 상관(시작 오프셋 탐색)으로 대조했다.

| legacy 파일 | 크기(B) | 중복 대상 | 상관 / 오프셋 |
|---|---|---|---|
| 2026-10-17_랑.wav | 113,285,198 | vod/15724523.wav | 0.93 / -4초 |
| 2026-10-17_토아.wav | 107,554,894 | vod/15723636.wav | 0.93 / -29초 |
| 2026-10-18.wav | 101,051,128 | vod/15741625.wav | 0.81 / -87초 |
| 2026-10-18_어비스.wav | 110,766,158 | vod/15740846.wav | 0.89 / -83초 |
| 2026-10-19_후야.wav | 170,455,150 | vod/15761307.wav | 1.00 / 0 (크기 거의 동일) |
| 2026-10-20.wav | 1,128,388,686 | vod/15779422.wav | 0.94 / -50초 |
| 2026-10-23.wav | 621,275,214 | vod/15821901.wav | 0.90 / -46초 |
| 2026-10-23_마시로.wav | 658,602,788 | vod/15827672.wav | 1.00 / 0 (크기 거의 동일) |

wav 8개 합계 2.80GiB. 오프셋이 있는 6개는 같은 방송이지만 시작 시각이 달라 파일이 같지는 않다(나중 `finalize`/`snap` 입력은 vod 쪽 기준). 영상 `vod/legacy/2026-10-19_후야.mp4`, `2026-10-23_마시로.mp4`(합계 9.65GiB)는 위 후야/마시로 방송의 영상본이며 `scene.py` 의 로컬 장면 입력이라 중복이어도 당장은 필요하다. `15761307.json/.mpd`, `15827672.json/.mpd` 는 그 영상의 다운로드 메타.
중복이 아닌 legacy wav(vod 에 대응 없음): 2026-10-06_나나, 2026-10-16_나나(나나 정답 21곡의 원본이라 보존 필요), 2026-10-19, 2026-10-21.

## 13. blind7 반영과 현재 한계 (2026-10-25)

- 사용자 답변은 `labels.py` BLIND7 상수와 메모리에 기록(평가 하네스에는 연결하지 않음: V번호 클립이 아니라 개별 후보). 요지: 마시로 B1 B2 C1 C2 E 와 히나 D3(마인크래프트 버스킹)는 라이브, 후야 A(게임 중 따라 부르기, 끝 끊김)와 히나 D1(무반주 5초 후 음원) D2(타인 음원)는 클립 대상 아님. 토아 G 가창자는 토키노 메리(싱크룸).
- `datasets/run_dataset.sh` 에 finalize 단계를 편입(cache/exp8f). 다른 run_*.sh 는 아직 refine 까지.
- 후야 A 가 현재 auto 에 남는 유일한 비정답이다. 장면 거리 0.0728 이 라이브 V13(0.0727)과 같고, 끝 음량/페이드/반복 신호(practice.py 검증)도 분리하지 못한다. 오디오·장면만으로는 못 거르는 유형(게임 중 우발적 가창)이며, 대책은 새 채널은 review 전용 시작, auto 는 채널별 승인 이력이 있을 때만 허용하는 정책(미구현). 90초 미만 랩 하한 완화는 라벨 없이는 오탐이 늘어 보류.

## 14. pipeline.py 와 장면 drop 규칙 변경 (2026-10-25)

- `pipeline.py <wav> [--video] [--id] [--name] [--force]`: detect(GPU 도커) -> refine -> finalize -> 장면(승인 풀) -> route(known_neg 포함) -> auto 클립은 out/<id>/clips, review 클립은 out/review/<id>, 증거 카드 out/<id>/cards. 멱등(재실행 0.7초). 마시로 15827672, 후야 15761307 로 기존 결과와 구간 대응 확인(경계 이동 최대 7.5~8.6초). 단계 파일 락 없음, practice.py 미연결.
- 검증 중 발견: 같은 채널 다른 방송 기준과 화면이 멀면(게임 레이아웃 변경) 정답 라이브가 scene>0.18 로 drop 됐다(마시로 정답 재생목록 3곡 0.27~0.29 + blind7 승인 4곡). 규칙 변경: scene>0.18 이어도 다중 참조가 watch/idle 로 확정하지 않으면(live/unknown) drop 이 아니라 review. 방송 단위 분할 평가(`python scene_pool.py eval broadcast`): auto+review 재현율 57% -> 100%, 통과한 오탐은 review 의 V24(마시로 커버 같이보기, 기지의 한계) 1개, auto 오탐 0. 마시로 15827672 drop 29 -> 8.
- 주의: review 가 많아진다. review 는 업로드하지 않는 큐여야 하며 이 큐를 줄이는 방향이 다음 과제(승인 이력 누적, 채널별 기준).
- 짧은 랩 하한 실험(experiments/exp12_*): 90초 유지. 하한을 낮춰도 랩 3개 중 1개(마시로 10-23, 72초)만 잡히고 나머지는 YAMNet 이 Speech 로 읽어 오디오 게이트에서 탈락. 하한 60~70은 쪼개진 정답 곡 복원 효과(재현율 44/50 -> 46~48/50)가 있으나 review 가 33~49개(41방송) 늘어 보류. 권고: speech<=0.08 조건 병행 시 70부터 검토.

## 15. 대규모 표본(60방송) 결과 (2026-10-25)

- 수집: data/vod_meta.json(6651건, 치지직 카테고리/제목 메타), data/vods12.json(60방송 299.7h: game 14, song 18, talk 19, piano 9). 다운로드 한도는 사용자 허용으로 해제(fetch_vod.py 기본 45MB/s, 연결 24개; 사용자가 작업/스트리밍 중이면 낮출 것). 다운로드는 40분, 병목은 GPU 처리(run_big.sh + run_big2.sh 로 2개 병행). 결과 out/<videoNo>, 요약 cache/exp12_summary.json. 후보 649개: auto 18, review 411, drop 220(실패 0).
- 카테고리 사전확률: 근거 없음(게임/잡담 대응률 신뢰구간 겹침, 음악/노래는 정답 날짜 방송 1개). route 미반영, category_prior.py 는 틀만(보정값 0).
- 히나 피아노: 탐지기는 피아노 연주에도 후보를 낸다. 구분 신호는 Demucs other 스템 비율(`piano_gate.py`: vocal<0.5 이고 other>=0.45 이면 drop, 후보 151개 중 6개). route.py 에 piano 플래그 drop 연결, 단 cache/exp12p/other.json 이 있어야 동작(`python piano_gate.py scan <videoNo>`). 귀로 확인하지 못함 -> 사용자 검수 Q5~Q7.
- 나나 10-16 오삭제 교정: scene_multi 의 `blk>0.10 이면 watch` 가 나나 노래방 화면(검은 배경 blk 0.55~0.58)을 같이보기로 오판 -> watch 조건에 black_max=0.50 추가. 나나 정답 후보 7/7 이 drop -> review, 같이보기 11개는 그대로 drop. blind5/6 평가 전후 동일, 통과 오탐 변화 없음. 0.50 은 오탐 최대 0.434 와 나나 최소 0.505 사이 틈에서 정한 값(좁음). 정답 2곡(Vitas, JUSTHIS)은 후보 자체가 없음.
- 정답 대응은 길이 +-15% 가 우연과 구별되지 않아 증거로 쓰지 않음. 위치 정답이 있는 3개 방송(나나, 마시로, 후야)만 실증.
- 위험: auto 18개 중 토아 싱크룸 10-24 의 9개는 한 방송에서 연속이라 오탐이면 한꺼번에 틀림(가창자가 토아인지 불명, 검수 Q2~Q4). review 가 411개로 크다(song 층이 시간당 4.2개로 지배). 새 채널은 승인 이력이 쌓이기 전까지 review 전용.
- 사용자 검수 요청: data/review/blind8/ASK.md (7개 파일: 리코 1, 토아 싱크룸 3, 히나 피아노 3).
- 알려진 충돌: 히나 15831370 의 811초(재생목록 HEARTBREAKER 와 길이 일치)는 사용자가 blind7 D2 로 '타인 음원'이라 답함. 길이 대응은 우연일 수 있어 사용자 라벨을 따른다.

## 16. blind8 사용자 답변과 규칙 변경 (2026-10-25)

- Q1(리코 10-17 2304초): 라이브 아님. 원곡/음원을 틀고 따라 부르기(곳곳에서 곡 3개, 중간에 멘트). **원곡에 덧씌워 부르는 경우, 즉 같은 멜로디를 2명 이상이 부르는 클립은(듀엣/싱크룸 제외) 라이브 클립으로 세지 않는다.** data/known_negatives.json 에 등록. 일반화 신호(원곡 지문)는 후순위.
- Q2~Q4(토아 10-24 싱크룸): 가창자는 토아가 아님(메리+히요리 듀엣, 메리 단독, 랑 단독, 토아는 호응) 그러나 **싱크룸 방송은 가창자와 무관하게 모두 정상 라이브 클립**. 따라서 토아 싱크룸 auto 9곡은 오탐이 아니다. 사용자 경계: Q2 파일 00:57~04:28, Q3 00:59~05:48 이상, Q4 00:59~04:25 (파일 0초 = 후보 시작 - 60초). 우리 후보는 Q2 시작 +3초 늦음, Q3 끝이 최소 60초 일찍 잘림, Q4 끝 14초 일찍 잘림 -> 끝 경계 분석 진행(별도 작업).
- 피아노: Q5/Q6 은 직접 피아노를 치며 부른 라이브(실수해도 이어감) -> **선택 옵션으로 분리**. 기본 탐지/클립/검증 세트에서 제외(실수가 기본이라 검증 데이터에 섞으면 안 됨). 피아노만 연주하고 가창이 없는 곡 완주도 선택/낮은 중요도. Q7 은 피아노 MR 에 부른 일반 라이브(직접 연주 아님): 판별 단서는 피치 상승/실수가 없고 정박이며 마지막에 멘트가 이어지는 것이나 오디오로는 구분이 어렵다. piano_gate 는 Q5~Q7 모두를 의심(drop 에서 `optional` 등급으로 변경): route 에 `optional` 등급 추가, pipeline 은 out/optional/<id> 에 별도 보관(기본 clips 아님), 사람이 MR 형은 승격. 평가 라벨은 `labels.py` BLIND8 에 piano_live=live None(평가 제외).
- 싱크룸/듀엣/합방 판별 근거는 방송 제목 키워드(w., 같이, 합방, 싱크룸)와 카테고리 메타(data/vod_meta.json). 싱크룸 방송은 장면 기준 풀이 평소와 달라 drop 되던 문제를 위에서 review 로 완화한 상태.

## 17. 끝 경계 조기 절단 수정 (2026-10-25)

- 원인: 곡 중간 3~4초 Music 하락(음량은 곡 수준 그대로)을 snap 의 cliff 가 곡 끝으로 오인(Q4 -14초, 나나 ong-ver3 -10.8초). `snap.py bridge`: 하락 직후 1초 에너지가 곡 중앙값보다 6dB 넘게 낮으면 진짜 끝, 아니면 이후 15초 안에서 Music>=0.5 이고 Speech<0.3 인 프레임이 4초 이내 틈으로 이어지는 마지막 지점+2.5초로 연장(말 2홉 이어지면 중단, 최대 4회, 360초 초과면 포기). 끝 표본 48개: 일찍 잘림 3->1, 최악 -13.5초 -> -2.5초, 악화 0건. 6dB 는 하락 근거 2개라 과적합 가능성 큼.
- Q3(토아 4342초): 후보 끝(파일 4:48)은 MR 종료 지점이고 이후는 말소리(음정 안정도 0.0~0.35)로 오디오상 노래가 이어진다는 근거 없음. 사용자 확인: 곡 종료는 04:48 이 맞음(05:48 은 오기). MR 종료가 메리 감탄 소리에 묻혀 불명확하고 바로 멘트로 이어짐 -> 우리 후보 끝은 맞았다(Q3 끝 오차 0, 이전 '-60초' 서술 정정).
- Q2 시작 +3초 원인(사용자 확인): 보컬은 01:00 에 정확히 들어오지만 MR 은 00:57 에 시작, 앞 3초가 드럼 하이햇 2+4박(6번) 카운트인. 별도 lead_in.py 로 카운트인 탐지 실험 중(연결 전).
- 규칙 변경 후 전체 재실행: `sh datasets/rerun_all.sh <0|1> 2` (cache/detect 점수 재사용, --force).

## 18. 규칙 반영 후 전체 재실행 결과 (2026-10-25)

- 60방송 `--force` 재실행 완료(실패 0). 후보 649개: auto 17, review 420, drop 207, optional 5(히나 피아노 의심 4방송, out/optional). 이전(auto 18, review 411, drop 220)과 비교: 리코 Q1 drop(known_neg), 피아노 5개 optional, 나나 노래방 7곡이 drop 에서 review 로.
- 토아 싱크룸 15837908: auto 9, review 5. 싱크룸이라 auto 9곡 전부 정상 라이브(가창자 무관). Q4 후보 끝 3606 은 사용자 확인 끝(3606.5)과 일치, Q3 4342~4570 도 정답(04:48), Q2 시작만 카운트인 3초 늦음(lead_in.py 연결 전).
- 나머지 auto 8곡(마시로 09-22 1, 15724523, 리코 10-17 25213, 15750233, 15758902, 후야 4692, 15781033, 15812877)은 정답 대조 없음.
- 미연결: lead_in.py(카운트인, 근거 1곡), category_prior.py(보정값 0), singer.py(AUC 0.5), practice.py(review 전용 신호, 길이 규칙이 안전망).
- 다음: (1) auto 8곡 위험 점검(재생목록/정답 날짜 대조) (2) review 420 축소: 채널별 승인 이력 정책(새 채널은 review 전용 유지, 사람이 승인한 곡을 풀에 추가하는 UX) (3) 백그라운드 서비스화/녹화기 통합은 범위 밖.

## 19. 디바이스 토글 (2026-10-25)

- `yamnet_backend.py`: `scores_windows(pcm, starts, device)`. device = `auto|cuda|cpu`, 인자(`detect.py <wav> device=cpu`, `refine.py ... device=cpu`) 또는 환경변수 `SONG_DEVICE`(기본 auto = torch.cuda 가능하면 cuda). cpu = 기존 TFLite(결과 비트 동일, 청크 병렬 `yamnet_workers`=0 이면 min(4,코어)), cuda = yamnet.tflite 의 int8 가중치를 torch 로 옮긴 배치 추론(추가 의존성 없음).
- GPU 부하 제한: `SONG_GPU_LIMIT`(기본 0.8, 배치 사이 휴지), `SONG_GPU_MEM`(기본 0.8, VRAM 비율).
- detect.py/refine.py 는 yamnet_backend.py 가 없는 옛 마운트에서도 기존 TFLite 루프로 돈다(fallback). docker -v 목록에 `yamnet_backend.py` 를 추가해야 GPU 경로가 켜진다(pipeline.py 는 반영, datasets/run_*.sh 와 위 실행 예시는 아직).
- 테스트: `test_yamnet_backend.py`(도커 안).

## 20. 상주 분석기 서비스와 80% 리소스 상한 (2026-10-25)

요구: 방송마다 `docker run --rm` 으로 컨테이너를 켜고 끄지 말고 분석기 컨테이너 1개가 계속 떠 있을 것(PC Windows 와 NAS Linux 환경 차이를 줄이려고 도커를 쓴다). CPU, GPU(사용률, VRAM), 네트워크는 항상 최대치의 80% 이하(회선 500Mbps -> 50MB/s, NAS LAN 1Gbps -> 100MB/s, 논리코어 80%).

### 구조
- `analyzer_server.py`(컨테이너 안, 포트 8765): 시작 시 YAMNet(cuda 는 torch 가중치 변환, cpu 는 tflite)과 Demucs 를 한 번 올려 둔다(PC 20초 안팎). `POST /detect {wav, params, out, force}`, `POST /refine {wav, in, out, params}` -> `{job, queue_pos}`, `GET /health`(준비 여부, 디바이스, VRAM 최대/상한), `GET /jobs`, `GET /jobs/<id>`(상태, 진행 로그, 오류). 직렬 큐: GPU 는 동시 작업 1개(두 번째 요청은 큐에서 대기, 시험으로 확인), CPU 는 `SONG_JOBS`(기본 1). 경로는 `/work/...` 만 허용.
- `detect.detect(..., in_process=True)`: 후보마다 spawn 프로세스를 띄워 모델을 다시 올리던 ProcessPool 대신 상주 Demucs 로 호출(GPU 1 스레드, CPU 는 `workers` 스레드). 기본값(False)이면 기존 CLI 동작 그대로. `refine.refine_file()` 로 refine CLI 본문을 함수로 뺐다(CLI 결과 동일).
- `analyzer_client.py`(호스트): `ensure_up()`(없으면 `docker compose -p song-analyzer ... up -d` 를 한 번, 있으면 재사용, /health 대기), `detect()`, `refine()`, `status()`, `jobs()`. 호스트 경로를 프로젝트 폴더 기준 `/work/...` 로 바꾼다(프로젝트 밖 경로는 `Unavailable`). 서버가 작업 중 죽으면 ensure_up 으로 되살려 1회 다시 요청, 그래도 안 되면 `Unavailable`.
- `pipeline.py`: `analyze()` 가 `SONG_ANALYZER=service`(기본)이면 클라이언트를, 서비스를 못 쓰면(`Unavailable`) 또는 `SONG_ANALYZER=run` 이면 예전 `docker run` 을 쓴다(그 목록에 `limits.py` 마운트 추가). 작업 오류(`JobError`)는 폴백하지 않고 중단.
- `docker-compose.analyzer.yml`: 프로파일 `gpu`(이미지 song-detect-gpu, nvidia 예약, `SONG_DEVICE=auto`)와 `cpu`(이미지 song-detect, `SONG_DEVICE=cpu`, GPU 설정 없음). 컨테이너 `song-analyzer`, `restart: unless-stopped`, `cpus=${SONG_CPU_LIMIT}`(논리코어의 80%: `python limits.py cpus`), `mem_limit 10g`, `127.0.0.1:8765` 만 바인딩, 프로젝트 폴더 전체 `.:/work` 마운트(코드를 고치면 `docker restart song-analyzer` 만, 이미지 재빌드 불필요), healthcheck.
- `limits.py`: `SONG_LIMIT_PCT`(80), `SONG_INTERNET_MBPS`(500), `SONG_LAN_MBPS`(1000), `cpu_cores()`, `net_MBps()`. 서비스 GPU 가동률/VRAM 기본값(`SONG_GPU_LIMIT`, `SONG_GPU_MEM`)과 torch 스레드, `yamnet_backend.py` 기본값이 여기서 온다.

### 사용
```
# PC (GPU). 파이프라인은 ensure_up 으로 알아서 띄우므로 수동 시작은 선택
docker compose -p song-analyzer -f docker-compose.analyzer.yml --profile gpu up -d     # SONG_CPU_LIMIT 기본 16, 다르면 SONG_CPU_LIMIT=$(python limits.py cpus)
python analyzer_client.py            # 상태와 최근 작업;   docker logs song-analyzer
python pipeline.py data/vod/<번호>.wav      # SONG_ANALYZER=run 이면 예전 방식
# NAS (CPU, Linux). 이미지 song-detect 가 있어야 한다
SONG_CPU_LIMIT=$(python3 limits.py cpus) docker compose -p song-analyzer -f docker-compose.analyzer.yml --profile cpu up -d
# 시험용 별도 인스턴스(운영과 분리): SONG_ANALYZER_NAME=song-analyzer-dev SONG_PORT=8766 SONG_ANALYZER_PORT=8766 로 위 명령(-p song-analyzer-dev) 과 클라이언트 모두에 지정
```
Dockerfile 의 COPY 에 `limits.py` 를 넣었지만 마운트가 코드를 덮으므로 이미지를 다시 빌드하지 않아도 된다.

### 호스트 쪽 상한
- 네트워크: `datasets/fetch_vod.py` 기본 속도 45 -> `limits.net_MBps("internet")`(50MB/s). `datasets/nas_ingest.py` 의 ffmpeg 에 `-readrate`(= LAN 예산 100MB/s / 동시 수집 수 / 원본 비트레이트, NAS 61개 실측 0.80~1.06MB/s)와 `-threads 2`. `make_final.py` 는 http 입력에 `-readrate`(동시 2작업 가정, 약 45배속)와 `-threads`(코어 80%의 절반). `scene.py` 키프레임 ffmpeg 는 `-threads 2` + 낮은 우선순위(Windows). `-readrate` 는 ffmpeg 가 입력을 배속 단위로 읽는 방식이라 바이트 상한이 아니라 원본 비트레이트 가정 위의 상한이다(NAS 파일 20초 분량을 3배속 지정 시 0.6초 -> 6.8초로 확인). 파이썬 스로틀 파이프는 TS 가 임의 접근/재연결이 필요해 쓰지 않았다.
- CPU: 컨테이너 `cpus`(논리코어 20 중 16), torch 스레드 16 이하. GPU: 서비스가 배치 사이 휴지로 가동률 80%(`SONG_GPU_LIMIT`)와 VRAM 80%(`SONG_GPU_MEM`)를 건다.

### 측정 (이 PC: RTX 4070 Ti 12GB, 논리코어 20, 58분 안팎 방송 3개: 15724523/15740846/15741625 의 사본)
- 컨테이너 시작: run 방식은 방송당 2회(detect, refine) = 3방송 6회, 서비스 방식은 처리 방송 수와 무관하게 1회(첫 요청 때 ensure_up 이 시작, 그 뒤 재사용; 모델 로딩 20초는 서비스 시작 때 1회).
- 방송당 시간(detect+refine): run 67/52/55초 = 합 174초, 서비스 48/36/37초 = 합 121초(-30%; 모델 로딩/컨테이너 기동 방송당 약 15~20초 절감). 서비스 시작 1회분 20초는 별도.
- 결과 동일성: YAMNet 점수는 서비스와 run 이 비트 동일(최대차 0.0). 방송 2개는 1_detect/2_refine 바이트 동일, 1개는 5초짜리 drop 후보 1개 차이: Demucs `apply_model(shifts=1)` 가 파이썬 `random` 으로 시간 이동을 정해서 run 방식 자체도 실행마다 다르다(같은 방송을 run 으로 4번 돌려 11, 11, 11, 10개). 서비스도 같은 성질. pipeline 전체(detect, refine, finalize, 장면, 카드) 서비스 대 폴백 비교에서 1_detect 동일, 2_refine 은 한 구간 시작이 0.4초 달랐다(GPU 컨볼루션의 알고리즘 선택이 실행마다 달라지는 것으로 보임; 서비스/run 무관한 기존 GPU 경로의 성질).
- 80% (서비스, 두 방송 연속 요청, 250ms 간격 nvidia-smi, 시험 시 다른 앱의 GPU 사용 약 15% 포함): GPU 평균 사용률 68.4% (상한 해제 `SONG_GPU_LIMIT=1.0` 은 85.6%, 소요 46초 -> 57초), 순간 최대 98%(배치 단위 휴지라 순간값은 100% 가능: 250ms 표본의 57% 가 80% 초과), VRAM 서비스 최대 5378MiB / 상한 9825MiB, 컨테이너 CPU 평균 0.75코어(상한 16코어), 메모리 1.4GiB / 10GiB. CPU 프로파일(PC 에서 시험): 7분 구간 detect 중 docker stats 평균 700% 최대 924% (상한 1600%), 컨테이너 시작 23초.
- 두 번째 요청은 큐에서 대기(첫 작업이 끝난 뒤 시작, 대기 25초). 서비스 강제 종료(`docker kill`) 시험: 클라이언트가 재시작을 기다려 다시 요청해 68초에 완료, 결과 동일. 서비스 불가(이미지 없음) 시험: pipeline 이 docker run 폴백으로 끝까지 완료.

### 임시 제한기 gpu_governor.py 제거 방법 (이 PC 에서 아직 돌고 있다 - 메인이 정리)
서비스 내장 스로틀(SONG_GPU_LIMIT 0.8)이 있으므로 필요 없다. 오히려 `ancestor=song-detect-gpu` 인 모든 컨테이너를 `docker pause` 하므로 song-analyzer 도 얼려서 healthcheck 를 unhealthy 로 만들고 시간만 늘린다(시험 중 확인: 시험 컨테이너가 주기적으로 paused). 제거: (1) `Get-CimInstance Win32_Process | ? {$_.CommandLine -match 'gpu_governor.py 80'}` 로 PID 확인 후 종료(종료 시 일시정지된 컨테이너는 스스로 푼다), (2) `tools/song-detect/gpu_governor.py` 삭제, (3) `docker ps --filter status=paused` 로 남은 것 확인.

### 한계
- GPU 가동률은 배치 사이 휴지 방식이라 평균은 80% 이하여도 1초 미만 순간값은 100% 가능(전력 제한 nvidia-smi -pl 은 관리자 권한 필요). 같은 PC 의 다른 프로그램 사용분은 보지 못한다.
- 프로젝트 폴더 밖 wav/출력은 컨테이너에 마운트돼 있지 않아 run 방식으로 폴백한다. 컨테이너는 root 로 쓰므로 Linux(NAS)에서는 cache/ 와 out/ 파일 소유자가 root 가 된다.
- 네트워크 상한은 앱(ffmpeg, fetch_vod) 단위다. `make_final.py --jobs` 를 2보다 올리면 READRATE 도 조정한다. 작업 기록은 서버 메모리에만 있어 재시작하면 사라진다(cache/detect 캐시는 남는다). 인증 없음(127.0.0.1 바인딩 전제).
- NAS(CPU 프로파일)는 이 PC 에서 CPU 프로파일로만 시험했고 실제 NAS 배포/실측은 하지 않았다.

## 21. 방송 자신 풀 제외, 나나 승격, likely, 여유 규칙, review 전체 완성본 (2026-10-26)

- 누수 제거: NAS 슬러그(YYYY-MM-DD_이름_n)의 (스트리머, 날짜)와 같은 풀 항목은 장면 기준/다중 참조에서 뺀다(`scene_pool.excluder("date", ...)`, `pool()` 이 항목마다 date 를 채움, `pipeline.py` 4_scene 단계). 나나 10-06 의 review 12개가 '정지 화면 0.000' 이던 원인(자기 방송 정답 프레임)이 사라졌고, 자기 방송을 뺀 나나/토아 10-24 는 기준 이력 부족이라 '새 채널' review 가 된다. 토아 10-24 싱크룸 auto 9곡은 이 때문에 review 로 내려갔다(사용자 규칙상 정상 라이브지만 NAS 시간축 정답이 없어 known_pos 로 못 올림). 영상번호 방송(VOD)은 기존 동작 그대로. `datasets/reroute_nas.py` 는 풀에 같은 스트리머+날짜가 있는 방송만 4_scene 을 지운다(`--all` 이면 전부).
- 나나 known_pos: data/refs.json 은 legacy wav 시간축이고 data/vod/nas/<슬러그>.wav 는 그 파일의 하드링크(inode 동일, 오프셋 0). `cache/exp15/mk_approved.py` 가 videoNo 자리에 슬러그 문자열을 넣은 항목을 추가(route.known_pos 는 str 비교라 코드 변경 불필요). 승인 경계와 후보 경계가 10초 넘게 어긋나면 auto 가 아니라 review(근거 코드 BD)로 남기고 `ref_bd` 를 카드에 기록.
- likely: `route.mark_likely`(review, multi==live, 125~340초, 5분 이후, 1시간 안 후보 20개 미만). `scene_pool.py eval broadcast` 끝에 정밀도 집계가 붙는다(blind5/6: 25/25, 합산 blind5/6/7/8: 28/29 = 97% [Wilson 83-99%], 오탐 7A 후야 게임 중 따라 부르기 1개). 카드에 `likely` 표시만 하고 별도 폴더는 만들지 않는다(make_final `--likely`, `--no-ctx` 옵션은 남겨 둠).
- 완성본 규칙 v2-pad(`make_final.RULE`, json.rule 이 다르면 재생성): 곡 시작 앞 2초 안의 마지막 말소리 뒤 공백 중 가장 긴 것의 시작+50ms 에서 진입(0.3초 미만이면 여유 없음), 끝 뒤 2초 안의 첫 말소리 앞 공백 중 가장 긴 것의 가운데에서 종료, 끝 여유가 0.8초 이상이면 곡 끝부터 페이드. 후보 공백 목록/선택/실제 여유는 json 의 lead/trail. 인코딩 사이에 인코딩 시간의 25% 휴지(nvenc 약 80%).
- 산출: out/final(auto), out/final_review(review, 파일명 끝 _R_코드[-L]), out/final_optional(optional, 현재 0개). `python datasets/final_nas.py auto review optional`, 점검과 INDEX 는 `python datasets/index_final.py`(out/final/INDEX.md). review 곡당 약 2.3분(HTTP TS 시킹+디코드 병목, nvenc 사용률 8%): 104곡 약 4시간.
- 한계: 공백 판정은 snap.quiet 기준(곡 중앙값보다 25dB 낮음 + Speech<0.3)이라 배경음이 큰 방송은 여유가 0 이 된다(117곡 중 앞 57, 뒤 75곡). 앞 곡 소리 조각은 말소리만 가려낸다. likely 표본은 사전 선별된 블라인드 세트라 낙관적.

## 22. 세션 마감 인계 (2026-10-26) - 새 세션은 이 절부터 읽는다

> 2026-10-27 갱신: 아래 '현재 상태'의 v3-pad, 0.8초 페이드, 리미터 -1dBFS, auto 13/review 104 는 낡았다. 최신 상태는 23~25절(규칙 v4-faithful, 리미터 기본 꺼짐, auto 40/review 23).

### 현재 상태
- 분석기: 상주 컨테이너 `song-analyzer`(GPU, restart unless-stopped, 127.0.0.1:8765, `python analyzer_client.py` 로 확인). 재부팅 후 Docker Desktop 이 켜지면 자동 복구. pipeline.py 는 서비스를 쓰고 실패하면 `docker run` 폴백. 리소스 상한은 항상 80%(limits.py, 사용자 요구: CPU/GPU/네트워크).
- NAS 10월 녹화(61방송, 338h)는 PC 에서만 처리했다(NAS 는 원본 읽기 API 만). 결과 out/<슬러그>/, 카드 out/<슬러그>/cards/*.json.
- 완성본 클립(규칙 v3-pad: 시작 앞 최대 2초/끝 뒤 최대 2초의 가장 긴 음성 없는 공백, 끝 0.8초 페이드, 리미터 -1dBFS): `out/final/`(auto 13곡 47.9분, 정식), `out/final_review/`(review 104곡, 사용자가 직접 듣고 판단하는 미검증 클립), `out/final_optional/`(피아노 의심, 현재 0). 목록 `out/final/INDEX.md`(스트리머/방송/곡/여유/근거), `data/nas_review_list.md`. v3 여유 분포: 앞 평균 0.88초(0초 32곡, 0~1초 38, 1~2초 47), 뒤 평균 0.45초(0초 34, 0~1초 80, 1~2초 3). 117곡 점검 전부 ok(컷 오차 0.1초 이내, A/V 싱크).
- 속도: 완성본 인코딩은 NVDEC+nvenc p3 로 곡당 약 30초(이전 2.3분: `-readrate` 가 처리를 3배 늦췄던 것이 원인, 제거).
- 정리 대기(삭제하지 않음): `out/stale_not_v3.txt`(이전 규칙 json 70개 목록, 같은 곡의 새 파일과 이름이 달라 중복으로 남음), `out/final_test/`(1.5GB 시험 산출물), `out/review/`(옛 미리보기 3.9GB), 낡은 NAS 미리보기 36개.
- 재개: `python datasets/final_nas.py auto review` (멱등, 끝난 곡은 건너뜀). 전체 재계산: `python datasets/reroute_nas.py` 후 필요 시 pipeline `--force`.

### 사용자가 곧 할 일(결과가 오면 반영)
- review 104곡(방송 시간순)을 직접 듣고 판정할 예정. 판정(라이브/아님/경계)이 오면: 라이브는 `data/approved.json` 승인 + `python scene_pool.py build`(채널 승인 이력 축적, 새 채널 auto 해금), 아님은 `data/known_negatives.json` 등록, 유형이 모이면 규칙화, 경계 지적은 snap.py/make_final.py 여유 규칙에 반영, labels.py BLIND9 로 기록 후 `eval_blind.py` 재평가. 사람 검수 요청은 최소화(사용자가 지침을 줌: 정말 판단이 안 되는 것 최대 10개, 풀영상 맥락, 파일 수=질문 수).

### 남은 개선 후보(우선순위순)
1. 여유 0초 곡(앞 32, 뒤 34) 원인 점검: 음성 없음 기준(Speech<0.3, Singing 낮음)이 배경음/게임 소리에서 안 맞는 곳. 사용자가 들어 본 피드백으로 기준 보정.
2. 토아 10-24 싱크룸 14곡은 승인 이력 누수 제거로 review 에 있음(싱크룸은 가창자 무관 정상 라이브). 사용자 판정 후 approved 로.
3. 나나 정답 6곡은 경계가 10초 넘게 어긋나 review(BD): 4:00 A.M. 끝 +82초, 야상곡 끝 -48초, Mama Lisa 시작 +31초 등. 후보 쪽/정답 쪽 중 어느 쪽이 맞는지 사용자 청취로 확인.
4. 미탐: 90초 미만 랩(YAMNet 이 Speech 로 읽음), 나나 정답 5곡 후보 없음. 연습/1절/게임 중 우발 가창은 known_neg 로만 대응.
5. NAS 배포(CPU 프로파일 compose 는 PC 에서만 시험, 실제 NAS 미배포), 녹화기와의 통합, 유튜브 업로드는 범위 밖(HANDOFF 6번 8항).
6. lead_in.py(카운트인 시작 보정, Q2 한 곡 근거)는 비활성: 연결 방법은 HANDOFF 17~18번.

### 주의
- git: `git commit -a` 금지(스테이징된 무관 삭제 60개가 섞임). 파일을 지정해 `git commit --only`. tools/song-detect 외 변경은 이 작업과 무관.
- 도커 -v 명령은 git bash 에서 `MSYS_NO_PATHCONV=1` 필수(없으면 `detect.py;C` 같은 빈 폴더 생성).
- 에이전트를 돌릴 때 GPU 작업이 겹치지 않게(80% 상한, 동시 GPU 작업 1개), `docker stop` 은 이름을 지정해서만.
- 메모리: project_live_song_clip_detection, feedback_limit_user_review_burden, feedback_resource_cap_80pct, feedback_bulk_download_network_etiquette.

## 23. blind9 경계 규칙 구현 (2026-10-27)

- `snap.snap(pcm, a, s, e, voc=None)` 에 규칙 5개를 넣었다(순서: 절벽/이음 E2 -> 무음 스냅 -> E1 -> E3 -> 시작 lead_start -> S1 아니면 S2). `voc` = `snap.voc_of(wav)` (cache/detect/*.vocal.json, 없으면 S1/S2 쉼). `finalize.fix(pcm, a, g, voc)`, `pipeline.py` 가 voc 를 넘긴다.
  - E2: `_bridge` 의 절벽 직후 에너지 검사를 1초 중앙값 -> 3초 평균(박수/외침 오탐 방지). E1: 끝 프레임이 Music>=0.85 & Speech<0.2 이면 gap 2초 이하로 이어지는 끝까지 연장(4초 이상, 90초 안). E3: 끝 앞 40초 안 마지막 깊은 무음 뒤 4초가 조용하면 무음 시작에서 끝. S1: 시작 뒤 40초 안 마지막 MR 정지(2초 이상) 뒤 -1초(정지 앞 보컬 비율<0.35, 뒤 90초 이상). S2: 시작 앞으로 vocal>=0.6 & Music>=0.2 & Speech<=0.1 창을 최대 30초.
- 측정: `python experiments/blind9_bounds.py rules <out.json> [E1,E2,E3,S1,S2|none]` (실제 흐름 snap -> fix -> snap_quiet, `none` 은 현재 경계를 정확히 재현) 후 같은 경로 평가. 회귀 점검 `python experiments/regress_snap.py`(전 방송 840구간, 규칙별 이동 수, 약 2분).
- 결과(blind9 평가 49곡, 숫자 정답 대략값 제외 6건 평균 |오차|): 17.2 -> 1.5초. 방향 일치 끝 early 0/12 -> 3/12, 끝 late 0/2 -> 2/2, 시작 early 0/4 -> 3/4, 시작 late 0/9 -> 3/9. ok 곡(끝 31, 시작 36)은 전부 2초 안 유지. snap evaltable(blind5/6) 변화 없음, evalnana 시작 12->13, 끝 12->14.
- 한계: 정답 없는 840구간 중 E1 34, E2 23, E3 33, S1 25, S2 49개가 1초 넘게 움직인다(대부분 N/BGM 이거나 정답 없음, 사람이 확인하지 않음). 안 풀린 곡: 끝 early 9곡(#18 #20 #22 #54 #63 #65 #71 #82 #142), 시작 late 6곡, 시작 early #111. 완성본 재생성(RULE 이 v4-faithful 이라 기존 out/final* 은 이전 경계)과 pipeline 3_final 재계산은 아직 안 했다.

## 24. v4-faithful 재생성 결과 (2026-10-27)

- 실행: 61방송 전부 `SONG_LIMIT_PCT=100 SONG_NOCLIP=1 python datasets/reroute_nas.py 3 --final`(3_final.json 과 4_scene.json 삭제 후 snap/finalize 재적용, detect/refine 은 캐시 재사용, 미리보기 클립은 생략) 593초. 이어 `final_nas.py auto` 와 `final_nas.py review` 를 동시에 2프로세스로 실행 2127초(63곡, auto 는 ctx20 포함 80파일). 분석기 컨테이너는 재시작하지 않았다(GPU 분석 작업이 없었고 호스트 쪽 ffmpeg/nvenc 만 썼다. 상한은 프로세스 환경변수로만 해제했으므로 되돌릴 것 없음, 컨테이너는 계속 80%).
- 등급 전/후: auto 13 -> 40, review 104 -> 23, drop 74 -> 128 (후보 191개 동일). auto 40 = 사용자 승인 라이브 24(blind9) + 재생목록 위치 정답 15 + 기타 1. review 23 = 경계 문제 판정(B) 19 + 경계 어긋남 3 + 새 채널 1. drop = 다중 참조 watch 65, 확인된 비대상 55, idle 6, 대기시간 2. weak review 는 0이라 제외된 곡 없음. 이 수치는 blind9 표본에 과적합된 결과다(사용자 허락): 새 방송에서는 review 가 다시 늘어난다.
- 완성본: out/final 40곡(+ctx20) 15GB, out/final_review 23곡 5.4GB, 63곡 모두 check ok(dur/start/end 오차 0), 리미터 꺼짐. 목록 `out/final/INDEX.md`. 이전 규칙 파일은 `out/stale_v3/{final,final_review}`(45GB, 목록 `out/stale_v3/LIST.txt` 229개 mp4)로 옮겼다(삭제 안 함).
- 경계(blind9 49곡, `experiments/blind9_bounds.py`, 소스는 auto+review 병합): 숫자 정답 6건 평균 오차 17.2 -> 1.5초(3초 이내 0 -> 5건), 끝 early 0/12 -> 3/12, 끝 late 0 -> 2/2, 시작 early 0/4 -> 3/4, 시작 late 0/9 -> 3/9, ok 곡(끝 31, 시작 36) 전부 유지. 23절의 snap 단독 측정과 같다(실제 파이프라인에서 재현됨). 전/후 원자료 `cache/pre_v4/bounds_{before,after}.txt`, 백업 `cache/pre_v4/<슬러그>/`.
- 사용자 지적 클립: 60(끝 -33.3초), 112(끝 -5.6초), 47(시작 +24.1), 51(시작 +7.9)은 정답 방향으로 이동. 19, 130(페이드 너무 빠름)은 경계가 아니라 새 페이드 규칙(곡 끝 이후 1초)으로 해결. 70, 82, 141(끝 early), 53(시작 late)은 이동 0(23절의 미해결 항목 그대로).
- 음량: 클립 대 NAS 원본 wav 구간 mean volume 차 +0.2~0.5 dB, max 동일(리미터 꺼짐, 눌림 없음).
- 한계: INDEX.md 가 클리핑 의심 26곡을 표시(원본 자체가 0dBFS 근처, 리미터를 껐으므로 의도된 결과). 정답 없는 구간의 이동은 사람이 확인하지 않았다.

## 25. blind9 리뷰 판정 반영 (2026-10-27) - 새 세션은 이 절과 23, 24절을 먼저 읽는다

(작업 지시서에서는 '23번 절'이라 불렀지만 23, 24절이 이미 있어 25절로 둔다.)

### 사용자 판정과 등록
- 145개(v3-pad 117 + 이전 규칙 stale 28, 같은 곡이 길이 1초 차이로 중복): L 34, B 36, N 75. 중복 제거 104곡 = L 25, B 24, N 55. 같은 곡의 L/B 가 갈린 1건은 B.
- N 유형: 자리비움 BGM 9, GTA 노래방 9, 타 스트리머 라이브 같이 보기 10, 커버 같이 보기 4, 리듬게임 8, 게임 OST 6, 따라 부르기 3, 잡담 중 BGM 5, 같이 듣기 1.
- 등록: labels.py BLIND9(키 `슬러그_시작초`, L 은 boundary_ok=True, B 는 False), `data/known_negatives.json` 2 -> 57건, `data/approved.json` 151건(B 는 boundary_ok=false 라 auto 근거 제외). 등록 도구 `experiments/mk_blind9.py`. data/*.json 은 .gitignore, 백업 `cache/*.bak.json`.

### 규칙 변경과 수치
- route/scene_multi: 영상 움직임 tstd > 34.5 면 watch drop(기존 40). 25 <= tstd <= 34.5 는 live 로 안 올리고 unknown + weak(카드에 기록, likely 제외, make_final 은 weak review 를 만들지 않음). 근거는 shortcut: 주석(라이브는 전부 tstd < 25, N 은 43개가 25 이상).
- likely 정밀도(중복 제거 기준): 61%(41/67) -> 79%(41/52) -> speech < 0.06 추가 후 91%(40/44). 남은 오탐 4개는 tstd 15~17 의 멘트 없는 배경음이라 신호로 못 가른다(known_negatives 로만 대응).
- N 75개 모두 known_neg 로 겹침 매칭되어 drop. 라이브 손실 0. 장면 풀은 blind9 클립 104개를 더해 208(키프레임 6032)로 확대.
- 한계: weak 대역 때문에 blind5/6 의 25~34.5 대역 라이브는 live 에서 unknown 으로 내려간다(review 유지). scene_multi LOSO live 재현율 4/7(이전 값 미확인).

### 오디오와 페이드 (make_final.py, RULE v4-faithful)
- 원본 음량 유지: 리미터는 기본 꺼짐(`--limiter` 또는 SONG_LIMITER=1 일 때만, json 에 기록). 덕킹도 하지 않는다.
- 종료 페이드: 곡 소리는 깎지 않는다. 컷 = max(기존 여유 컷, 곡 끝 + 1.0초), 페이드는 곡 끝에서 시작해 길이 min(1.5, 컷 - 곡 끝)(1.0~1.5초). 오디오와 영상이 같은 시각/길이. json 에 fade=[시작, 길이].
- 한계: 곡 끝 직후 1초 안에 말이 있는 곡이 41%. 페이드로 거의 가려지나 완전히 제거되지는 않는다. 컷 직전 0.3초만 짧게 페이드하는 변형은 사용자 청취 비교가 필요해 미구현. 리미터 펌핑은 시험 곡 1개(나나 10-06 #01)에서 재현 안 됨(on/off 차 0.04dB).

### 경계 개선과 재생성 결과
- 경계 규칙 E1,E2,E3,S1,S2 는 23절, 전체 재생성은 24절. 요약: 숫자 정답 6건 평균 오차 17.2 -> 1.5초, auto 13 -> 40, review 104 -> 23, drop 74 -> 128, 완성본 63곡 전부 check ok. 이 수치는 blind9 표본에 과적합된 결과(사용자 허락).
- 완성본: out/final 40곡, out/final_review 23곡, 이전 규칙은 out/stale_v3. 요약 파일 out/READ_ME_FIRST.md.

### 남은 과제
- 경계 미해결: 끝 early 9곡(#18 #20 #22 #54 #63 #65 #71 #82 #142), 시작 late 6곡(#50 #54 #58 #65 #129 #144), 시작 early #111. 근본 해결 후보(detect gap_s 20 -> 30, E1 6초 grace)는 GPU 재탐지가 필요해 보류. #70/#71 은 MR 이 말 아래에서 계속되는 경우라 YAMNet 으로 불가.
- 자리비움 BGM 과 tstd < 25 오탐은 신호로 못 가려 known_negatives 등록만으로 막는다. 새 스트리머/새 방송에서는 review 가 다시 늘어난다.
- 이동량이 큰 경계(#127 시작 -14.3초, #20 -9.2초, S1 최대 +40초)와 정답 없는 840구간 중 이동한 곳은 사람이 확인하지 않았다.

### 사용자가 곧 할 일
- out/final_review 23곡(대부분 B 판정 19곡)과 이동량 큰 몇 곡만 청취 확인. 판정이 오면 approved/known_negatives/BLIND9 에 반영 후 `eval_blind.py blind9`.
- 정리 대기(삭제 안 함): out/stale_v3(45GB), out/stale_not_v3.txt, out/final_test, out/review.

### 리소스 상한
- 사용자가 2026-10-27 09:00 까지 PC 를 쓰지 않아 작업 프로세스에만 SONG_LIMIT_PCT=100 을 줬다. 분석기 컨테이너는 계속 80% 라 되돌릴 것이 없고, 09:00 이후 모든 작업은 80% 상한(limits.py)을 따른다.

## 26. P2 끝 경계 보강 (2026-10-28, PLAN_NEXT 4절 P2)

조건(채택 기준): (a) `python experiments/golden_gate.py` 이탈 0, (b) `python experiments/memo_audit.py` 끝 early 곡 hit@3 개선(저장본 기준), (c) `python experiments/regress_snap.py -c` 전 방송 840구간 이동 목록에서 N/BGM 연장 부작용 확인. 셋 다 만족한 것만 채택, 기각은 기록. 모든 경계 판단은 `experiments/end_view.py`(스펙트로그램 + 0.25초 rms + 점수)를 Read 로 직접 보고 했다(귀로 듣지는 못함). 원자료: `cache/p2_*.txt`, `cache/p2/*.png`.

### 채택 1. E1b (snap.env_end, 끝 연장) - 커밋 e920318
- 이식: g1_envelope_end.py 의 2단계(Music>=0.5 틈 5초, 소리 >= 곡 중앙값-12dB) + 직후 감쇠 확정. 시험판 그대로는 전 방송에서 49구간이 움직였고 승인 L(15086957@7143 +58초)이 깨져서 가드를 추가했다.
- 가드(전부 일반 규칙, 등록부 무관): (1) 끝 앞 30초 vocal 비율 평균 >= 0.5(노래 도중에 잘린 끝만, 곡이 끝나고 BGM/MR 이 이어지는 경우 제외: 승인 곡 7143 은 0.11), (2) 연장 중 2초 중앙값이 곡 중앙값-15dB 아래로 내려가면 거기서 중단(9667909@13682 는 13880 에서 끊기는데 Music 점수가 남아 +120초 가던 것이 +75초로), (3) 직후 확정은 -15dB 아래, 또는 말이 얹혀도 -6dB 아래일 때만(소리가 그대로인 MR 위 멘트 #70/#71 류는 안 붙임), (4) 곡 360초 초과 불가, vocal.json 없으면 쉼.
- finalize 길이 안전장치 2배 -> 2.5배(MAXRATIO): #20 이 2.22배라 snap 전체(S2 시작 포함)가 통째로 취소되고 있었다. 전 방송 840구간 sweep 에서 1.6배 넘는 결과는 4개(2.22 #20, 1.99 #25, 1.78, 1.76)뿐이라 다른 곡은 새지 않는다.
- 기각: 계획서의 '연장 상한 곡 길이 +20%'. 상한을 걸면 #18(+19%)만 통과하고 #25(+49%), #20(+113%), #26 이 안 풀린다. 대신 위 보컬/절벽 가드와 sweep 확인으로 대체.

| 변경 | memo_audit engine hit@0.5/3/10 | 중앙 abs 오차 | 방향(dir) | 길이 오차>5초 | golden 이탈 | sweep E1b 이동(비drop) |
|---|---|---|---|---|---|---|
| 시작(P3 저장본) | 4 / 7 / 9 | 1.9 | 11/27 | 3 | 0(화이트리스트 1) | - |
| 시험판 그대로(가드 없음) | - | - | - | - | 2(7143 +58) | 38구간(다른 규칙과 함께), 비drop 14 |
| + 보컬/직후 가드 | - | - | - | - | 0 | 11구간, 비drop 6(미확인 3) |
| + 2초 절벽 중단 + finalize 2.5배 | 5 / 9 / 11 | 1.9 | 13/27 | 2 | 0 | 10구간, 비drop 6 + drop 4 |

- 끝 early 중 숫자 정답이 있는 곡은 20, 24(23), 26(25), 49(48) 4곡뿐이고 4곡 모두 hit@3 이다(계획서의 '9곡 중 5곡'은 정답이 있는 곡이 4곡이라 불가능한 기준이었다). 오차: #20 끝 -150.0 -> +2.4, #26 끝 -99.5 -> 0.0, #24 +0.5, #49 -0.9 유지. 정답이 없거나 unresolved 인 22, 63, 65, 71, 82, 142 는 이동 없음(규칙을 바꾸지 않음), #18 은 일반 규칙으로 +19.5초 움직였다(오디오로 확인 가능한 부족분과 일치, 메모 '1분'은 미확인이라 unresolved 유지).
- memo_audit 의 '수동 감사 판정 13/13 일치'가 11/13 으로 보이는 것은 #20 끝, #26 끝이 수동 판정(실패)에서 이제 통과로 바뀌어서다(의도한 개선).
- 스펙트로그램 자체 검수(E1b 로 연장된 곡): #18 (10484.0: 10464 는 곡 한가운데였고 10483.5 에서 감쇠 끝), #20 (11181.9: 소리 감쇠 끝, 정답 11179.5), #25/26 (29331.5: 음악 끝 직후 멘트), 15764339@11554 (+56초: 11727 의 -40dB 틈 뒤로 하모닉 소리가 11783 까지 이어짐), 14781626@22409 (+43초: 22698 은 곡 중간, 22743 에서 감쇠 끝), 9667909@13682 (13878.8: 절벽 직전, 잡음 구간 제외).

### 채택 2. E3 코다 검사 (snap.deep_end + music_run) - `fix: E3 큰 이동...`
- 이동이 15초를 넘고 잘라낼 구간에 (Music>=0.85 & Speech<0.2, 틈 1초 이하)가 8초 이상 이어지면 코다로 보고 안 당긴다. D2(후야 @726)는 끝 1056.1 -> 1081.5(정답 오차 -26.9 -> -1.5), 13790961@14652(23초 이음), 8573134@3(9초)이 같이 막힌다. #60(음악 5.0초, 끝 +0.3 유지)과의 간격이 5.0 대 9.0 으로 좁고 표본 4개 근거다(shortcut 주석).
- sweep E3 큰 이동(12초 초과) 중 코다로 안 막힌 곡을 스펙트로그램으로 확인: #60, 14781626@23139(-24), 15840388@24642(-29), 15724523@400(-29), 15762485@7082(-19) 모두 곡이 끝나고 무음 뒤 다른 소리(멘트/BGM)라 이동이 맞다.
- golden 을 재동결했다(D2 화이트리스트 삭제). 바뀐 곡은 4개: V16/V15/#45(P1 수정 반영으로 review/drop -> auto), D2(끝 1081.5).
- 기각: 단순 15초 상한(#60 -33 이 깨짐), 임계 변형(audit_e3_variant.py: -12dB 를 -20/-25 로 올리면 #60 도 꺼짐).

### 채택 3. TAIL 가드 (make_final.tail_cut, 엔진도 같은 함수) - `feat: TAIL 가드`
- 컷 = max(여유 컷, 곡 끝+1초). 단 곡 끝 뒤 1초 안에 들리는 말소리(점수 창 중심 기준 Speech>0.15, 음량 >= 곡 중앙값-25dB)가 시작하면 그 0.05초 앞, 최소 곡 끝+0.3초. 페이드 길이 = min(1.5, 컷-곡 끝) = 0.3~1.5초(assert 하한 0.3).
- 선택 근거(말 직전 컷 vs 컷 +1초 유지 + 페이드 축소): #105(21405.5), #138(4056.5), #126(1173.5), #71(3331.3), #14(14865.5) 스펙트로그램에서 곡이 끝나자마자 말 포먼트가 이어진다(음량 -10~0dB). 페이드는 곡 끝에서 시작하므로 +1초 컷에서는 말이 -3~-6dB 로 0.3~0.7초 들린다. 말 직전 컷은 곡 소리를 깎지 않고(곡 끝~컷은 무음/꼬리) 잃는 것이 말소리뿐이라 사용자 요구('페이드는 곡 끝 이후에만')는 그대로 지키고 '컷 +1초'만 양보한다.
- 효과(golden 113곡, 곡 끝~컷 안에 들리는 말소리 프레임 포함 여부): 포함 곡 44 -> 19, 프레임 233 -> 54, 컷이 줄어든 곡 54개(0.3~0.85초). 승인 L 25곡은 8곡 -> 2곡(#105, #138 은 곡 끝에 이미 말이 시작해 0.3초 남음, 계획서의 '0건'은 못 맞춤). 클립 길이 변화는 최대 0.7초라 golden 의 3초 기준에는 안 걸린다.
- 주의: RULE("v4-faithful")은 올리지 않았다(index_final, mk_review_csv 가 RULE 로 거른다). 기존 out/final* 클립은 이전 컷이고, 새 컷으로 만들려면 RULE 을 올리고 `final_nas.py` 를 다시 돌려야 한다(인코딩 약 35분). 이 결정과 '컷 +1초 원칙 양보'는 사용자 확인이 필요하다.

### 변경 후 전체 수치
- golden 113곡 이탈 0건(화이트리스트 0), `blind9 N 75행` 등록부 없이 auto 0, selftest(snap, finalize, make_final), `test_route.py` 통과. memo_audit 저장본 갱신(이전 P3 저장본은 `memo_audit_baseline_p3.json`).
- 전 방송 sweep(`python experiments/regress_snap.py -c`, 4분): 규칙별 이동 구간 E1 34, E1b 10(검토 등급 6, drop 4), E2 22, E3 27, S1 25, S2 49. N/BGM 에 붙는 연장은 E1b 에서 drop 등급의 4곳뿐이고 최종 산출물에는 영향이 없다.
- 새 도구: `experiments/end_view.py`(끝 경계 그림), `regress_snap.py` 의 `-c`(다른 규칙 전부 켠 상태에서 비교)/`-r규칙` 옵션과 등급/장면 표시.

### 안 한 것, 남은 것
- 끝 early 중 22, 63, 65, 71, 82, 142(및 54): 이동 없음. 63(곡 뒤 무반주 10초), 65(허밍 아웃트로 3.2초), 71(MR 위 멘트, 점수로 안 보임)은 이번 규칙으로 안 풀렸다. 142 는 감쇠 구간이라 정답 불확실.
- unresolved(사용자 답 대기, 규칙 변경 안 함): 22/82/18 의 실제 끝 시각, 승인 시작이 늦은 5곡의 의도, #45 전주 포함 선호. 이번 변경이 22, 82, 45 를 움직이지 않음을 memo_audit 로 확인했다.
- 승인 구간 12개가 후보에 매칭되지 않아 golden 이 못 본다(P1 기록 그대로). out/ 의 카드와 final json 에는 E1b/E3/TAIL 결과가 아직 없다(재생성 전).

## 27. P1~P4, P6 반영 재생성과 자체 시청 검수 (2026-10-28)

### 한 일과 소요
- `SONG_NOCLIP=1 python datasets/reroute_nas.py 3 --final`(61방송, 80% 상한 그대로) 11분(예상 10~14분). 이어 완곡본 RULE 을 `v5-bounds` 로 올리고(E1b, E3 코다, TAIL 가드가 들어간 컷), 이전 파일은 `out/stale_v4/{final,final_review}`(목록 `out/stale_v4/LIST.txt`)로 옮긴 뒤 `python datasets/final_nas.py auto review` 로 63곡을 다시 만들었다(auto 42 + review 21). 순차 실행의 병목은 NAS LAN 읽기(곡당 약 1분, GPU 사용률 평균 35%)여서 review 만 별도 프로세스로 동시에 돌려 44분(예상 35분의 1.26배)에 끝냈다. 이동 이력은 `cache/regen/{reroute,encode*}.log`.
- 등급(후보 191개): auto 40 -> 42, review 23 -> 21, drop 128 -> 128. 바뀐 곡 2개(nana 10-16 #14, toa 10-24 #8)는 review -> auto(P1 의 D5, D3 수정으로 승인 이력 겹침이 맞음). 곡 경계가 1초 넘게 움직인 후보 7개: review 3(#20 끝 +151.5, #25 끝 +99.5, #18 끝 +19.5, 모두 E1b), drop 4(모두 drop 유지). 전 `python experiments/regen_compare.py`.
- 파일 기준 비교(`python experiments/regen_clips_diff.py`): 63곡 모두 `ok`, 리미터 켜진 클립 0, 음량은 원본 wav 구간 대비 mean +0.2~0.5dB(3곡 확인). 승인(auto) 클립은 곡 시작/끝 이동 0이고 컷만 TAIL 가드로 0.25~0.70초 줄었다(클립 길이 변화 전부 3초 미만, 의도된 변화, 26절). golden gate 이탈 0.

### 메모 감사 전/후 (`python experiments/memo_audit.py out/stale_v4/final,out/stale_v4/final_review out/final,out/final_review`)
| 항목 | 전(v4-faithful 실제 클립) | 후(v5, 실제 클립) |
|---|---|---|
| 숫자 정답 13곡-경계 hit@0.5 / 3 / 10 | 4 / 7 / 9 | 5 / 9 / 11 |
| 방향 지적 통과 | 11/27 | 13/27 |
| 길이 오차 > 5초 곡 | 3 | 2 |
| 경계 좋음 유지 / 곡 사라짐 | 67/67 / 0 | 67/67 / 0 |
- 실제 클립과 엔진 계산(`audit_engine`)의 곡 경계 차이 0.00초(재생성이 엔진 예측을 그대로 재현). 못 푼 항목: #20 시작 +42.4(P5), #44 시작 +25.8, #54, 22/82/18/45 와 승인 시작 5곡은 unresolved 로 규칙을 바꾸지 않음.

### 자체 시청 검수 (`data/review/blind11/self_check.json`, 63클립 전부)
- 방법: `experiments/self_check_media.py` 가 클립마다 프레임 3장(시작/중간/끝)과 시작/끝 스펙트로그램(+0.25초 rms+점수, 컷/곡 표식)을 그려(`cache/regen/media/*.png`) 모두 Read 로 직접 보았다. 판정은 `experiments/self_check_build.py` 가 메모(blind9 labels)와 묶는다. 귀로 듣지는 못했다.
- 화면: live 62, other 1. other 는 review 의 `2026-10-21_rang_1 #02`(새 채널): 3D 게임 화면, 본인 모델 없음, 끝 프레임 게임 안내 그림 = 게임 BGM 으로 보이는 N(rel_db -4.76 이 임계 -5.7 바로 위라 오디오 신호로 못 걸렀고 화면 의미 신호가 있어야 가려진다, P6 기록과 같은 유형). 새 채널이라 review 에 남은 것이며 완성본은 사람이 보는 폴더. 사용자 확인 뒤 known_negatives 후보.
- 시작: ok 50, late 11(컷 앞에도 같은 소리가 이어져 전주/호흡이 잘림 = P5 영역 + 메모와 부합), speech 2. 끝: ok 43, speech 7(곡 끝 직후 말 온셋이 TAIL_MIN 0.3초 동안 남음, 알려진 한계), early 9, late 3, mr 1(MR 위 멘트, 알려진 한계). 확신도 high 24 / mid 31 / low 8.
- 메모가 있는 49클립 중 28클립은 지적이 해소/일치했고 17클립은 지적이 그대로 남아 있다(주로 시작 late 11, 끝 early 6). 남은 것은 P5(시작 후보 제안)와 'MR 끝 뒤 딥 후 소리가 이어지는 끝'(mary1_03, toa3_05)이다. 후자는 딥 뒤 소리가 노래인지 말인지 점수로 못 가려 규칙을 안 만들었다.
- low 8개(사람이 볼 우선순위): nana 10-06 #10(시작 직전 같은 MR), nana 10-16 #14(메모 두 행 상반, 미결 질문 3), nana 10-16 #17(시작 앞 8초 소리 종류 불명), toa 10-24 #5(딥 뒤 소리), 리제 10-04 #21(18번 '1분'), nana 10-06 #2(재생목록 +82초와 어긋남), toa 10-24 #4, #9.
- 화면에 '클립 금지' 문구가 상시 표시되는 방송이 있다(nana 10-16 #19~#22, 방송자가 클립 금지를 요청한 것으로 보임). 정책 확인 필요.

### 규칙 수정 1회(반복 1/2): 종료 컷 연장 (make_final.tail_cut)
- 원인: 자체 시청에서 `rang 10-17 #2`(auto, 메모 '종료 fade out 1초 더')와 `toa 10-24 #12`(메모 'MR 종료 반주가 남은 채 잘림')의 곡 끝 표식 뒤에도 -8~-10dB 의 마지막 화음/감쇠가 말 없이 이어지는데 컷이 곡 끝 +1.0초라 화음 한가운데서 페이드가 시작/컷됨.
- 수정: 곡 끝 +1초 안에 말이 없고 컷 직전 0.5초 중앙값이 곡 중앙값-20dB 이상이면 소리가 작아지거나 말이 시작할 때까지 최대 곡 끝 +3초까지 컷을 늘린다. 페이드는 컷 앞 min(1.5, 곡 끝~컷) 초로(곡 끝 +1.5초 안에서는 이전과 같음). 곡 끝/시작 경계와 golden 은 안 바뀐다.
- 영향(`python experiments/tail_ext_audit.py`): 63곡 중 6곡이 컷 +0.3~1.3초(nana 10-16 #14, rang 10-17 #2, hiyori 10-18 #2, toa 10-24 #8, #4, #12). golden 이탈 0, test_route/selftest 통과.
- 미완: NAS 파일 API 가 01:42 경 로그인 필요(401)로 바뀌어(apps/api auth 커밋 477c723/db66e0c 배포) 6곡 중 nana 10-16 #14 만 새 컷으로 다시 만들었다. 나머지 5곡(rang 10-17 #2, hiyori 10-18 #2, toa 10-24 #4, #8, #12)은 아직 이전 컷이다. NAS 접근(로그인 쿠키 또는 서비스 계정)이 복구되면 `python datasets/final_nas.py auto review` 한 번이면 되고(이름이 바뀐 곡만 인코딩, 약 6분), 이어 `python experiments/regen_clips_diff.py --archive` 로 오래된 사본을 `out/stale_v4/iter1/` 로 옮긴다. ssh nas-claude 는 녹화 폴더 읽기 권한이 없어 대체 경로가 아니다.
- 반복 2/2 는 쓰지 않았다: 남은 지적은 시작 late(P5)와 딥 뒤 이어지는 소리 두 유형이고 둘 다 점수만으로 일반 규칙이 안 서며, P5 는 이번 범위 밖이다.

### 사용자 확인 필요
- TAIL 가드(말 직전 컷, 곡 끝 +0.3~1.0초)와 종료 컷 연장(최대 +3초)이 '컷 곡 끝 +1초' 원칙을 바꾼다(청취 확인 필요).
- 미결 3건(22/82/18 끝 시각, 승인 시작 늦은 5곡 의도, #45 전주 포함 선호)은 unresolved 그대로.

## 28. blind9 자체 검수와 게이트 도입 (2026-10-28) - P1~P4, P6 총정리

(번호 메모: 계획 때는 26절로 예정했으나 26절은 P2, 27절은 재생성 기록으로 이미 쓰였다. 세부 전/후 표는 26, 27절에 있고 여기는 통합 인덱스다.)

### 지난 처리의 문제 (인정)
25절까지의 처리는 사용자 판정(L/N/B)과 수치 규칙(tstd, speech, 등록부)만 맞추고, 메모에 적힌 곡 길이, 화면, 실제 시작/종료 시각을 직접 검증하지 않은 채 컨펌을 요청했다. 이번 원칙은 (1) 메모를 점검 항목으로 구조화해 전/후를 자동 검증, (2) 결과 클립을 프레임/스펙트로그램으로 직접 보고 자체 검수, (3) 승인 라이브 클립 이탈 점검, (4) 등록부에 기대지 않는 일반 규칙 우선이다.

### 새 도구와 사용법 (모두 tools/song-detect, 비커밋 입력은 data/ 아래)
- `python experiments/golden_gate.py` : 승인 라이브 113곡(동결 `experiments/golden_v4.json`)의 경계/클립 길이/등급 이탈 목록. 이탈 있으면 종료코드 1. 화이트리스트는 사유 필수. `blind9 N 75행` 이 등록부 없이 auto 가 되는지도 같이 본다. 규칙을 바꿀 때마다 먼저 돌린다.
- `python experiments/memo_audit.py` (`build`, `--save`, `--attrib`) : 메모 기대값(expectations.json, 숫자 정답 13곡-경계)에 대해 hit@0.5/3/10, 길이 오차, 방향 지적, 화면 tag 게이트 예측, 이동 규칙 귀속률. engine 으로 현재 코드를 재계산하므로 재생성 없이 전/후 비교가 된다.
- `python experiments/logo_route.py build|eval` : 신호 표(cache/audit/signals.csv) 기반 그룹 제외(스트리머/방송) 신호 선택과 임계, 부트스트랩 구간. `--golden --cands rel_db,bursts_per_min` 으로 승인 라이브 포함.
- `experiments/self_check_media.py`, `self_check_build.py` : 클립별 프레임 3장 + 시작/끝 스펙트로그램을 그리고 메모와 묶어 `data/review/blind11/self_check.json` 을 만든다.
- `python experiments/mk_review_csv.py data/review/blind11` : 판정용 review.csv/xlsx (자체 검수 열, 이전 대비 shift/deviation, priority=1 상위 10곡).

### 규칙 변경과 전/후 (채택/기각)
| 단계 | 변경 | 전 | 후 |
|---|---|---|---|
| P1 | D1 움직임 drop 승인 구간 auto, D3 BD 비교 범위, D5 겹침 하나라도 맞으면 auto, 134/135 병합 | golden 이탈 4 | 0 |
| P2 | E1b 끝 연장(가드 4), E3 코다 검사, TAIL 가드 (26절) | hit@0.5/3/10 4/7/9, 방향 11/27 | 5/9/11, 13/27 |
| P3 | 경계 이동 규칙 귀속(stages), memo_audit | 숫자 정답 6 | 13곡-경계, 귀속 859/859 |
| P4 | logo_route (등록부 없는 일반화 측정) | 표본 내 수치만 | hold-out 구간 |
| P6 | 오디오 신호 rel_db < -5.7 또는 bursts > 2.1 로 weak (움직임 대역 대체) | 노출 23 + weak 숨김 22 | 노출 14/55, 라이브 걸림 0/136 |
| 재생성 | RULE v5-bounds, 종료 컷 연장(최대 +3초) | - | 63곡, 이탈 0 (27절) |
- 기각: E1b 연장 상한 +20%, E3 단순 15초 상한, 군집 전파(라이브 2~3곡 추가 손실), scene 거리 신호(누수), diff_med/ctx_speech 등(P6 신호표 참조), 반복 2회(남은 지적이 점수로 규칙화 불가).

### 일반화 한계 (LOGO)
- 행 A(현재 임계, 표본 내 선택) 재현: blind9 N 55 노출 23 / weak 22 / drop 10, 과적합 참고값이다.
- tstd 임계만 그룹 밖에서 재추정하면 노출 45/55(82%): 현재 weak 대역은 일반화되지 않는다.
- 신호 선택(방송 단위 hold-out) m=0.1: 노출 10/55 [8-32%], 라이브 손실 0/49. 그러나 m 0.0 에서 라이브 6곡 손실, 0.2 에서 1곡 손실(비단조): 점추정이 아니라 구간으로 읽는다.
- 배포 규칙(승인 golden 포함 라이브 136): 노출 14/55 [11-42%], hold-out 라이브 손실 2/136. 목표 10/55 이하와 라이브 손실 0은 동시 미달성.
- 오디오로 못 거르는 남은 N: GTA 노래방/콘서트, 타 스트리머 같이보기, 따라 부르기. 화면 의미 신호(SigLIP 등, 미설치)가 필요하고 지금은 등록부로만 막힌다.
- 표본이 스트리머 11~18명이라 새 스트리머에서 라이브 일부가 weak 로 갈 수 있다(승인 곡은 known_pos 로 영향 없음).

### 자체 검수 결과 (63클립 전부 프레임/스펙트로그램으로 봄, 귀로 듣지 못함)
- 화면 live 62 / other 1(rang 10-21 #02, 게임 BGM 으로 보임, 등록 안 함). 시작 ok 50 / late 11 / speech 2, 끝 ok 43 / speech 7 / early 9 / late 3 / mr 1. 확신도 high 24 / mid 31 / low 8.
- 메모가 있는 49클립 중 28 해소/일치, 17 지적 남음(시작 late 11과 끝 early 6: P5와 딥 뒤 이어지는 소리).
- 승인(auto) 클립 이탈: review.csv 기준 곡 경계 2초 이상 / 클립 길이 3초 이상 변화 승인 이탈 0건. review 3곡만 E1b 연장으로 끝이 +20/+99.5/+152.4초 이동(일반 규칙, 스펙트로그램으로 감쇠 끝 확인).
- 판정용 파일: `data/review/blind11/review.csv`(+xlsx). priority=1 10곡만 보면 된다.

### 미결 질문 3개 (사용자 답 전까지 규칙 변경 없음, golden_v4.json unresolved 에 기록)
1. 22/82/18번: 클립 안에서 곡이 끝났다고 들은 시각이 몇 분 몇 초인가(22 재생목록 25428.6 vs 오디오 25511 vs 메모 약 1분, 82 음악 끝 18074.4 뒤 컷, 18 확인된 부족분 19.5초).
2. 승인 시작이 음악 시작보다 15~25초 늦은 5곡(나나 10-06 25775 등): 전주를 뺀 의도인가, 탐지 당시 값이 승인된 것뿐인가.
3. #45: 재생목록 정답은 MR 전주 포함 15.6초 앞인데 L. 전주 없는 시작이 선호인가 포함이 선호인가.

### 다음 단계
- 사용자 review.csv 판정/메모 -> 판정 반영(labels.py BLIND11 등)과 TAIL/종료 컷 연장 청취 확인(컷 곡 끝 +1초 원칙 변경).
- NAS 로그인(401) 복구 후 `python datasets/final_nas.py auto review` 와 `regen_clips_diff.py --archive` (5곡 새 컷 반영, 27절).
- P5(시작 후보 제안, B/review 후보로만), P7(사람 후보 10곡 선택), 화면 의미 신호 시험. '클립 금지' 표시 방송(nana 10-16 #19~#22) 정책 확인.

## 29. 프로토타입 5개 통합 (2026-10-29, 브랜치 proto/sd-integrate, 기준선 song-detect/baseline-20261029) - 새 세션은 이 절과 experiments_log/integration.md 를 먼저 읽는다

자세한 표와 근거는 `experiments_log/integration.md`. 여기는 인덱스다.

### 한 일 (단계마다 별도 커밋, 단계마다 게이트 전/후 표)
- 도구: `harness/`(manifest, replay, shadow_diff, scene_real, check, fill_vis), `tune.py`(SONG_TUNE 상수 오버라이드), `experiments/integ_final_diff.py`(61방송 4538구간 경계 비교), `experiments/integ_holdout.py`(공통 지표 A/B).
- sweep 상수: 점수 임계 7개 양자화 재중심화(동작 불변), E1B_LOUD 12 -> 10, black_max 0.50 -> 0.47(motion 34.5 유지).
- boundary: S3 시작 제안(auto 가 아닌 곡에만), memo_audit/check 의 engine_rev, golden 화이트리스트 6건(3개 review 곡, 재생목록 정답 쪽 이동).
- visual: n_visual(SigLIP2) + route.mark_likely 훅(weak 표시, 단 review 등급 weak 는 `make_final` 이 클립을 만들지 않는다) + 4_scene 단계 연결. **임계는 통합 때 0.8045 -> 1.026 으로 재보정**(golden 113곡을 배포 경로로 점수화하니 144p 라이브 둘이 0.76/0.79 로 기존 임계에 0.015 까지 붙었다).
- 연결: scene.NasDown(NAS 401 을 빈 배열로 삼켜 scene=None 이 저장되던 위험 제거, reroute 는 실패 방송을 되돌리고 중단), pipeline.decide/card_file 공용, `reroute_nas.py --manifest`(출력이 pipeline 경로와 3_final 61/61, 카드 191/191 동일함을 확인 후).

### 공통 정의 (N 노출 수치 모순 정리, 자세한 것은 integration.md 0절)
- N 노출 = blind9 N 55곡 중 등록부 없이 보이는 곡 수. A = 배포 임계 표본 내(회귀 감시용), B = 스트리머 hold-out + 라이브 풀 136(일반화 주장은 B 로만).
- 전/후: A(머리 수치) 오디오만 14/55 -> 배포 경로 vis 포함 11/55(191카드와 일치), 라이브 손실 0. B 규칙 D 16/55 -> +n_visual 13/55(배포 경로 vis, 프로토 프레임이면 14/55), 라이브 손실 1/49(규칙 D 의 hold-out 손실, m=0.1 에서 visual 이 더한 것은 0, m=0.0 에서 전체 풀 +1). 같은 규칙이 풀/분할에 따라 10~16/55 를 오간다. **n_visual 이득의 스트리머 부트스트랩 95% 구간은 [0, 7]곡(0 포함)이라 효과 크기를 말할 수 없다.** 메모 감사 hit@0.5/3/10 5/9/11 -> 8/11/12, 방향 13 -> 16/27, 길이>5초 2 -> 1, 좋음 67/67, golden 이탈 0. **메모 감사 이득은 규칙을 설계한 곡이라 표본 내다**(사용자 정답 8행은 hit@0.5 3 -> 4, 에이전트 audio 정답 5행은 2 -> 4, boundary LOGO +0 [-5, +4]: integration.md 4.1).

### 쓰는 법
- `python harness/check.py`(12초: selftest 11개, golden, 메모 감사(engine_rev), logo_route, 변화 리포트), 의도한 변경이면 `--accept`. 종료코드 0 통과 / 1 게이트 실패 / 2 점검 오류.
- 경계 규칙을 고친 뒤: `python experiments/integ_final_diff.py cache/proto_integrate/final_base`(3_final 비교), `python datasets/reroute_nas.py --manifest`(바뀐 단계만, 호스트 venv python 이면 vis 까지).
- 화면 신호: torch+open_clip 이 있는 `C:/_tools/wt/venv/Scripts/python.exe` 로 실행해야 붙는다(아니면 stderr 한 줄 후 옛 동작). HF 가중치 timm/ViT-B-16-SigLIP2 는 오프라인 배포 시 사전 캐시 필요. 임계 재보정은 `integ_holdout.py cal`.

### 사용자 결정이 필요한 것
- E1B_LOUD/S3 를 기존 완성본에 반영하려면 RULE 상향 + reroute --manifest + final_nas(NAS 로그인 필요). 27절의 TAIL/종료 컷 청취 확인과 같이 결정.
- 미결 질문 3개(22/82/18 끝 시각, 승인 시작 늦은 5곡 의도, #45 전주 포함 선호)는 그대로. S3 를 auto 에 쓰려면 질문 2, 3 의 답이 필요하다.

### 기각/보류 (integration.md 5절)
- (a) 시각 점수 review 정렬: 노출 N 이 vis 가 낮아 상위 10곡 중 N 2(무작위 1). (b) 규칙 AND 학습형 weak(CRC): alpha 0.05 에서 라이브 손실 증가 또는 N 1~2곡 이득. (c) asr 가사 힌트: 통합 경계에서 끝 tp 3/12 fp 1/31, 시작 tp 4/9 fp 1/36, 연결 비용 대비 이득 작아 미연결. (d) YAMNet 추가 클래스: 시작 late 와 구별 못 함(AUROC 0.23~0.76, 허밍 #65 의 Humming 0.02).

### 한계
- 귀로 못 들음(S3 #50 #65 등 unverifiable). n_visual 은 표본 내 보정이고 golden gate 는 weak/vis 를 안 본다(shadow diff 와 golden 직접 점수로 확인). reroute --manifest 는 임시 폴더(2방송)에서 NAS 재계산과 vis 까지 끝까지 시험했고 61방송 메인 out/ 에는 돌리지 않았다(산출물 보호, 처음 실행은 191후보 전부를 읽어 약 25분).

## 30. 61방송 재생성: RULE v6-integrate (2026-10-29, 브랜치 proto/sd-integrate) - 새 세션은 이 절과 experiments_log/integration.md 8절을 먼저 읽는다

29절의 "사용자 결정이 필요한 것" 1번(E1B_LOUD/S3/화면 신호를 기존 완성본에 반영)을 실행했다. 자세한 표는 `experiments_log/integration.md` 8절.

### 한 일 (총 약 1시간, 예상의 1.5배 초과 단계 없음, NAS 401 없음)
- `make_final.RULE` "v5-bounds" -> "v6-integrate". 이전 클립은 `out/stale_v5/{final,final_review}`(삭제 안 함), 이전 카드/3_final/4_scene 은 `out/stale_v5/state/<방송>/`.
- `SONG_NOCLIP=1 C:/_tools/wt/venv/Scripts/python.exe datasets/reroute_nas.py --manifest`(호스트 venv, vis 까지, 28분) -> `SHARD=k/n python datasets/final_nas.py auto|review` 4 프로세스(27분, 새 SHARD 환경변수). 이후 `experiments/self_check_media.py`, `self_check_build.py`(blind12), `regen_clips_diff.py`, `regen_compare.py`, 새 `regen_loudness.py`.

### 결과
- 등급 수 auto 42 / review 21 / drop 128 그대로(등급 이동 0). weak 후보 60 -> 72(+12). review 1곡(rang 10-21 #02, 3D 게임 화면)이 weak 가 되어 클립은 63 -> 62곡.
- golden 이탈 0(화이트리스트 6), 승인(auto 42곡) 곡 시작/끝 이동 0(컷 1곡 +0.30초), 메모 감사(실제 클립) hit@0.5/3/10 5/9/11 -> 8/11/12, 중앙 오차 1.9 -> 0.35초, 방향 13 -> 16/27, 길이>5초 2 -> 1, 경계 좋음 67/67, 곡 사라짐 0(golden 113 기준. 탐지가 쪼개 후보가 없는 승인 구간 12건은 못 보는 사각지대: 31절). selftest 11/11, test_route ok, logo_route 14/55 / 라이브 걸림 0/49. 클립 62/62 ok, 원본 음량 차이 평균 -0.07dB(최대 |0.22|), 리미터 0.
- 바뀐 클립 6곡: rize 10-04 #23 끝 -2.4초(E1B_LOUD), nana 10-16 #13/#19/#21 시작 -25.7/-13.1/-6.8초와 mary 10-18 #03 시작 -16.3초(S3), toa 10-24 #08 끝 컷 +0.3초.
- 자체 시청 검수(`data/review/blind12/self_check.json`, 62클립 프레임/스펙트로그램을 모두 직접 봄, 귀로는 못 들음): 시작 ok 52 / late 7 / speech 3, 끝 ok 41 / speech 9 / early 7 / late 3 / mr 2, 확신도 high 21 / mid 31 / low 10, 메모 49클립 전부 메모 대비 기록. 시작 late 11 -> 7(S3 4곡 중 검증된 것은 #44 #54 둘, #50 #65 는 방향만).
- 규칙 수정 0회: 명백한 결함은 mary 10-23 #01 의 시작(컷이 곡 음량 수준의 짧은 비음성 잡음 위)이 하나였고, 원인은 `lead_pad` 의 음성 없음 공백 폴백(음량 무제한)이다. 음량 제한(승인 auto 컷과 시작 late review 를 움직임)과 온셋 규칙(0곡 반응) 두 후보를 대입해 보고 채택하지 않았다(integration.md 8.5).

### 사용자 결정/확인이 필요한 것
- 청취 확인(unverifiable): S3 #50, #65(허밍), 종료 컷 연장/TAIL 전부, 끝 뒤 소리 종류(low 10곡). 27절의 "컷 곡 끝 +1초" 원칙 변경은 여전히 사용자 확인 사항이다.
- 미결 질문 3개(22/82/18 끝 시각, 승인 시작 늦은 곡 의도, #45 전주 포함 선호)는 그대로. S3 를 auto 에 쓰려면 2, 3번 답이 필요하다.
- n_visual 임계 1.026 은 표본 내 보정이다(29절). 이번 재생성에서 라이브(auto/review 62곡) vis 최대 0.59 로 임계와 간격은 충분했다.

## 31. 리뷰 반영 (2026-10-29, 브랜치 proto/sd-integrate) - 항목별 판정은 experiments_log/integration.md 9절

세 리뷰(통계 A1~A7, codex B0 + 재실행 결과 B1~B9, 도메인 메모 C1~C10)의 finding 27개를 직접 재현해 판정했다(재현 안 된 것 없음). 요약:
- 문서 정정: 메모 감사 이득은 표본 내(사용자 정답 행/에이전트 audio 행 분리), n_visual 이득은 구간 [0, 7]곡, "모든 조건에서 0" 은 m=0.1 한정(m=0.0 에서 +1), A 지표 정의를 배포 경로 11/55 로 고정(오디오만 14, 프로토 프레임 12 는 이름 바꿔 병기), "246곡" 은 고유 218 이하.
- 도구/게이트: `integ_holdout.py eval` 이 배포 경로 vis(4_scene) 표를 머리로 + 임계 민감도, `integ_boot.py`(스트리머 부트스트랩), `golden_gate.py` recall 게이트(승인 구간 중 keep 이 50% 못 덮는 것의 기준선 8개), `memo_audit.EXISTS` 에 #33 추가 + `check.py` 가 허용 목록 {64, 33} 외의 새 실패 차단, `clip_banner.py`('클립 금지' 문구 클립 목록).
- 코드: `make_final.lead_pad(settle=)` 를 auto 가 아닌 곡에만 켜 mary 10-23 #1 시작이 큰 잡음 위인 결함을 고쳤다(62클립 중 2곡만 움직임, auto 불변, 두 클립만 재생성, 이전 클립은 `out/stale_v6`). golden 화이트리스트 사유와 15761307@2703 시작 정답(두 곡을 묶은 재생목록 항목)을 바로잡았다. 자체 검수 #111 을 ok -> soundcheck 로 정정.
- 정리: `out/READ_ME_FIRST.md` 를 v6 로 다시 썼고 `out/final/INDEX.md` 를 다시 만들었으며 빈 폴더를 지웠다.

### 사용자 결정/확인이 필요한 것 (29/30절 목록에 더해, 리뷰로 되살린 것)
- **'클립 금지' 화면 문구 클립 4곡**(나나 10-16 #19 #20 #21 review, #22 auto): 목록 `out/CLIP_BANNER.txt`. 올릴지 뺄지 결정 전에는 아무것도 옮기지 않았다.
- 끝 페이드 0.3초 클립 17개(auto 12, review 5): 컷 곡 끝 +1초 원칙(27절)과 같은 결정.
- 메모가 곡이 있다고 한 구간 2곳(#64 데뷔방송 앞 5분 예외, #33 앞부분을 자르면 라이브)은 아직 안 만들어진다. check.py 가 알면서 허용한다.
- 소리 확인(MR 점검) 약 4.7초가 남은 #111(토아 10-23 #1, 메모는 00:05 부터 시작).
- 탐지가 조각 내서 클립이 없는 재생목록 정답 곡 6곡(나나 10-06 3, 나나 10-16 2, 후야 1): 탐지 재현율 문제(이번 범위 밖). recall 게이트가 늘어나지 않는지만 감시한다.

- codex 적대적 리뷰(9.1절)도 돌렸다: B1~B6, B8, B9 를 고쳤다(NAS 화면 신호 전부 실패 -> NasDown, vis 덜 채워진 방송은 완료 기록 안 함, manifest 캐시 키 보강과 has_refs 재계산, 손상 manifest 복구, 섀도 diff 가 카드 삭제를 이탈로, 클립 재사용에 컷 일치). `out/manifest.json` 은 새 키 정의로 한 번 옮겼다.

### 한계 (정직하게)
- NAS 세션 쿠키가 ffmpeg 명령행(`nas_auth.ffargs`)에 실리는 방식은 기준선부터 있고 그대로다(codex B7, 같은 PC 의 다른 사용자가 없다는 전제).
- 청취 검수 없음(S3 #50 #65, TAIL, settle 의 두 클립 컷 모두 프레임/스펙트로그램으로만 확인). n_visual 임계 1.026 은 표본 내 보정이고 임계를 낮추지 않은 이유는 integration.md 3절 5.
- settle 은 사례 2곡 근거다(shortcut: `make_final.lead_pad` 주석). RULE 문자열은 그대로 "v6-integrate" 라서 같은 이름 규칙으로 두 가지 컷이 섞여 있다(바뀐 두 클립만 새로 만들었고 나머지는 같은 결과로 판단).

## 32. 프로토타입 5트랙 실측과 통합, 적대적 리뷰 (2026-10-29) - 29~31절의 총정리, 새 세션은 이 절부터 읽는다

### 32.1 구조와 위치
- 기준선 `song-detect/baseline-20261029`(8f841a3) 위에 트랙 5개를 병렬로 측정했다. 브랜치(모두 origin 에 push)와 worktree: `proto/sd-sweep`(상수/임계 탐색), `proto/sd-boundary`(경계 규칙), `proto/sd-visual`(화면 의미), `proto/sd-asr`(전사/가사), `proto/sd-harness`(구조/도구 + 선행 연구 조사 `research.md`), 각 `C:/_tools/wt/sd-<트랙>`. 채택안만 `proto/sd-integrate`(`C:/_tools/wt/sd-integrate`)에 단계마다 커밋했고, 이 브랜치가 UI 브랜치 `feat/ui-redesign-auth` 에 fast-forward 로 병합돼 있다(병합 결과는 push 하지 않음, 5개 proto 브랜치와 integrate 는 push 완료).
- 트랙별 원본 실험 로그는 해당 proto 브랜치에만 있다: `git show proto/sd-visual:tools/song-detect/experiments_log/visual.md` (asr.md, boundary.md, sweep.md + sweep_tables.md, harness.md + research.md 도 같은 방식). 통합 기록은 이 브랜치의 `experiments_log/integration.md`(0절 정의, 2절 단계별 게이트 표, 8절 재생성, 9절 리뷰 판정).
- 데이터(`data/`, `cache/`, `out/`)는 gitignore 이고 worktree 들이 메인 폴더의 것을 연결해 쓴다. 트랙 산출물은 `cache/proto_<트랙>/`, 통합은 `cache/proto_integrate/`, 재생성 산출물 비교는 `cache/regen_v6/`.
- 귀로 못 들었다. 모든 경계/화면 판단은 파형, 점수, 스펙트로그램, 프레임 이미지다(unverifiable 은 해당 절에 표기).

### 32.2 트랙별 핵심 실측 (설정 -> 결과 -> 판정)
수치는 트랙 로그의 값이고 표본 내/hold-out 여부를 같이 적었다. 채택은 통합에 들어간 것, 보류는 근거가 있으나 켜지 않은 것, 기각은 꺼 둔 것이다.

#### sweep (상수/임계 탐색, route 는 GPU torch 벡터화로 설정 100만 개를 3초에 평가, 경계 규칙은 CPU 병렬 0.8~2.5초/회)
| 설정 | 결과 | 판정 |
|---|---|---|
| 경계 상수 60개 x +-20% (2% 간격, 약 1200 설정) | 25개는 +-20% 에서 실패 없음, 첫 실패까지 거리 2% 이하 8개, 10% 이하 18개. golden_v4 는 현재 출력으로 동결돼 이탈 지표는 정확도가 아니라 "이동 허용 폭"이다 | 기록(규칙이 표본 몇 건에 맞춰져 있다는 근거) |
| 점수 임계 양자화: YAMNet int8 출력이라 점수가 32개 값만 가짐, 임계 7개를 동치 구간 중앙으로 | 840구간 경계 변화 0, 게이트 전부 동일, 상수를 동시에 +-1% 흔들 때 golden 0 유지 2/60 -> 8/60 | 채택(동작 불변, 여유만 늘림) |
| E1B_LOUD 12 -> 10 + black_max 0.50 -> 0.47 | golden 0, hit@0.5 5 -> 6, 840구간 중 1곡 이동(rize 10-04 #20 끝 -2.4초). 정답 1건 근거 | 채택(근거 1건이라 shortcut 주석) |
| route 임계 14개 Sobol 1,048,576 설정 + TPE/CMA-ES | 라이브 손실 0 이면서 N 노출 최소 15(기본과 같음, CMA-ES 14) | 기각(기본값이 이미 고원) |
| 학습 최적 설정을 스트리머 단위 hold-out 으로 | plateau/first 선택은 라이브 손실 37/136, robust 선택도 7/136 | 기각(튜닝 최적은 새 스트리머에서 위험) |
| 위험 상한(Clopper-Pearson), 라이브 손실 0/136 | 95% 상한: 행 2.2%, 방송 그룹 8.9%, 스트리머 23.8% | 기록(0 손실의 보증은 새 스트리머에 약함). 트랙 당시 golden 48행은 오디오 신호 2개만 시험된 값이었으나 구조 규칙까지 채워 다시 세어도 배포 규칙 0/136(integration.md 9.2절 A2-3) |
| 경계 상수 약 40개 동시 TPE(스트리머 hold-out) | 방향 +2 뿐, 이동 곡 26곡 이상 | 기각 |
| 끝 규칙 on/off | 전부 끄면 hit 0/0/4, 방향 0/27. 모든 규칙이 기여, 순서 E1,E1b,E3 유지 | 현행 유지 |

#### boundary (경계 규칙)
| 설정 | 결과 | 판정 |
|---|---|---|
| S3: 시작 앞 30초 안 마지막 깊은 무음(< -50dBFS, 0.5초 이상)의 끝을 시작 제안으로, 가드 3개(S1 이 민 곡 제외, 사이 말 비율 < 0.4, 사이 Singing+Music 평균 >= 0.25) | engine_rev: hit@0.5/3/10 5/9/11 -> 7/11/12, 방향 13 -> 16/27, 길이>5초 2 -> 1, 좋음 67/67, golden 0(화이트리스트 6). 전 방송 이동 10구간(auto 1, review 4, drop 5) | 채택, **auto 가 아닌 곡에만** (`alt_start` 로 기록) |
| S 변형 18종(범위 10~60초, 깊이 -45~-65, 말 가드, 길이 등) | back 20 은 golden 이탈 9, 말 가드 끄면 ok 58/67, S1 가드 끄면 golden 17 | 기본값 유지 |
| 호흡 보존(S14, 12설정), SSM novelty 봉우리(S16), 비트 격자(D02), 사운드체크 재시작(S18) | 호흡: 방향 변화 0. SSM: 방향 19/27 이지만 ok 59~60/67. 비트: 정답 0.1초 이내 4/13(무작위 기대 2.6). 사운드체크: #111 안 풀림 | 기각 |
| 끝 이른 곡: E1b 상수 18개 격자, E4(조용한 소리 연장), E5(에너지 미확인 끝) | 격자 방향 13/27 불변. E4 -55dB 는 방향 15 이지만 ok(all) 65/67. E5 는 ok 61~62/67 | 기각/보류(끝 이른 곡은 상수 문제가 아님) |
| 끝 정책 비교(131곡): 현재 vs 고정 +1.0 vs 말 직전 컷 | 현재 말 유입 30곡 8.5초/꼬리 손실 49곡 76.9초. 고정 +1.0: 유입 62곡 37.3초. 말 직전 컷 최소 +0.0: 유입 0 이나 곡 끝 추정 오차 0.5초로 마지막 음을 자를 위험 | 보류(청취 A/B 필요, 27절 TAIL) |
| detect 단계 변형 17종 시뮬레이션 | 히스테리시스(lo 0.05, 연결 60초): keep 191 -> 208, #20 10842-11178(정답 10841.6-11179.5)과 #144 해소, 그러나 승인 15곡 시작이 앞당겨짐. talk_break_s 20: #144 해소, 승인 1곡 끝 +77.5초(원인 미확인) | 보류(승인 시작 전주 정책 질문 2, 3과 묶임) |
| 그룹 제외 평가(LOGO) | S3 계열 9개 풀 +4 [0, +11], 98개 설정 풀에서 고르면 +0 [-5, +4]. 이득은 16개 방송 그룹 중 2개(나나 10-16, 메리 10-18) | **일반화 주장 불가**(알려진 4곡 되찾기와 회귀 감시로만 주장) |

#### visual (등록부 없이 화면 의미로 N 가르기, 표본 204곡 = 라이브 133 + N 71, 스트리머 단위 hold-out)
| 설정 | 결과 | 판정 |
|---|---|---|
| 제로샷 CLIP B/32, L/14, SigLIP B/16, SigLIP2 B/16 (프롬프트 5세트) | AUC 0.69~0.88. 세트 편차 크고 game 세트는 라이브 6~17곡 손실 | 보류 |
| 선형 프로브/적응/kNN/Tip-Adapter 캐시 | 그룹 hold-out AUC 0.78~0.88 이나 스트리머 hold-out 0.58~0.73(같은 스트리머의 다른 방송을 외움) | 기각(그룹 단위 수치는 스트리머 누수) |
| 선택 없는 4모델 x 5세트 앙상블 | AUC 0.881 [0.765, 0.968], m=0.1 에서 N 22/71 라이브 손실 0 | 기록(하한 수치로만 인용, 코드 미채택: 코드에는 아래 단독 모델만 있다) |
| SigLIP2 B/16 단독, 프레임 8장 max, squash 전처리 | AUC 0.895 [0.806, 0.963], m=0.1 N 37/71 손실 0(모델 선택은 표를 본 뒤라 선택 편향). 크롭은 0.840, 144p 통제로 해상도 누수 없음 | 채택(`n_visual.py`) |
| 오디오 4신호 + 시각 로지스틱 | AUC 0.922, N 56/71 손실 0 (표본 내 점수화) | 점수화 후보, 단독 drop veto 는 보류(GTA 노래방 안 라이브 1곡) |
| 오디오 hold-out 규칙 D 위에 시각 veto | 노출 10 -> 8(m=0.1, 손실 추가 0), m=0 이면 3 이나 손실 +1 | 보류(m 에 민감) |
| 구조 특징 18개(OpenCV), 소형 VLM(SmolVLM-500M), 타 스트리머 같이보기 전용 프롬프트 | 구조 특징 합치면 AUC 0.49~0.59, VLM 은 비용 100배에 정확도 낮음, 전용 프롬프트 veto 0/12 | 기각 |
| 못 거르는 N 유형 | 타 스트리머 같이보기 0/12, 따라 부르기 0/3, 대기 화면 0/4: 라이브와 화면이 같음(눈으로 확인) | 화면으로는 불가, 오디오(원곡 지문 등) 필요 |

#### asr (전사/가사 신호, faster-whisper + silero + demucs + torchcrepe, 49곡 검증)
| 설정 | 결과 | 판정 |
|---|---|---|
| 전사 13종(small/medium/large-v3, 언어 고정, 온도 폴백, VAD, 보컬 스템 등) | small + `multilingual=True` 가 단어 +75%, 오프셋 분산 최소. medium/large-v3 는 rtf 2~2.3배에 이득 없음(끝 flag medium 3/12, large-v3 5/12 이나 시작 2/9), VAD 는 MR 위 가창을 비음성으로 잘라 단어 -69% | small + multilingual 기준, 나머지 기각 |
| 사후 필터 14종(환각 필터, 오디오 지지, 사슬 k/gap/W) | 환각 필터를 끄면 커버리지 2배, 오탐 4배. 기본 사슬(k 3, gap 8, W 20)이 가장 균형 | 기본 유지 |
| 활동 신호 6종(같은 사슬) | musv(Music>=0.85 & Speech<0.2): 끝 6/12, 오탐 1/31. silero VAD 는 스트리머 말에도 켜져 오탐 21~29/31 | 기존 점수 신호가 최선 |
| 가사 경계 -> 곡 경계 | 가사 첫 단어 - 곡 시작 중앙 30초(IQR 24-33), 전주/후주 6~144초라 hit@0.5 0/36 | 경계를 정하는 용도 기각, 검증(flag)만 가능 |
| 메모 감사에 얹기 | ASR 끝: hit 중립. ASR 시작: hit@3 -1, 승인 곡 1개 훼손, 이동량 20~60초 | 기각(auto 에 못 씀) |
| 검증기 성능(통합 경계에서 재측정) | 끝 early tp 3/12 fp 1/31, 시작 late tp 4/9 fp 1/36 | 카드 힌트로만 가능, 미연결(비용 대비 이득 작음) |
| N 신호(가사 단어/분, 환각 비율 등), 따라 부르기 피치, 강제 정렬(MMS_FA) | 가사 단어/분 AUROC 0.85 로 기존 rel_db 0.82 와 같은 정보, 라이브 손실 0 이면 추가 포착 0/18. 피치: 가설 반증. 정렬: Whisper 가 이미 0.2초 수준 | 기각 |

#### harness (구조/도구) + 선행 연구 조사
| 설정 | 결과 | 판정 |
|---|---|---|
| 단계 매니페스트(AST 해시 키) | 593초(scene 191후보 전부 NAS)가 임계 변경 1.0초, snap 규칙 변경 약 17초(바뀐 후보 scene 만)로. 처음 전체 실행이 현행과 3_final 61/61, 카드 191/191 동일 | 채택 |
| 카드 v2 + 결정 재생(replay) | 규칙 1회 5ms(파일 stat 제거 전 73ms), 650조합 격자 2초. 191/191 재현 | 채택 |
| 섀도 diff + check.py 상시 점검 | 병렬 15초. 회귀 주입(wait_s 300 -> 600)을 종료코드 1로 잡음(승인 라이브 2곡 노출 하락), E1b/E3 끄기 시 이탈 4건과 규칙 귀속 재현 | 채택 |
| 학습형 랭커(LR/LGB/XGB/RF 등) 단독 | 방송 단위 hold-out N 노출 15~30/55 로 규칙 D(10/55)보다 못함. 규칙 D 와 AND 하면 6~10/55, CRC alpha 0.05 AND 는 5/55 | 단독 기각, AND 는 보류(CRC, 아래 32.7) |
| Conformal risk control(CRC) 임계 | 그룹 hold-out 에서 목표 놓침률 0.05 -> 실제 0.011~0.034, 스트리머 hold-out 에서도 낮은 alpha 는 지킴. 표본 163행, 임계 sd 15~50% | 보류 |
| 사람 후보 선택 active learning 재생 | 불확실도 계열 P@K 가 무작위의 1.6~2.0배(K=10 에서 2배 미달). "유력 순으로 보기"는 마지막 AUC 0.64~0.73 으로 판정 데이터가 편향 | 보류(위원회 + 불확실 상위 중 k-center) |
| Go 상주 작업 큐(songd) + TS 클라이언트 | 호출당 파이썬 시작 471ms -> 상주 p50 5ms. 작업자 재시작/인증/레인 분리 미구현 | 보류(통합 안 함) |
| 선행 연구 조사(research.md) | 한국어 가창 환각, 호흡, 비트, 랩, 지문, 화면 분류, CRC 를 출처 신뢰도(verified/partly/unverified)로 분류. 학습형 경계 회귀(YOHO)와 외부 지문 카탈로그는 근거 부족으로 기각 | 참고 |

### 32.3 통합 전/후 (공통 정의, 자세한 단계별 표는 integration.md 2절)
정의: N 노출 = blind9 사용자 N 55곡 중 **등록부(known_negatives) 없이** 사람에게 보이는 곡 수. A = 배포 임계 그대로(임계를 이 표본에서 정했으므로 회귀 감시용), B = 스트리머 단위 hold-out + 라이브 풀 136(일반화 주장은 B 로만). 라이브 손실 = 라이브 곡 중 drop 이거나 weak 인 수.

| 지표 | 기준선 | 통합 후 | 성격 |
|---|---|---|---|
| golden gate 이탈(승인 라이브 113곡) | 0 | 0 (화이트리스트 6: 재생목록 정답 쪽 이동 3곡) | 회귀 게이트 |
| 메모 감사 hit@0.5/3/10 (숫자 정답 13곡-경계) | 5/9/11, 중앙 오차 1.9초 | 8/11/12, 0.35초 | **표본 내**: 사용자 정답 8행에서는 hit@0.5 3 -> 4, 에이전트 audio 정답 5행에서 2 -> 4, boundary LOGO +0 [-5, +4] |
| 방향 지적 해소 / 길이 오차>5초 / 경계 좋음 | 13/27 / 2곡 / 67/67 | 16/27 / 1곡 / 67/67 | 방향 이득 3건(#50 #54 #65)은 S3 설계 곡 |
| A: N 노출 | 오디오만 14/55 | 화면 포함 11/55(배포 경로 vis, 191카드와 일치). 오디오만 14, 프로토 프레임 12 는 이름 바꿔 병기 | 표본 내, 라이브 손실 0/49 |
| B: N 노출 | 규칙 D 16/55 | + n_visual 13/55 | 부트스트랩 95% 구간 [0, 7]곡(0 포함) -> 효과 크기를 말할 수 없음. 스트리머 6명 중 이득이 있는 것은 2명. **vis 의 hold-out 은 임계뿐이고 그 임계도 폴드 9/11 이 표본 내와 같은 곡(히나 144p 1곡)이 정해 독립 증거가 아님**(정규화 mu/sd 까지 재적합해도 14/55로 같음, integration.md 2절, 9.2절 A2-1, A2-2) |
| 등급 수 auto/review/drop | 42/21/128 | 42/21/128 (등급 이동 0) | 61방송 191후보 재생성 |
| weak 후보 / 완성본 클립 | 60 / 63 | 72 / 62 (rang 10-21 #02 가 3D 게임 화면이라 weak) | 화면 신호 효과 |
| 승인(auto 42곡) 클립 경계 이동 | - | 0 (toa 10-24 #08 끝 컷 +0.30초 하나) | 재생성 실측 |
| 바뀐 클립 | - | 8곡: E1B_LOUD 1(rize 10-04 #23 끝 -2.4초), S3 4(nana 10-16 #13 #19 #21, mary 10-18 #03), settle 2(mary 10-23 #1 +0.6초, toa 10-24 #9 +0.2초), auto 컷 1 | `regen_clips_diff.py` |
| 자체 시청(62클립, 프레임/스펙트로그램) | 63클립: 시작 late 11 | 시작 ok 52 / late 7 / speech 2 / soundcheck 1, 끝 ok 41 / speech 9 / early 7 / late 3 / mr 2 | 시작 late 해소 중 검증된 것은 #44, #54 둘뿐 |
| 하네스 | 게이트를 따로 돌리고 수작업 비교(약 45초 + 수작업) | `python harness/check.py` 19초, 종료코드 0 | selftest 13/13(33절에서 check.py 자체 selftest 추가, 이전 12/12), 메모 8/11/12, 방향 16/27, 좋음 67/67, logo 오디오만 14/55 화면 11/55(곡 집합을 저장본과 비교) |

### 32.4 새 도구 사용법 (모두 tools/song-detect, 한 줄 요약. 상세는 각 파일 머리말)
- `python harness/check.py` (`--fast` 메모/logo 생략, `--accept` logo 집합과 변화 리포트 기준 갱신(logo 는 라이브 손실이 있으면 저장을 거부하고, 저장본이 없으면 실패하므로 처음에는 `--accept` 로 초기화한다. 33절), `--rescene` golden 게이트 전에 치지직 golden 방송 12개의 장면 단계를 현재 코드로 다시 계산(약 13분, 인터넷, 장면 규칙/풀을 바꾼 뒤), `--step 이름`): selftest 13개(check.py 자체 포함), golden + recall 게이트(등급 입력은 저장된 4_scene.json), 메모 감사(engine_rev) + exists 허용 목록 {64, 33}, logo_route(배포 규칙 N 노출 두 집합을 저장본 `cache/harness/check_accepted/logo_sets.json` 과 곡 단위로 비교해 새로 노출된 N 과 라이브 손실(blind9 49, 풀 136)만 이탈, 개수는 보고만), 변화 리포트. 종료코드 0 통과 / 1 게이트 실패 / 2 점검 오류. **규칙을 바꿀 때마다 먼저 돌린다.**
- `SONG_TUNE='{"snap.E1B_LOUD":9}' python experiments/memo_audit.py ...` (`tune.py`): 코드를 안 고치고 상수를 덮어써 전/후를 비교한다. 키는 `모듈.상수`, `모듈.P.항목`, `모듈.함수.기본인자`. `python tune.py list` 로 129개 이름과 현재 값. golden_gate, memo_audit, logo_route 가 `import tune` 해 둔다.
- `python harness/shadow_diff.py --set np.rel_db=-5.0 --set mp.motion=30 [--registry-off]`: 결정 규칙 변경의 등급 이동/승인 라이브 이탈/N 노출 변화를 0.3초에 낸다(`rp.`=route.P, `mp.`=scene_multi.P, `np.`=n_signals.P). 경계 규칙 변경은 `--root-a/--root-b` 로 매니페스트 루트 두 개를 비교. 종료코드 1 = 이탈.
- `python harness/replay.py baseline`: 카드 v2(`out/<방송>/cards2.json`)만으로 등급 결정을 5ms 에 재계산(wav, NAS 불필요). 격자 스윕의 기반.
- `python datasets/reroute_nas.py --manifest` (호스트 venv `C:/_tools/wt/venv/Scripts/python.exe` 로 실행해야 화면 신호까지 붙음): 입력이 바뀐 단계만 다시 한다(`out/manifest.json`, 키는 코드 AST + 입력 서명 + 장면 풀/보정 서명). 경계 규칙을 고친 뒤에는 `python experiments/integ_final_diff.py cache/proto_integrate/final_base`(3_final 구간 비교)를 먼저. 클립 만들기는 `SHARD=k/n python datasets/final_nas.py auto|review`(NAS 세션 필요, 401 이면 멈춤).
- **n_visual 설치/가중치**: `n_visual.py`(SigLIP2 B/16 제로샷, 프레임 8장, 프롬프트 5세트 z 평균, 보정 `n_visual_cal.json`)는 torch + open_clip 이 있는 호스트 venv 에서만 돈다(분석기 컨테이너에는 없음). 아니면 stderr 에 한 줄 남기고 옛 동작(vis 없음)이다. 가중치는 HF 허브 `timm/ViT-B-16-SigLIP2`, 오프라인 배포는 `~/.cache/huggingface/hub/models--timm--ViT-B-16-SigLIP2` 를 미리 채운다(이 PC 에는 있음). NAS 에서 화면 신호를 전부 못 읽으면 `scene.NasDown` 을 내고 일부만 못 읽은 방송은 manifest 에 완료로 기록하지 않는다.
- 지표/보정: `python experiments/integ_holdout.py eval|cal|build|golden` (공통 정의 A/B, 배포 경로 vis 표, 임계 재보정은 `cal --write`), `python experiments/integ_boot.py` (스트리머 부트스트랩 구간), `python experiments/golden_gate.py`, `python experiments/memo_audit.py` (`build --save --attrib`), `python experiments/logo_route.py build|eval`.
- 산출물 점검: `python experiments/clip_banner.py` ('클립 금지' 문구 클립 목록 -> `out/CLIP_BANNER.txt`), `python experiments/mk_review_csv.py data/review/blind12` (판정용 csv/xlsx), `experiments/regen_clips_diff.py`, `regen_compare.py`, `regen_loudness.py`.
- 사용자 판정용 파일: `data/review/blind12/review.csv` + `review.xlsx` (utf-8-sig 전체 인용, 62클립). 열: 자체 검수 5개(self_screen, self_start, self_end, self_confidence, self_note), 이전(v5) 대비 4개(prev_clip_len, shift_start, shift_end, deviation), 판정(L/N/B)과 메모 빈 열, `priority`. **priority=1 은 위험 점수(이탈 8, 화면 other 6, 확신 low 4, 시작/끝 지적 각 1.5, 확신 mid 1) 상위 10곡**이고 사용자는 이 10곡만 보면 된다(최대 10곡 원칙). 승인(auto) 클립의 "승인 이탈"은 0건이고 review 5곡만 "이동"(S3 4곡, E1B_LOUD 1곡)이다.

### 32.5 적대적 리뷰와 처리 (1차: 통계 A 7건, codex B0 1건 + 재실행 B1~B9 9건, 도메인 메모 C 10건 = 27건. 항목별 판정은 integration.md 9, 9.1절)
- 모든 finding 을 같은 명령으로 재현했고 재현 안 된 것은 없었다. 판정: fixed 22, partial 1(A6 E1B_LOUD 단일 표본: 코드 그대로, 주석만), rejected 1(B7 쿠키가 ffmpeg 명령행에 실림: 기준선부터의 방식), deferred 4(C6 0.3초 페이드, C2 소리 확인 규칙화, C3 메모 필수 곡 생성, A5 탐지 재현율). 문서 정정을 fixed 에 포함했고, 문서/게이트는 고치고 규칙화만 미룬 항목은 두 곳에 겹쳐 셌다.
- 통계(A): 메모 감사 이득은 표본 내라고 분리 보고, n_visual 이득 구간 [0, 7]곡으로 정정, "모든 조건에서 라이브 손실 0" 은 m=0.1 한정(m=0.0 에서 전체 풀 +1)으로 정정, A 지표 정의를 배포 경로 11/55 로 고정, 임계 1.026 민감도 표(0.8045/0.907/0.968/1.026 -> N 노출 7/9/10/11, 라이브 손실 모두 0)와 `integ_boot.py` 추가, golden recall 게이트 추가(승인 구간 130개 중 keep 이 50% 못 덮는 8개를 기준선으로, 새 실패 0).
- codex(B): 처음 실행은 환경 오류로 검토가 없었고(verdict block 은 코드 판단이 아님) 재실행해 9건(high 2). NAS 화면 신호 읽기 실패가 정상으로 저장되던 것 -> NasDown + partial 기록 안 함, sig/scene 캐시 키에 점수 npy, 장면 풀 5개 파일, vis 보정 mu/sd 추가, has_refs 현재 풀로 재계산, manifest 원자적 쓰기, 섀도 diff 가 카드 삭제를 이탈로 셈, make_final 클립 재사용에 컷 시각 일치.
- 도메인(C): '클립 금지' 문구 클립 4곡 발견(목록 도구), #111 소리 확인 4.7초 남음(자체 검수 ok -> soundcheck 정정), mary 10-23 #1 시작이 큰 잡음 위 -> `lead_pad(settle=)`(auto 아닌 곡만, 2클립 재생성), 메모 필수 곡 #64 #33 미생성(허용 목록으로 새 실패만 차단), 자체 검수/문서 낡음 정정.
- **2차 리뷰**: 2건(finding 8건, 1건, 둘 다 `ship_with_fixes`)이 돌았다. finding 8건(A2-1~A2-8, fable)은 이번에 본문을 받아 모두 직접 재현해 처리했다(integration.md 9.2절: fixed 8). 나머지 1건(finding 1건)의 본문은 여전히 전달되지 않아 처리하지 못했다. 새 세션은 그 리뷰의 원문 확인 또는 재실행이 첫 일이다.
- 2차 반영 요약: n_visual B 열 hold-out 이득 주장 삭제(임계가 표본 내와 같은 곡으로 정해짐), golden 라이브 48행을 같은 규칙으로 센 B 수치 정정(규칙 D 라이브 손실 blind9 1/49 -> 0/49, 풀 4/136 -> 2/136), check.py logo 단계를 개수 단언에서 곡 집합 비교로, `--rescene` 추가(치지직 golden 12개 방송 장면 재계산: 이탈 0), 메모 감사 수동 참조 #44 #54 정정(selftest 11/13), 임계 1.026 입력 출처 명시(배포 경로로 치환하면 1.017, 결과 불변), 화이트리스트 15713736@20467 사유를 미결 질문 3 대기로.

### 32.6 알려진 한계 (정직하게)
- 청취 검수가 없다: S3 #50(-13.2초) #65(-16.4초, 허밍 여부), TAIL/종료 컷 연장 전부, settle 두 클립, 끝 뒤 소리 종류(low 10곡). 프레임/스펙트로그램으로 방향만 확인했다.
- 개선 수치 대부분이 표본 내다. 메모 감사 8/11/12 는 규칙을 설계한 곡 위, n_visual 임계 1.026 은 알려진 라이브 최댓값 + 0.1 x 범위(표본 내 보정), N 노출 이득은 스트리머 6명, hold-out 이득 구간이 0 을 포함한다. 같은 규칙이 풀과 분할에 따라 N 노출 10~16/55 를 오간다.
- golden gate 는 weak/vis 를 안 본다(경계와 등급만: 매번의 vis 감시는 check.py logo 단계의 라이브 풀 136 손실 0 이 맡는다). 등급 입력(장면)은 저장된 4_scene.json 이고 치지직 golden 12개 방송은 통합 전 산출물이라 장면 규칙을 바꾸면 `check.py --rescene` 으로 확인한다(이번 실측 이탈 0). 승인 구간 12개(고유 10곡)는 탐지가 조각내 후보가 없어 어느 게이트도 못 센다(재생목록 정답 6곡 클립 없음: 나나 10-06 3, 나나 10-16 2, 후야 1). 탐지 재현율 문제이며 recall 게이트가 늘어나는지만 감시한다.
- 화면 신호로 못 거르는 N: 타 스트리머 같이보기, 따라 부르기, 대기 화면, 게스트 있는 합방 라이브와 겹치는 장면(원곡 지문 등 오디오 신호 필요, 미착수). 144p 라이브(0.76/0.79)가 있어 임계를 낮추지 못했고 그 대가로 N 약 4곡이 노출된다.
- 클립에 남는 결함: '클립 금지' 문구 4곡, 끝 페이드 0.3초 17개, #111 소리 확인, 시작 늦은 곡(rize 10-04 #23 +42.4초 등), 끝이 이른 곡(#22 #63 #65 #71 #82 #142). 규칙 조정으로 안 풀리고 구조적이다(MR 위 멘트, 무반주 구절).
- NAS 세션 쿠키가 ffmpeg 명령행(`nas_auth.ffargs`)에 실린다(기준선부터). n_visual 은 호스트 venv 에서만 돈다. `make_final.RULE` 은 "v6-integrate" 그대로라 같은 이름 규칙에 settle 이 섞였다(바뀐 두 클립만 새로 만듦). `out/manifest.json` 을 새 키 정의로 한 번 옮겼다(백업 `cache/review_A/manifest.bak.json`, 되돌리려면 코드의 키 정의도 같이).

### 32.7 사용자 답이 필요한 질문과, 답에 따라 켤 수 있는 보류 규칙
질문 (답 전까지 규칙 변경 없음, golden_v4.json unresolved 에 기록):
1. **22/82/18번 끝 시각**: 클립 안에서 곡이 끝났다고 들은 시각이 몇 분 몇 초인가. 22는 재생목록 25428.6 vs 오디오 25511 vs 메모 "약 1분", 82는 음악 끝 18074.4 뒤 컷, 18은 확인된 부족분 19.5초 (rize 10-04 #21 의 "1분 끊김", nana 10-06 #02 의 +82초).
2. **승인 시작이 음악 시작보다 15~25초 늦은 5곡**(나나 10-06 25775 등): 전주를 뺀 의도인가, 탐지 당시 값이 그대로 승인된 것뿐인가.
3. **#45(nana 10-16 #14)**: 재생목록 정답은 MR 전주 포함(15.6초 앞)인데 L 판정. 전주 없는 시작이 선호인가, 포함이 선호인가.
- **Go 상주 큐(songd)+TS 클라이언트를 통합할지**: `proto/sd-harness` 에만 있고 통합하지 않았다(호출당 파이썬 시작 471ms -> 상주 p50 5ms, 작업자 재시작/인증/레인 분리 미구현). 요구 여부는 이 저장소에서 확인하지 못했다(33절).
- 이어서 정할 것: '클립 금지' 4곡(나나 10-16 #19 #20 #21 review, #22 auto)을 올릴지 뺄지, 컷 곡 끝 +1초 원칙과 0.3초 페이드(27절 TAIL), 청취 확인(S3 #50 #65, 종료 컷), 메모 #64(메리 10-18 데뷔방송 앞 5분 예외)와 #33(리제 10-09, 앞을 자르면 라이브인데 등록부 N 이 이김).

답에 따라 켤 수 있는 보류 규칙 (각 규칙은 켜기 전 `python harness/check.py` 로 영향 곡을 보고, 의도한 이동이면 golden_v4.json 화이트리스트에 사유를 적고 `--accept`):
| 답 | 켜는 규칙 | 근거 수치와 비용 |
|---|---|---|
| 질문 2, 3 이 "전주 포함 선호" | (a) S3 를 auto 에도 적용 (`make_final.make` 의 `tier != "auto"` 조건 해제, #45 가 -15.5초 움직이고 golden 이탈로 잡힘) | boundary: 영향 구간 10개 중 auto 1 |
| 위와 같음 | (b) detect 히스테리시스(lo 0.05, 연결 60초) | keep 191 -> 208, #20 #144 해소, 승인 15곡 시작이 앞당겨짐(전주 포함 정책을 한꺼번에 켬). GPU 로 refine 재실행 + golden 재동결 필요 |
| 위와 같음 | (c) `talk_break_s` 20 | keep 191 -> 181, #144 해소, 승인 1곡(rize 10-19 끝 +77.5초) 원인 확인 필요 |
| 질문 2, 3 이 "전주 제외 선호" | 위 (a)~(c) 모두 끄고 S3 는 review 에만 유지(현재 상태) | 변경 없음 |
| 질문 1 에서 늦은 끝(오디오 시각)이 맞다고 확인 | 끝 연장 계열(E4: 끝 뒤 조용한 소리 연장, floor -55dB)을 review/B 후보에만 시험. 재생목록(이른 끝)이 맞으면 memo_audit 정답만 수정하고 규칙 변경 없음(이 연결은 계획이고 실측 아님) | E4 -55dB: 방향 13 -> 15(#54 +1.3초, #65 +3.3초). 전체 적용이면 ok 65/67(#57 #69 훼손), review/B 한정이면 67/67 |
| TAIL 청취 확인에서 "말 유입이 더 거슬린다" | 말 직전 컷 최소 +0.0~0.15, 페이드 0.3초 미만 허용(`make_final` 의 페이드 assert 변경) | 말 유입 30곡 8.5초 -> 0~30곡 0~4.5초, 곡 끝 추정 오차 0.5초로 마지막 음을 자를 위험 |
| "클립 금지" 4곡 제외 | `clip_banner.py` 판정을 `make_final` 에 연결 | 현재는 목록만(마스크가 nana 10-16 문구 하나) |
| #111 류 소리 확인 | "딥 직전 컷" 규칙 | 표본 1곡이라 게이트와 표본이 더 필요 |
| n_visual 임계 완화 | `integ_holdout.py cal --write` | 1.026 -> 0.968 이면 N 노출 11 -> 10, 새 방송 라이브 vis 가 쌓인 뒤 |
| 라이브 풀의 스트리머가 지금(11명)보다 충분히 늘면(예: 20명) | 학습형 AND(LR + CRC alpha 0.05) weak 표시 전용 | 규칙 D 위 AND 로 10 -> 5/55(sd-harness). 규칙 D + vis 위 통합 재시험에서는 4 -> 3 으로 1곡 이득이고 alpha 0.05 에서 blind9 라이브 손실 1/49, 임계 sd 15~50%. weak 표시만, drop 금지 |
| 사용자 검수 부담을 더 줄여야 하면 | 위원회 불일치 + 불확실 상위 중 k-center 로 10곡 선택(P7) | 무작위 대비 1.7배, 사용자 판정 1회 더 필요 |
| 카드 힌트가 필요하면 | asr 가사 힌트(`proto/sd-asr` 의 `experiments/asr_bounds.propose`) | 끝 tp 3/12 fp 1/31, 시작 tp 4/9 fp 1/36, 호스트에 faster-whisper 와 후보당 약 20초 GPU, auto 금지 |

## 33. 최종 리뷰와 마감 (2026-10-29, 브랜치 proto/sd-integrate) - 32절 다음에 읽는다

32절 이후 마지막으로 돌린 두 리뷰(codex 관점 B 의 verdict block, 적대적 총괄 D 의 ship_with_fixes)의 medium 이상 7건(B-1~B-5, D-1, D-2)을 직접 재현해 고쳤다. 새 리뷰 라운드는 없다. 항목별 재현/조치는 `experiments_log/integration.md` 9.3절.

### 33.1 한 일
- 게이트 신뢰성(B-1, B-2, B-5): `check.py logo` 가 라이브 손실을 저장본 유무와 `--accept` 와 무관하게 이탈로 본다(손실 상태를 기준으로 저장하지 않음, 저장본이 없으면 실패), `with_golden` 이 golden 행을 조용히 빼면 예외, 자식 출력을 UTF-8 로 통일(cp949 콘솔에서 죽던 것). check.py 자체 selftest 추가(selftest 13/13).
- 하네스(B-3, B-4): `manifest.Run.run` 을 root 단위 OS 잠금으로 감싸 동시 실행을 직렬화, scene 키에 NAS 영상 경로와 크기 추가. 키 정의가 바뀌어 `out/manifest.json` 을 한 번 옮겼다(옛 정의로 61/61 최신 단언 후, 출력 불변, 백업 `cache/review_final/manifest.bak.json`).
- 판정용 표(D-1, D-2, D-3): `review.csv`/`review.xlsx` 를 다시 만들었다(클립은 그대로). 열 `blind9_memo`, `memo_check` 추가, 메모 방향 미충족 곡은 위험 점수 +1.5, 동점이면 메모가 있는 곡 -> 승인 곡 순. priority=1 은 10곡 그대로이고 2곡이 바뀌었다(빠짐: 나나 10-06 `auto_261006_nana1_10`, 토아 10-24 `review_..._toa3_09` / 들어옴: 토아 10-24 `auto_..._toa3_05`, 나나 10-06 `review_..._nana1_02`). #50(`review_261016_nana1_19`) 노트에 두 번째 말 구간과 대안 시작 22418.9(-4.7초 늦음)를 적었다.
- 문서(D-4, D-5): 32.2 앙상블 행 판정 정정, 32.7 에 Go/TS 통합 여부 추가.
- 코드로 클립이 바뀐 곳은 없다. `make_final`, `snap` 등 경계/등급 코드는 이번에 건드리지 않았다.

### 33.2 최종 게이트
`python harness/check.py` 종료코드 0: selftest 13/13, golden 이탈 0(화이트리스트 6, 안 쓰인 0), recall 새 실패 0(기준선 8), 메모 감사 hit@0.5/3/10 8/11/12 방향 16/27 좋음 67/67 사라짐 0 길이>5초 1, logo 오디오만 14/55 화면 11/55 라이브 손실 0/49(라이브 풀 136 전체 0), drift 0. 전체 게이트 둘을 동시에 돌려도(잠금 시험) 둘 다 종료코드 0.
`python harness/check.py --rescene`(789초)도 종료코드 0: 치지직 golden 12개 방송(70곡)의 장면 단계를 현재 코드로 다시 계산해도 golden 이탈 0(화이트리스트 6), 프레임 못 읽은 후보 12(저장본 12), has_refs 달라진 방송 5(32.5 A2-4 와 같음). 이 실행 중에 전체 게이트 둘을 더 동시에 돌렸고 모두 종료코드 0이었다(manifest 잠금).

### 33.3 못 한 것과 이유 (정직하게)
- NAS 접속/로그인이 필요한 일은 금지 조건이라 하지 않았다: `reroute_nas --manifest` 재실행, 새 클립 인코딩, NAS 프레임으로 n_visual 다시 점수화. 그래서 이번 변경이 클립에 영향이 없음은 코드 경로(경계/등급 코드 불변, 61방송 manifest plan "전부 최신", 게이트 drift 0)로 확인한 것이고 클립을 새로 만들어 비교한 것은 아니다.
- codex 의 not run 목록(옛 manifest 롤백, 마이그레이션 멱등성, Windows 경로 길이와 대소문자 충돌, 신규 환경 의존성 설치, 로그/cache 전체 비밀 전수검사)은 하지 않았다. `cache/nas_session.txt` 는 gitignore 에 걸려 있고 전 브랜치 이력에 없다.
- B-6(holdout selftest 의 재적합 분기 누수 변이), B-7(NaN/분산 0 입력)은 low 라 미뤘다(참고 지표 쪽이고 게이트에 영향 없음, integration.md 9.3).
- 청취 검수 없음은 그대로다(S3 #50 #65, 종료 컷 전부, settle 두 클립). #50 은 시작이 22410.4(-13.1초)인지 22418.9(-4.7초)인지 귀로 확인해야 한다.
- 32.5 의 "본문이 전달되지 않은 2차 리뷰 1건"은 이번에도 받지 못했다(최종 라운드 두 리뷰와는 별개다). 'xhigh' 요청의 이행 기록은 저장소 어디에도 없어 요구 여부를 확인하지 못했다.

### 33.4 사용자가 일어나서 볼 것
`out/READ_ME_FIRST.md`(경로, 먼저 볼 10곡, 결정 질문 3개 + 정책 2개, 표본 내/hold-out 구분 수치, 한계). 질문 3개: 22/82/18 끝 시각, 승인 시작이 늦은 5곡의 의도, #45 전주 포함 선호. 정책 2개: '클립 금지' 문구 클립 4곡, 끝 페이드 0.3초 17개(컷 곡 끝 +1초 원칙). 핵심 수치의 성격: 메모 감사 8/11/12 와 N 노출 14/55 -> 11/55 는 표본 내, hold-out 은 13/55 에 이득 구간 [0, 7]곡(0 포함)이라 효과 크기를 말할 수 없다. 62클립 중 위험 점수 상위 10곡만 보면 된다.
