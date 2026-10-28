# research 트랙: 선행 연구/기법 조사 (2026-10-29)

범위: 라이브 방송 VOD 에서 스트리머 본인 가창 클립을 자동 추출하는 일에 쓸 수 있는 선행 사례와 기법. 조사 전용이다. 모델 학습이나 파이프라인 변경은 하지 않았고, 메인 저장소와 공유 cache/data/out 에는 아무것도 쓰지 않았다. 이 파일만 sd-harness 브랜치에 커밋한다.

PLAN_NEXT.md 2절(mir_eval 지표, LOGO, Dagster/Medallion, PySceneDetect, SigLIP 프로브, 원곡 지문, 불확실도 샘플링, 히스테리시스 병합 아이디어, 곡 길이 prior)과 겹치는 것은 새 정보만 적었다. 부족했던 영역(한국어 가창 ASR 환각, 짧은 랩, 호흡/들숨, 비트 기반 곡 시작, VLM 프레임 질의 비용)은 5절에서 깊게 다룬다.

## 0. 읽는 법

confidence (이번 세션에서 실제로 무엇을 읽었는가)
- verified: 논문 본문(arXiv HTML, PDF 텍스트 추출) 또는 공식 README/소스 코드를 직접 읽고, 아래 수치를 거기서 확인했다.
- partly: 초록, 공식 소개 페이지, 검색 요약만 읽었다. 방법 개요는 확인했지만 본문 수치는 못 읽었다. 수치는 "초록에 적힌 값"일 때만 적었다.
- unverified: 읽지 못했다. 8절에 목록만 두고 근거로 쓰지 않는다.
- computed: 이번 세션에서 직접 계산/실행해 얻은 값(1절 말미 7절 참조).

비용 표기: "추정"은 측정 전 값이다. VRAM 은 트랙당 3GB 상한 기준.

파이프라인 단계 약칭: detect(YAMNet+Demucs 후보) / refine(0.1초 YAMNet 경계) / snap(경계 규칙 E1,E1b,E2,E3,S1,S2,TAIL) / scene(화면 게이트) / route(auto,review,drop) / final(make_final 컷).

## 1. 트랙별 시도해 볼 구체 기법 Top5

### 1.1 visual 트랙

1. SigLIP 2 임베딩 + 강한 정규화 로지스틱 프로브(스트리머 단위 GroupKFold). 설치할 것이 없다: venv 의 open_clip 3.3.0 이 `ViT-B-16-SigLIP2`, `ViT-B-16-SigLIP2-384`, `ViT-SO400M-14-SigLIP2`, `ViT-SO400M-14-SigLIP2-378` 등 SigLIP2 항목을 이미 갖고 있음(computed, 7절). 모델 4종 86M/303M/400M/1B (verified: abs). 제로샷 프롬프트는 콜드스타트 보조로만. 논문 https://arxiv.org/abs/2502.14786 / 카드 https://huggingface.co/google/siglip2-base-patch16-224 . 첫 실험: R15.
2. 오디오-영상 동기(AV synchrony): "화면 속 사람이 지금 소리를 내는가"를 본다. 아바타/입 영역의 프레임 변화 에너지와 보컬 스템 RMS 포락선의 지연 상호상관. 같이보기/자리비움 BGM/게임 OST 는 소리와 화면 속 인물이 무관해야 한다. 이론 틀: 오디오와 영상 위치별 상호정보량으로 소리 근원을 찾는 Hershey & Movellan 1999 https://papers.neurips.cc/paper_files/paper/1999/hash/b618c3210e934362ac261db280128c22-Abstract.html (partly), 입술-음성 동기 신뢰도(LSE-C)를 쓰는 SyncNet https://ora.ox.ac.uk/objects/uuid:6bdd4768-6fbd-40ac-8efc-edca8a0325b3 (partly). 이 도메인(버튜버 아바타) 적용은 선행 사례를 못 찾았다: 새 가설이다. 첫 실험: R16.
3. PySceneDetect ContentDetector 의 content_val 통계(평균, p90, 컷 수, 정지 비율). 기본값 threshold 27.0, min_scene_len 15, 가중치 hue/sat/lum 1.0/1.0/1.0, edges 0.0 (verified: 공식 문서 https://www.scenedetect.com/docs/latest/api/detectors.html). 키프레임 차분 중앙값 < 6 신호(키프레임 간격에 민감)의 안정판. 첫 실험: R17.
4. 화면 글자(OCR): 노래방 가사 자막, 같이보기 플레이어 UI, 제목 표시줄. PaddleOCR-VL 은 한국어를 명시 지원(0.9B 파라미터, Apache-2.0) https://github.com/PaddlePaddle/PaddleOCR (verified: README). 가벼운 PP-OCR 계열의 한국어 지원은 이번에 확인 못 했다(unverified). 첫 실험: R18.
5. 초소형 VLM 이진 질의: "다른 사람의 영상 플레이어가 화면에 떠 있나", "게임 플레이 화면인가". SmolVLM-256M 은 추론 시 GPU 메모리 1GB 미만(abs, partly) https://arxiv.org/abs/2504.05299 , 새 SmolVLM 은 토큰당 4096 픽셀(2B 는 1820) https://huggingface.co/blog/smolervlm (partly). 후보당 3프레임(시작/중간/끝)만 질의하면 비용이 작다. 첫 실험: R19.

### 1.2 asr 트랙

1. 환각 억제 3단: Silero VAD 게이트 + 반복 제거(delooping) + 환각 구문 목록(BoH). 비음성+음성 혼합 입력에서 large-v3 WER 104.8 -> Silero 8.0, delooping+BoH 17.1, 셋 결합 6.5 (verified) https://arxiv.org/abs/2501.11378 . 단 이 논문 데이터에서 가창/음악은 제거되었다. 가창에서는 speech VAD 가 가창을 얼마나 통과시키는지부터 재야 한다(SR-SAD 근거, 1.2 4번). 첫 실험: R09, R10.
2. 가창 모드 디코딩: 언어 고정(ko), "lyrics:" 접두 프롬프트(LyricWhiz 에서 최선, 긴 지시형 프롬프트는 열세), 라인 no-speech 확률 > 0.9 폐기 https://arxiv.org/abs/2306.17103 (verified). 세그먼트 경계가 보컬을 자르면 환각이 늘고 RMS-VAD cut&merge 가 줄인다(IR10 1.31% -> 0.35%) https://arxiv.org/abs/2506.15514 (verified). 보컬 분리가 WER 을 항상 개선하지는 않으므로 혼합 오디오를 기본 입력으로 둔다. 첫 실험: R10.
3. ASR 을 판정이 아니라 경계/신원 증거로: 첫/마지막 가사 단어의 시각. WhisperX(VAD cut&merge + 강제정렬) https://arxiv.org/abs/2303.00747 (partly), 대조학습 정렬(AAE 0.15초, 1.2M 파라미터, 영어만 학습해도 ES/DE/FR 0.37~0.47초) https://arxiv.org/abs/2306.07744 (verified). 한국어는 어느 쪽도 시험되지 않았다. 첫 실험: R10(전주/간주 삽입 지표) 뒤 R13.
4. Whisper-AT: 한 번의 순전파로 전사 + AudioSet 527 태그, 추가 비용 1% 미만, 태그 시간 해상도 기본 10초(0.4초의 배수) https://github.com/YuanGongND/whisper-at (verified: README). 태그가 가창/랩/허밍을 YAMNet 보다 잘 가르는지 비교. 첫 실험: R12.
5. 가창 구간 디코딩 설정 스윕(추론): Whisper 의 temperature fallback 은 gzip 압축비 > 2.4 를 반복 루프로 보지만(verified: Whisper 논문 4.5절) 후렴 반복은 정상 가사다. `compression_ratio_threshold`, `condition_on_previous_text`, `hallucination_silence_threshold`(기본 None), `clip_timestamps` 조합을 가창 구간에서 스윕. 기본값은 faster-whisper 소스에서 확인(verified). 첫 실험: R10 의 설정 격자.

### 1.3 boundary 트랙

1. 비트 격자 기반 곡 시작: Beat This!(ISMIR 2024, MIT 라이선스, final0 약 78MB / small0 약 8.1MB, `pip install beat-this`, DBN 불필요) https://arxiv.org/abs/2407.21658 , https://github.com/CPJKU/beat_this (verified: README). 가설: MR 시작 = 길이 8박 이상 안정 비트 격자의 첫 박. 카운트인(드럼 하이햇)도 격자에 들어온다. 곡 시작 검출에 비트 추적을 직접 쓴 선행 사례는 못 찾았다. 첫 실험: R04.
2. 히스테리시스 + 최소 지속: Silero 구현이 neg_threshold = threshold - 0.15 로 진입/이탈 임계를 나눈다(verified: 소스). Cances 등이 hysteresis/slope 후처리를 비교(수치는 초록 두 버전이 상충해 인용 안 함) https://arxiv.org/abs/1906.06909 (partly). 방송 음악/말 분할의 최소 지속 1.3초(말)/3.4초(음악), 최대 침묵 0.4초/0.6초 (verified) https://arxiv.org/abs/2102.09959 . 점수 캐시만으로 평가 가능. 첫 실험: R07.
3. 프레임 해상도 올리기: PANNs Cnn14_DecisionLevelMax 프레임 SED(mAP 0.385, hop 320샘플@32kHz = 10ms) https://github.com/qiuqiangkong/audioset_tagging_cnn , https://github.com/qiuqiangkong/panns_inference (verified: README). 먼저 모델 교체 없이 YAMNet 클래스를 늘리는 것이 더 싸다: 캐시 scores.npy 는 3클래스뿐이다(5절, R01).
4. 호흡/들숨 보존: Nakano 등 HMM(MFCC+delta) 27곡 recall 97.5% / precision 77.7%, 호흡 스펙트럼 봉우리 남 1.6kHz / 여 1.7kHz https://staff.aist.go.jp/t.nakano/Breath/ (verified: 페이지). 규칙형 프레임 호흡 검출(300ms 이상, ZCR 높음, mel 스펙트로그램 분산 VMS 높음) https://arxiv.org/abs/2402.00288 (verified). 시작 late 11클립의 "호흡 잘림" 시험. 첫 실험: R06.
5. 합성 덕킹 평가와 회귀형 경계: 말-음악 덕킹을 7~18 LU 로 합성해 학습/평가(MIREX 2018 음악 F 85.76, 비교 시스템 31.24~54.78) https://arxiv.org/abs/2102.09959 (verified). YOHO 는 시작/끝을 직접 회귀 https://arxiv.org/abs/2109.00962 (partly). 우리는 학습보다 평가 쪽: L 곡 끝 +0~10초에 말을 얹어 70/71(MR 위 멘트) 규칙을 시험. 첫 실험: R26.

### 1.4 sweep 트랙

1. 보증형 임계 선택: Learn-then-Test https://arxiv.org/abs/2110.01052 (partly), NP umbrella https://arxiv.org/abs/1608.03109 (partly). 직접 계산(7절): 라이브 136곡에서 손실 0 이어도 진짜 손실률 단측 95% 상한은 2.18%, 49곡이면 5.93%, 25곡이면 11.29%. 임계 = 관측된 최소 라이브 점수로 두는 NP 식 규칙이 "손실 0" 선택의 표준 형태. 첫 실험: R21.
2. 무작위 탐색 + 파레토(라이브 손실 대 N 노출): 격자보다 무작위가 효율적(유효 차원이 낮을 때) https://jmlr.org/papers/v13/bergstra12a.html (partly). 스윕 승자 선택 자체가 낙관 편향이므로 중첩 검증이 필요 https://jmlr.org/papers/v11/cawley10a.html (partly). m 0.0 / 0.1 / 0.2 의 비단조 결과(HANDOFF 28절)는 단일 임계 스윕의 전형적 불안정이다. 첫 실험: R22.
3. 신호 은행 확장(모델 교체 없이): YAMNet 추가 클래스 Rapping(31), Humming(32), Breathing(36), Sigh(23), Gasp(39), Pant(40), Hip hop music(212), Video game music(267), Background music(262), Theme music(263) (verified: yamnet_class_map.csv) + Scheirer & Slaney 의 4Hz 변조 에너지/저에너지 프레임 비율(13개 특징, 프레임 오류 5.8%, 2.4초 구간 1.4%: verified, PDF 본문) https://www.cs.princeton.edu/courses/archive/spring13/cos598C/ScheiS97-mussp.pdf . 모두 LOGO 로. 첫 실험: R01.
4. 프레임 분류기 교체 스윕: YAMNet(balanced mAP 0.306, 창 0.96초 50% 겹침: verified README) 대 PANNs CNN14 0.431 / Wavegram 0.439 (verified README+abs) 대 AST 0.485 https://arxiv.org/abs/2104.01778 (partly) 대 BEATs 50.6(AS-2M) https://arxiv.org/abs/2212.09058 (partly). 지표는 AudioSet mAP 가 아니라 우리 N 유형/경계 AUC. transformers 5.21 에 ASTForAudioClassification, ClapModel 이 이미 있음(computed). 첫 실험: R03.
5. 사람 질의 선택(최대 10곡): 저예산에서는 "전형적" 샘플을 먼저 묻는 편이 낫다는 결과(TypiClust, 10개 라벨에서 랜덤 대비 +39.4%p) https://arxiv.org/abs/2202.02794 (partly). PLAN_NEXT 의 P7(경계 분산이 큰 곡 우선)과 방향이 반대이므로 둘을 같은 예산으로 비교. 첫 실험: R23.

### 1.5 harness 트랙

1. "horse" 점검: 점수가 정답과 교란된 다른 특징(스트리머 EQ, 레이아웃, 방송 길이)에서 나오는지 확인하는 방법 Sturm 2014 https://ieeexplore.ieee.org/document/6847693 (partly: 초록), 이어서 Sturm 2016 https://arxiv.org/abs/1606.03044 (partly). 참고로 GTZAN 오류(중복, 오라벨)가 평가를 왜곡한다는 분석 https://arxiv.org/abs/1306.1461 (partly): 우리의 stale 쌍(145행 -> 104곡) 중복과 같은 문제. 첫 실험: R25.
2. 메모를 행동 테스트로: CheckList 의 능력 x 테스트 유형 매트릭스 https://arxiv.org/abs/2005.04118 (partly: 초록은 유형 정의를 적지 않았다). memo_audit 의 방향 지적이 곧 방향성 기대 테스트, 불변성 테스트(앞에 5초 무음을 붙여도 상대 경계 동일, 이득 +-3dB)를 추가. 첫 실험: R25.
3. 결정론: PyTorch 문서(verified) "릴리스/커밋/플랫폼 간 완전 재현 보장 없음", "CPU/GPU 간 불일치", "cudnn.benchmark 는 같은 머신에서도 다른 알고리즘을 고를 수 있음". 처방 benchmark=False, deterministic=True, use_deterministic_algorithms(True), 파이썬 random 시드(Demucs shifts) https://docs.pytorch.org/docs/2.14/notes/randomness.html . HANDOFF 20절의 0.4초 경계 차이와 같은 현상. 첫 실험: R24.
4. 단계 캐시: DVC 는 명령/의존성/파라미터가 같으면 stage 를 건너뛰고 run-cache 에서 출력을 복원하며 `dvc repro --dry` 로 실행 없이 stale 만 보고한다(verified) https://doc.dvc.org/user-guide/pipelines/running-pipelines . 개념만 차용: 단계 json 에 {code_version, input_hash, params_hash} 를 적고 "무엇이 stale 인가" 보고만 먼저. 이미 이 트랙의 매니페스트/replay 시제품과 같은 방향이다.
5. 그룹 hold-out 과 구간: Roberts 2017(블록 CV 가 예측 평가에 거의 항상 적합) https://pred.uni-regensburg.de/id/eprint/1455/ (partly), Flexer 2007(아티스트 필터: 같은 아티스트가 학습/시험에 걸치면 장르가 아니라 아티스트를 분류) https://archives.ismir.net/ismir2007/paper/000341.pdf (partly). 스트리머가 11~18명이면 클러스터 부트스트랩(스트리머 단위 재표집). ML Test Score(28개 테스트 루브릭) https://research.google/pubs/the-ml-test-score-a-rubric-for-ml-production-readiness-and-technical-debt-reduction/ (partly)를 게이트 체크리스트로.

## 2. 핵심 발견 (20개 이내, 수치는 출처 확인된 것만)

1. 한국어 가창의 ASR 환각을 직접 측정한 논문/벤치마크는 찾지 못했다. LyricWhiz 의 다국어 데이터(MulJam)는 EN/FR/ES/IT/RU/DE 이고 한국어가 없다(verified). Syed 2025 는 DE/EN/ES/FR 만 시험(verified). Whisper 논문 3.4절은 KO 를 데이터량 추세보다 성능이 낮은 언어로 분류(verified). 우리가 직접 재야 한다(R10).
2. 비음성 입력에서 Whisper large-v3 는 40.3%(121,378/301,317) 추론에서 환각, 그중 9.1%가 반복 루프. 클립 길이별 1초 52.1%, 10초 11.6%, 20초 27.4%, 30초 62.3%. 최빈 출력 "thank you" 24.76%. 그 데이터는 가창/음악을 제거한 것이라 우리 도메인 수치가 아니다 (verified, 2501.11378).
3. 환각 완화: 음성+비음성 혼합 WER 104.8 -> SileroVAD 8.0, delooping+BoH 17.1, 결합 6.5. WebRTC VAD 는 68.3 에 그친다 (verified).
4. 보컬 분리가 ASR 을 개선한다는 가정은 틀릴 수 있다: Jam-ALT 혼합 20.99 대 분리(mdx_extra) 21.08, MUSDB-ALT 혼합 23.59 대 분리 20.00 대 진짜 스템 14.19. 분리는 삭제와 삽입을 늘린다(삽입 3.01% 대 1.76%). RMS-VAD 구간 분할은 혼합 입력에서도 23.02 -> 20.35 (verified, 2506.15514).
5. speech VAD 는 가창을 거부하지 못할 수 있다: 같은 데이터로 재학습한 STA-VAD 는 가창 거부 정확도 0.534, 가창 거부를 학습한 SR-SAD 0.979, speech 만 학습하면 SR-SAD/SR-SAD-LC/AS-pVAD 가 0.12~0.19 로 붕괴(STA-VAD 0.43, ResNet50 0.03). 랩과 블루스에서 가장 약하다 (verified, 2512.09713). Silero/pyannote 는 이 논문에서 비교되지 않았다.
6. 로컬 사실: cache/detect/*.scores.npy 는 (N, 3) = Singing/Speech/Music 3클래스뿐이다(computed). YAMNet 클래스 맵에는 Rapping, Humming, Breathing, Video game music 등이 있고 `yamnet_backend.scores_windows(..., cls=...)` 가 이미 임의 클래스를 지원한다. 모델 교체 없이 재계산만 하면 랩/허밍/호흡 채널이 생긴다(R01).
7. 프레임 분류기 비교(AudioSet): YAMNet balanced mAP 0.306(창 0.96초), PANNs CNN14 0.431 / Wavegram 0.439, PANNs 프레임 SED(DecisionLevelMax) 0.385 @ 10ms hop, AST 0.485, BEATs 50.6 (모두 verified 또는 abs). 우리 refine 의 0.1초 간격은 0.96초 창 위에서 만들어진 값이다.
8. 호흡: 가창 호흡 HMM 검출 recall 97.5% / precision 77.7%(27곡), 같은 곡 안에서 호흡 스펙트럼이 비슷하고 1.6~1.7kHz 봉우리 (verified). 규칙형 호흡 검출은 300ms 이상 + ZCR/VMS 로 precision 0.982(recall 0.450)이고 자기학습 3회 뒤 IoU 0.836 (verified, 영어 낭독 음성 데이터).
9. 짧은 랩: 랩은 speech 와 singing 사이의 가장 어려운 경계다(SR-SAD 결론). Gärtner & Dittmar(ICMLA 2009)는 반주가 저수준 특징을 오염시킨다고 보고하고, 2010 ISMIR 후속은 고립 보컬 트랙 기준이다 (partly). YAMNet 이 랩을 Speech 로 읽는 HANDOFF 14절 현상과 일치.
10. 비트 추적: Beat This! 는 DBN 없이 비트/다운비트를 낸다. 가중치 MIT, final 약 78MB, small 약 8.1MB, pip 설치 (verified README). 곡 시작 검출에 직접 쓴 선행은 못 찾았다.
11. 방송 음악/말 분할: 합성 덕킹(7~18 LU)만으로 학습한 CRNN 이 MIREX 2018 TV 27시간에서 음악 F 85.76(P 79.37, R 93.27), 말 F 92.21. 비교 시스템 음악 F 31.24~54.78 (verified, Venkatesh 2021). 최소 지속 1.3/3.4초.
12. 가수 식별: SSL 가수 임베딩은 16kHz 입력에서 in-domain EER 2.16% -> 6.39% 로 나빠지고 학습은 고립 보컬 940시간(44.1kHz) (verified, 2401.05064). 우리 캐시 wav 는 16kHz mono 라 이 경로는 원본 오디오를 다시 받아야 한다.
13. 음원 지문: Wang 2003 의 landmark(스펙트로그램 봉우리 쌍, 32비트 해시, 시간 오프셋 히스토그램 봉우리로 판정)는 잡음과 코덱에 견딘다 (verified). audfprint 는 일관된 시각의 일치 해시 5~6개 이상이면 진짜 일치로 보고(min-count 5), 2547초를 21.6초에 처리(0.008배속) (verified). 외부 카탈로그 없이 우리 승인 라이브 라이브러리(MR 재사용)에 쓸 수 있다.
14. 통계 한계(computed): 라이브 손실 0/136 의 단측 95% 상한 2.18%, 0/49 5.93%, 0/25 11.29%. N 노출 14/55 의 Wilson 95% 15.8~38.3%, 10/55 는 10.2~30.3% 라 기준선 14/55 와 목표 10/55 는 통계적으로 구별되지 않는다. 손실 상한 1%를 5% 신뢰로 보이려면 라이브 299곡이 필요하다.
15. 능동 선택: 저예산에서는 전형적 샘플, 고예산에서는 비전형 샘플이 낫다(위상 전이)는 결과. 10개 라벨에서 TypiClust 는 랜덤 대비 +39.4%p (CIFAR-10 반지도) (partly, 2202.02794). 우리 10곡 예산은 저예산 쪽이다.
16. 재현성: PyTorch 는 CPU/GPU 간, 릴리스/플랫폼 간, 같은 머신의 benchmark 모드에서도 결과 불일치를 허용한다고 명시 (verified). Demucs shifts 의 파이썬 random 과 함께 경계 0.4초 흔들림의 원인으로 설명된다. 시드와 deterministic 플래그로 먼저 줄일 수 있다.
17. VLM 비용: Qwen2.5-VL 카드(verified)의 예제는 min/max_pixels 를 28x28 의 배수(256~1280 x 28 x 28)로 지정하고 기본 시각 토큰 범위가 4~16384/이미지다. 토큰당 28x28 픽셀은 카드가 직접 적지 않아 코드에서 추론한 값이다. 3B 를 bf16 으로 올리면 가중치만 약 6GB(산술)라 트랙당 3GB 상한을 넘는다. SmolVLM-256M(1GB 미만)과 SigLIP2 B/16 이 상한 안이다.
18. LyricWhiz: "lyrics:" 접두 프롬프트가 최선이고 길고 지시형인 프롬프트는 열세. 프롬프트 제거 시 Jamendo WER 24.25 -> 33.21. 환각 사례는 음악 설명, 이모지, 웹사이트 워터마크, 광고 (verified).
19. 라이브 대 스튜디오 판별, 커버/따라 부르기 판별, 단일 가수 대 유니즌 인원수 추정은 벤치마크가 있는 선행 연구를 찾지 못했다(검색 3~4회). 유니즌 합창은 다중 F0 추정이 어렵다는 결과만 있다(Cuesta 등, partly). 이 영역은 지문 + 가수 임베딩 + 규칙으로 직접 풀어야 한다.
20. 오디오-영상 동기 신호는 선행 문헌이 일반 틀(Hershey & Movellan, SyncNet)만 있고 버튜버/스트림 도메인 적용 사례는 못 찾았다. 새 가설이고 위험도 높다.

## 3. 영역별 조사 표

공통 열: 항목 | 출처 | 핵심 방법과 수치 | confidence | 넣을 단계 | 바로 해볼 실험 | 예상 비용

### 3.1 가창/말/랩 분류와 프레임 분류기

| 항목 | 출처 | 핵심 | conf | 단계 | 실험 | 비용 |
|---|---|---|---|---|---|---|
| YAMNet 한계 | https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/README.md | 521클래스, 창 0.96초 50% 겹침, balanced mAP 0.306, d-prime 2.318 | verified | detect, refine | R01 | 재계산: 1시간 8초(HANDOFF) x 후보 구간만 |
| 클래스 맵 | https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv | Rapping 31, Humming 32, Breathing 36, Sigh 23, Gasp 39, Pant 40, Hip hop music 212, Background music 262, Theme music 263, Video game music 267, Tender/Scary music | verified | detect, refine, scene | R01 | 코드 수정 1줄(cls=) |
| PANNs | https://github.com/qiuqiangkong/audioset_tagging_cnn , 논문 https://arxiv.org/abs/1912.10211 | CNN14 0.431, Wavegram-Logmel 0.439, DecisionLevelMax SED 0.385, hop 10ms. 체크포인트 zenodo 3987831 | verified | refine 보강 | R02 | 설치+체크포인트 10~20분 추정, VRAM 2GB 미만 추정 |
| AST | https://arxiv.org/abs/2104.01778 , 카드 https://huggingface.co/MIT/ast-finetuned-audioset-10-10-0.4593 | AudioSet mAP 0.485, ESC-50 95.6%, BSD-3 | partly | detect 신호 | R03 | transformers 에 클래스 있음 |
| BEATs | https://arxiv.org/abs/2212.09058 | AudioSet-2M 50.6% | partly | 신호 | R03(선택) | 체크포인트가 별도 저장소(미확인) |
| CLAP | https://arxiv.org/abs/2211.06687 , https://github.com/LAION-AI/CLAP | 633,526쌍, music_speech_audioset 체크포인트(ESC50 89.98%, GTZAN 51%), 48kHz 입력, CC0. 문장 질의("a person rapping over a beat") 제로샷 | partly(논문), verified(README) | scene 대체 신호 | R03 | 48kHz 재샘플 필요 |
| MERT | https://arxiv.org/abs/2306.00107 | 95M/330M, 14개 음악 이해 과제 | partly | 가수/가창 프로브 | 보류 | 평가 과제 목록 미확인 |
| Whisper-AT | https://github.com/YuanGongND/whisper-at | 527 태그, 10초 해상도, 추가비용 1% 미만, small mAP 39.8 ~ large-v1 42.1 | verified | asr 와 병용 | R12 | whisper_at 설치(Windows 우회 명령 README) |
| 말/음악 판별 고전 | https://www.cs.princeton.edu/courses/archive/spring13/cos598C/ScheiS97-mussp.pdf | 13개 특징(4Hz 변조 에너지, 저에너지 프레임 비율 등), 프레임 오류 5.8%, 2.4초 1.4%. 후속 연구는 4Hz 특징이 빠른 말/가창에 취약하다고 지적(2차 요약) | verified(본문) | 신호 | R01 | CPU 초 |
| speech 와 singing 분리 | https://arxiv.org/abs/2512.09713 | SR-SAD 870K 파라미터, 2초 청크, AUC 0.910, 가창 거부 AUC_SiRR 0.572, RTF 32 (CPU) | verified | ASR 게이트, scene | R09 | 코드 공개 여부는 본문에 없음 |
| 가창 검출 설문 | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8775013/ | 특징/CRNN 정리, 주 데이터 Jamendo/RWC/MIR-1K (검색 요약) | partly | 배경 | - | - |
| 가창 검출 증강 | https://www.ismir2015.uma.es/articles/264_Paper.pdf | 라벨 보존 변환 중 피치 시프트가 가장 유익, 공개 데이터 최고 정확도 약 90% (검색 요약, 서버 중단으로 본문 못 읽음) | partly | 증강 | 보류 | - |
| 랩 대 가창 | Gärtner & Dittmar, ICMLA 2009 (DOI 형식 검색 결과 https://publica.fraunhofer.de/handle/publica/365491) | 저수준 특징 + 베이지안/GMM, 반주가 특징을 오염 | partly | 신호(랩) | R01, R05 | - |
| 랩 리듬 구조 | MCFlow https://labs.sonicfield.org/library/mcflow-a-digital-corpus-of-rap-transcriptions | 124곡/374벌스, 강세 음절의 박 위치 분석(검색 요약) | partly | 신호(랩) | R05 | - |

### 3.2 방송 음악/말 분할과 후처리

| 항목 | 출처 | 핵심 | conf | 단계 | 실험 | 비용 |
|---|---|---|---|---|---|---|
| 합성 학습/덕킹 | https://arxiv.org/abs/2102.09959 | 8초 예제 40,960개(약 91시간), 덕킹 7~18 LU(ITU BS.1770-4), CRNN(conv 2 + B-GRU 2 x 80), 후처리 최소 지속 1.3/3.4초, 최대 침묵 0.4/0.6초. 로컬 테스트 F 96.69, MIREX 2018 음악 F 85.76 / 말 F 92.21 | verified | snap 평가 | R26 | ffmpeg 25개 |
| 다중 클래스 분할 | Gimeno 등 2020 https://www.isca-archive.org/iberspeech_2018/gimeno18_iberspeech.html | BLSTM + HMM 식 재분할, 클래스 music/speech/speech+music/speech+noise/other, Albayzin 2010 상대 개선 15.75%(2018판), 2020판 19.72% / 5.35% | partly | 분류 정의 | R26 | - |
| inaSpeechSegmenter | https://github.com/ina-foss/inaSpeechSegmenter | CNN 음성/음악/잡음, MIREX 2018 말 검출 우승(자기보고) | partly | 비교 기준 | 보류 | 설치 무거움(TF) |
| YOHO | https://arxiv.org/abs/2109.00962 | 시작/끝 회귀형, 분류형 대비 추론 6배 빠름, F +1~6% 상대 | partly | refine 대체 | 보류(학습 필요) | - |
| 후처리 | https://arxiv.org/abs/1906.06909 | hysteresis, slope, 중앙값 필터 비교, 라이브러리 aeseg | partly | snap/detect 병합 | R07 | CPU 분 |
| Silero VAD | https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/utils_vad.py | threshold 0.5, neg_threshold = threshold - 0.15, min_speech 250ms, min_silence 100ms, speech_pad 30ms, 16kHz, 청크당 1ms 미만 | verified | asr 게이트, 말 구간 | R09 | 이미 venv 에 silero-vad 6.2.3 |
| 병합 규칙 | PLAN_NEXT 2.3절 | 간주 병합은 "틈 하나"가 아니라 (틈, Music 연속, 말 없음, 병합 후 길이 상한) 조합 | - | detect | R07 | - |

### 3.3 한국어 가창 ASR 환각 (깊게)

| 항목 | 출처 | 핵심 | conf |
|---|---|---|---|
| 비음성 환각 규모 | https://arxiv.org/html/2501.11378 | 301,317개 비음성 파일(AudioSet, MUSAN, UrbanSound8K, FSD50K, 백/핑크 노이즈, 무음)에서 large-v3 가 40.3% 환각, 9.1% 루프. 범주별: 불명 48.9, 자연음 44.2, 동물 40.2, 사물 39.4, 사람 36.7, 환경 31.4. 최빈 "thank you" 24.76%, "thanks for watching" 10.32%(영상 자막 학습 영향). 음성+30초 비음성 증강 시 44.5%(비중첩) / 46.1%(중첩), 무음 증강 17.1% (그중 BoH 67.5%). 빔 크기 1 은 검출 환각 수가 최소였지만 WER 은 107.2 로 개선 없음. hallucination silence threshold 20초에서 14.7%(WER 39.8) | verified |
| BoH 구축 절차 | 같은 논문 | 비음성 추론 결과에서 빈출 구문(4회 초과)을 모으고 n-gram LM log-prob < -10 으로 흔한 영어 구문을 제외. 제거는 delooping 후 Aho-Corasick 문자열 매칭, wav2vec 2.0 강제정렬로 확인(선택) | verified |
| 환각 보고 | https://arxiv.org/html/2402.08021v1 | 약 1% 전사에 환각 구문, 38%가 유해 요소 포함, 비발화 구간 길이가 환각의 유의한 예측 변수(계수 0.064). 2023-11 말 업데이트(무음 건너뛰기) 뒤 187개 중 12개로 감소 | verified |
| 가창 ALT 성능 | https://arxiv.org/html/2506.15514 | Whisper large-v2(faster-whisper), 언어 지정, beam 5. Jam-ALT 장문 WER 혼합 23.02(고유 분할) -> 20.35(RMS-VAD). 언어별(RMS-VAD 혼합) DE 16.12, EN 24.73, ES 14.28, FR 24.41. 삭제 지배적: 비어휘 발성/백보컬의 절반 이상 삭제 | verified |
| 프롬프트와 앙상블 | https://ar5iv.labs.arxiv.org/html/2306.17103 | Jamendo 24.25 / Hansen 7.85 / DSing 13.78 (LyricWhiz), 프롬프트 제거 33.21 / 8.75 / 13.40, ChatGPT 앙상블 제거 28.18 / 8.07 / 15.22. 환각: 음악 설명, 이모지, 웹사이트 워터마크, 광고. "Thank you." 세그먼트 제외 | verified |
| 장문 휴리스틱 | https://ar5iv.labs.arxiv.org/html/2212.04356 (4.5절) | beam 5, fallback 0->1.0 (0.2 단계) 조건 avg logprob < -1 또는 압축비 > 2.4, 직전 텍스트 조건화는 온도 < 0.5, no-speech 0.6 과 logprob -1 결합, 첫 타임스탬프 0~1초 제한. 3.4절: KO 는 추세보다 낮은 언어 | verified(앞 100k자) |
| 소스 기본값 | https://raw.githubusercontent.com/SYSTRAN/faster-whisper/master/faster_whisper/transcribe.py | no_speech 0.6, log_prob -1.0, compression 2.4, condition_on_previous_text True, prompt_reset_on_temperature 0.5, hallucination_silence_threshold None, clip_timestamps "0", vad_filter False, multilingual False | verified |
| 한국어 가창 | https://scholarworks.sogang.ac.kr/item/bf67d5ec-82e9-4ccb-b770-e78316ef210f | RefWhisper: 불완전한 가사를 참조해 정렬, 한국 민요 13,801곡 전사/타임스탬프 공개(검색 요약) | partly |
| 한국어 방송 | https://doc.scenemaker.solbox.com/en/blog/4 | faster-whisper large-v3 에서 반복 루프, 언어 오인식 보고(일화적, 말하기 음성) | partly |

결론과 설계 시사점
- 선행 연구는 영어/유럽어 가창 또는 비음성 음향에 한정된다. 한국어 가창에서의 환각률은 모른다. 우리 데이터에는 이를 싸게 재는 방법이 있다: 우리는 전주/간주/곡 사이 무음 구간을 점수로 이미 알고 있다. 그 구간에 Whisper 가 낸 텍스트의 비율 = 환각률 대리 지표(삽입 지표, 정답 가사가 필요 없음). Syed 2025 가 같은 아이디어로 IR10 이라는 삽입률 대리 지표를 쓴다(verified).
- 영어 BoH 목록은 쓸 수 없다. 같은 절차를 우리 전주/간주 구간 출력에 적용해 한국어 BoH 를 만든다(R10).
- 입력 선택: 혼합 오디오 + 곡 구간 안 RMS-VAD 분할이 기본, 분리 보컬은 비교군.
- speech VAD 가 가창을 통과시키면 환각 게이트로서 기능이 반대로 동작할 수 있다(가창이 "음성"으로 통과). 어느 쪽이든 R09 로 먼저 분포를 본다.

### 3.4 가사 정렬과 ASR 경계

| 항목 | 출처 | 핵심 | conf | 단계 | 실험 |
|---|---|---|---|---|---|
| WhisperX | https://arxiv.org/abs/2303.00747 | VAD cut&merge + 배치 + 음소 강제정렬, 12배 빠름 주장, 할당 모델 이름은 초록에 없음 | partly | boundary 증거 | R13 |
| 대조학습 정렬 | https://arxiv.org/html/2306.07744v1 | JamendoLyrics 영어 AAE 0.15초(문자 모델 M6) / PCO 92%, 영어만 학습해도 ES 0.37, DE 0.41, FR 0.47, 1.2M 파라미터(4.8MB), 언어 조건화 학습 시 전체 0.18 | verified | boundary 증거 | R13 |
| stable-ts, whisper-timestamped | 읽지 않음 | - | unverified | - | - |
| ASR 텍스트 반복 | 추론(출처 없음) | 후렴 반복은 압축비 임계를 쓸데없이 건드린다 | unverified | asr | R10 |

활용: 곡의 첫/마지막 가사 단어 시각을 "MR 시작보다 이른 가사 없음 / 컷 뒤 가사 없음"의 부정 증거로 쓴다(PLAN_NEXT 가 말한 "끝 뒤 가사 존재 여부" 진단). 한국어에서 정렬 모델의 정확도는 시험되지 않았으므로 정확도 주장 없이 존재 여부만 쓴다.

### 3.5 곡 경계/구조 분석

| 항목 | 출처 | 핵심 | conf | 비고 |
|---|---|---|---|---|
| 신규도(novelty) | Foote ICME 2000, 개요 https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S4_NoveltySegmentation.html | 자기유사도 행렬 대각선을 따라 체커보드 커널로 경계 신규도. 본문은 못 읽음 | partly | PLAN_NEXT 가 이미 보류. 이번에 새 정보 없음 |
| 구조 분석 일반 | Nieto & Bello, Serra 등 | 이번 세션에서 읽지 않음 | unverified | 인용하지 않음 |
| 방송 곡 시작 | (선행 없음) | 방송 음악 분할 문헌은 구간 분류 + 최소 지속이 전부(3.2절). 곡 "시작 시각" 자체를 비트/MR 격자로 푼 문헌은 못 찾음 | - | R04 는 새 가설 |

### 3.6 호흡/들숨 검출 (깊게)

| 항목 | 출처 | 핵심 | conf |
|---|---|---|---|
| 가창 호흡 HMM | https://staff.aist.go.jp/t.nakano/Breath/ | 18명 128분 1,488 호흡 분석, MFCC + delta + delta-power HMM, 27곡 recall 97.5% / precision 77.7%, 같은 곡 안에서 호흡 스펙트럼 유사, LTAS 봉우리 남 1.6kHz 여 1.7kHz, 데이터 RWC 팝 | verified |
| 규칙 + 자기학습 | https://arxiv.org/html/2402.00288v2 | 호흡 후보 = 휴지 중 300ms 이상, ZCR 높음, VMS(mel 분산) 높음, NA-VMS. 규칙만 precision 0.982 / recall 0.450. 3회 자기학습 후 IoU 0.836, precision 0.924, recall 0.897. Conformer 8블록 + BiLSTM, 10ms 프레임. 영어 오디오북(LibriTTS-R). 들숨/날숨은 구분 안 함 | verified |
| Ruinskiy & Lavner 2007 | IEEE TSALP 15(3) (DBLP 목록) | 단시간 켑스트럼 + 영상 인식 식 템플릿 매칭(검색 요약) | partly |
| Breath Activity Detection | https://arxiv.org/pdf/1602.07767 | 읽지 않음 | unverified |

우리 쪽 시사점
- 호흡은 곡 시작 직전 1~4초에 짧고 저레벨로 나타나며, 우리 snap 의 lead_pad 규칙이 이를 "말소리"로 오분류해 시작을 늦추는 사례(51/52, HANDOFF 25절)가 있다. 검출기를 모델로 쓰기 전에 규칙형(Nakano 의 1.6~1.7kHz 봉우리 + 300ms + ZCR/VMS)이 곡 시작 앞 8초에서 후보를 내는지 먼저 본다(R06).
- 호흡은 가창 쪽의 "시작 근거"이고 말 쪽 반대 증거(호흡 뒤 바로 보컬 온셋)를 만든다. 오탐은 말 사이 호흡이므로 "호흡 뒤 Music 점수 상승/보컬 온셋이 이어질 때만"으로 제한.
- 가창 호흡 선행은 Nakano 팀 한 곳(RWC 팝, 영어/일본어 곡)뿐이고 한국어 발성/스트리머 마이크 조건에서는 미검증이다.

### 3.7 비트 기반 곡 시작 (깊게)

| 항목 | 출처 | 핵심 | conf |
|---|---|---|---|
| Beat This! | https://arxiv.org/abs/2407.21658 , https://github.com/CPJKU/beat_this | 트랜스포머 비트/다운비트, DBN 후처리 없음, 시간 이동에 관대한 손실. 가중치/코드 MIT. `File2Beats(checkpoint_path="final0", device="cuda", dbn=False)` -> (beats, downbeats). final 약 78MB, small 약 8.1MB, `--float16` 가능. 속도 수치와 최대 길이는 README 에 없음 | verified(README) |
| 시간 단위/청킹 | 같은 README | 시간 단위와 긴 오디오 처리는 명시 안 됨: 곡 구간 단위(후보 +-60초)로 호출해 시험하고 단위를 코드로 확인해야 함 | - |

설계
- 가설 H1: 후보 시작 앞 45초 창에서 비트 간격 변동계수(CV) 5% 미만이 8박 이상 이어지는 최초 구간의 첫 박 = MR 시작(전주 포함). 카운트인 하이햇도 포함.
- 가설 H2: 보컬 온셋이 비트 격자의 박 위에서 시작하는 경우가 많으므로, S2 로 늘린 시작을 가장 가까운 박으로 스냅(다운비트 우선).
- 위험: 승인 시작이 음악 시작보다 15~25초 늦은 5곡(PLAN_NEXT 5절 질문 2)은 의도에 따라 오답이 된다. 따라서 auto 에는 쓰지 않고 B/review 후보 경계로만(PLAN P5 와 같은 정책).
- 비용: 후보 191개 x (앞 45초 + 컷 구간) 은 분량이 작아 GPU 분 단위 추정, small 체크포인트면 VRAM 1GB 미만 추정.

### 3.8 짧은 랩 검출 (깊게)

현황: 랩 72~98초 정상 클립이 YAMNet 에서 Speech 로 읽혀 탈락(HANDOFF 14절). 하한 60~70초는 재현율 44/50 -> 46~48/50 이나 review 가 33~49개(41방송) 늘어 보류.

| 항목 | 출처 | 핵심 | conf |
|---|---|---|---|
| speech VAD 의 한계 | https://arxiv.org/html/2512.09713v1 | 랩/블루스에서 가창 거부가 가장 낮음. 랩은 학습에서 제외했고 랩 전용 수치는 없음 | verified |
| 랩 대 가창 분류 | Gärtner & Dittmar 2009, Gärtner 2010 | 저수준 특징 + 베이지안, 반주 영향. 고립 보컬 트랙(2010) | partly |
| 랩 리듬 | MCFlow | 랩 음절의 박 위치 통계 | partly |
| 특허 | US 12340822 | 랩을 대화와 음악 양쪽에 닮은 별도 클래스로 둠 | partly(검색 요약), 인용만 |

제안 신호(우리 데이터로 시험 가능한 것)
- YAMNet Rapping(31)/Hip hop music(212) 채널 (R01).
- 보컬 스템 위 음절 온셋의 박 정렬도: Beat This! 박 격자에 대한 음절 에너지 온셋의 위상 집중도. 랩과 가창은 높고 일반 말은 낮다는 가설(미검증, MCFlow 는 랩 박 정렬을 시사하지만 말과의 정량 대비는 없다).
- 말 속도/음정 평탄도: 랩은 말보다 빠르고 음높이가 평탄하다(추론). 지금 신호 "sing_std", "tstd" 와 중복되는지 LOGO 로.
- 평가: 구조적 미탐 랩 3곡(재생목록 우사기 랩 등)과 마시로 10-23(72초) 복구 여부, review 증가 수, 승인 라이브 이탈 0.

### 3.9 음원 지문, 커버, 거부 신호

| 항목 | 출처 | 핵심 | conf | 단계 | 실험 |
|---|---|---|---|---|---|
| Shazam landmark | http://www.ee.columbia.edu/~dpwe/papers/Wang03-shazam.pdf | 봉우리 별자리, 앵커-타깃존 쌍 해시(f1, f2, dt)를 32비트로, 오프셋 히스토그램 봉우리로 판정, 잡음과 GSM 압축에서 견딤 | verified | scene/route 신호 | R14 |
| audfprint | https://github.com/dpwe/audfprint | new/add/match/precompute, min-count 5, 0.008배속, 기본 262k 트랙 | verified | 도구 | R14 |
| 신경망 지문 | https://arxiv.org/abs/2010.11910 | 대조학습, 시간 이동, 배경 잡음, 룸/마이크 IR 증강, 저장 10배 절약(초록). 수치는 본문 못 읽음 | partly | 후순위 | - |
| 판별 틀 | 우리 가설 | (a) 따라 부르기/같이보기/OST: 원곡 음원(보컬 포함)이 섞임, (b) 스트리머 MR 라이브: 반주만. 외부 카탈로그 대신 우리 승인 라이브/known_negatives 라이브러리와 대조 | - | route | R14 |

주의: MR 은 원곡 반주와 같은 음원이라 landmark 의 반주 봉우리가 원곡과도 일치할 수 있다. 원곡 보컬 봉우리의 존재(원곡에는 있고 MR 에는 없음)를 못 구하면 L/N 구분력은 약하다. 그래서 이 신호는 "같은 MR 이 이전 승인 라이브에 있었다"는 양성 증거(재사용 MR)와 "같은 게임 OST/같이보기 오디오가 known_negatives 에 있었다"는 음성 증거로 쓰는 형태가 현실적이다.

### 3.10 가수 식별과 ECAPA 실패 원인

- PLAN_NEXT 는 ECAPA AUC 0.50 의 원인 분해(말-말, 말-노래, 분리 후 노래-노래)를 요구한다. 이번 조사에서 얻은 외부 단서: SSL 가수 임베딩 연구(https://arxiv.org/html/2401.05064, verified)는 44.1kHz 입력이 16kHz 보다 일관되게 낫고(in-domain EER 2.16% -> 6.39%), 학습 데이터가 고립 보컬 약 25,000트랙(940시간)이며 혼합 입력은 평가하지 않았다. 음성 사전학습 XLSR-53 이 가수 식별 전체에서 최고였다.
- 우리 캐시 wav 는 16kHz mono 이므로 이 모델 계열을 쓰려면 NAS 원본 오디오를 다시 받아야 하고(NAS 로그인 401 위험) 분리 보컬이 필요하다. 비용이 크고 PLAN_NEXT 의 "원인 분해 먼저" 원칙에 따라 후순위.
- 단일 가수 대 유니즌(따라 부르기) 인원수 추정은 선행 벤치마크를 못 찾았다(Cuesta 등은 유니즌에서 다중 F0 가 어렵다고 보고, partly). 지문(3.9)과 규칙이 현실적인 대안.

### 3.11 화면 의미 분류, VLM 비용, OCR (깊게)

| 항목 | 출처 | 핵심 | conf |
|---|---|---|---|
| SigLIP 2 | https://arxiv.org/abs/2502.14786 | B 86M / L 303M / So400m 400M / g 1B. 다국어 개선(한국어 명시는 없음). NaFlex 가변 해상도 | partly |
| open_clip SigLIP2 | 로컬 실행(7절) | `ViT-B-16-SigLIP2`, `-256/-384/-512`, `ViT-L-16-SigLIP2-*`, `ViT-SO400M-14-SigLIP2(-378)`, `ViT-SO400M-16-SigLIP2-*` 등 15개 이상(webli) | computed |
| transformers 제로샷 | https://huggingface.co/google/siglip2-base-patch16-224 | pipeline("zero-shot-image-classification"), 0.4B 파라미터 | partly |
| SmolVLM | https://arxiv.org/abs/2504.05299 , https://huggingface.co/blog/smolervlm | 256M 은 추론 시 1GB 미만. 새 모델은 4096 픽셀/토큰, 2B 는 1820. 벤치 수치는 그림이라 못 읽음 | partly |
| Qwen2.5-VL-3B | https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct | 기본 시각 토큰 4~16384/이미지, 예제 min 256x28x28 ~ max 1280x28x28 픽셀, 종횡비 유지, 28 배수 반올림. 카드에 한국어 지원 언급 없음. 양자화는 커뮤니티 모델 링크뿐 | verified |
| PaddleOCR | https://github.com/PaddlePaddle/PaddleOCR | PaddleOCR-VL 0.9B, 한국어 명시, Apache-2.0. PP-OCR 계열 모델 크기 1.5M~34.5M 이나 한국어 포함 여부 불명 | verified |
| PySceneDetect | https://www.scenedetect.com/docs/latest/api/detectors.html | 위 1.1절 | verified |
| 프롬프트 질의 대안 | CLAP 의 이미지판 | 해당 없음 | - |

비용 모델(추정, 모두 측정 전)
- 대상 프레임: 장면 풀 208클립 키프레임 6032장(HANDOFF 28절). 전수 질의 대신 후보당 3프레임이면 191후보 x 3 = 573프레임.
- 3B VLM bf16 = 가중치 약 6GB(파라미터 수 x 2바이트 산술) -> 트랙당 3GB 상한 초과. 4비트 양자화가 필요하고 이는 이번에 확인 못 했다. SmolVLM-256M/500M, SigLIP2-B/16 은 상한 안.
- 토큰 수(추론: 카드 예제 코드의 28 배수 규칙): Qwen2.5-VL 은 (H/28) x (W/28). 640x360 -> 약 264토큰, 1280x720 -> 약 1,000토큰. 573프레임 x 264 = 약 15만 토큰.
- 질의는 이진 질문 + 한 단어 답변으로 제한(출력 토큰 최소). 모델 선택은 R19 에서 초당 프레임, VRAM 피크를 실측한 뒤.

### 3.12 방송 하이라이트, 채팅, 스트림 의미

| 항목 | 출처 | 핵심 | conf |
|---|---|---|---|
| 채팅 반응 | https://arxiv.org/abs/1707.08559 | 시각 특징 + 채팅 텍스트(영/중), LoL 챔피언십 Twitch 방송, 문자 단위 CNN-RNN. 수치는 초록에 없음 | partly |
| 멀티뷰 비지도 | https://arxiv.org/pdf/1807.09715 | 게임 화면 + 스트리머 얼굴 + 음성, 합성곱 오토인코더 + 순환 융합(PUBG) | partly |
| 치지직 채팅 | 커뮤니티 코드(검색 요약) | VOD 채팅이 playerMessageTime 으로 페이징되는 것으로 보이나 공식 문서는 못 찾았다. yt-dlp 치지직 추출기는 v3 videos 엔드포인트 사용 | unverified |

판단: 채팅은 목표(본인 MR 라이브, 경계 정밀)와 거리가 있고, 수집 방법이 미확정이며 사용자 허락이 필요한 외부 호출이다. 시험한다면 R20 처럼 엔드포인트 확인을 먼저 하고, 채팅 밀도와 반응어를 "후보 신뢰도 보조"로만. 하이라이트 문헌(주로 게임/스포츠)에서 가져올 구조적 아이디어는 "스트리머 반응(음성/얼굴)을 신호로 쓴다" 정도.

### 3.13 few-shot, 그룹 hold-out, 보증, 사람 루프

| 항목 | 출처 | 핵심 | conf |
|---|---|---|---|
| 블록 CV | https://pred.uni-regensburg.de/id/eprint/1455/ | 구조(시간, 공간, 계층) 데이터는 블록 CV 가 예측 평가에 거의 항상 적합. 블록화는 외삽을 요구해 보수적 | partly |
| 아티스트 필터 | https://archives.ismir.net/ismir2007/paper/000341.pdf | 같은 아티스트가 학습/시험에 걸치면 장르 분류가 아니라 아티스트 분류가 된다. 감소폭은 본문 못 읽음 | partly |
| MIR 타당성 | https://arxiv.org/abs/2301.01578 | 4가지 타당성 유형(Shadish 2002)으로 MIR 실험 검토. 세부 권고는 초록에 없음 | partly |
| LTT | https://arxiv.org/abs/2110.01052 | 위험 통제를 다중 가설 검정으로. 유한 표본 보증, 모델 재학습 불필요 | partly |
| NP | https://arxiv.org/abs/1608.03109 | 제1종 오류를 상한 alpha 로 두고 제2종 최소화. 임의 점수형 분류기에 적용. 순서통계량 규칙은 본문 못 읽음 | partly |
| 중첩 검증 | https://jmlr.org/papers/v11/cawley10a.html | 모델 선택 기준 과적합이 성능 평가 편향을 만든다 | partly |
| TypiClust | https://arxiv.org/abs/2202.02794 | 저예산 전형, 고예산 비전형 | partly |
| 소수 라벨 임베딩 프로브 | PLAN_NEXT 2.1 | SigLIP 프로브 GroupKFold | - |

우리 숫자(computed, 7절)가 말하는 것: 현재 표본으로 "라이브 손실 0"은 상한 2~6% 수준 이상의 주장이 불가능하고, N 노출률의 14/55 와 10/55 는 구분 불가. 따라서 보고는 점추정이 아니라 구간, 채택 기준은 "구간 상한이 기준선보다 낮은가"로 바꿔야 한다. (PLAN_NEXT 3.4 와 같은 방향의 수치 근거.)

### 3.14 규칙 + 모델 혼합, 멱등 캐시, 결정론

| 항목 | 출처 | 핵심 | conf |
|---|---|---|---|
| 재현성 | https://docs.pytorch.org/docs/2.14/notes/randomness.html | 위 1.5절 | verified |
| DVC | https://doc.dvc.org/user-guide/pipelines/running-pipelines | 명령/의존성/파라미터 불변이면 stage skip, run-cache 복원, `dvc repro --dry` | verified(페이지에 해시 상세는 없음) |
| CheckList | https://arxiv.org/abs/2005.04118 | 능력 x 테스트 유형 매트릭스, 템플릿으로 대량 생성 | partly |
| ML Test Score | https://research.google/pubs/the-ml-test-score-a-rubric-for-ml-production-readiness-and-technical-debt-reduction/ | 28개 테스트와 점수화 | partly |
| 규칙 + 모델 | PLAN_NEXT 3.2 | 하드 규칙 유지 + 소수 특징 강한 정규화 로지스틱 | - |

## 4. 이 저장소 단계별 삽입 지도

| 단계 | 넣을 수 있는 것 | 근거 절 |
|---|---|---|
| detect | YAMNet 추가 클래스, PANNs/AST 비교, 히스테리시스 병합(점수 캐시) | 3.1, 3.2 |
| refine | PANNs 프레임 SED(10ms), 호흡 후보, 랩 채널 | 3.1, 3.6 |
| snap | 비트 격자 시작 후보(B/review 전용), 호흡 보존 후보, 합성 덕킹 평가 | 3.6, 3.7, 3.2 |
| scene | SigLIP2 프로브, content_val 통계, OCR, VLM 이진 질의, AV 동기 | 3.11 |
| route | NP/LTT 보증형 임계, 지문 양/음 증거, 군집 대표 질의 | 3.9, 3.13 |
| final | 변경 없음 | - |
| asr(새 보조 단계) | VAD 게이트 + delooping + BoH, 가창 프롬프트, 첫/끝 가사 시각 | 3.3, 3.4 |
| harness | 결정론 플래그, 행동 테스트, stale 보고, 클러스터 부트스트랩 | 3.14, 3.13 |

## 5. 실험 설계 목록 (R번호, 트랙이 가져다 쓴다)

채택 기준은 모든 실험 공통으로 golden gate 이탈 0, memo_audit hit@0.5/3/10 비악화, N 노출(등록부 제외) 비악화, 라이브 손실 0 이다. 새 산출물은 cache/proto_<track>/ 에만 쓴다.

| ID | 가설 | 입력/방법 | 지표 | 비용(추정) | 트랙 |
|---|---|---|---|---|---|
| R01 | 캐시에 없는 YAMNet 채널(Rapping, Humming, Breathing, Sigh, Gasp, Hip hop, Video game music, Background music, Theme music)이 랩 미탐과 N 유형을 가른다 | `yamnet_backend.scores_windows(pcm, starts, cls=(...))` 로 후보 +-60초와 N 55곡만 재계산, 기존 3클래스 캐시는 보존 | 구조적 미탐 랩 3곡 복구, N 유형별 단독 AUC, LOGO 조합 이득, 라이브 손실 | GPU 분 단위(전수는 1시간 8초 x 338시간 = 약 45분) | sweep |
| R02 | PANNs 프레임 SED(10ms)가 refine 의 0.1초 YAMNet 보다 경계 hit@0.5 가 좋다 | panns_inference + Cnn14_DecisionLevelMax, 후보 +-30초 | memo_audit hit@0.5/3/10, 시작/끝 분리 | 설치 10~20분, 실행 분 | boundary |
| R03 | AST/CLAP/BEATs 클립 점수가 YAMNet 보다 N 유형(같이보기, 자리비움, OST)에서 낫다 | AST(transformers), CLAP music_speech_audioset(48kHz), 곡 구간 10초 창 평균. 문장 질의(CLAP) 포함 | N 유형 AUC(LOGO), 라이브 손실 | 분~십분 | sweep |
| R04 | 안정 비트 격자의 첫 박이 MR 시작이다 | Beat This! small0/final0, 후보 시작 앞 45초 | 시작 late 11클립과 숫자 정답 시작 hit@3, golden 이탈 | 분 단위, VRAM 1GB 미만 | boundary |
| R06 | 호흡 후보(1.6~1.7kHz 봉우리, 300ms 이상, ZCR/VMS 높음 + 뒤따르는 보컬 온셋)를 시작에 포함하면 late 시작이 줄고 말 오탐은 없다 | 규칙형, 시작 앞 8초 | 시작 hit@3, 호흡 메모 행(51/52), 말 포함 곡 수 | CPU 초 | boundary |
| R07 | 이중 임계 히스테리시스 + 최소 지속 병합이 조각화(20/21, 144)를 고치고 거짓 병합이 적다 | 점수 캐시, 최소 지속 3.4초/틈 0.6초 출발점 스윕 | 정답 곡 길이 hit@5초, 거짓 병합 수, golden 0 | CPU 분 | boundary, sweep |
| R09 | speech VAD(Silero)는 보컬 스템/혼합의 가창, 랩, 말에서 확률 분포가 어떻게 다른가 | silero-vad 6.2.3, 라이브 곡 구간 대 말 구간 대 랩 구간 | 곡 구간 speech 확률 분포, 말/랩/가창 AUC | CPU 분 | asr |
| R10 | 한국어 가창에서 환각률은 설정으로 크게 달라진다 | faster-whisper, 라이브 20 + 랩 10 + 말 10 + 전주/간주 구간. 설정: 원본, VAD 게이트, delooping+한국어 BoH, 언어 고정, "lyrics:" 접두, compression_ratio_threshold on/off, condition_on_previous_text False | 전주/간주 구간 텍스트 삽입률(환각 대리), 루프율, 단어 수/초, BoH 적중 | GPU, large 계열은 VRAM 3GB 초과 가능성(미측정): small/medium 또는 int8 로 | asr |
| R12 | Whisper-AT 태그가 YAMNet 보다 가창/랩/허밍을 잘 가른다 | whisper-at small, at_time_res 10 | 라벨 있는 곡 구간 AUC | GPU 분 | asr |
| R13 | 첫/마지막 가사 단어 시각이 시작 late / 끝 early 곡의 부정 증거가 된다 | 정렬(WhisperX 식) | 11 late + 9 early 곡 중 가사가 컷 밖에 있는 비율 | R10 이후 | asr, boundary |
| R14 | 승인 라이브 MR 재사용 지문 일치가 L 양성 증거, known_negatives 오디오 재사용이 N 음성 증거다 | audfprint(또는 landmark numpy 구현 약 100줄), 승인 151곡과 known_neg 57건, 방송 날짜 단위 LOGO | 양/음성 증거 정밀도, 새 노출 수 | 0.008배속, 분 | asr(신원) |
| R15 | SigLIP2 임베딩 프로브가 화면 N 유형을 라이브 손실 0 에서 얼마나 거르나 | open_clip `ViT-B-16-SigLIP2`, 키프레임 6032장, 로지스틱 C 스윕, 스트리머 GroupKFold | N 재현율 at 라이브 손실 0, 클러스터 부트스트랩 | 10~30분 추정, VRAM 1~2GB 추정 | visual |
| R16 | 아바타 ROI 움직임과 보컬 RMS 의 지연 상호상관이 L 과 N(같이보기/자리비움/OST)을 가른다 | 방송별 ROI 1회 지정, 10fps, +-0.5초 최대 상관 | AUC(LOGO) | 영상 디코딩이 병목. NAS 401 이면 중단 | visual |
| R17 | content_val 통계(평균, p90, 컷 수, 정지 비율)가 키프레임차 신호를 안정화한다 | scenedetect 0.7.2 (venv 설치됨) | 단독 AUC, 기존 신호 추가 이득 | 곡당 수 초 | visual |
| R18 | OCR 로 가사/노래방 UI/플레이어 UI 존재율이 N 유형을 가른다 | PaddleOCR-VL(한국어), 후보당 3프레임 | 텍스트 박스 수, 한글 비율, 하단 자막 띠 | 모델 다운로드 필요, GPU 분 | visual |
| R19 | 초소형 VLM 이진 질의가 같이보기/게임 화면을 거른다 | SmolVLM-256M/500M, 후보당 3프레임 | 정확도, s/프레임, VRAM 피크, 라이브 손실 | 분 단위 | visual |
| R20 | 채팅 밀도/반응어가 후보 신뢰도 보조 신호다 | 먼저 엔드포인트 확인(사용자 허락 필요) | AUC | 불확실 | (보류) |
| R21 | 라이브 보호 임계를 NP/LTT 로 정하면 손실 상한이 보증되고 N 노출은 얼마나 늘어나는가 | 현재 신호 은행 점수, 임계 = 최소 라이브 점수(k 번째) | 보증 상한(스트리머 클러스터 부트스트랩), N 노출 | CPU 초 | sweep |
| R22 | 무작위 탐색 + 파레토가 격자 스윕의 비단조 결과(m 0.0/0.1/0.2)를 안정화한다 | 신호 임계 200 설정, 중첩 LOGO | 선택된 설정의 hold-out 편차 | CPU 분 | sweep |
| R23 | 군집 대표(전형) 질의가 경계 분산 질의보다 사용자 지적 곡을 먼저 찾는다 | SigLIP2 + 오디오 임베딩 군집, 10곡 질의 시뮬레이션 | 사용자 지적 곡 precision@10 | CPU 분 | sweep |
| R24 | 시드와 deterministic 플래그로 분석기 경계 흔들림(0.4초, 후보 수 10/11)이 줄어든다 | benchmark=False, deterministic=True, random.seed, 같은 방송 4회 | 4회 간 경계/후보 수 차이 | GPU 분 | harness |
| R25 | 메모를 MFT/불변성/방향성 테스트로 바꾸면 회귀 감지력이 는다 | memo_audit 항목 분류 + 불변성(앞 5초 무음, +-3dB) 추가, "horse" 점검(방송 길이/스트리머 EQ 단독으로 N 예측) | 테스트 수, 불변성 실패 수, 단독 예측 AUC | CPU 분 | harness |
| R26 | 합성 덕킹(7~18 LU)으로 MR 위 멘트(70/71, 61/62)의 끝 규칙을 정답 있는 L 곡에서 평가할 수 있다 | L 25곡 끝 +0~10초에 말 얹기 | 끝 오차, 조기 절단율 | ffmpeg 25개 | boundary |

R05(랩 박 정렬도)는 R04 의 비트 격자를 재사용하므로 R04 이후 boundary/sweep 이 추가. R08(YOHO 식 회귀 헤드), R11, R27(SSL 가수 임베딩 44.1kHz)은 학습 또는 원본 재수집이 필요해 보류.

## 6. 기각/보류와 이유

- YOHO 식 회귀 모델 학습: 정답 경계 104곡으로 학습은 과적합(PLAN_NEXT 2.2와 같은 이유). 합성 덕킹 데이터 생성 아이디어만 평가에 차용.
- 보컬 분리 전 후보 적용: Syed 2025 에서 분리가 ASR 을 개선하지 않았고 삽입을 늘렸다(verified). 분리는 비교군으로만.
- 외부 음원 카탈로그 지문: 카탈로그 확보와 저작권 비용(HANDOFF 6항 6번). 자기 라이브러리 지문만.
- SSL 가수 임베딩: 44.1kHz 원본과 분리 보컬이 필요. 후순위.
- 채팅 수집: 엔드포인트 미확정 + 목표 거리. R20 보류.
- 신경망 지문: 수치를 못 읽었고 landmark 로 충분한지 먼저.
- Foote/Serra/Nieto 구조 분석: 이번에 본문을 못 읽었고 PLAN_NEXT 가 이미 보류.
- 곡 길이 prior 문헌: 근거 문헌을 못 찾았다. 우리 승인 라이브러리의 같은 곡 길이 일관성으로 대체(R13 의 부산물).

## 7. 이번 조사에서 실제로 실행한 것 (computed)

| 무엇을 | 결과 |
|---|---|
| venv(C:\_tools\wt\venv) 패키지 점검 | 설치됨: torch 2.6.0+cu124, torchaudio, faster-whisper 1.2.1, ctranslate2 4.8.4, open_clip_torch 3.3.0, transformers 5.21.0, silero-vad 6.2.3, scenedetect 0.7.2, torchcrepe 0.0.24, librosa 1.0.0, mir_eval 0.8.2, scikit-learn 1.9.1, scipy, onnxruntime 1.31.1, timm. 없음: panns_inference, madmom, beat_this, pyannote, speechbrain, demucs, paddleocr, laion_clap, whisper_at |
| GPU | RTX 4070 Ti, 12,282MiB 중 2,245MiB 사용(다른 트랙 포함) |
| `cache/detect/*.scores.npy` 형상 | (48359, 3) float32: Singing/Speech/Music 3클래스뿐. 파일 303개(scores 147개) |
| open_clip 지원 목록 | SigLIP2 15개 이상(`ViT-B-16-SigLIP2` 포함), nllb-clip-siglip 4개 |
| transformers 임포트 | ASTForAudioClassification, ClapModel 임포트 성공 |
| 이항분포 정확 계산 | 손실 0/136 단측 95% 상한 2.18%, 0/113 2.62%, 0/49 5.93%, 0/25 11.29%, 2/136 4.56%. N 노출 Wilson 95%: 23/55 29.7~55.0%, 14/55 15.8~38.3%, 10/55 10.2~30.3%. 손실 상한 5%/2%/1%(신뢰 95%)에 필요한 무손실 표본 59/149/299곡. n=136 에서 임계를 최소 라이브 점수로 두면 진짜 손실률이 3%를 넘을 확률 0.016 |
| 사용한 방법의 한계 | 위 구간은 곡을 독립으로 본 것이라 스트리머 클러스터링을 반영하지 않는다. 실제 구간은 더 넓다(PLAN_NEXT 의 스트리머 단위 구간 14/55 [11-42%]가 그 예) |

모델 학습/추론 실험은 이 트랙에서 돌리지 않았다(조사 전용). R번호가 모델 실험이다.

## 8. 읽지 못해 근거로 쓰지 않은 것 (unverified)

- Foote 2000 본문, Serra 2012, Nieto & Bello 2016, Grill & Schlüter 2015 (구조/경계 분석).
- Schlüter & Grill 2015 본문 수치(서버 중단), 가창 검출 설문 본문(접속 검증 화면), Gimeno 2020 본문 수치, Albayzin 평가 표.
- Gärtner & Dittmar 2009/2010 본문 수치, Ruinskiy & Lavner 2007 본문, Breath Activity Detection(1602.07767).
- 신경망 지문 본문 수치, MERT/AST/BEATs/CLAP/SigLIP2/SmolVLM 의 본문 표.
- 치지직 VOD 채팅 엔드포인트의 정확한 사양, PP-OCR 계열의 한국어 모델 유무, SyncNet 저장소의 현재 상태, aeseg, Whisper 논문 부록 D 의 한국어 FLEURS/Common Voice 수치.
- stable-ts, whisper-timestamped, pyannote segmentation 3.x, madmom.

## 9. 출처 목록 (전체, confidence)

verified(본문/README/코드를 직접 읽음): 2501.11378, 2506.15514, 2306.17103(ar5iv), 2402.08021(HTML), 2212.04356 앞부분(ar5iv), faster-whisper transcribe.py, 2306.07744(HTML), 2512.09713(HTML), 2402.00288(HTML), 2102.09959(ar5iv), 2401.05064(HTML), Scheirer & Slaney 1997(PDF), Wang 2003(PDF), audfprint README, Nakano 호흡 페이지, YAMNet README+class map, PANNs README, panns_inference README, Silero README+소스, Beat This README, Whisper-AT README, LAION-CLAP README, PaddleOCR README, scenedetect 문서, Qwen2.5-VL-3B 카드, PyTorch randomness, DVC running-pipelines.

partly(초록/소개/검색 요약): 2303.00747, 2307.03183, 2109.00962, 1906.06909, 2104.01778, 2212.09058, 2211.06687, 2306.00107, 2502.14786, 2504.05299, SmolVLM 블로그, SigLIP2 카드, AST 카드, 2407.21658, 1912.10211, 2306.15412(RMVPE), 1802.06182(CREPE), 2010.11910, 1707.08559, 1807.09715, 1606.03044, 1306.1461, 2301.01578, 2110.01052, 1608.03109, 2202.02794, Roberts 2017, Flexer 2007, Cawley & Talbot, Bergstra & Bengio, CheckList, ML Test Score, Sturm 2014, Hershey & Movellan, SyncNet(ORA), Gimeno(ISCA), inaSpeechSegmenter, Gärtner & Dittmar, MCFlow, Cuesta 등, RefWhisper, 가창 검출 설문.

## 10. 한계와 위험

- 대부분의 외부 수치는 영어/유럽어, 음악 DB(Jamendo, RWC, MUSDB), 낭독 음성에서 나왔다. 한국어 가창, 버튜버 스트림, 게임 소리가 섞인 방송에는 직접 적용되지 않는다. 채택 근거는 우리 데이터의 LOGO 결과뿐이다.
- WebFetch 요약은 요약 모델을 거치므로 표의 일부 수치는 원문 재확인이 필요할 수 있다. 의사결정에 쓰는 수치(2절 2, 3, 4, 5, 8, 11)는 각 본문에서 읽은 것이지만 코드로 재현한 것은 아니다.
- 비용 열의 "추정"은 모두 측정 전이다. VRAM 3GB 상한 안에 들어가는지는 R번호 실험에서 첫 단계로 실측해야 한다(특히 Whisper large 계열, PANNs, CLAP).
- 지문 신호(R14)는 MR 이 원곡 반주와 같아 L/N 구분력이 약할 수 있다: 양/음성 증거로만 쓴다.
- AV 동기(R16)는 영상 디코딩 비용과 NAS 인증(401) 위험이 있고 도메인 선행 사례가 없다.
