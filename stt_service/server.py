"""Speech-to-text server for the chat app's "nemo" voice mode: hishab's Bangla
titu_stt_bn_fastconformer on NeMo. POST /transcribe takes a WAV body and returns
{"text": ...}. Runs on the GPU box (see README.md); the app calls it at STT_URL."""
import hmac
import io
import os
import tempfile
import threading

import librosa
import numpy as np
import soundfile as sf
import torch
import nemo.collections.asr as nemo_asr
from fastapi import FastAPI, Header, HTTPException, Request
from omegaconf import open_dict

MODEL = os.environ.get("STT_MODEL", "hishab/titu_stt_bn_fastconformer")
API_KEY = os.environ.get("STT_API_KEY", "")
MAX_BYTES = int(os.environ.get("STT_MAX_MB", "10")) * 1024 * 1024
RATE = 16000  # what the model was trained on

model = nemo_asr.models.ASRModel.from_pretrained(MODEL).cuda().eval()
decoding = model.cfg.decoding
with open_dict(decoding):
    decoding.strategy = "greedy_batch"  # same output as "greedy", faster
model.change_decoding_strategy(decoding, verbose=False)
lock = threading.Lock()  # one transcription at a time on the GPU

app = FastAPI(title="titu-stt")


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}


@app.post("/transcribe")
async def transcribe(request: Request, x_api_key: str | None = Header(default=None)):
    if API_KEY and not hmac.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(401, "bad or missing X-API-Key")
    raw = await request.body()
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(413 if raw else 400, "send one WAV file as the request body")
    try:
        audio, rate = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
    except Exception:
        raise HTTPException(400, "the body isn't a readable WAV file")
    audio = audio.mean(axis=1)
    if rate != RATE:
        audio = librosa.resample(audio, orig_sr=rate, target_sr=RATE)
    return {"text": _transcribe(np.ascontiguousarray(audio))}


def _transcribe(audio: np.ndarray) -> str:
    # The model reads files, so the clip goes through a temporary 16 kHz mono WAV.
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp, lock, torch.inference_mode():
        sf.write(tmp.name, audio, RATE, subtype="PCM_16")
        out = model.transcribe([tmp.name], verbose=False)[0]
    return (out.text if hasattr(out, "text") else str(out)).strip()


# The first transcription after start takes ~10 s (CUDA/kernel warmup on the Spark), later
# ones ~40 ms; pay it here so no customer waits for it.
_transcribe(np.zeros(RATE, dtype=np.float32))
