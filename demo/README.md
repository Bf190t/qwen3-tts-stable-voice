# 示范音频 / Demo audio

全部由千问 Qwen3-TTS 自带的说话人"福叔"（uncle_fu）合成，没有用任何真人录音。第 1–3 个文件念的是仓库里的原创测试小说 `skills/stable-tts-voice/assets/test_passage.txt`，按一个读书 app 的分段切成 9 段。参考录音念的是一句讲历史书的开场白，意思取自 1890 年的公版书《海权对历史的影响》开头。
All audio is Qwen3-TTS's preset speaker uncle_fu; no human voice was used. Files 1–3 read the original test story; the reference paraphrases the opening line of Mahan's public-domain 1890 book.

| 文件 / File | 做法 / Setup | 测出来 / Measured |
|---|---|---|
| `reference-uncle_fu.wav` | 参考录音（1.7B CustomVoice 念的一句，9.4 s，24 kHz 单声道） / the reference | 133 Hz |
| `1-customvoice-same-sentence-6-seeds.m4a` | 1.7B CustomVoice，同一句换 6 个种子 / one sentence, six seeds | 110–189 Hz |
| `2-before-customvoice-parts-5-7.m4a` | 1.7B CustomVoice + 讲书人提示 + 温度 0.6，第 5–7 段 / parts 5–7 | 第 5、6 段声纹偏（对参考 0.62），第 7 段高 4.4 个半音 / parts 5–6 sound like someone else, part 7 is 4.4 semitones higher |
| `3-after-base-xvec-parts-5-7.m4a` | 0.6B Base 只学音色，参考同上，第 5–7 段 / timbre-only clone, parts 5–7 | 0 段偏，全篇音高 133–158 Hz / no part off |

只学音色念得比原来快约 40%：它只取参考的声纹，节奏是模型自己的。app 里可以用保音高的倍速调慢。
The clone reads about 40 % faster: it takes only the timbre, the rhythm is the model's own.
