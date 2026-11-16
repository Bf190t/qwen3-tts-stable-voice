# stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
"""Makes candidate reference recordings: one sentence, several voices or seeds. The user picks one by ear.

  # a preset speaker under several seeds (find the take that sounds most like "the" voice)
  PY -B make_candidates.py --model CUSTOMVOICE --mode custom --speaker uncle_fu --seeds 1-8 --out cands/福叔
  # new voices from descriptions (VoiceDesign 1.7B; used once, never at reading time)
  PY -B make_candidates.py --model VOICEDESIGN --mode design --descriptions 描述.txt --seeds 1-3 --out cands/新声音

--descriptions: one voice per line, "key: description", e.g.
  d1: 四十多岁的男声，嗓音低沉温厚，语速平稳偏慢，像深夜电台里读小说的人，情绪克制。
Writes OUT/<key>-s<seed>.wav and OUT/manifest.json (same format as render_passage.py, so
measure_voice.py and listening_page.py work on it).
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import qwen_runner  # noqa: E402
from tts_text import prepare_text, token_limit  # noqa: E402
from voice_audio import trim, write_wav  # noqa: E402

DEFAULT_TEXT = {
    "chinese": "那天傍晚，雨终于停了。他推开窗，看见街对面的灯一盏一盏亮起来，心里忽然安静了许多。",
    "english": "That evening the rain finally stopped. He opened the window and watched the lights come on, one by one.",
}


def seeds(spec):
    values = []
    for piece in spec.split(","):
        if "-" in piece:
            a, b = piece.split("-"); values += range(int(a), int(b) + 1)
        elif piece:
            values.append(int(piece))
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    qwen_runner.add_arguments(parser)
    parser.add_argument("--descriptions", help="design: file with one 'key: description' per line")
    parser.add_argument("--seeds", default="1-4")
    parser.add_argument("--sentence", help="what every candidate says (default: a calm narration line, ~7 s)")
    parser.add_argument("--label")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    text = prepare_text(args.sentence or DEFAULT_TEXT[args.language], args.language)
    voices = []
    if args.mode == "design":
        if not args.descriptions:
            raise SystemExit("design needs --descriptions")
        for line in Path(args.descriptions).read_text(encoding="utf-8").splitlines():
            key, sep, description = line.partition(":") if ":" in line else line.partition("：")
            if sep and description.strip():
                voices.append((key.strip(), description.strip()))
        if not voices:
            raise SystemExit("no 'key: description' lines in --descriptions")
        args.instruct = voices[0][1]
    else:
        voices.append((args.speaker or args.mode, args.instruct))

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    runner = qwen_runner.from_arguments(args)
    rows = []
    for key, description in voices:
        if args.mode == "design":
            runner.instruct = description
        for seed in seeds(args.seeds):
            audio, gen, _, _ = runner.say(text, seed, token_limit(text))
            audio = trim(audio, runner.rate)
            name = f"{key}-s{seed}"
            write_wav(out / f"{name}.wav", audio, runner.rate)
            rows.append({"i": len(rows) + 1, "name": name, "file": f"{name}.wav", "text": text, "seed": seed,
                         "description": description, "audio_s": round(audio.size / runner.rate, 2),
                         "gen_s": round(gen, 2)})
            print(f"{name}: {rows[-1]['audio_s']}s", flush=True)
    manifest = {"label": args.label or out.name, "kind": "candidates", "model": Path(args.model).name,
                **runner.describe(), "parts": rows, "peak_gb": runner.peak_gb()}
    if args.mode == "design":
        manifest["descriptions"] = dict(voices)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {len(rows)} candidates -> {out}")


if __name__ == "__main__":
    main()
