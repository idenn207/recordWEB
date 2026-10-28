# 통합 기록 (브랜치 proto/sd-integrate, 기준선 song-detect/baseline-20261029 = 8f841a3, 2026-10-29)

다섯 프로토타입(sd-sweep, sd-boundary, sd-visual, sd-harness, sd-asr)의 채택안을 기준선 위에 한 단계씩 별도 커밋으로 얹고, 단계마다 게이트를 돌려 전/후를 적었다. 원시 결과는 `cache/proto_integrate/`(메인 cache 의 하위 폴더), 도구는 `harness/`와 `experiments/integ_*.py`.
검수 한계: 모든 경계/화면 판단은 파형, 점수, 스펙트로그램, 프레임 이미지를 Read 로 직접 보고 했다. 귀로는 듣지 못했다(청취가 필요한 항목은 unverifiable).

## 0. 공통 표본과 정의 (모든 수치는 이 정의로 다시 적었다)

트랙마다 "N 노출 10/55", "14/55", "23/55" 가 서로 다른 것을 셌다. 아래로 고정한다.

표본
- N 55: blind9 사용자 N 판정 고유 곡 55개(`data/review/blind9/labels.json`). NAS 후보 191개 중 등록부 N 라벨 55개(known_negatives 의 blind9 항목)와 개수가 같다(곡 단위 대조는 안 함).
- 라이브 49: blind9 라이브 고유 곡 49개(신호 표 기준). NAS 후보 카드로는 라이브 61(blind9 47 + 재생목록 14)이 같은 범위를 덮는다.
- 승인 golden 113: `experiments/golden_v4.json`(이탈 게이트, 승인 라이브 경계/클립/등급).
- hold-out 라이브 풀 136: 신호 표 라이브 88 + 표에 없는 golden 라이브(`logo_route.py --golden`).

용어
- N 노출 = N 55 중 **등록부(known_negatives/approved) 없이** 사람에게 보이는 곡 수. 보임 = 등급 auto 이거나 weak 가 아닌 review/optional. (등록부를 켜면 55곡 전부 drop 이라 0 이고 이것은 규칙 성능이 아니다.)
- 라이브 손실 = 라이브 곡 중 drop 이거나 weak 인 수. golden 113 은 별도로 golden gate 가 경계/클립/등급 하락을 센다.
- 두 열로만 보고한다.
  - A(표본 내): 배포 임계 그대로. 임계가 이 표본에서 정해졌으므로 **회귀 감시용**이지 일반화 수치가 아니다.
  - B(hold-out): 스트리머 단위로 제외하고 신호 선택과 임계를 다시 정함(`logo_route` 행 D m=0.1), 라이브 풀 136, 그 위에 n_visual 임계도 스트리머 제외로 다시 정해 얹음. **일반화 주장은 B 로만 한다.** 표본이 스트리머 11명이라 구간이 넓다.

과거 수치의 정체 (같은 이름, 다른 것)
| 과거 표기 | 실제 내용 | 정의 | 이번 재보고 값 |
|---|---|---|---|
| 14/55 (HANDOFF 28, sweep, harness) | 배포 임계, 신호만, 표본 내 | A | 14/55 (통합 후 visual 추가 시 11~12/55) |
| 23/55 (행 A, HANDOFF 25) | 옛 weak 대역(움직임 25~34.5)을 "노출"로 센 표본 내 값 | A 의 옛 규칙 | 참고(현행 규칙 아님) |
| 10/55 [8-32%] (HANDOFF 28) | hold-out(행 D m=0.1), 라이브 풀 88(golden 제외) | B 의 낙관판 | 풀 136 + 스트리머 단위로 다시: 16/55 |
| 14/55 [11-42%] (logo --golden, 방송 단위) | hold-out, 풀 136, 방송 단위 그룹 | B 의 다른 분할 | 위와 같은 정의 안의 분할 차이 |
| 10/55 (visual V23) | 배포 규칙 위에 시각 신호(표본 내 임계 0.8045, 클립 프레임) | A + visual | 12/55 (임계 1.026, 클립 프레임) / 11/55 (임계 1.026, NAS 후보 프레임) |
| 6~8/55, 5/55 (harness H20/H49) | 학습형 AND(그룹 hold-out, 풀 88) | B 의 낙관판 | 아래 5절(b) |

B 가 풀과 분할에 이렇게 민감하다는 것 자체가 결과다: 같은 규칙이 10~16/55 사이를 오간다. 점추정 하나로 읽지 않는다.

## 1. 요약

채택(모두 게이트 통과, 각각 별도 커밋)
- 도구: harness(manifest, replay, shadow_diff, check), tune.py, 단계별 3_final 비교(integ_final_diff), hold-out 지표(integ_holdout).
- sweep: 점수 임계 7개 양자화 재중심화(동작 불변), E1B_LOUD 12 -> 10, black_max 0.50 -> 0.47. motion 34.5 는 그대로.
- boundary: S3 시작 제안(auto 가 아닌 곡에만) + engine_rev 지표 + golden 화이트리스트 6건.
- visual: n_visual + route.mark_likely 훅(weak 표시만), 4_scene 단계 연결, **임계 0.8045 -> 1.026 으로 통합 때 재보정**.
- 연결: NasDown 가드(scene=None 저장 방지), pipeline.decide/card_file 공용화, manifest 를 reroute_nas --manifest 로 연결(출력 동일 확인 후).

기각/보류(5절): (a) 시각 점수로 review 정렬, (b) 규칙 AND 학습형 weak(CRC), (c) asr 가사 힌트 카드 연결, (d) YAMNet 추가 클래스.

## 2. 단계별 게이트 (전/후)

| 단계 | 커밋 | golden 이탈(화이트리스트) | memo hit@0.5/3/10 (중앙 오차) | 방향 | 좋음 | 길이>5초 | 3_final 4538구간 start/end 변화 | A: 배포 규칙 blind9 N 노출 / 라이브 | 191카드 등록부 끔 N 노출(L,B 손실) |
|---|---|---|---|---|---|---|---|---|---|
| 기준선 8f841a3 | - | 0 (0) | 5/9/11 (1.9) | 13/27 | 67/67 | 2 | - | 14/55 / 0/49 (0/136) | 14/55 (0) |
| 0 도구 | 5924581 e446b2b aaa57e1 | 0 | 5/9/11 | 13/27 | 67/67 | 2 | 0 | 14/55 / 0/49 | 14 |
| 1a 점수 임계 7개 | 0644985 | 0 | 5/9/11 | 13/27 | 67/67 | 2 | 0 (필드 변화도 0) | 14/55 / 0/49 | 14 |
| 1b E1B_LOUD 10 | 79a4e86 | 0 | 6/9/11 (0.85) | 13/27 | 67/67 | 2 | 1 (rize 10-04 #20 끝 -1.5초) | 14/55 / 0/49 | 14 |
| 1c black_max 0.47 | d5a983b | 0 | 6/9/11 | 13/27 | 67/67 | 2 | 1 (동일) | 14/55 / 0/49 | 14 |
| 2 boundary S3 | 5e643ac d170ef7 | 0 (6) | engine_rev 8/11/12 (0.35) | 16/27 | 67/67 | 1 | 1 (동일), alt_start 새 키 10 | 14/55 / 0/49 | 14 |
| 3 visual 모듈 | 33cb952 | 0 (6) | 8/11/12 | 16/27 | 67/67 | 1 | 동일 | 14/55 / 0/49 | 14 (vis 없음 = 옛 동작) |
| 4 연결(NasDown, decide, manifest) | cb8db4f | 0 (6) | 8/11/12 | 16/27 | 67/67 | 1 | 동일 | 14/55 / 0/49 | 14 |
| 5 vis 연결 + 임계 0.8045 | be2faba | 0 (6) | 8/11/12 | 16/27 | 67/67 | 1 | 동일 | 14/55 / 0/49 | 7 (L,B 손실 0) |
| 5 vis 재보정 1.026 | bd347a1 | 0 (6) | 8/11/12 | 16/27 | 67/67 | 1 | 동일 | 14/55 / 0/49 | **11** (L,B 손실 0) |

모든 행에서: test_route(n_visual 시험 포함), snap/finalize/make_final/pipeline/detect/manifest/shadow/memo/tune/n_visual selftest 통과(check.py selftest 11/11), eval_blind blind9 출력이 기준선과 바이트 동일, logo_route 행 A 재현(노출 23 / weak 22 / drop 10 of 55), 곡 사라짐 0. 이동 > 1초 경계 886개의 규칙 이름 귀속 100%(memo_audit --attrib).

B(hold-out) 열은 경계 단계(1~4)에서 변하지 않는다(경계 규칙은 route 신호를 안 건드림). 변하는 것은 5단계뿐이다.
| 구성 | blind9 N 노출 | blind9 라이브 손실 | 전체 라이브 손실(136) |
|---|---|---|---|
| 규칙 D m=0.1 (단계 0~4) | 16/55 | 1/49 | 4/136 |
| + n_visual(스트리머 제외 임계 m=0.1, 단계 5) | 14/55 | 1/49 | 4/136 |
| 라이브 풀 88(golden 제외), 스트리머 단위, 규칙 D m=0.1 | 10/55 [11-29%] | 0/49 | 2/88 |
| 위 + n_visual (vis 임계 학습 풀에는 golden 포함) | 8/55 | 0/49 | 2/88 |

n_visual 이 더하는 손실은 모든 조건에서 0. 규칙 D 자체의 손실(1/49, 4/136)은 통합 전부터 있던 hold-out 특성이다. 배포 규칙(표본 내)의 0 손실을 일반화 수치로 읽으면 안 된다.

## 3. 단계 상세

### 0 도구
- sd-harness 에서 manifest/replay/shadow_diff/scene_real/check, Makefile 만 가져왔다(Go 서비스, 학습 랭커, 후보 선택은 안 가져옴). `PH` 를 `cache/harness` 로 분리해 프로토타입 캐시와 섞이지 않는다.
- memo_audit selftest 단언 13 -> 11(26절 P2 이후 #20, #26 끝이 수동 판정 실패에서 통과로 바뀐 의도한 개선), check.py 의 KNOWN 예외 삭제.
- sd-sweep 의 tune.py 와 게이트 3개의 `import tune`. tune selftest 는 채택 상수로 바뀌어도 깨지지 않게 시작 값을 기억하도록 고쳤다(원본은 snap.LOW == 0.25 를 단언해서 1a 뒤 실패했을 것).
- check.py 기준 스냅샷 --accept: 단계마다 변화 리포트를 보고 받아들였다. 기준선 스냅샷은 `cache/harness/check_accepted_s0`, 통합 전 memo 저장본은 `data/review/blind9/audit/memo_audit_baseline_pre_integrate.json`.
- 새 도구 `experiments/integ_final_diff.py`: 61방송 4538구간(keep 아닌 구간 포함)의 3_final.json 을 단계 전 복사본(`cache/proto_integrate/final_base`)과 구간 단위로 비교한다.

### 1 sweep 상수 (3 커밋)
- 1a 양자화 재중심화: LOW 0.2305, MU 0.457, SPEECH 0.7031, E1_MU 0.8262, E1_SP 0.2305, E1B_MU 0.457, E1B_SP 0.2969. 4538구간 start/end 와 다른 필드 변화 모두 0, golden/memo 지표 동일 -> 동작 불변 재확인.
- 1b E1B_LOUD 10: 이동 구간은 정확히 1개(rize 10-04 #20, 끝 11181.0 -> 11179.5). memo hit@0.5 5 -> 6, 중앙 오차 1.9 -> 0.85. 자체 검수: 스펙트로그램(`cache/proto_integrate/views/e1b_loud_rize_11180.png`)에서 11179.5 는 소리가 -15dB 에서 감쇠를 시작하고 Speech 점수가 0.75 로 오르는 지점이고, 이전 끝 11181.0 은 감쇠 한가운데다. 재생목록 정답 11179.5 와 일치.
- 1c black_max 0.47: 저장된 191후보의 blk 에 0.47~0.50 구간이 없어(0.4498 다음이 0.5077) 등급/카드가 안 바뀐다. 위험은 새 방송에서 blk 0.47~0.50 같이보기 N 이 watch 가 아니라 live 풀 비교로 넘어가는 것(표본 0건).
- motion 34.5 는 낮추지 않았다(30 으로 내리면 승인 라이브 V15 류가 drop).

### 2 boundary S3
- sd-boundary 의 소스 커밋(ad9c032)을 그대로 가져왔다(snap.start_s3, finalize alt_start, make_final 은 tier != auto 에서만 사용, pipeline 카드에 alt_start, audit_engine/memo_audit engine_rev/golden_gate/golden_v4.json 화이트리스트 6건). check.py 의 memo 단계 소스를 engine_rev 로 바꾸고 `memo_audit.py --save --attrib` 로 저장본 갱신.
- 기대치와 일치: golden 0, engine_rev 8/11/12, 방향 16/27, 좋음 67/67.
- 영향 구간은 10개(auto 1: #45 는 make_final 이 쓰지 않음, review 4: #44 #50 #54 #65, drop 5). 화이트리스트 6건은 3개 review 곡(재생목록 정답 쪽으로 가까워지는 이동)의 시작이동과 클립길이.
- 자체 검수(스펙트로그램 `views/s3_*.png`, 현재 시작과 제안 시작을 표시):
  - #44(nana 10-16 @20110): 제안 20079.3, 재생목록 정답 20079.15. 깊은 무음 뒤 저음량 전주가 시작하는 지점과 일치.
  - #54(nana 10-16 @23290): 제안 23283.2 = 오디오 근거 정답 23283.2. 직전 -55dB 딥 뒤 저음량 MR 전주가 시작, 본 소리는 23289.9. 메모 "전주 MR 약 5초 더"(1.7초 차)와 부합.
  - #50(nana 10-16 @22424): 제안 22410.4(-13.2초). 메모 "앞부분 조금 잘림"과 방향은 맞지만 정답 시각이 없어 양은 확인 못 함.
  - #65(mary 10-18 @2739): 제안 2722.9(-16.4초). 메모는 "앞 허밍이 빠짐". 저음량 구간이 제안 지점부터 이어지는 것은 보이나 허밍인지는 귀로 확인 못 함(unverifiable).
  - #45(auto, L)는 제안(-15.5초)이 있어도 쓰지 않아 승인 경계 그대로다(전주 포함 선호는 미결 질문 3).
- 한계(소스 주석에도 있음): 앞에 멘트/박수가 낀 #60 류를 못 거르는 가드(EXT_MU)가 표본 1건 근거.

### 3 visual 모듈
- n_visual.py(SigLIP2 B/16 제로샷, 프레임 8장, 프롬프트 5세트 z 평균), n_visual_cal.json, route.mark_likely 훅(오디오 신호와 합쳐 weak 표시만, drop 아님), test_route 시험. vis 가 없으면 옛 동작이라 이 커밋은 동작 불변(모든 게이트 동일).
- 가중치는 HF 허브의 timm/ViT-B-16-SigLIP2 를 받는다. 오프라인 배포는 `~/.cache/huggingface/hub/models--timm--ViT-B-16-SigLIP2` 를 미리 채워야 한다(이 PC 는 이미 있음). torch+open_clip 은 호스트 venv(C:/_tools/wt/venv)에만 있고 분석기 컨테이너에는 없다.

### 4 연결 (NAS 가드 먼저)
- NasDown: `scene.thumbs` 는 ffmpeg 실패(401 포함)를 빈 배열로 삼켜 reroute 가 scene=None 을 저장할 수 있었다. `scene.nas_thumbs` 가 NAS 주소에서 프레임 3장 미만이면 NasDown 을 내고, `pipeline.main` 은 4_scene.json 을 쓰기 전에 중단한다. `reroute_nas.py` 는 실패한 방송의 지운 단계 파일(3_final, 4_scene)을 둘 다 되돌리고 NasDown 이면 남은 방송을 건너뛴다. 로그인은 시도하지 않는다. 시험: 존재하지 않는 NAS 경로 -> NasDown, 로컬 경로 -> 옛 동작.
- manifest 연결: 등급 결정(`pipeline.decide`)과 카드 파일 이름(`card_file`)을 pipeline.main 과 manifest.Run.route 가 같은 코드로 쓴다(두 벌 방지). `reroute_nas.py --manifest` 가 입력이 바뀐 단계만 다시 한다.
- 활성화 조건 확인
  - 기준선 코드에서 manifest 출력 = 기존 out/: 3_final 61/61, 카드 191/191(등급, 사유, likely, weak, 경계, stages, nsig, 장면 포함) 동일.
  - 현재 코드에서 같은 입력으로 pipeline.py 경로(61회 실행 25초)와 manifest 경로(13초): 3_final 61/61, 카드 191/191 완전 동일. 기존 out/ 과의 차이는 의도한 1구간(#20 끝)뿐.
  - 실제 NAS 재계산 시험(임시 루트, 2방송 45후보, 282초): 경계가 같은 43후보의 장면값이 저장값과 동일, 바뀐 1후보는 tstd 22.017 -> 21.999(같은 분류).
- 스크립트 끝까지 시험: song-detect 를 임시 폴더로 복사하고 data/cache 는 연결, out/ 에는 2방송(rize 10-04, nana 10-16)만 넣어 `reroute_nas.py --manifest` 를 호스트 venv 로 실행했다. 단계 실행 final 1.4초, scene+vis 353초(45후보, 후보당 약 8초), route 1.1초. 결과의 등급/likely/weak/경계/vis 가 스크래치 결과와 전부 같았고 vis 는 45/45 채워졌다(임시 폴더는 지웠고 메인 out/ 은 그대로).
- 개선: 장면 재사용은 scene 코드/풀 키가 지난 실행과 같을 때만(black_max 나 풀이 바뀌면 같은 경계도 multi 가 달라질 수 있어 전부 다시 읽음). 처음 `--manifest` 실행은 기록이 없어 NAS 에서 191후보를 다 읽는다(후보당 약 8초라 약 25분). 이후는 경계가 바뀐 후보만.
- 메인 out/ 은 건드리지 않았다(재생성 안 함). 실사용 전환은 아래 7절.

### 5 vis 연결과 임계 재보정
- `pipeline.fill_vis`(torch+open_clip 이 없으면 stderr 한 줄 남기고 건너뜀), manifest 는 vis 를 장면 필드로 재사용하고 n_visual 코드/보정 파일이 바뀌면 장면과 route 를 stale 로 본다, `IN_KEYS` 에 vis. `n_visual.frames_of` 는 4개 동시 ffmpeg 로 곡당 약 5초 -> 1.3초.
- 스크래치 루트(out_m)의 191후보 전부에 vis 채움(5.3분, 못 읽은 후보 0).
- 발견: golden 113곡을 **배포 경로**(프레임 8장, NAS 1080p 또는 치지직 144p)로 다시 점수화했더니(9분) 144p 곡 둘이 0.79(15831370@1190, blind7/8 사용자 라이브), 0.76(15827672@10612, 재생목록 정답)이었다. visual 트랙의 라이브 133곡 최대는 0.588 이라 임계 0.8045 와의 간격이 0.015 밖에 안 됐다(해상도에 따라 같은 곡 점수가 바뀜). 임계를 알려진 라이브 246곡(133 + golden 113)의 최댓값 + 0.1 x 범위 = **1.026** 으로 올렸다(`integ_holdout.py cal`).
- 효과(191후보): 등록부 끈 N 노출 14 -> 11(0.8045 였다면 7), L/B 손실 0, 등록부 켠 노출 0 유지. 기준선 대비 바뀐 후보 12(N 7, U 5), 등급 이동 0, shadow diff 이탈 0. 라이브 vis 최대 0.59(NAS 후보), golden 113 최대 0.789 < 1.026, 초과 0.
- U 에서 weak 로 바뀌는 review 등급 후보는 1개뿐(rang 10-21 @21381, vis 1.38): 프레임을 직접 보니 3D 게임 화면(구르는 공), 아바타 없음 = 27절 자체 검수에서 게임 BGM 으로 본 곡이다. 나머지 바뀐 후보는 이미 drop.
- 프레임 직접 확인(`views/vis_m1.jpg`): 라이브로 판정된 GTA 노래방 장면(rize 10-03 @14649, vis 0.59)과 4인 합동 노래방(toa 10-24 @3086, 0.59)은 임계 아래로 남고, N 인 웹페이지+GTA 창(nana 10-07 @18838, 0.84)과 영상 창 위에 아바타(hiyori 10-20 @534, 0.83)는 0.8~0.85 로 **임계 근처**라서 새 임계 1.026 에서는 이 둘이 weak 가 아니게 된다. 즉 재보정은 N 3~4곡 대신 라이브 안전 간격(0.24)을 산 것이다.
- 재현: visual 트랙 캐시 프레임 204곡을 배포 코드로 다시 점수화하면 라이브 133곡 0 초과(최대 0.588), N 71 중 35 초과(임계 0.8045 기준). 유형별 거름 N: 리듬게임 8/9, 커버 같이보기 8/12, GTA 노래방 6/9, 자리비움 5/9, 게임 OST 5/7, 잡담 BGM 3/5, 대기 화면 0/4, 따라 부르기 0/3, 타 스트리머 같이보기 0/12, 같이 듣기 0/1.
- 한계: golden gate 는 route.tier 까지만 보고 mark_likely(weak)와 vis 를 안 본다. 그래서 "승인 라이브 노출 하락 0"은 shadow diff(NAS 191후보 L/B 61곡)와 golden 113곡의 vis 직접 계산으로 확인했다.

## 4. 이번 통합으로 달라진 숫자 요약 (정의 A/B 로)
- A: 배포 규칙 N 노출 14/55 -> 11/55(카드) 또는 12/55(클립 프레임), 라이브 손실 0 유지. 메모 감사 hit@0.5/3/10 5/9/11 -> 8/11/12, 방향 13 -> 16/27, 길이>5초 2 -> 1. golden 이탈 0.
- B: 규칙 D 16/55 -> 14/55(풀 136, 스트리머 제외), 라이브 손실은 그대로(규칙 D 의 1/49).
- 일반화로 말할 수 있는 것: 시각 신호는 hold-out 에서도 N 노출을 1~3곡 줄이고 라이브 손실을 더하지 않았다. 효과의 크기는 표본이 정하지 못한다(스트리머 11명, 구간 5절 참조).

## 5. 추가 시도 (게이트 통과분만 채택, 기각도 기록)

### (a) 시각 점수로 review 정렬 -> 기각
- 방법: 등록부 끈 191후보에서 노출된 review/optional 68곡(N 7, L 43, B 18)을 vis 내림차순으로 정렬.
- 결과: 노출 안 N 7 vs 라이브 61 의 AUROC 0.789, 상위 10곡 중 N 2(무작위 기대 1.0), 상위 5곡 중 N 2. weak 표시가 vis 가 높은 N 을 이미 가져가서 남은 N 은 vis 가 낮아(0.0~0.57) 라이브와 섞인다. 등록부를 켠 실제 review 21곡은 B 18 + L 2 + U 1 이라 정렬로 얻을 것이 없다. 표본 N 7 개라 통계적 검정력도 없다.
- 채택 안 함. review.csv 우선순위는 기존(자체 검수 low/mid/high) 그대로.

### (b) 규칙 AND 학습형 weak (CRC alpha <= 0.05) -> 기각
- 방법: sd-harness 의 ranker(LR C=0.3, 18특징, 그룹 hold-out)에 vis 특징을 더해 규칙 D + vis 와 AND. CRC 임계는 학습 라이브의 안쪽 교차검증 p 에서 (k+1)/(n+1) <= alpha. 스트리머 hold-out, 신호 표 163행(라이브 풀 88).
- 결과(blind9 N 55 / 라이브 49): 규칙 D + vis 4/55 손실 0/49(전체 2/88). 여기에 LR(18특징, FULL) AND: alpha 0.05 -> N 3, **blind9 라이브 손실 1/49**, 전체 4/88. alpha 0.10 -> N 3, 손실 3/49, 전체 9/88. q0(학습 라이브 최솟값) -> N 3, 손실 0/49, 전체 3/88. 특징에 vis 를 더하면(FULL+vis): alpha 0.05 -> N 2, 손실 1/49, 전체 5/88 / alpha 0.10 -> N 1, 손실 2/49, 전체 9/88 / q0 -> N 2, 손실 0/49, 전체 2/88.
- 판정: CRC alpha <= 0.05 는 목표(손실 0)를 어기고, q0 는 N 4 -> 2~3 으로 1~2곡 줄이는데 표본 163행짜리 모델을 배포해야 하고 임계 표준편차가 15~50%다. 이득이 구간 안(55곡 중 1~2)이라 채택 안 함. 도구는 sd-harness 브랜치에 있다.

### (c) asr 가사 힌트(끝 뒤 가사 지속, 시작 앞 가사 존재)를 B/review 카드 힌트로 -> 연결 안 함(측정만)
- 방법: asr 트랙 전사 캐시(t_small_auto, 49곡)와 사슬 규칙(k=3, gap 8초, W 20초, 시험 전에 정한 값)을 **통합 트리 경계(engine_rev)** 에서 재측정. 양성 = 메모가 early/late 한 곡, 음성 = ok 로 판정한 곡.
- 결과: 끝 early tp 3/12, fp 1/31 (S3 영향 없음). 시작 late tp 4/9, fp 1/36(플래그 20, 50, 54, 144). 힌트로는 오탐이 낮다(3%).
- 판정: 연결하려면 호스트에 faster-whisper 와 후보당 약 20초 GPU 전사가 파이프라인에 들어간다. 근거는 양성이 끝 12곡, 시작 9곡뿐이고 구간이 넓다(asr 트랙 hold-out 구간 끝 [0.15, 0.72]). 63곡 중 힌트가 도움 될 곡은 서너 곡이라 비용 대비 이득이 작아 연결하지 않았다. 필요하면 `proto/sd-asr` 의 `experiments/asr_bounds.propose` 를 카드 힌트로만(auto 금지) 쓰면 된다.

### (d) YAMNet 추가 클래스(Rapping/Humming/Breathing 등) -> 기각
- 방법: 분석기 컨테이너(ai_edge_litert + GPU)에서 현재 시작 앞 40초~뒤 10초를 0.5초 간격으로 다시 점수화(9개 클래스), 시작 late 9곡 vs ok 36곡. (캐시에는 Singing/Speech/Music 3열만 있고 cache/proto_* 에 추가 클래스 점수는 없었다.)
- 결과: 시작 앞 20초 max/mean 의 단독 AUROC(late 이 큼): Humming 0.56~0.57, Breathing 0.23~0.37, Rapping 0.52~0.54, Whispering 0.38~0.50, Chant 0.56~0.60, Yodeling 0.65~0.76(중앙값은 late/ok 모두 0). 메모가 명시적으로 "허밍이 빠졌다"고 한 #65 의 시작 앞 20초 Humming 최대가 0.02, 전주가 짧게 빠진 #58 의 Breathing 최대 0.11.
- 판정: 놓친 전주/허밍/호흡을 YAMNet 클래스는 가리지 못한다(점수가 거의 0). 기각. 원자료 `cache/proto_integrate/yam_out.npz`.

## 6. 위험과 한계 (정직하게)
- 청취 검수 없음: S3 의 #50 #65, 모든 끝 규칙은 귀로 확인하지 못했다. 메모와 방향이 맞는지만 봤다.
- n_visual 은 표본 내 보정이다. 임계는 알려진 라이브 246곡 최대 + 0.1 x 범위이고, 표본이 스트리머 11명이라 새 스트리머의 라이브가 1.026 을 넘을 수 있다(넘어도 weak 표시일 뿐 drop 아님). 144p 와 1080p 의 점수 차이를 임계 하나로 덮었다. 임계 근처 N(0.83~0.84)은 프레임 선택에 따라 오간다(NAS 후보 프레임 vs 블라인드 클립 프레임에서 3곡이 달랐다).
- golden gate 가 weak/vis 를 보지 않는다(경계와 등급만). vis 안전은 shadow diff(NAS 191후보)와 golden 113곡 직접 점수로 확인한 것이다.
- black_max 0.47: 새 방송에서 blk 0.47~0.50 같이보기 N 이 샐 수 있다(표본 0건).
- E1B_LOUD 10, S3 가드(EXT_MU)는 각각 정답 1건/표본 1건 근거다(소스에 shortcut 주석).
- `reroute_nas --manifest` 는 임시 폴더(2방송)에서 NAS 재계산과 vis 까지 끝까지 시험했지만, 61방송 메인 out/ 에 돌려 보지는 않았다(산출물 보호).
- integ_holdout 의 vis 표는 visual 트랙 프레임 캐시(cache/proto_visual, 프로토타입 산출물)에 의존한다.

## 7. 실사용으로 켜는 방법 (사용자 결정 필요)
1. 경계 변경(E1B_LOUD, S3)은 RULE("v5-bounds")을 올리지 않아 기존 out/final* 클립에는 아직 반영되지 않았다. 반영하려면 RULE 상향 + `python datasets/reroute_nas.py --manifest`(호스트 venv python 으로: 화면 신호까지) + `python datasets/final_nas.py auto review`(NAS 로그인 필요) 순서다. TAIL/종료 컷 연장의 청취 확인(27절)과 함께 결정할 것.
2. 화면 신호를 쓰려면 `pipeline.py`/`reroute_nas.py` 를 torch+open_clip 이 있는 python 으로 실행해야 한다. 아니면 stderr 에 "n_visual 건너뜀" 한 줄만 남고 옛 동작이다.
3. 한 번에 점검: `python harness/check.py`(약 12초, 종료코드 0/1/2), 승인된 변경 뒤 `--accept`.

## 8. 61방송 재생성 (RULE v5-bounds -> v6-integrate, 2026-10-29)

통합 코드(proto/sd-integrate)로 NAS 61방송 전체를 다시 처리했다. 청취는 못 했고 모든 판정은 프레임/스펙트로그램(Read)이다.

### 8.1 한 일, 예상 대비 실제 시간
| 단계 | 예상 | 실제 | 방법 |
|---|---|---|---|
| 백업 | - | 1분 | `out/<방송>/{3_final.json,4_scene.json,cards}` 를 `out/stale_v5/state/` 로 복사, 카드 요약은 `cache/regen_v6/before_cards.json` |
| RULE 상향 | - | - | `make_final.RULE` "v5-bounds" -> "v6-integrate", selftest assert 도 같이. 이전 클립은 `out/stale_v5/{final,final_review}` 로 이동(105개 mp4, 삭제 없음) |
| 경계/장면/화면/등급 | 30분(후보 191 x 8초 + vis) | 28분(scene 1615초 = NAS 프레임 + vis, final 5.8초, sig 5.4초, route 6.0초) | `SONG_NOCLIP=1 C:/_tools/wt/venv/Scripts/python.exe datasets/reroute_nas.py --manifest` (호스트 venv: vis 까지). `--final` 은 필요 없다: 매니페스트 기록이 없어 final 단계부터 61방송 전부 stale 이었다 |
| 완성본 클립 | 25분(NAS 지연 위주라 동시 실행) | 27분(08:04~08:31) | `SHARD=k/n python datasets/final_nas.py auto|review` 4 프로세스(auto 3 + review 1, 새 `SHARD` 환경변수). GPU 사용률 38% 안팎 |
- 예상의 1.5배를 넘은 단계는 없어 방법을 바꾸지 않았다. NAS 는 시작 전 세션 확인(200)이었고 401 은 없었다. 로그인 시도 없음.
- 단계마다 manifest 가 `out/manifest.json` 을 남기므로 다음 `reroute --manifest` 는 바뀐 후보만 NAS 에서 다시 읽는다.

### 8.2 게이트 전/후
| 항목 | 전(v5-bounds 산출물) | 후(v6-integrate) |
|---|---|---|
| golden_gate 이탈(화이트리스트) | 0 (6) | 0 (6) |
| 승인(auto 42곡) 클립 곡 시작/끝 이동 (`regen_clips_diff.py`) | - | **0**. 컷만 1곡: toa 10-24 #08 끝 컷 +0.30초(27절 종료 컷 연장 미반영분), 클립 길이 변화 최대 0.30초 |
| 등급 수 auto / review / drop | 42 / 21 / 128 | 42 / 21 / 128 (등급 이동 0). 단 review 1곡이 weak 로 바뀌어 클립 63 -> 62 |
| weak 후보 | 60 | 72 (+12: drop 11 + review 1, vis 1.07~1.58 > 임계 1.026) |
| memo_audit(실제 클립) hit@0.5/3/10 | 5 / 9 / 11 | **8 / 11 / 12** (실제 클립 = engine_rev 예측과 모든 지표 동일) |
| 중앙 오차, 방향, 길이>5초, 경계 좋음, 곡 사라짐 | 1.9초, 13/27, 2, 67/67, 0 | 0.35초, 16/27, 1, 67/67, 0 |
| memo_audit 수동 감사 일치 | 11/13 | 9/13 (#44, #54 시작이 수동 판정 실패에서 통과로: 의도한 개선, selftest 단언도 9 로) |
| 3_final 4538구간 start/end 변화 | - | 1(rize 10-04 카드 #23 끝 -1.5초), 새 키 alt_start 10 |
| logo_route(check.py) | 14/55, 라이브 걸림 0/49 | 14/55, 0/49 (배포 규칙 표본 내, 규칙은 안 바뀜) |
| selftest / test_route | 11/11 / ok | 11/11 / ok |
| 클립 ok | 63/63 | 62/62: dur_err <= 0.008초, A/V 시작 차 0, 프레임 수 일치, 1920x1080, 리미터 0, nvenc, auto ctx20 42개 |
| 원본 음량 유지 (`experiments/regen_loudness.py`) | -0.07dB(v5, 같은 도구로 측정) | 클립-원본 rms 차이 평균 -0.07dB, 최소 -0.22, 최대 -0.01, 허용 1.0dB 초과 0 |
| vis (등급 안전) | - | auto 42곡 최대 0.59, review(weak 제외) 최대 0.34, 임계 1.026 |

### 8.3 바뀐 곡 (파일 기준 `regen_clips_diff.py`, 카드 기준 `regen_compare.py`)
- 클립 경계가 바뀐 곡 6개 (모두 review 5 + auto 컷 1):
  - rize 10-04 #23(메모 #20): 곡 끝 -2.40초(E1B_LOUD 10), 클립 -2.65초. memo #20 끝 정답 오차 +2.4 -> 0.0.
  - nana 10-16 #13(#44) 시작 -25.70초, #19(#50) -13.10초, #21(#54) -6.80초, mary 10-18 #03(#65) -16.30초 (S3 제안 적용, auto 가 아닌 곡). #13 은 재생목록 정답 20079.15 에 0.1초, #21 은 오디오 근거 23283.2 에 0.1초 차.
  - toa 10-24 #08(auto): 끝 컷 +0.30초만(곡 경계 그대로).
- 클립이 안 만들어진 곡 1개: rang 10-21 #02(review -> weak). 프레임을 다시 보니 3D 게임 화면(구르는 공)과 애니 그림 카드뿐이고 본인 모델이 없다. N 이 맞다(과거 클립은 `out/stale_v5/final_review/` 에 있다).
- 카드만 바뀐 것: alt_start(S3 제안) 새 키 10개(auto 1, review 4, drop 5), weak 12개. 등급은 한 개도 안 바뀌었다.

### 8.4 자체 시청 검수 (`data/review/blind12/self_check.json`, 62클립 전부)
- 방법: `experiments/self_check_media.py`(클립마다 프레임 3장 + 시작/끝 스펙트로그램/0.25초 rms/점수, `cache/regen_v6/media/*.png`)를 62장 모두 Read 로 보고 `verdicts.json` 에 적은 뒤 `self_check_build.py` 가 메모(blind9 labels)와 묶었다. 귀로는 듣지 못했다.
- 화면: live 62(본인 모델 또는 4인 싱크룸 화면). 시작: ok 52, late 7, speech 3. 끝: ok 41, speech 9, early 7, late 3, mr 2. 확신도 high 21, mid 31, low 10. 메모가 있는 49클립 전부에 메모 대비 결과(memo_vs)를 적었다.
- 이전(blind11, 63클립)과 달라진 판정 10개. 클립이 바뀌어서 달라진 것: 시작 late -> ok 4곡(S3: nana #13, #19, #21, mary #03, 단 #19, #03 은 확신 low). blind11 검수 뒤에 이미 종료 컷 연장으로 다시 만들어진 클립(이번 재생성의 전 상태 stale_v5)이라 판정이 달라진 것: rang 10-17 #2 끝 early -> ok(마지막 화음과 글리산도가 감쇠하며 끝남, 메모 "fade out 1초 더"와 부합), toa 10-24 #12 끝 early -> mr(연장 +1.3초로 일부 해소, 반주가 남은 채 컷). 클립은 같은데 다시 보고 판정을 바꾼 것: nana 10-06 #09, #10 끝 ok -> speech(곡 끝 앞뒤 말소리 점수가 보임), mary 10-23 #01 시작 ok -> speech(컷이 짧고 큰 잡음 위, 8.5 참조), nana 10-16 #18 확신 high -> mid.
- 메모 있는 곡의 결과: 메모가 지적한 시작/끝 중 S3 로 해소된 것은 #44(Mama Lisa 전주), #54(전주 MR 5초)이고 #50, #65 는 방향만 부합(양과 허밍 여부는 unverifiable). 종료 컷 연장으로 부합 쪽으로 간 것은 rang 10-17 #2. 그대로 남은 것은 시작 late(rize 10-04 #23 +42.4초 P5, toa 10-17 #3, toa 10-24 #3, #8, #14, nana 10-16 #14), 끝 early/mr(rang 10-17 #3, toa 10-24 #4, #5, #9, #12, #14, hiyori 10-18 #3).
- 이슈가 있는 클립(시작/끝이 ok 가 아니거나 확신 low) 28개:

| 클립 | 시작/끝 | 확신 | 메모 대비 |
|---|---|---|---|
| auto_261006_nana1_06 | ok/late | mid |  |
| auto_261006_nana1_09 | ok/speech (이전 ok/ok) | mid |  |
| auto_261006_nana1_10 | ok/speech (이전 ok/ok) | low |  |
| auto_261010_nana2_01 | ok/speech | mid | memo L '후렴부터 모른다고 MR 끔, 완곡 안 함': 곡 끝이 MR 꺼진 뒤 1.4초 늦어 말이 포함됨(승인 경계라 변경 안 함) |
| auto_261016_nana1_14 | late/ok | low | memo L 두 행 상반('경계도 좋음' / '전주 MR 과 들숨이 잘림'): 시작 late 쪽 부합, 미결 질문 3(#45 전주 포함 선호) |
| auto_261016_nana1_16 | ok/speech | mid |  |
| auto_261016_nana1_17 | speech/speech | low |  |
| auto_261018_hiyori1_03 | ok/mr | mid | memo L '완곡했으나 종료경계가 MR 끝나기 전에 잘림, 마지막에 MR 과 함께 멘트': 부합(알려진 대가) |
| auto_261021_mary1_01 | ok/speech | mid | memo L '경계도 좋음' 일치 |
| auto_261024_toa3_05 | ok/early | low | memo L '종료 fade out 이 완곡 전에 나와 아쉬움': 부합 가능성(딥 뒤 소리 종류 불명) |
| auto_261024_toa3_08 | late/late | mid | memo 두 행 상반(B '전주 MR 이 조금 잘림' / L '경계도 좋음'): 시작은 B 쪽과 부합 |
| auto_261024_toa3_10 | ok/speech | mid | memo L '4명 라이브, 경계도 좋음' 일치 |
| auto_261024_toa3_13 | ok/speech | mid | memo L '경계도 좋음' 일치 |
| review_261004_rize1_21 | ok/ok | low | memo B '노래 완곡 안 됨, 1분 끊김': 끝은 +19.5초 해소, 1분 주장은 미확인(unresolved 18) |
| review_261004_rize1_23 | late/ok | high | memo(#20): 시작 +42.4 미해결(P5), 끝 정답 11179.5 와 일치(오차 0.0) |
| review_261006_nana1_02 | ok/ok | low | memo B '완곡 안 됨, 1분 끊김': 오디오상 끝은 25511 근처로 보이나 확인 못 함(재생목록 +82초와 어긋남, 미결 질문 1) |
| review_261006_nana1_12 | speech/ok | mid | memo B '완곡 안 됨 종료': 끝 +99.5초 연장으로 해소(P2 오디오 근거 29331.5) |
| review_261016_nana1_19 | ok/ok (이전 late/ok) | low | memo B '논브리스 오블리주 앞부분 조금 잘림': 방향 부합(13초 앞당김), 양은 귀로 확인 필요 |
| review_261016_nana1_20 | ok/speech | mid | memo B '실제 시작 00:06 호흡, 1절 2절만 부르고 후렴에서 끝': 시작 해소로 보임, 끝에 말 2초 포함(메모와 같은 방향의 문제) |
| review_261017_rang1_03 | ok/early | mid | memo B '종료가 완곡 전에 끝나서 잘림': 부합 가능성(귀로 확인 불가) |
| review_261017_toa1_03 | late/early | high | memo B '시작경계가 조금 많이 잘림, 앞에 MR 이 더 있음': 부합(시작 약 1초 늦음) |
| review_261018_mary1_03 | ok/early (이전 late/early) | low | memo B '앞 허밍 빠짐, 종료 완곡 전 끊김': 시작 방향 부합(16.4초 앞당김, 허밍 여부는 unverifiable), 끝은 그대로 early |
| review_261023_mary1_01 | speech/late (이전 ok/late) | mid | memo B '완곡 종료 04:26, 뒤에 종료 경계가 조금 많이 남음': 부합(끝에 곡 아닌 소리 약 3초) |
| review_261024_toa3_03 | late/ok | mid | memo B '시작부분 전주 MR 이 잘림': 부합 |
| review_261024_toa3_04 | late/early | low | memo B '전주 MR 이 조금 잘림': 시작 부합 가능성, 끝은 tail 연장이 일부 보완 |
| review_261024_toa3_09 | ok/early | low | memo B '완곡 전에 fade out, 뒤에 노래가 더 있을 가능성': 소리가 이어진다는 점은 부합(종류 불명) |
| review_261024_toa3_12 | ok/mr (이전 ok/early) | mid | memo B '완곡은 했는데 MR 종료 반주가 남은 상태에서 잘림': 연장으로 일부 해소(+1.3초), 여전히 반주 도중 컷이라 부합 |
| review_261024_toa3_14 | late/early | high | memo B '전주 MR 과 노래 부분이 많이 잘림': 부합(시작 앞 소리가 이어짐, 끝도 소리가 이어짐) |

(전체 62클립의 시작/끝/근거/확신은 `data/review/blind12/self_check.json`. data/ 는 gitignore 라 위 표가 저장소에 남는 요약이다.)

### 8.5 결함 점검과 규칙 수정 판단 (재생성 0/2회 사용)
자체 검수에서 명백히 보인 결함은 한 건이다. 나머지(시작 late, 끝 early/mr/speech)는 메모와 부합하는 알려진 유형이고 점수만으로 일반 규칙이 서지 않는다(27절).
- mary 10-23 #01(review): 클립이 -14 -> -7dB 의 짧은 큰 잡음(0.4초, 말 끝의 숨/웃음으로 보임) 한가운데서 시작한다. 원인: `make_final.lead_pad` 가 무음 공백(곡 중앙값-25dB 아래)이 없어 "음성 없음" 공백(Speech<0.3, Singing<0.3, 음량 제한 없음)으로 폴백했고, 그 공백(18744.1부터 1.0초)에 YAMNet 이 말/노래로 안 보는 큰 소리가 들어 있어 시작+0.05초에 컷이 놓였다.
- 수정 후보 두 가지를 62클립에 대입해 보고(재생성 없이 컷 계산만) 둘 다 채택하지 않았다.
  - (a) 음성 없음 공백에도 `음량 < 곡 중앙값` 제한: 시작 여유 6곡, 끝 여유 12곡의 계산 값이 바뀌고(최종 끝 컷은 tail_cut 이 따로 정함) 그중 승인 auto 가 시작 1곡(toa 10-24 #08, 이미 시작이 늦은 곡이 0.45초 더 늦어짐)과 끝 8곡이다. 시작이 늦은 review(toa 10-17 #3)는 1.4초 더 늦어져 악화. MR 카운트인이 이 공백에서 허용되던 설계와 충돌한다.
  - (b) 컷 프레임이 직전보다 15dB 이상 크고 곡 중앙값보다 5dB 이상 클 때만 컷을 늦추기: 0곡이 움직인다(이 잡음은 곡 중앙값보다 1.9dB 낮아 "곡보다 큰 소리"가 아니다).
  - 결론: 표본 1곡(review, 비승인)을 위해 승인 클립 컷을 움직이는 규칙은 넣지 않는다. shortcut: 컷 프레임이 곡 음량 수준의 비음성 잡음이면 클립이 그 위에서 시작한다, 사례가 더 모이면 lead_pad 에 "컷 프레임 음량 <= 곡 중앙값-10dB" 같은 조건을 시험한다(승인 auto 컷 불변을 조건으로).
- 종료 컷 연장 한계(toa 10-24 #12): 컷이 곡 끝+2.3초에서 멈춘다. 연장은 말이 시작하면 멈추는 규칙이고 이 곡은 반주 위에 말이 얹혀 있어(메모 "MR 종료 반주가 남은 채 잘림") 27절의 알려진 한계 그대로다.

### 8.6 남은 것과 사용자 결정
- 귀로 못 들음(unverifiable): S3 #50(-13.2초)와 #65(-16.4초, 허밍 여부), 종료 컷 연장/TAIL(곡 끝 +0.3~3초) 전부, 끝 뒤 소리 종류(박수/환호/노래, low 10곡).
- 사용자 답 대기(규칙 변경 없음): 22/82/18 끝 시각(rize 10-04 #21 의 "1분 끊김", nana 10-06 #02 의 +82초), 승인 시작 늦은 곡의 의도, #45(nana 10-16 #14, 시작 late/low 로 남음) 전주 포함 선호.
- 되돌리기: 이전 클립은 `out/stale_v5/{final,final_review}`, 이전 카드/3_final/4_scene 은 `out/stale_v5/state/<방송>/`. RULE 을 되돌리려면 `make_final.RULE` 과 selftest/`memo_audit.py` selftest 단언(11/13)도 함께.
- n_visual 은 호스트 venv 에서만 돈다. 이번 재생성 중 `4_scene.json` 191후보 전부에 vis 가 채워졌다(건너뜀 0).
- 이후 경계 규칙만 바꾼 재실행은 `reroute_nas.py --manifest`(바뀐 후보만 NAS 를 읽음)와 `SHARD` 동시 실행 `final_nas.py` 로 약 10분 안팎으로 줄일 수 있다.
