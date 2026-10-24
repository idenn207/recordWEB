#!/bin/sh
# data/vod/*.wav 가 생기는 대로 탐지(GPU) -> 경계 재분석을 이어서 돌린다. 전체(vods.json 의 개수)가 처리되면 끝난다.
# 결과: data/exp8/<videoNo>.segments.json (탐지), data/exp8r/ (경계 재분석 후). 사용: ./run_dataset.sh [전체 개수]
total=${1:-25}; mkdir -p data/exp8 data/exp8r
while :; do
  for w in data/vod/*.wav; do
    id=$(basename "$w" .wav)
    [ $(( $(date +%s) - $(stat -c %Y "$w") )) -gt 60 ] || continue      # 아직 쓰는 중인 파일은 건너뜀
    [ -f data/exp8/$id.segments.json ] || MSYS_NO_PATHCONV=1 docker run --rm --gpus all -v "$PWD/data:/work/data" -v "$PWD/detect.py:/work/detect.py" song-detect-gpu "$w" vocal_thr=0.2 --out=data/exp8/$id.segments.json > data/exp8/$id.log 2>&1
    [ -f data/exp8r/$id.segments.json ] || MSYS_NO_PATHCONV=1 docker run --rm --entrypoint python -v "$PWD/data:/work/data" -v "$PWD/detect.py:/work/detect.py" -v "$PWD/refine.py:/work/refine.py" song-detect-gpu refine.py "$w" data/exp8/$id.segments.json data/exp8r/$id.segments.json > /dev/null 2>&1
  done
  [ $(ls data/exp8r/*.segments.json 2>/dev/null | wc -l) -ge "$total" ] && break
  sleep 60
done
echo finished
