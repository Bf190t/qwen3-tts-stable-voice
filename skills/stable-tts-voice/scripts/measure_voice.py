# stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
"""Measures how steady a voice is across the parts of one or more runs.

  PY -B measure_voice.py runs/现在 runs/克隆 --ref voice.wav --encoder BASE_MODEL_DIR

For every part: pitch (median F0), speaking rate (characters per second of speech), level, and —
with --encoder (a Qwen3-TTS *Base* model folder; use the 0.6B Base so numbers stay comparable) —
how close its speaker embedding is to the run's average voice and to --ref. Embeddings are compared
after subtracting the average of 21 different voices (assets/speaker_background.json): on that
scale different voices score about −0.15, parts of one steady voice 0.90–0.97 to their run. If RUN/asr.tsv exists (transcribe.swift), the character error
rate is added (files the recognizer failed on are skipped, not counted as errors). Parts shorter
than 1.5 s get no speaker similarity (too little audio for a stable embedding). Writes
RUN/measure.json and prints a summary.

Flags (a part is "off" when any holds):
  pitch    more than 4 semitones from the run's middle pitch (an older/younger-sounding voice;
           ordinary narration moves a part's median up to ~3.5 semitones)
  voice    speaker similarity more than 0.08 below the run's median — to --ref when given, else to
           the run's average (sounds like someone else); with --ref also any part below 0.7 to the
           reference (the same floor as voice_guard.py), so a run that is wholly another person is
           never "steady"
  rate     more than 25 % faster or slower than the run's median
  content  character error rate above 15 % (words skipped, repeated or invented)
  limited  hit the length cap (the model rambled on)
A run is "steady" when no part is off. Separately, a run whose middle pitch is more than 2 semitones
from --ref is marked (the clone moved the voice up or down), and so is a run whose median similarity
to --ref is below 0.75 (it does not sound much like the reference; xvec clones measured 0.81–0.89).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from tts_text import spoken_chars  # noqa: E402
from voice_audio import cosine, f0_median, level_db, read_wav, semitones, trim  # noqa: E402

PITCH_FLAG = 4.0      # semitones from the run's middle
SIM_DROP = 0.08       # below the run's median similarity
RATE_FLAG = 0.25      # fraction from the run's median rate
CER_FLAG = 0.15
OFFSET_FLAG = 2.0     # semitones between the whole run and --ref: the clone moved the voice up or down
MIN_EMBED_SECONDS = 1.5
REF_FLOOR = 0.7       # a part this unlike the reference is someone else (voice_guard.GUARD)
REF_MATCH_WARN = 0.75 # a whole run below this (median) does not sound much like the reference


def bare(text):
    return re.sub(r"[\s，。！？、…,.!?：:；;“”\"'—\-（）()《》]", "", text)


def cer(ref, hyp):
    r, h = bare(ref), bare(hyp)
    d = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hc in enumerate(h, 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (rc != hc)); prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


BACKGROUND = Path(__file__).resolve().parent.parent / "assets" / "speaker_background.json"


class Encoder:
    def __init__(self, path, background=BACKGROUND):
        import os
        for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
            os.environ[key] = "1"
        import mlx.core as mx
        from mlx_audio.tts.utils import load_model
        self.mx = mx
        mx.set_cache_limit(256 * 1024 * 1024)
        self.model = load_model(path)
        if getattr(self.model, "speaker_encoder", None) is None:
            raise SystemExit("--encoder must be a Qwen3-TTS Base model (it has the speaker encoder)")
        self.mean = None
        if background and Path(background).exists():
            data = json.loads(Path(background).read_text(encoding="utf-8"))
            dim = int(self.model.config.speaker_encoder_config.enc_dim)
            if data["dim"] == dim:
                self.mean = np.array(data["mean"], dtype=np.float64)
            else:
                print(f"注意：背景声纹是 {data['dim']} 维，这个编码器是 {dim} 维；相似度没去掉共同成分，"
                      "区分度会很差。请改用 0.6B Base 当 --encoder，或用 make_background.py 重做背景。", file=sys.stderr)

    def embed(self, audio):
        """Unit-length speaker embedding."""
        vector = np.array(self.model.extract_speaker_embedding(self.mx.array(audio.astype(np.float32)))).reshape(-1)
        return vector / np.linalg.norm(vector)

    def voice(self, audio):
        """Embedding with the average voice taken out (what similarities are computed on)."""
        vector = self.embed(audio)
        if self.mean is not None:
            vector = vector - self.mean
        return vector / np.linalg.norm(vector)


def load_parts(run):
    manifest_path = run / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"label": run.name, "parts": [{"i": i, "file": p.name, "text": ""}
                                                  for i, p in enumerate(sorted(run.glob("*.wav")), 1)]}
    asr = {}
    if (run / "asr.tsv").exists():
        for line in (run / "asr.tsv").read_text(encoding="utf-8").splitlines():
            name, _, text = line.partition("\t")
            if text.strip() and text.strip() != "<error>":
                asr[name] = text
    return manifest, asr


def measure_run(run, encoder=None, ref_embedding=None, ref_f0=0.0):
    manifest, asr = load_parts(run)
    rows, embeddings = [], []
    for part in manifest["parts"]:
        audio = read_wav(run / part["file"])
        speech = trim(audio)
        seconds = speech.size / 24000
        row = {"i": part["i"], "name": part.get("name"), "file": part["file"], "text": part.get("text", ""),
               "seconds": round(seconds, 2), "f0": f0_median(speech), "level_db": level_db(speech),
               "limited": bool(part.get("limited"))}
        chars = spoken_chars(row["text"])
        row["rate"] = round(chars / seconds, 2) if chars and seconds > 0.3 else None
        if part["file"] in asr and row["text"]:
            row["asr"] = asr[part["file"]]
            row["cer"] = round(cer(row["text"], asr[part["file"]]), 3)
        vector = encoder.voice(speech) if encoder and seconds >= MIN_EMBED_SECONDS else None
        embeddings.append(vector)
        if vector is not None and ref_embedding is not None:
            row["sim_ref"] = round(cosine(vector, ref_embedding), 3)
        rows.append(row)

    f0s = [r["f0"] for r in rows if r["f0"] > 0]
    center = float(np.median(f0s)) if f0s else 0.0
    valid = [v for v in embeddings if v is not None]
    centroid = np.mean(valid, axis=0) if valid else None
    for row, vector in zip(rows, embeddings):
        if vector is not None and centroid is not None:
            row["sim_run"] = round(cosine(vector, centroid), 3)
    sims = [r["sim_run"] for r in rows if "sim_run" in r]
    sim_median = float(np.median(sims)) if sims else None
    ref_sims = [r["sim_ref"] for r in rows if "sim_ref" in r]
    ref_median = float(np.median(ref_sims)) if ref_sims else None
    rates = [r["rate"] for r in rows if r["rate"]]
    rate_median = float(np.median(rates)) if rates else None

    for row in rows:
        flags = []
        row["pitch_st"] = round(semitones(row["f0"], center), 2) if row["f0"] > 0 else None
        if row["pitch_st"] is not None and abs(row["pitch_st"]) > PITCH_FLAG:
            flags.append("pitch")
        if ref_median is not None and "sim_ref" in row:
            if row["sim_ref"] < ref_median - SIM_DROP or row["sim_ref"] < REF_FLOOR:
                flags.append("voice")
        elif sim_median is not None and "sim_run" in row and row["sim_run"] < sim_median - SIM_DROP:
            flags.append("voice")
        if rate_median and row["rate"] and abs(row["rate"] / rate_median - 1) > RATE_FLAG:
            flags.append("rate")
        if row.get("cer", 0) > CER_FLAG:
            flags.append("content")
        if row["limited"]:
            flags.append("limited")
        row["flags"] = flags

    summary = {
        "label": manifest.get("label", run.name), "parts": len(rows),
        "f0_center": round(center, 1), "f0_min": min(f0s) if f0s else 0, "f0_max": max(f0s) if f0s else 0,
        "pitch_spread_st": round(semitones(max(f0s), min(f0s)), 2) if f0s else None,
        "pitch_off": sum("pitch" in r["flags"] for r in rows),
        "voice_off": sum("voice" in r["flags"] for r in rows),
        "rate_off": sum("rate" in r["flags"] for r in rows),
        "content_off": sum("content" in r["flags"] for r in rows),
        "limited": sum(r["limited"] for r in rows),
        "parts_off": sum(bool(r["flags"]) for r in rows),
        "sim_run_median": round(sim_median, 3) if sim_median is not None else None,
        "sim_run_min": min(sims) if sims else None,
        "rate_median": round(rate_median, 2) if rate_median else None,
        "realtime_factor": manifest.get("realtime_factor"), "peak_gb": manifest.get("peak_gb"),
    }
    if ref_sims:
        summary["sim_ref_median"] = round(float(np.median(ref_sims)), 3)
        summary["sim_ref_min"] = min(ref_sims)
        summary["ref_mismatch"] = summary["sim_ref_median"] < REF_MATCH_WARN
    if ref_f0:
        summary["ref_f0"] = ref_f0
        summary["offset_from_ref_st"] = round(semitones(center, ref_f0), 2)
        summary["offset_warning"] = abs(summary["offset_from_ref_st"]) > OFFSET_FLAG
    cers = [r["cer"] for r in rows if "cer" in r]
    if cers:
        summary["cer_mean"] = round(float(np.mean(cers)), 3)
    summary["steady"] = summary["parts_off"] == 0
    result = {"summary": summary, "parts": rows}
    (run / "measure.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--ref", help="the reference voice WAV, to compare every run with")
    parser.add_argument("--encoder", help="a Qwen3-TTS Base model folder, for speaker similarity")
    args = parser.parse_args()
    encoder = Encoder(args.encoder) if args.encoder else None
    ref_embedding, ref_f0 = None, 0.0
    if args.ref:
        ref = trim(read_wav(args.ref))
        ref_f0 = f0_median(ref)
        ref_embedding = encoder.voice(ref) if encoder else None
        print(f"参考录音：{ref.size / 24000:.1f} 秒，音高 {ref_f0:.0f} Hz")
    for run in args.runs:
        if not (Path(run) / "asr.tsv").exists():
            print(f"（{run} 没有 asr.tsv，跳过错字率；要算就先跑 transcribe）")
        s = measure_run(Path(run), encoder, ref_embedding, ref_f0)["summary"]
        line = (f"{s['label']}：{s['parts']} 段，音高中位 {s['f0_center']:.0f} Hz（{s['f0_min']:.0f}–{s['f0_max']:.0f}，"
                f"跨度 {s['pitch_spread_st']} 个半音），偏离的段：音高 {s['pitch_off']} / 嗓音 {s['voice_off']} / "
                f"语速 {s['rate_off']} / 内容 {s['content_off']} / 跑长 {s['limited']}")
        if s.get("sim_run_median") is not None:
            line += f"；段间相似度中位 {s['sim_run_median']}，最低 {s['sim_run_min']}"
        if "sim_ref_median" in s:
            line += f"；像参考 {s['sim_ref_median']}"
            if s.get("ref_mismatch"):
                line += "（整篇不太像参考）"
        if "offset_from_ref_st" in s:
            line += f"；比参考 {s['offset_from_ref_st']:+} 个半音"
            if s["offset_warning"]:
                line += "（整体被" + ("抬高" if s["offset_from_ref_st"] > 0 else "压低") + "了）"
        print(line + ("  → 稳" if s["steady"] else "  → 有漂移"))


if __name__ == "__main__":
    main()
