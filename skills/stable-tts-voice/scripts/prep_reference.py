# stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
"""Turns the chosen take into the app's reference voice: 24 kHz mono 16-bit WAV, silence trimmed,
peak at -1 dBFS, plus a JSON note saying where it came from.

  PY -B prep_reference.py cands/福叔/uncle_fu-s3.wav app/voices/narrator.wav --name 福叔 \
      --source "1.7B CustomVoice uncle_fu, seed 3, 2026-11-12, chosen by ear" [--text "the exact words"]

PY is the app's TTS python (numpy is needed; the system python3 has none). Any format afconvert reads
is accepted, but start from the original WAV, not a compressed preview. A good reference is one or
two calm sentences, 5–12 seconds, no music or noise, no long pauses,
spoken the way the app should read (narration for a book reader, not an excited line).
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from voice_audio import f0_median, level_db, read_wav, trim, write_wav  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source"); parser.add_argument("target")
    parser.add_argument("--name", required=True); parser.add_argument("--source-note", "--source", dest="note", default="")
    parser.add_argument("--text", help="exact words spoken (needed only for icl cloning)")
    args = parser.parse_args()
    audio = trim(read_wav(args.source))
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if peak <= 0:
        raise SystemExit("the recording is silent")
    audio = audio * (10 ** (-1 / 20) / peak)
    target = Path(args.target); target.parent.mkdir(parents=True, exist_ok=True)
    write_wav(target, audio)
    seconds = audio.size / 24000
    note = {"name": args.name, "source": args.note, "text": args.text, "seconds": round(seconds, 2),
            "f0_median_hz": f0_median(audio), "level_db": level_db(audio), "format": "24 kHz mono 16-bit WAV"}
    target.with_suffix(".json").write_text(json.dumps(note, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(note, ensure_ascii=False))
    if not 4.0 <= seconds <= 15.0:
        print(f"注意：参考录音 {seconds:.1f} 秒，最好在 5–12 秒之间", file=sys.stderr)


if __name__ == "__main__":
    main()
