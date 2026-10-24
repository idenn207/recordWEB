#!/bin/sh
# 어려운 표본(게임 방송 등) 수집 -> GPU 탐지 -> 경계 재분석. 결과는 data/exp11(탐지), data/exp11r(경계 재분석 후). 기존 exp8/exp9/exp10 은 건드리지 않는다.
# 있는 data/vod/<번호>.wav 는 재사용. 사용: ./run_hard.sh <videoNo>...   (fetch_vod.py 의 속도 상한 7MB/s 그대로, 낮은 우선순위)
mkdir -p data/exp11 data/exp11r
for id in "$@"; do
  [ -f data/vod/$id.wav ] || nice -n 19 python fetch_vod.py $id >> data/fetch11.log 2>&1
  [ -f data/exp11/$id.segments.json ] || MSYS_NO_PATHCONV=1 docker run --rm --gpus all -v "$PWD/data:/work/data" -v "$PWD/detect.py:/work/detect.py" song-detect-gpu data/vod/$id.wav vocal_thr=0.2 --out=data/exp11/$id.segments.json > data/exp11/$id.log 2>&1
  [ -f data/exp11r/$id.segments.json ] || MSYS_NO_PATHCONV=1 docker run --rm --entrypoint python -v "$PWD/data:/work/data" -v "$PWD/detect.py:/work/detect.py" -v "$PWD/refine.py:/work/refine.py" song-detect-gpu refine.py data/vod/$id.wav data/exp11/$id.segments.json data/exp11r/$id.segments.json > /dev/null 2>&1
  echo done $id
done
echo finished
