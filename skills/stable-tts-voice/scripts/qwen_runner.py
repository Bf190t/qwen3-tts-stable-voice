# stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
"""One Qwen3-TTS setup (model + how the voice is chosen), generating one part at a time.

Modes
  custom  CustomVoice model, a preset speaker (and optional instruct; 0.6B ignores instruct)
  xvec    Base model + reference audio, speaker embedding only ("只学音色": timbre, model's own rhythm)
  icl     Base model + reference audio + its exact transcript ("学音色和节奏": timbre and rhythm)
  design  VoiceDesign model + a text description; a new person every call, so only for making
          candidates, never for reading a book
"""
from __future__ import annotations

import os
import sys
import time

sys.dont_write_bytecode = True
for _key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
    os.environ[_key] = "1"

import numpy as np  # noqa: E402

CACHE_LIMIT = 256 * 1024 * 1024   # peak ~3.3 GB instead of ~6 GB for 0.6B in the pet's tests
STREAM_INTERVAL = 0.32


class Runner:
    def __init__(self, model_path, mode, speaker=None, instruct=None, ref=None, ref_text=None,
                 language="chinese", stream=False, sampling=None):
        import mlx.core as mx
        from mlx_audio.tts.utils import load_model
        self.mx = mx
        mx.set_cache_limit(CACHE_LIMIT)
        started = time.monotonic()
        self.model = load_model(model_path)
        self.load_seconds = round(time.monotonic() - started, 2)
        self.rate = int(self.model.sample_rate)
        self.kind = getattr(getattr(self.model, "config", None), "tts_model_type", "")
        self.mode, self.speaker, self.instruct = mode, speaker, instruct
        self.language, self.stream = language, stream
        self.sampling = {k: v for k, v in (sampling or {}).items() if v is not None}
        self.ref_text = ref_text
        self.reference = None
        if mode in ("xvec", "icl"):
            if self.kind != "base":
                raise SystemExit(f"{mode} needs a Base model; this one is '{self.kind}'")
            if not ref:
                raise SystemExit(f"{mode} needs --ref")
            if mode == "icl" and not ref_text:
                raise SystemExit("icl needs --ref-text (the exact words spoken in the reference)")
            from mlx_audio.utils import load_audio
            self.reference = load_audio(ref, sample_rate=self.rate)
        elif mode == "custom":
            speakers = [s.lower() for s in self.model.get_supported_speakers()]
            if not speakers:
                raise SystemExit(f"custom needs a CustomVoice model; this one is '{self.kind}'")
            if (speaker or "").lower() not in speakers:
                raise SystemExit(f"unknown speaker {speaker!r}; this model has: {', '.join(speakers)}")
        elif mode == "design":
            if self.kind != "voice_design" or not instruct:
                raise SystemExit("design needs a VoiceDesign model and --instruct")

    def _calls(self, text, max_tokens):
        lang_name = self.language.capitalize()
        common = dict(max_tokens=max_tokens, **self.sampling)
        if self.stream:
            common.update(stream=True, streaming_interval=STREAM_INTERVAL)
        if self.mode == "custom":
            options = dict(text=text, speaker=self.speaker, language=lang_name, **common)
            if self.instruct:
                options["instruct"] = self.instruct
            return self.model.generate_custom_voice(**options)
        if self.mode == "design":
            return self.model.generate_voice_design(text=text, instruct=self.instruct, language=lang_name, **common)
        options = dict(text=text, ref_audio=self.reference, lang_code=self.language, **common)
        if self.mode == "icl":
            options["ref_text"] = self.ref_text
        return self.model.generate(**options)

    def say(self, text, seed, max_tokens):
        """Audio (float32 mono at self.rate), generation seconds, seconds to the first chunk, and
        whether generation ran into max_tokens (mlx-audio leaves EOS out of token_count, so a count
        that reaches max_tokens means the model never finished on its own)."""
        self.mx.random.seed(seed)
        started, first, chunks, tokens = time.monotonic(), None, [], 0
        generator = self._calls(text, max_tokens)
        try:
            for result in generator:
                tokens += int(getattr(result, "token_count", 0) or 0)
                audio = np.asarray(result.audio, dtype=np.float32).reshape(-1)
                if audio.size:
                    if first is None:
                        first = time.monotonic() - started
                    chunks.append(audio)
        finally:
            close = getattr(generator, "close", None)
            if close:
                close()
        self.mx.clear_cache()
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        return audio, time.monotonic() - started, first, tokens >= max_tokens

    def describe(self):
        import importlib.metadata as meta
        try:
            version = meta.version("mlx-audio")
        except meta.PackageNotFoundError:
            version = None
        return {"mode": self.mode, "model_type": self.kind, "speaker": self.speaker, "instruct": self.instruct,
                "ref_text": self.ref_text, "language": self.language, "stream": self.stream,
                "sampling": self.sampling, "sample_rate": self.rate, "mlx_audio": version,
                "load_seconds": self.load_seconds}

    def peak_gb(self):
        return round(self.mx.get_peak_memory() / 1e9, 2)


def add_arguments(parser):
    parser.add_argument("--model", required=True, help="local model folder")
    parser.add_argument("--mode", required=True, choices=["custom", "xvec", "icl", "design"])
    parser.add_argument("--speaker", help="custom: preset speaker, e.g. uncle_fu")
    parser.add_argument("--instruct", help="custom: style instruction (1.7B only); design: voice description")
    parser.add_argument("--ref", help="xvec/icl: reference WAV (24 kHz mono; see prep_reference.py)")
    parser.add_argument("--ref-text", help="icl: the exact words spoken in the reference")
    parser.add_argument("--language", default="chinese", choices=["chinese", "english"])
    parser.add_argument("--stream", action="store_true", help="generate in streamed chunks like a live reader")
    for name in ("temperature", "top_p", "repetition_penalty"):
        parser.add_argument("--" + name.replace("_", "-"), type=float)
    parser.add_argument("--top-k", type=int)


def from_arguments(args):
    sampling = {"temperature": args.temperature, "top_p": args.top_p, "top_k": args.top_k,
                "repetition_penalty": args.repetition_penalty}
    return Runner(args.model, args.mode, args.speaker, args.instruct, args.ref, args.ref_text,
                  args.language, args.stream, sampling)
