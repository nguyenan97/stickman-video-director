"""Local Kokoro-82M narration adapter for Autopilot (replaces gemini-media.mjs speech).

Runs fully offline with the cached hexgrad/Kokoro-82M weights; makes no network
request and needs no API key. Writes one continuous narration WAV, a request
receipt (<output>.request.json) and, optionally, word timings in the same
{"words": [{start, end, word}]} format as scripts/align_captions.py.

Each non-empty line of the text file is one spoken line; lines are joined with
a fixed silence. Voice/speed come from explicit flags or an approved brand.json
("primary_voice"). Existing outputs are never overwritten.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

MODEL = "hexgrad/Kokoro-82M"
SAMPLE_RATE = 24000
LANG_CODES = {"en-US": "a", "en-GB": "b"}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def cached_revision():
    hub = Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub")
    snapshots = hub / "models--hexgrad--Kokoro-82M" / "snapshots"
    revisions = sorted(p.name for p in snapshots.iterdir()) if snapshots.is_dir() else []
    return revisions[-1] if len(revisions) == 1 else (revisions or None)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--text", type=Path, required=True, help="UTF-8 file with the exact approved narration")
    parser.add_argument("--output", type=Path, required=True, help="Destination .wav (must not exist)")
    parser.add_argument("--brand", type=Path, help="brand.json whose primary_voice sets voice/speed/pause/language")
    parser.add_argument("--voice", help="Kokoro voice ID, e.g. af_bella")
    parser.add_argument("--speed", type=float, help="Kokoro speed (service default 1.0)")
    parser.add_argument("--pause", type=float, help="Silence between lines in seconds (default 0.24)")
    parser.add_argument("--language", choices=sorted(LANG_CODES), help="default en-US")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu", help="cpu keeps the GPU free for ComfyUI/ACE-Step")
    parser.add_argument("--loudnorm", type=float, metavar="LUFS", help="Also loudness-normalize to LUFS and resample to 48 kHz (ffmpeg)")
    parser.add_argument("--words", type=Path, help="Write Kokoro word timings JSON here (must not exist)")
    args = parser.parse_args()

    voice = {}
    if args.brand:
        voice = json.loads(args.brand.read_text(encoding="utf-8")).get("primary_voice") or {}
        if voice.get("engine") != "kokoro":
            parser.error("brand.json primary_voice.engine is not kokoro")
        if voice.get("model", MODEL) != MODEL:
            parser.error(f"brand.json model {voice.get('model')} is not {MODEL}")
    args.voice = args.voice or voice.get("voice_id")
    args.speed = args.speed if args.speed is not None else voice.get("speed", 1.0)
    args.pause = args.pause if args.pause is not None else voice.get("inter_line_pause_seconds", 0.24)
    args.language = args.language or voice.get("language", "en-US")
    if not args.voice:
        parser.error("Set --voice or --brand")
    if args.language not in LANG_CODES:
        parser.error(f"Kokoro English pipeline supports {sorted(LANG_CODES)}, not {args.language}")
    if not 0.5 <= args.speed <= 2.0 or not 0 <= args.pause <= 3:
        parser.error("speed must be 0.5-2.0 and pause 0-3 s")
    if args.output.suffix.lower() != ".wav":
        parser.error("Output must be .wav")
    args.output = args.output.resolve()
    args.receipt = args.output.with_name(args.output.name + ".request.json")
    for target in [args.output, args.receipt, args.words]:
        if target and target.exists():
            parser.error(f"{target} exists; inspect it instead of overwriting")
    if args.loudnorm is not None and not shutil.which("ffmpeg"):
        parser.error("--loudnorm needs ffmpeg on PATH")
    return args


def main():
    args = parse_args()
    lines = [line.strip() for line in args.text.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not lines:
        raise SystemExit("Narration text is empty")

    import numpy as np
    import soundfile as sf
    import torch
    from kokoro import KPipeline

    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA requested but unavailable")
    torch.set_num_threads(4)
    pipeline = KPipeline(lang_code=LANG_CODES[args.language], repo_id=MODEL, device=args.device)

    parts, words, cursor = [], [], 0.0
    pause = np.zeros(round(SAMPLE_RATE * args.pause), dtype=np.float32)
    with torch.inference_mode():
        for index, line in enumerate(lines):
            if index and len(pause):
                parts.append(pause)
                cursor += len(pause) / SAMPLE_RATE
            for result in pipeline(line, voice=args.voice, speed=args.speed, split_pattern=None):
                audio = result.audio.detach().cpu().numpy().astype(np.float32)
                for token in result.tokens or []:
                    start, end = getattr(token, "start_ts", None), getattr(token, "end_ts", None)
                    text = (token.text or "").strip()
                    if text and start is not None and end is not None and end > start:
                        if all(not ch.isalnum() for ch in text) and words:
                            words[-1]["word"] += text  # attach punctuation to the previous word
                        else:
                            words.append({"start": round(cursor + start, 3), "end": round(cursor + end, 3), "word": text})
                parts.append(audio)
                cursor += len(audio) / SAMPLE_RATE

    audio = np.concatenate(parts)
    if not np.isfinite(audio).all() or float(np.abs(audio).max()) < 0.01:
        raise SystemExit("Generated audio is silent or invalid")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.loudnorm is None:
        sf.write(args.output, audio, SAMPLE_RATE, subtype="PCM_16")
    else:
        raw = args.output.with_name(f".{args.output.stem}.raw.wav")
        sf.write(raw, audio, SAMPLE_RATE)
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-i", str(raw),
                            "-af", f"loudnorm=I={args.loudnorm}:TP=-2:LRA=7", "-ar", "48000", "-ac", "1",
                            "-c:a", "pcm_s16le", str(args.output)], check=True)
        finally:
            raw.unlink(missing_ok=True)

    info = sf.info(args.output)
    receipt = {
        "kind": "speech",
        "provider": "local-kokoro",
        "model": MODEL,
        "cached_revision": cached_revision(),
        "voice_id": args.voice,
        "language": args.language,
        "speed": args.speed,
        "inter_line_pause_seconds": args.pause,
        "device": args.device,
        "loudnorm_lufs": args.loudnorm,
        "brand": str(args.brand.resolve()) if args.brand else None,
        "text_file": str(args.text.resolve()),
        "text_sha256": sha256(args.text),
        "lines": len(lines),
        "output": str(args.output),
        "sha256": sha256(args.output),
        "duration_seconds": round(info.duration, 3),
        "sample_rate_hz": info.samplerate,
        "network": False,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "complete",
        "human_listening": "not_checked",
    }
    if args.words:
        if not words:
            raise SystemExit("Kokoro returned no word timings; use scripts/align_captions.py instead")
        args.words.parent.mkdir(parents=True, exist_ok=True)
        with args.words.open("x", encoding="utf-8") as handle:
            json.dump({"words": words, "method": "kokoro token timestamps; human text/timing review required"}, handle, ensure_ascii=False, indent=2)
        receipt["words"] = {"path": str(args.words.resolve()), "count": len(words)}
    with args.receipt.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"output": str(args.output), "receipt": str(args.receipt), "duration": receipt["duration_seconds"],
                      "words": len(words) if args.words else None}))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
