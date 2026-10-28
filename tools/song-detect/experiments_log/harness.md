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
