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
