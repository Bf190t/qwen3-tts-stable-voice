# stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
"""Builds the "average voice" that speaker similarity is measured against.

Raw Qwen3-TTS speaker embeddings of *any* two voices have cosine 0.91–0.99, so they cannot tell a
drifting part from a steady one. Subtracting the average embedding of many different voices first
spreads them out: different voices then score about −0.15 (−0.70 to 0.75), parts of one steady
voice 0.90–0.97. measure_voice.py uses assets/speaker_background.json automatically. The shipped
file averages 21 voices: 12 distinct ones (6 Kokoro, 5 Qwen presets, macOS Tingting) and 9 VoiceDesign
prototypes (3 descriptions x 3 seeds, so fairly alike). More distinct voices would make it better.

Only needed again for a different encoder (the shipped file is for the 0.6B Base encoder, 1024-d):
  PY -B make_background.py --encoder BASE_MODEL_DIR --out ../assets/speaker_background.json \
      voiceA/*.wav voiceB/*.m4a …     (by default every folder is one voice, e.g. one render_passage run)
  --group-by name: files in one folder, grouped by the part of the name before the last "-"
                   (kokoro-zf_059-1.wav, kokoro-zf_059-2.wav → voice "kokoro-zf_059"; how the shipped file was made)
Use at least 15 clearly different voices (men, women, young, old, several TTS engines).
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from measure_voice import Encoder  # noqa: E402
from voice_audio import read_wav, trim  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+")
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--encoder-id", default="", help="e.g. mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit@<revision>")
    parser.add_argument("--per-voice", type=int, default=3)
    parser.add_argument("--group-by", choices=["folder", "name"], default="folder",
                        help="folder: each folder is one voice (default); name: by the file name before the last '-'")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    groups = {}
    for name in args.files:
        path = Path(name)
        key = str(path.resolve().parent) if args.group_by == "folder" else path.stem.rsplit("-", 1)[0]
        groups.setdefault(key, []).append(path)
    encoder = Encoder(args.encoder, background=None)  # raw embeddings: the background is what is being built
    voices = {}
    for voice, files in sorted(groups.items()):
        vectors = [encoder.embed(trim(read_wav(f))) for f in sorted(files)[:args.per_voice]]
        mean = np.mean(vectors, axis=0)
        voices[voice] = mean / np.linalg.norm(mean)
    if args.group_by == "folder":   # keep the stored names short: the folder name, made unique if needed
        named = {}
        for key, vector in voices.items():
            name, n = Path(key).name, 2
            while name in named:
                name, n = f"{Path(key).name}-{n}", n + 1
            named[name] = vector
        voices = named
    if len(voices) < 2:
        raise SystemExit(f"只分出了 {len(voices)} 个声音；背景要很多个不同的声音（至少 15 个）。检查 --group-by。")
    background = np.mean(list(voices.values()), axis=0)
    data = {"encoder": args.encoder_id or Path(args.encoder).name, "dim": int(background.size),
            "voices": sorted(voices), "mean": [round(float(x), 6) for x in background]}
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"{len(voices)} voices -> {args.out}")


if __name__ == "__main__":
    main()
