#!/bin/sh
# data/*.wav 중 아직 결과(.segments.json)가 없는 것을 순서대로 탐지한다
for w in data/20*.wav; do
  [ -f "${w%.wav}.segments.json" ] || docker run --rm -v "$PWD/data:/work/data" song-detect "$w"
done
