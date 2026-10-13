# NeMo Framework image (multi-arch, runs on DGX Spark / arm64). Its NeMo source tree at
# /opt/NeMo isn't installed, so the ASR toolkit is installed from it; the image's
# PIP_CONSTRAINT keeps NVIDIA's own torch build.
FROM nvcr.io/nvidia/nemo:26.08

RUN pip install --no-cache-dir -e "/opt/NeMo[asr]" uvicorn

WORKDIR /srv
COPY server.py .

EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
