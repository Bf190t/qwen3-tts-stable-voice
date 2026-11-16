# 稳定朗读音色 · Qwen3-TTS Stable Voice

**让本地 Qwen3-TTS 念长文时，从第一段到最后一段都是同一个人的声音。**

一个给 Claude Code / Codex 用的 skill，也可以不用 AI 助手、直接跑里面的脚本。免费、本地、离线，不需要任何云端 API。

> 💡 **创意和流程：[@Bf190t](https://github.com/Bf190t)**
> 作者在给自己的桌宠做朗读功能时发现：把声音定成一段参考录音、让 Base 模型"只学音色"，就能治好 Qwen3-TTS 的声音漂移。后来把它整理成可以反复使用的流程，在 Claude Code 协助下写好脚本和测量方法。欢迎使用、修改、转载，请保留署名（MIT 许可）。

> ⚠️ **只在中文（普通话）上测过。** Qwen3-TTS 本身支持英语、日语等多种语言，但这套流程里的门槛数字、文字清理规则、测试文本、背景声纹都是按中文定的，**英文和其他语言的效果没有测过**。测过的朋友欢迎在 Issues 里分享数字。

[English README](README.en.md)

---

## 遇到过这种情况吗

用开源的 Qwen3-TTS 给讲解视频、科普视频、有声书、AI 读书配音，一段一段地生成，结果：

- 这一段是低沉的大叔，下一段变成了青年音；
- 同一句话只换种子念 6 遍，音高从 110 Hz 到 189 Hz 都有（差 9 个半音）；
- 在提示词里写"全程同一位讲述人、保持音高"，或者把 temperature 调低，都压不住，有时反而更糟。

**原因**：Qwen3-TTS 的内置说话人（CustomVoice）每次生成都会重新"抽"一次嗓子；按文字描述造声音（VoiceDesign）则每次都重新造一个人。分段越多，越容易听出来。

## 思路（一句话）

**把声音定成一段参考录音，之后每一段都用 0.6B Base 模型照这段录音的声纹念（只学音色，不学节奏）。**

配套还有：

| 工具 | 做什么 |
|---|---|
| 测量脚本 | 每段的音高、声纹相似度、语速、错字率，自动标出"偏了"的段 |
| 声纹守门 | 一个可以复制进 app 的打分类：每段念完对参考打分，低于 0.7 就让 app 换个种子重念一次、留更像的那版（单独运行时只给 WAV 打分） |
| 中文试听页 | 几种做法并排对比，偏了的段标黄，最后用耳朵定 |
| 参考实现 | 一个已经上线的朗读进程：流式、可取消、第一声约 0.12 秒 |

## 实测效果

中文，Apple Silicon Mac mini 16 GB。同一篇约 1150 字的原创小说，切成 9 段：

| 做法 | 偏了的段 | 每段音高范围 | 内存峰值 | 生成速度 |
|---|---|---|---|---|
| 千问自带说话人"福叔"（1.7B CustomVoice + 讲书人提示 + 温度 0.6） | **3 / 9** | 106–153 Hz | 10.5 GB | 实时的 2.8 倍 |
| 照福叔的一段参考录音，0.6B Base 只学音色 | **0 / 9** | 133–158 Hz | 7.5 GB* | 实时的 3.4 倍 |

\* 整段一次生成时的峰值。改成流式生成（每块约 0.32 秒）后，桌宠的声音实测约 3.3 GB；福叔这一轮没测流式。这一轮在 mlx-audio 0.6.4 里跑，锁文件里是 0.6.5（桌宠测的版本）。

接进实际的读书 app、再加上声纹守门后，两章 66 段没有一段偏。其中女声 Serena 那章整体比参考低 2.1 个半音，略超过脚本 ±2 的提醒线，试听后接受。所有数字和测法见 [cases.md](skills/stable-tts-voice/references/cases.md)。

### 听一听

在 [`demo/`](demo/) 文件夹里（点开文件后选 "View raw" 或下载播放）：

| 文件 | 内容 |
|---|---|
| `reference-uncle_fu.wav` | 参考录音：福叔念的一句话，9 秒 |
| `1-customvoice-same-sentence-6-seeds.m4a` | 原来的做法：同一句话只换种子，念 6 遍，嗓子明显不一样 |
| `2-before-customvoice-parts-5-7.m4a` | 原来的做法念第 5–7 段：第 5、6 段像换了个人，第 7 段音高突然抬高 |
| `3-after-base-xvec-parts-5-7.m4a` | 只学音色念同样的第 5–7 段：一直是同一个人 |

所有声音都是千问 Qwen3-TTS 自带的说话人"福叔"（uncle_fu）合成的，没有用任何真人录音。第 1–3 个文件念的是原创测试小说；参考录音念的是一句讲历史书的开场白，意思取自 1890 年出版的公版书《海权对历史的影响》的开头。

## 需要什么

- Apple Silicon Mac（M1 及以后），macOS 14 以上（算错字率的本机识别要 macOS 26）
- Python 3.12 + mlx-audio 0.6.5（仓库里有带哈希的锁文件）
- Qwen3-TTS 0.6B Base 8bit 模型，约 2 GB（脚本会按固定版本下载，逐个文件核对 sha256）
- 建议 16 GB 内存
- 当 skill 用时：Claude Code 或 Codex

Windows、Linux、Intel Mac 跑不了这些脚本（基于 Apple 的 MLX）。但"定参考录音 + Base 只学音色"这个思路和平台无关，可以搬到 PyTorch 版的 Qwen3-TTS 上。

## 安装

**方式一：Claude Code 插件**（在 Claude Code 里输入）

```
/plugin marketplace add Bf190t/qwen3-tts-stable-voice
/plugin install stable-tts-voice@bf190t-voice
```

**方式二：克隆后用脚本装**

```bash
git clone https://github.com/Bf190t/qwen3-tts-stable-voice.git
cd qwen3-tts-stable-voice
./install.sh            # 装到 Claude Code（~/.claude/skills/）
./install.sh --codex    # 装到 Codex（~/.codex/skills/）
```

已经装过旧版时，`install.sh` 会先把旧的移到 `~/.claude/skill-backups/`（Codex 是 `~/.codex/skill-backups/`）备份，不删除、不覆盖。

**方式三：手动**：把 `skills/stable-tts-voice/` 整个文件夹复制到 `~/.claude/skills/` 或 `~/.codex/skills/`。

装好以后直接用中文说就行，例如：

- "我的 app 朗读声音忽高忽低，帮我看看为什么"
- "给我的讲解视频配音定一个稳定的声音"
- "用我自己的录音克隆一个读书的声音"

AI 会一步一步来：先量出现状，再做试听页让你用耳朵挑，下载模型前会先问你。

## 不用 AI 助手，直接跑脚本

```bash
cd skills/stable-tts-voice
M="$HOME/tts-models/Qwen3-TTS-12Hz-0.6B-Base-8bit"

# 1. 下载模型（约 2 GB，固定版本，逐个文件核对）
python3 scripts/get_base_model.py "$M"

# 2. 建 Python 环境（要先装好 Python 3.12）
python3.12 -m venv ~/tts-venv
~/tts-venv/bin/pip install --only-binary=:all: --require-hashes --no-deps -r assets/tts-requirements.lock.txt

# 3. 照参考录音"只学音色"，把测试小说一段段念出来
~/tts-venv/bin/python -B scripts/render_passage.py --model "$M" --mode xvec \
    --ref ../../demo/reference-uncle_fu.wav --text assets/test_passage.txt --label "只学音色" --out runs/clone

# 4. 测每段稳不稳，做试听页
~/tts-venv/bin/python -B scripts/measure_voice.py runs/clone --ref ../../demo/reference-uncle_fu.wav --encoder "$M"
python3 scripts/listening_page.py runs/clone --out 试听/对比.html --title "音色对比"
open 试听/对比.html
```

这条命令按默认的 80 字切段，会切成 17 段，数字和上面表格（9 段）不会一模一样。参考录音换成你自己有权使用的录音即可：一两句平静的话，5–12 秒，没有噪音和长停顿。完整流程（挑参考、几种克隆方式对比、接进 app、验收）见 [SKILL.md](skills/stable-tts-voice/SKILL.md)，朗读进程的注意事项见 [runtime.md](skills/stable-tts-voice/references/runtime.md)。

## 仓库里有什么

```
skills/stable-tts-voice/
├── SKILL.md                 给 AI 助手看的完整流程（中文）
├── scripts/                 生成、测量、试听页、声纹守门、模型下载
├── references/
│   ├── runtime.md           朗读进程清单，每条对应一个踩过的坑
│   ├── cases.md             实测数字
│   └── desktop-companion/   参考实现（朗读进程 + 带校验的安装）
├── assets/                  背景声纹、模型清单、依赖锁文件、测试小说
└── agents/openai.yaml       Codex 用的界面信息
demo/                        前后对比的示范音频
```

## 声音的使用规矩

- **只克隆你有权使用的声音**：你自己的、已获授权的、模型自带的说话人，或者按文字描述新造的声音。
- 不要拿真人、演员、配音演员、游戏或动画角色的录音去克隆；描述新声音时，也不要写他们的名字。
- 做成视频或公开发布时，按平台规定标注"AI 合成声音"。

## 致谢和许可

- **创意和流程**：[@Bf190t](https://github.com/Bf190t)
- **脚本和文档**：在 [Claude Code](https://claude.com/claude-code) 协助下编写和实测
- [Qwen3-TTS](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base)：阿里巴巴通义千问团队，Apache-2.0。本仓库**不包含**模型权重，脚本从 Hugging Face 的 [mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit) 下载固定版本。
- [mlx-audio](https://github.com/Blaizzy/mlx-audio)（MIT）和 Apple 的 [MLX](https://github.com/ml-explore/mlx)（MIT）
- 本仓库：[MIT 许可](LICENSE)

本项目和阿里巴巴、Anthropic、OpenAI、Apple 都没有隶属关系。
