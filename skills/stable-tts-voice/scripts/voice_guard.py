# stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
"""声纹守门：每段念完，看它像不像参考声音；太不像就换个种子重念一次，留更像的那版。

0.6B Base 只学音色时，偶尔有一段整段像换了个人，音高却只差 1–2 个半音，音高守门抓不住。
读书 app 实测（2026-11-12，两章 66 段）：正常段对参考 0.83–0.95，跑偏的一段 0.31，
重念后 0.84；正常段从不触发，所以几乎不增加耗时。

只配 0.6B Base（1024 维声纹编码器），而且**必须**带上 assets/speaker_background.json：
不去掉 21 个声音的共同成分，完全不同的两个人也能打出 0.9 以上，守门就失效了。所以文件不在、
维度不对时这里直接报错，不会悄悄照常运行。

VoiceGuard 这个类只用 numpy 和已经加载好的模型，可以整段复制进 app 的朗读进程，
把 speaker_background.json 一起复制过去，并用绝对路径传进来：

    from pathlib import Path
    from voice_guard import VoiceGuard, GUARD, RETRY_SEED_STEP
    guard = VoiceGuard(model, {"narrator": reference_audio},
                       background=Path(__file__).resolve().with_name("speaker_background.json"))
    audio = generate(text, seed)                      # app 自己的生成函数
    score = guard.similarity(audio, "narrator")       # 太短的段返回 None，不判断
    if score is not None and score < GUARD:           # 只重念一次
        again = generate(text, seed + RETRY_SEED_STEP)
        if guard.similarity(again, "narrator") > score:
            audio = again

也可以单独跑，给已经念好的 WAV 打分（不生成声音）：

    "$PY" -B voice_guard.py --model <0.6B Base 目录> --ref 参考.wav runs/B/part-01.wav runs/B/part-02.wav
"""
import json
import sys
from pathlib import Path

import numpy as np

GUARD = 0.7              # 对参考的相似度低于这个就重念
RETRY_SEED_STEP = 7919   # 重念用的种子 = 原种子 + 这个数（读书 app 的做法）
MIN_SECONDS = 1.5        # 太短的段声纹不可靠，不打分
BACKGROUND = Path(__file__).resolve().parent.parent / "assets" / "speaker_background.json"


class VoiceGuard:
    def __init__(self, model, references, background=BACKGROUND):
        """model：已加载的 Qwen3-TTS Base 模型；references：{声音 id: 参考录音（numpy 或 mx.array，模型采样率）}。

        background：speaker_background.json 的路径。文件不在、读不了或维度不对都会报 ValueError。
        只有明确传 None 才不用背景（分数几乎分不出人，只适合做实验）。
        """
        import mlx.core as mx
        self.mx, self.model = mx, model
        self.sample_rate = int(getattr(model, "sample_rate", 24000))
        self.mean = None
        if background is not None:
            try:
                data = json.loads(Path(background).read_text(encoding="utf-8"))
                dim = int(model.config.speaker_encoder_config.enc_dim)
                mean = np.array(data["mean"], dtype=np.float64)
            except (OSError, ValueError, KeyError, AttributeError, TypeError) as error:
                raise ValueError(f"背景声纹 {background} 读不了（{error}）。复制进 app 时要把 "
                                 "speaker_background.json 一起带上，用绝对路径传进来。") from error
            if int(data.get("dim", 0)) != dim or mean.size != dim:
                raise ValueError(f"背景声纹是 {data.get('dim')} 维，这个模型的声纹编码器是 {dim} 维。"
                                 "要用 0.6B Base，或用 make_background.py 给这个模型重做背景。")
            self.mean = mean
        self.targets = {voice: self.vector(audio) for voice, audio in references.items()}

    def vector(self, audio):
        """去掉 21 个声音共同成分后的单位声纹向量。"""
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        value = np.array(self.model.extract_speaker_embedding(self.mx.array(samples)), dtype=np.float64).reshape(-1)
        value = value / np.linalg.norm(value)
        if self.mean is not None:
            value = value - self.mean
        return value / np.linalg.norm(value)

    def similarity(self, audio, voice):
        """1 最像。太短（不到 1.5 秒）的段返回 None，表示不判断。"""
        if np.asarray(audio).size < self.sample_rate * MIN_SECONDS:
            return None
        return float(np.dot(self.vector(audio), self.targets[voice]))


def main():
    import argparse
    import os
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from voice_audio import read_wav
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
        os.environ[key] = "1"
    parser = argparse.ArgumentParser(description="给已经念好的 WAV 打声纹分（对参考录音）")
    parser.add_argument("--model", required=True, help="Qwen3-TTS 0.6B Base 模型目录")
    parser.add_argument("--ref", required=True, help="参考录音 WAV")
    parser.add_argument("--background", default=str(BACKGROUND))
    parser.add_argument("wavs", nargs="+")
    args = parser.parse_args()
    import mlx.core as mx
    from mlx_audio.tts.utils import load_model
    mx.set_cache_limit(256 * 1024 * 1024)
    model = load_model(args.model)
    if getattr(model, "speaker_encoder", None) is None:
        raise SystemExit("--model 要用 Qwen3-TTS Base 模型（只有它带声纹编码器）")
    try:
        guard = VoiceGuard(model, {"ref": read_wav(args.ref)}, args.background)
    except ValueError as error:
        raise SystemExit(str(error))
    low = skipped = 0
    for path in args.wavs:
        score = guard.similarity(read_wav(path), "ref")
        if score is None:
            skipped += 1
            print(f"   —    太短，没打分  {path}")
            continue
        low += score < GUARD
        print(f"{score:6.3f}  {'要重念' if score < GUARD else '      '}  {path}")
    print(f"共 {len(args.wavs)} 段，低于 {GUARD} 的 {low} 段" + (f"，{skipped} 段太短没打分" if skipped else ""))


if __name__ == "__main__":
    main()
