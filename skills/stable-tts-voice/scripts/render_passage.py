# stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
"""Reads a passage part by part with one setup, the way a reader app does, and saves every part.

Run it with the Python of the app's own TTS runtime (needs mlx-audio; numpy comes with it):
  PY -B render_passage.py --model DIR --mode custom --speaker uncle_fu --text passage.txt --out runs/现在
  PY -B render_passage.py --model BASE --mode xvec --ref voice.wav --text passage.txt --out runs/克隆

Writes OUT/part-01.wav … and OUT/manifest.json (setup, every part's text, timing, peak memory).
To match an app, copy its own settings: its instruct, sampling (--temperature …), seed, and its
segmentation (write its segments one per line and pass --lines, plus --raw if it does no cleanup).
The seed is reset to the same value before every part (what the apps do); --seed-step 1 gives each
part its own seed instead, which shows how much the voice depends on the seed.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qwen_runner  # noqa: E402
from tts_text import duration_limit, prepare_text, split_parts, token_limit  # noqa: E402
from voice_audio import write_wav  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    qwen_runner.add_arguments(parser)
    parser.add_argument("--text", required=True, help="UTF-8 text file")
    parser.add_argument("--lines", action="store_true", help="one part per non-empty line, not re-split "
                        "(use the app's own segmentation to match it exactly)")
    parser.add_argument("--raw", action="store_true", help="send the text as is, without tts_text.prepare_text "
                        "(for apps that do no text cleanup of their own)")
    parser.add_argument("--max-part", type=int, default=80)
    parser.add_argument("--seed", type=int, default=82040)
    parser.add_argument("--seed-step", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0, help="only the first N parts")
    parser.add_argument("--label", help="name shown on the listening page")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    source = Path(args.text).read_text(encoding="utf-8")
    clean = (lambda text: text.strip()) if args.raw else (lambda text: prepare_text(text, args.language))
    if args.lines:
        parts = [clean(line) for line in source.splitlines() if line.strip()]
    else:
        parts = split_parts(clean(source), args.max_part)
    if args.limit:
        parts = parts[:args.limit]
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    runner = qwen_runner.from_arguments(args)
    runner.say("嗯。" if args.language == "chinese" else "Hm.", args.seed, 40)   # warm-up, not timed
    rows, started = [], time.monotonic()
    for i, text in enumerate(parts, 1):
        seed = args.seed + (i - 1) * args.seed_step
        audio, gen, first, limited = runner.say(text, seed, token_limit(text))
        audio = audio[:int(duration_limit(text) * runner.rate)]
        name = f"part-{i:02d}.wav"
        write_wav(out / name, audio, runner.rate)
        rows.append({"i": i, "file": name, "text": text, "seed": seed, "audio_s": round(audio.size / runner.rate, 2),
                     "gen_s": round(gen, 2), "first_s": round(first, 3) if first is not None else None,
                     "limited": limited})
        print(f"{i:02d}/{len(parts)}  {rows[-1]['audio_s']:5.1f}s audio  {gen:5.1f}s  {text[:24]}", flush=True)
    audio_total = sum(r["audio_s"] for r in rows)
    gen_total = sum(r["gen_s"] for r in rows)
    manifest = {"label": args.label or out.name, "model": str(Path(args.model).name), "ref": args.ref,
                **runner.describe(), "seed": args.seed, "seed_step": args.seed_step, "max_part": args.max_part,
                "parts": rows, "audio_seconds": round(audio_total, 1),
                "realtime_factor": round(gen_total / audio_total, 3) if audio_total else None,
                "peak_gb": runner.peak_gb(), "wall_seconds": round(time.monotonic() - started, 1)}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {len(rows)} parts, {audio_total:.0f}s audio, RTF {manifest['realtime_factor']}, "
          f"peak {manifest['peak_gb']} GB -> {out}")


if __name__ == "__main__":
    main()
