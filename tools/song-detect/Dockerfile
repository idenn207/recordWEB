# GPU 이미지: --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu124
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
FROM python:3.12-slim
ARG TORCH_INDEX
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy ai-edge-litert soundfile \
 && pip install --no-cache-dir torch torchaudio --index-url ${TORCH_INDEX} \
 && pip install --no-cache-dir demucs speechbrain librosa
WORKDIR /work
COPY detect.py yamnet_backend.py paths.py models ./
ENV TORCH_HOME=/work/cache/.torch
ENTRYPOINT ["python", "detect.py"]
