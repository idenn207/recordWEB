#!/bin/sh
# data/vods12.json 전체: 없는 방송은 fetch_vod.py 로 받고(1개 프로세스, fetch_vod.py 기본 상한, nice 19), 받는 대로 pipeline.py 로 처리(GPU 1개씩).
# 결과 out/<videoNo>, 로그 cache/logs/exp12_*. 실패는 cache/logs/exp12_fail.txt 에 "번호 이유" 로 남기고 계속한다.
# 사용: nohup sh datasets/run_big.sh &   (다운로드와 처리는 서로 다른 백그라운드 루프)
mkdir -p cache/logs; : > cache/logs/exp12_fail.txt; rm -f cache/logs/exp12_dl_done
python -c "
import json
open('cache/logs/exp12_list.txt','w',encoding='utf8',newline='\n').write(''.join(f\"{v['videoNo']} {v['name']}\n\" for v in json.load(open('data/vods12.json',encoding='utf8'))))"
(while read id name; do
  [ -f data/vod/$id.wav ] || nice -n 19 python datasets/fetch_vod.py $id >> cache/logs/exp12_fetch.log 2>&1 || echo "$id 다운로드 실패" >> cache/logs/exp12_fail.txt
done < cache/logs/exp12_list.txt; touch cache/logs/exp12_dl_done) &
done_ids=" "
while :; do
  prog=0
  while read id name; do
    case "$done_ids" in *" $id "*) continue;; esac
    if [ -f data/vod/$id.wav ] && ! [ -f data/vod/$id.m4a ]; then   # m4a 가 있으면 아직 변환 중
      timeout 10800 python pipeline.py data/vod/$id.wav --name "$name" >> cache/logs/exp12_pipe.log 2>&1 || echo "$id 파이프라인 실패" >> cache/logs/exp12_fail.txt
      done_ids="$done_ids$id "; prog=1; echo "처리 $id" >> cache/logs/exp12_progress.txt
    fi
  done < cache/logs/exp12_list.txt
  [ $prog = 0 ] && { [ -f cache/logs/exp12_dl_done ] && break; sleep 20; }
done
echo finished >> cache/logs/exp12_progress.txt
