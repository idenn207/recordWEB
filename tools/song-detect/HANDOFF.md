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
