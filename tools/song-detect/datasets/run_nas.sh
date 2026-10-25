#!/bin/sh
# NAS 10월 녹화 전체 수집+탐지. 사용: nohup sh datasets/run_nas.sh > cache/logs/nas_run.log 2>&1 &   (재실행하면 이어서)
python datasets/nas_ingest.py index && python datasets/nas_ingest.py run 3 2 ; python datasets/nas_ingest.py summary
