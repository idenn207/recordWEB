#!/bin/sh
# 경계/라우팅 규칙을 바꾼 뒤 목록(cache/logs/exp12_list.txt: "번호 스트리머")의 방송을 --force 로 다시 처리한다(cache/detect 의 YAMNet/Demucs 점수는 재사용).
# 사용: sh datasets/rerun_all.sh <작업자 번호 0|1> <작업자 수>   (홀짝으로 나눠 병렬)
w=${1:-0}; n=${2:-1}; i=0
while read id name; do
  i=$((i+1)); [ $((i % n)) -eq $w ] || continue
  [ -f data/vod/$id.wav ] || continue
  timeout 10800 python pipeline.py data/vod/$id.wav --name "$name" --force >> cache/logs/rerun_$w.log 2>&1 || echo "$id 재실행 실패" >> cache/logs/rerun_fail.txt
  echo "재실행 $id" >> cache/logs/rerun_progress_$w.txt
done < cache/logs/exp12_list.txt
echo finished >> cache/logs/rerun_progress_$w.txt
