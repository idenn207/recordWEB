# 트랙 harness 실험 로그

브랜치 proto/sd-harness, 작업 위치 tools/song-detect/harness/. 원시 결과는 cache/proto_harness/ (메인 cache 의 하위 폴더, 다른 산출물은 안 건드림).
표기: 가설 -> 설정 -> 지표(전/후) -> 판정(채택/기각/보류). 시간은 이 PC(CPU 20스레드) 실측 초.

## 축 (a) 단계 매니페스트 (harness/manifest.py, exp_a.py, scene_probe.py)

구현: 단계(final / sig / scene / route)마다 키 = 해시(코드 AST + 입력 파일 해시/서명). 코드 해시는 주석/독스트링을 뺀 AST라 주석만 고치면 stale 이 아니다.
sig(bursts, rel_db)와 scene 은 후보(경계 0.1초 반올림) 단위로 재사용한다. route 키에는 이 방송에 해당하는 등록부 항목만 넣는다. 처음 전체 실행이 현행 결과와 같은지 먼저 확인했다:
3_final.json 61/61 동일, 카드 191/191(등급, 사유, likely, weak, 경계) 동일.

| # | 가설 | 설정 | 현행(전부 다시) | 매니페스트 | 판정 |
|---|---|---|---|---|---|
| H01 | 재처리 593초는 어디서 드는가 | 단계별 시간 분해 (61방송 191후보) | reroute.log 방송별 합 1816초(3동시 593초 벽시계). route 만 다시 돌리는 pipeline.main 61방송 26.2초 | 같은 결과를 만드는 final 6.4 + sig 6.4 + route 6.9 = 17.5초(scene 재사용) | 병목은 scene(NAS 키프레임, 후보당 약 4.0초 실측 3개, 저장값과 완전 동일)이다. final/route 는 초 단위 |
| H02 | 아무것도 안 바꾸면 0 | 변경 없음 재실행 | 26.2초(route 재계산) | 계획 0.24초, stale 0 | 채택 |
| H03 | 주석만 고치면 재처리 0 | route.py 에 주석 한 줄 | 26.2초 | stale 0 (AST 해시) | 채택 |
| H04 | 임계 한 개(n_signals.P rel_db -5.7 -> -5.0)는 route 만 | 61방송 | 전체 재처리 593초 또는 route 26.2초 | stale route 61 / final,scene 0. 실행 1.0초(route 0.58), 등급 변화 0건 | 채택. sig 캐시가 임계(P)와 무관하게 유지됨 |
| H05 | snap 규칙 변경(FWD 15 -> 20)은 final 전부 + 경계 바뀐 후보 scene 만 | 61방송 | 593초(scene 191후보 전부) | final 61, 경계가 바뀐 후보 2/191개만 scene/sig 재계산. 비 NAS 부분 8.3초 + scene 2개 약 8초(추정 4초x2) | 채택. 재처리 약 593초 -> 약 17초(NAS 가능 시), 후보 단위 재사용률 99% |

한계: (1) 경계 반올림이 같은 후보는 같은 후보로 본다(경계 0.05초 차이로 장면 값이 달라질 수 있음은 H05 에서 확인 안 함). (2) 파일 서명은 크기+mtime. (3) scene 단계는 NAS 접근이 필요하고 scene.thumbs 가 401 을 빈 배열로 삼키므로 scene_real.py 에서 예외로 바꿔 두었다(현행 reroute 에 401 가드가 없다: 세션 만료 상태로 --final 을 돌리면 장면 값이 전부 None 으로 저장될 수 있다).

## 축 (b) 증거 카드 v2와 결정 재생 (harness/replay.py, exp_b.py)

카드 v2 = 카드 + route 입력 전부(g_in: 점수/장면/bursts/rel_db/길이/경계) + has_refs. replay 는 wav, 점수 캐시, NAS 없이 route.tier -> known_pos -> known_neg -> mark_likely 만 다시 계산한다.
라벨은 등록부에서 만든 NAS 191후보 라벨: L 43, B 18, N 55, 미확인 U 75(registry=False 로 등록부를 끈 모드가 'N 노출을 등록부에 기대지 않고' 본 수치).
아래 수치는 전부 표본 내(NAS 10월 191후보) 값이다. 일반화 주장은 (c) 의 그룹 hold-out 에서만 한다.

| # | 가설 | 설정 | 지표 | 판정 |
|---|---|---|---|---|
| H06 | 카드만으로 현행 결정을 재현한다 | 191카드 replay | 등급, likely, weak 191/191 동일. 73ms (pipeline.main 61방송 26.2초 대비 약 360배, manifest route 단계 0.58초 대비 약 8배). 등록부 끈 모드 N 노출 14/55(HANDOFF 기준선 14/55 재현), 라이브 L,B 손실 0 | 채택 |
| H07 | 격자 스윕이 분 단위에서 초 단위로 | rel_db -9..-3(0.25) x bursts 1.0..3.5(0.1) 650조합 | 78.9초(121ms/조합). 지금 방식이면 650 x 26초 = 4.7시간, 매니페스트 route 만 0.6초 x 650 = 6.5분. 라이브 손실 0 인 조합 중 N 노출 최소 9/55 (rel_db -4.0, bursts 1.0) | 채택(도구). 수치는 표본 내: 라이브 최저 rel_db -3.96 이 임계를 정한 바로 그 표본이라 과적합 |
| H08 | 신호 기여 분해 | n_signals 신호 하나씩 끄기 | 둘 다 끔(옛 대역) 45/55 노출 -> rel_db 만 22 -> bursts 만 28 -> 둘 다 14. 라이브 손실 전부 0 | 현행 유지(둘 다 필요) |
| H09 | 임계 변형: motion 34.5 -> 30 / 40, scene_idle 0.02/0.05, scene_drop 0.14, wait_s 600 | 각각 replay | motion 30: 노출 12 (라이브 손실 0, 단 review 107->97). motion 40, scene_idle, scene_drop 변형은 변화 0(이 191후보에서는 그 임계에 걸린 후보가 없음). wait_s 600: 노출 13, 라이브 L 1 B 1 손실 | motion 30 은 보류(일반화 근거 약함: 25~34.5 대역은 이전에 hold-out 에서 실패), wait_s 600 기각(라이브 손실) |
| H10 | 규칙 순서/조합 변경 | speech>=0.06 이면 likely 제외가 아니라 drop / speech>=0.10 drop / multi!=live 면 auto 금지 / 길이 게이트 앞당김 | speech 0.06 drop: 노출 14 -> 9, 그러나 B 2곡 손실(review 107 -> 80). speech 0.10: 변화 0. multi 규칙: 변화 0(등록부 없이 auto 가 1개뿐). 길이 앞당김: 노출 13, B 1 손실 | 전부 기각 또는 보류: 노출 감소 1~5 와 라이브 손실이 맞바뀐다(오탐보다 승인 라이브 손실이 더 나쁨 원칙) |

관찰: 등록부를 끄면 auto 가 42 -> 1이 된다(auto 는 거의 전부 승인 목록 겹침이 만든다, HANDOFF 25절과 같은 결론). 카드 v2 한 파일(61방송 합 약 0.9MB)이 규칙 실험의 입력으로 충분했다.
