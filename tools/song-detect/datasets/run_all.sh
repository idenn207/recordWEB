#!/bin/sh
# data/vod/legacy/20*.wav 중 아직 결과(cache/detect/*.segments.json)가 없는 것을 순서대로 탐지한다
for w in data/vod/legacy/20*.wav; do
  b=$(basename "$w" .wav)
  [ -f "cache/detect/$b.segments.json" ] || docker run --rm -v "$PWD/data:/work/data" -v "$PWD/cache:/work/cache" -v "$PWD/paths.py:/work/paths.py" song-detect "$w"
done
