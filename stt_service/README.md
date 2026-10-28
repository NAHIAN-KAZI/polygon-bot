# Titu STT server

Speech-to-text for the chat app's **Titu STT** voice mode (`audio_mode: "nemo"`): a Bangla
CTC model on NVIDIA NeMo, chosen with `STT_MODEL` (default
[hishab/titu_stt_bn_conformer_large](https://huggingface.co/hishab/titu_stt_bn_conformer_large)).

| `STT_MODEL` | `STT_MODEL_FILE` | Size | Licence | Tested (2026-10-27, 97 Bangla clips) |
|---|---|---|---|---|
| `hishab/titu_stt_bn_conformer_large` (default) | — | 490 MB | CC-BY-NC-4.0 | WER 5.5%, all amounts kept |
| `hishab/titu_stt_bn_fastconformer` | — | 460 MB | CC-BY-NC-4.0 | WER 9.0%, all amounts kept |
| `teamvillagers/titu-stt-bn-conformer-large-finetuned` | `titu_bn_finetuned_lighten.nemo` | 490 MB | none stated | WER 7.6%, dropped 5 of 9 amounts: don't use |

Latency on the DGX Spark: ~60 ms for a 3-10 s clip with either hishab model; at 30 s,
170 ms for conformer_large vs 85 ms for fastconformer.

`STT_MODEL_FILE` is needed only when the repo's `.nemo` isn't named after the repo.

## Run (on the GPU box, e.g. DGX Spark)

```bash
cd stt_service
echo "STT_API_KEY=$(openssl rand -hex 24)" > .env   # same value goes in the app's .env
# optional: echo "STT_PORT=8791" >> .env           # host port, default 8791
docker compose up -d --build                        # first build pulls nvcr.io/nvidia/nemo:26.08 (~19 GB)
docker compose logs -f stt                          # wait for "Application startup complete"
curl localhost:8791/health
```

The model downloads into `~/.cache/huggingface` on first start.
If the image pull asks for a login: `docker login nvcr.io`, user `$oauthtoken`, password = NGC API key.

## Several models side by side

One compose project per model, each with its own port. `STT_BIND=127.0.0.1` keeps a test
instance off the network; reach it with `ssh -L 18792:localhost:8792 <gpu-box>`.

```bash
STT_PORT=8792 STT_BIND=127.0.0.1 STT_MODEL=hishab/titu_stt_bn_conformer_large \
  docker compose -p stt-conformer-large up -d
STT_PORT=8793 STT_BIND=127.0.0.1 STT_MODEL=teamvillagers/titu-stt-bn-conformer-large-finetuned \
  STT_MODEL_FILE=titu_bn_finetuned_lighten.nemo docker compose -p stt-large-finetuned up -d
docker compose -p stt-conformer-large down                # remove one
```

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
