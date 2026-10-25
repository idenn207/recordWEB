#!/bin/sh
# run_big.sh 의 두 번째 작업자: 같은 목록을 뒤에서부터 처리한다(GPU 는 1개 작업이 다 쓰지 않고 144p 장면 읽기가 네트워크 대기라 2개 병행 가능).
# 첫 작업자가 처리했거나(out/<id> 있음) 진행 중인 방송을 만나면 멈춘다. shortcut: 락 없음, 만나는 지점에서 한 방송이 겹쳐 돌 수 있다(멱등이라 결과는 같음).
tac cache/logs/exp12_list.txt | while read id name; do
  [ -d out/$id ] && break
  [ -f data/vod/$id.wav ] && ! [ -f data/vod/$id.m4a ] || continue
  timeout 10800 python pipeline.py data/vod/$id.wav --name "$name" >> cache/logs/exp12_pipe2.log 2>&1 || echo "$id 파이프라인 실패(2)" >> cache/logs/exp12_fail.txt
  echo "처리2 $id" >> cache/logs/exp12_progress2.txt
done
echo finished2 >> cache/logs/exp12_progress2.txt
