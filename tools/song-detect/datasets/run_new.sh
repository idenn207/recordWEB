#!/bin/sh
# 새 표본 수집 -> GPU 탐지 -> 경계 재분석. 결과는 cache/exp10(탐지), cache/exp10r(경계 재분석 후). 기존 exp8/exp9 는 건드리지 않는다.
# 있는 data/vod/<번호>.wav 는 재사용. 사용: ./run_new.sh <videoNo>...   (fetch_vod.py 의 기본 속도 상한 그대로, 낮은 우선순위)
mkdir -p cache/logs cache/exp10 cache/exp10r
for id in "$@"; do
  [ -f data/vod/$id.wav ] || nice -n 19 python datasets/fetch_vod.py $id >> cache/logs/fetch10.log 2>&1
  [ -f cache/exp10/$id.segments.json ] || MSYS_NO_PATHCONV=1 docker run --rm --gpus all -v "$PWD/data:/work/data" -v "$PWD/cache:/work/cache" -v "$PWD/paths.py:/work/paths.py" -v "$PWD/detect.py:/work/detect.py" song-detect-gpu data/vod/$id.wav vocal_thr=0.2 --out=cache/exp10/$id.segments.json > cache/exp10/$id.log 2>&1
  [ -f cache/exp10r/$id.segments.json ] || MSYS_NO_PATHCONV=1 docker run --rm --entrypoint python -v "$PWD/data:/work/data" -v "$PWD/cache:/work/cache" -v "$PWD/paths.py:/work/paths.py" -v "$PWD/detect.py:/work/detect.py" -v "$PWD/refine.py:/work/refine.py" song-detect-gpu refine.py data/vod/$id.wav cache/exp10/$id.segments.json cache/exp10r/$id.segments.json > /dev/null 2>&1
  echo done $id
done
echo finished
