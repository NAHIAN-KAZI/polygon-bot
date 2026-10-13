# Titu STT server

Speech-to-text for the chat app's **Titu STT** voice mode (`audio_mode: "nemo"`):
[hishab/titu_stt_bn_fastconformer](https://huggingface.co/hishab/titu_stt_bn_fastconformer),
a Bangla FastConformer CTC model on NVIDIA NeMo. Licence: CC-BY-NC-4.0.

## Run (on the GPU box, e.g. DGX Spark)

```bash
cd stt_service
echo "STT_API_KEY=$(openssl rand -hex 24)" > .env   # same value goes in the app's .env
# optional: echo "STT_PORT=8791" >> .env           # host port, default 8791
docker compose up -d --build                        # first build pulls nvcr.io/nvidia/nemo:26.08 (~19 GB)
docker compose logs -f stt                          # wait for "Application startup complete"
curl localhost:8791/health
```

The model (~460 MB) downloads into `~/.cache/huggingface` on first start.
If the image pull asks for a login: `docker login nvcr.io`, user `$oauthtoken`, password = NGC API key.

## Connect the app

In the app's `.env`:

```
STT_URL=http://<gpu-box>:8791
STT_API_KEY=<same value as above>
```

Restart the app. The voice-mode pill then cycles through **Voice: Titu STT** as well.

## API

`POST /transcribe` — body: one WAV file (any rate, mono or stereo; resampled to 16 kHz),
header `X-API-Key` when `STT_API_KEY` is set. Returns `{"text": "..."}`.

## Notes

- Trained on ~18K hours of Bangla (mostly news). Output is Bangla script; English words come
  out transliterated, so mixed English/Bangla speech is better served by the gemma4 modes.
- Customer voice is sent here: keep the STT port reachable only from the app host, and set `STT_API_KEY`.
