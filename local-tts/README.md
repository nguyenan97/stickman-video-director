# Local narration for Autopilot (Kokoro-82M, offline)

Replaces `scripts/gemini-media.mjs speech` with the local Kokoro checkout at
`..\kokoro` (override with `$env:KOKORO_HOME`). No network request, no API key.
Autopilot only needs a narration file (`project.json` -> `voice.path`), so the
Docker runtime stays unchanged: TTS runs on the host, render runs in the container.

## One video

```powershell
# 1. Exact approved narration, one spoken line per row (UTF-8; BOM is fine)
#    -> <project>\script.txt

# 2. Narration + word timings (brand.json primary_voice sets voice/speed/pause)
.\local-tts\kokoro-speech.ps1 --text <project>\script.txt `
  --output <project>\narration.wav --words <project>\words.json `
  --brand ..\AI-Video-Studio\ideas\<idea-id>\brand.json --loudnorm -18

# 3. Captions in the container (paths relative to /work = AI-Video-Studio\ideas)
.\docker\run.ps1 autopilot captions <idea-id>/<project>/words.json <idea-id>/<project>/captions.json
```

Without `--brand`, pass `--voice af_bella` (and optionally `--speed`, `--pause`,
`--language en-US|en-GB`). English voices only; Kokoro has no Vietnamese voice.

Pronunciation: pass `--lexicon lexicon.json` with `{"entries": {"Ms Tuyen": "mˈɪz twˈiən"}}`.
Entries are whole-phrase, case-sensitive IPA overrides; the script stays plain text
(inline `[word](/ipa/)` markup is rejected) and word timings keep the plain words.
Use phrases ("Mr An") rather than bare words ("An") so articles are not changed.

## Behavior

- Output: 24 kHz mono PCM16 WAV, or 48 kHz loudness-normalized with `--loudnorm`.
- Receipt `<output>.request.json`: provider, model, cached revision, voice ID,
  speed, pause, device, text/output SHA-256, duration, `human_listening: not_checked`.
- `--words` writes `{"words": [{start, end, word}]}` from Kokoro token timestamps,
  the same format as `scripts/align_captions.py`, so Whisper is optional. Review text
  and timing by ear; Whisper alignment is still available as a cross-check.
- Never overwrites output, receipt or words files.
- `--device cpu` by default so the GPU stays free (2026-11-05 test on i7-10875H:
  7.2 s of audio in about 15 s wall time, model load included); `--device cuda` is faster but must not run alongside ComfyUI or ACE-Step.
