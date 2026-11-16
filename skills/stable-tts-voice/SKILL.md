---
name: stable-tts-voice
description: 让本地 Qwen3-TTS（mlx-audio / MLX，Apple Silicon Mac）朗读的声音在长文本里始终是同一个人的完整流程：量出漂移 → 把声音定成一段参考录音 → 用 0.6B Base 照参考"只学音色"、按段生成 → 用脚本测每段的音高、声纹、语速、错字，做中文试听页让用户挑 → 落到 app 的朗读进程并验收。凡是 AI 读书、有声书、讲解或科普视频配音、语音助手、整点报时的声音不稳（忽高忽低、大叔音和青年音来回换、每段像换了个人、念着念着变声），要换声音、设计新声音、克隆声音、给 app 接本地 TTS 时，都用这个 skill，即使用户没说"skill"。目前只在中文（普通话）上测过。Also use for any Qwen3-TTS voice drift, voice consistency, voice cloning or voice design work on a Mac (tested with Mandarin Chinese only).
license: MIT
compatibility: Apple Silicon Mac, macOS 14+, Python 3.12, mlx-audio 0.6.5, Qwen3-TTS 0.6B Base 8bit (about 2 GB). transcribe.swift needs macOS 26. Tested with Mandarin Chinese only.
metadata:
  version: "1.2.1"
  updated: "2026-11-17"
  author: "Bf190t (idea and workflow)"
  homepage: "https://github.com/Bf190t/qwen3-tts-stable-voice"
---

# 稳定朗读音色（Qwen3-TTS · mlx-audio）

> 创意和流程：[Bf190t](https://github.com/Bf190t)。脚本和文档在 Claude Code 协助下整理，MIT 许可。
>
> **语言范围**：目前只在中文（普通话）上测过。Qwen3-TTS 本身支持多种语言，但这里的门槛数字、文字清理规则、测试文本、背景声纹都是按中文定的。用户要做英文或其他语言时，先说清楚"没测过"，按第 1 步先量一遍再下结论，门槛可能要重新校。

这套流程来自作者的桌宠项目（开源版 [Desktop Companion](https://github.com/Bf190t/mac-desktop-companion)）的朗读功能。先把声音设计出来，定成一段固定的参考录音，之后每一段都照着这段录音的声纹念，所以整篇听起来都是同一个人。

作者自用的一个 AI 读书 app 有同样的问题："大叔音、青年音来回换"。2026-11-12 用本 skill 的脚本测过：
- 按这个 app 自己的分段和参数，原来的做法（1.7B CustomVoice 福叔，加了讲书人提示、温度 0.6）9 段里有 3 段偏；
- 照参考录音"只学音色"后，没有一段偏，而且更快、更省内存；
- 同一天接进 app，加上声纹守门后，两章 66 段没有一段偏（女声那章整体比参考低 2.1 个半音，略超 ±2 的提醒线，试听后接受）。

数字见 `references/cases.md`。

## 先弄懂为什么会漂

Qwen3-TTS 三种模型决定"像谁"的方式不一样：

| 模型 | 声音从哪来 | 长文本里稳不稳 |
|---|---|---|
| CustomVoice（自带说话人，如 uncle_fu 福叔） | 每个说话人只有一个学到的标记，其余全靠每次采样 | **会漂**。每段都重新抽一次嗓子；同一句话只换种子，音高就从 110 Hz 跳到 189 Hz |
| VoiceDesign（按文字描述造声音） | 每次调用都按描述重新造一个人 | **最不稳**。只能用来做候选，不能拿来朗读 |
| Base + 参考录音 | 从参考录音里算出一个声纹向量，每段都用同一个 | **稳**。桌宠用的就是这个 |

Base 有两种克隆方式：
- **只学音色**（`xvec`）：只给参考录音。音色像，节奏是模型自己的，轻、快、稳，是默认首选。
- **学音色和节奏**（`icl`）：再给参考录音的逐字原文。音色更像，但会连语气、节奏、瑕疵一起学，可能把嗓子整体抬高；读书 app 测出来高了 2.3 个半音。桌宠试听时，有一个样本用 icl 出了问题。

所以核心只有一句：**把声音定成一段录音，之后每段都照着它念。** 其余步骤都是为了挑出好的参考，证明它真的稳了，而且没有带来新问题。

## 和用户一起做的方式

- 用中文、用口语说话。必须提到术语时顺手解释一句，例如"半音：钢琴上相邻两个键的音高差""声纹相似度：两段声音像不像同一个人，1 最像"。
- 一步一步来。每一步给出中文试听页加几个关键数字，让用户用耳朵定，声音的选择权在用户。
- 下载模型前先说清楚名字、大小、用途，等用户同意。1.7B Base 约 2.5–3 GB，VoiceDesign 1.7B 约 4 GB。
- 生成或测量要跑好几分钟时，先告诉用户大概要多久、几点完成。
- 先看项目里有没有进度表、修改前备份和自己的测试。没让改 app 时只读不动，实验都在草稿目录里做。
- **只克隆有权使用的声音**：用户本人的声音、已获授权的声音、模型自带的说话人，或按文字描述新造的声音。不要照真人、演员、配音演员或游戏、动画角色的录音克隆；新造声音时，描述里也不要写某个真人或角色的名字。

## 流程

先设好这几个变量。脚本一律用 app 自己 TTS 环境里的 python 加 `-B` 运行，不往系统里装任何东西；`python3`（Command Line Tools 自带的 3.9）没有 numpy，只能跑 `listening_page.py`、`tts_text.py` 和 `get_base_model.py`。

```bash
S=<这个 SKILL.md 所在的目录>/scripts     # Claude Code 一般是 ~/.claude/skills/stable-tts-voice/scripts，Codex 是 ~/.codex/skills/…
PY="<app 的 TTS 环境>/bin/python"         # 例：$HOME/Library/Application Support/<App>/tts/venv/bin/python
ENC="<0.6B Base 8bit 模型目录>"            # 声纹编码器，见下面"准备环境"
SCRATCH=<本会话的草稿目录>/voice-test; mkdir -p "$SCRATCH"; cd "$SCRATCH" # 实验都放这里，不放进 app
```

macOS 默认的 shell 是 zsh，通配符没匹配到会直接报错，所以下面的命令都把目录一个个写出来。

### 准备环境（换了电脑、或 app 还没有 TTS 环境时）

- **命令行工具**：`python3` 和 `swiftc` 都来自 Xcode Command Line Tools。新 Mac 上一敲就会弹安装框；先问用户，再装：`xcode-select --install`。
- **模型**：先在本机找现成的 0.6B Base 8bit。各 app 给它起的目录名不一样，比如有的叫 `Qwen3-TTS-12Hz-0.6B-Base-8bit`，Desktop Companion 叫 `model`。所以按里面的 `speech_tokenizer` 子目录找，再逐个核对：
  ```bash
  find "$HOME/Library/Application Support" -maxdepth 6 -type d -name speech_tokenizer 2>/dev/null
  python3 $S/get_base_model.py --check "<上面找到的目录的上一级>"     # 全部对上的才能当 $ENC
  ```
  本机没有的话，先问用户（名字、约 2 GB、用来给声音打分和只学音色朗读），同意后再下载。它只从 Hugging Face 取固定版本，每个文件都核对 sha256，断了再运行会接着下，不会覆盖别的 app 的文件：
  ```bash
  python3 $S/get_base_model.py "<放模型的目录>/Qwen3-TTS-12Hz-0.6B-Base-8bit"
  ```
- **Python 环境**：优先用 app 自己的 TTS venv。没有的话先问用户，再建一个只给这套脚本用的环境。
  - `assets/tts-requirements.lock.txt` 是带哈希的锁文件：mlx-audio 0.6.5，为 Python 3.12、Apple Silicon、macOS 14 以上编译。
  - 它由 `assets/tts-requirements.in` 编出来，重编的命令写在锁文件开头，里面的文件名要换成这两个。
  - 要先有 Python 3.12，系统不带。可以从 python.org 下官方安装包，或者用户已有 Homebrew 时 `brew install python@3.12`，有 uv 时 `uv python install 3.12`。
  - 装好后约 470 MB（用几乎同一份锁文件装的环境实测）：
  ```bash
  python3.12 -m venv "<环境目录>"
  "<环境目录>/bin/pip" install --only-binary=:all: --require-hashes --no-deps -r "$S/../assets/tts-requirements.lock.txt"
  ```
- **本机识别**（算错字率，可选）：要 macOS 26 和 `swiftc`。没有中文识别模型时，`transcribe` 会提示；先问用户，再运行 `"$SCRATCH/transcribe" --install zh_CN`，由系统下载。

### 0. 摸清现状

- 读 app 的配置（例如 `engine.json`），找到 python、模型目录和模型 revision。
- 在朗读进程里搜 `generate_custom_voice`、`generate(`、`generate_voice_design`、`seed`、`instruct`、`temperature`、`ref_audio`，弄清楚现在用哪种模型、怎么切段、种子怎么设。
- 看内存（`sysctl hw.memsize`）。16 GB 的机器一次只跑一个模型。不流式时，1.7B 念 150 字左右的长段，峰值约 10.5 GB。
- 测声纹用的编码器只在 Base 模型里有。没有 Base 模型就只能测音高、语速和错字，下载要先问用户。

### 1. 量出现状（先有数字再动手）

**要和 app 完全一致**：把 app 的风格提示（instruct）、采样参数、种子、分段都照搬过来，否则测到的不是用户听到的。

举例：app 的参数写在它的朗读模块里，分段由它自己的某个函数完成（下面写作 `<分段模块>.<分段函数>`，按实际情况改，返回值的格式也要照实际改）：

```bash
# 用 app 自己的分段函数，把测试文字切成一行一段（只读导入 app 的代码）
python3 -B -c "import sys; sys.path.insert(0,'<app 的代码目录>'); from <分段模块> import <分段函数> as split; \
t=open('$S/../assets/test_passage.txt',encoding='utf-8').read(); \
print('\n'.join(p.replace('\n','') for p in split(t)))" > segments.txt
"$PY" -B $S/render_passage.py --model <现在的模型> --mode custom --speaker uncle_fu \
    --instruct "<app 里的风格提示>" --temperature 0.6 --top-k 40 --top-p 0.9 --repetition-penalty 1.05 \
    --seed 82041 --text segments.txt --lines --raw --label "现在的做法" --out runs/A
```

- `assets/test_passage.txt` 是原创的约 1150 字小说，有对话、引号、省略号和钟点。按上面那个 app 的分段切成 9 段，大多 110–155 字；按 80 字切则是 17 段。
- `--raw` 表示原样送字，适用于 app 自己不做文字清理的情况。
- 最好再拿 app 里一章真书测一次。

### 2. 定一段参考声音

参考录音有三个来源：
1. **从现有声音里挑一条**：用户喜欢现在的内置声音（比如福叔），只是嫌它漂。
   ```bash
   "$PY" -B $S/make_candidates.py --model <CustomVoice> --mode custom --speaker uncle_fu \
       --instruct "<app 里的风格提示>" --temperature 0.6 --seeds 1-8 --out cands/福叔
   ```
   同一句念 8 遍。参数和 app 一致，念出来才是用户平时听到的那个福叔。在试听页里按音高从低到高排好，让用户挑最像"它本来样子"的那条。
2. **按描述新造**：用 VoiceDesign 1.7B，写 2–3 种描述，每种 3 个种子。
   ```bash
   "$PY" -B $S/make_candidates.py --model <VoiceDesign> --mode design --descriptions 描述.txt --seeds 1-3 --out cands/新声音
   ```
   描述要写具体：年龄、音高、音色、语速、情绪，但不要写真人或角色的名字。例：`d1: 四十多岁的男声，嗓音低沉温厚，语速平稳偏慢，像深夜电台里读小说的人，情绪克制。`
3. **用户自己提供的录音**：只在用户明确有权使用时才用（本人的声音，或已获授权）。

让用户挑之前，先测候选、做试听页。这时还没有参考，所以不加 `--ref`：
```bash
"$PY" -B $S/measure_voice.py cands/福叔 --encoder "$ENC"
python3 $S/listening_page.py cands/福叔 --out 试听/候选.html --title "挑一条福叔"
open 试听/候选.html        # 用户习惯用某个浏览器时：open -a "<浏览器名>" …
```

选定后，从候选的原始 WAV（不要用试听页里压缩过的 m4a）做成正式参考，旁边会生成一个写来历的 JSON：
```bash
"$PY" -B $S/prep_reference.py cands/福叔/uncle_fu-s3.wav voices/narrator.wav --name 福叔 --source "…，谁在哪天选的"
# 第 5 步改 app 时，再把 voices/ 里的录音和 JSON 放进 app
```

好的参考是一两句平静的话，5–12 秒，没有噪音和长停顿，语气就是 app 该有的语气：读书就选叙述，不选激动的台词。

### 3. 用几种克隆方式各念一遍

同一篇文字、同样的种子规则：

| 做法 | 命令要点 | 什么时候试 |
|---|---|---|
| 现在 | app 现在的参数 | 当基准 |
| 只学音色 · 0.6B | `--mode xvec --ref 参考.wav` | 默认首选，又快又省内存 |
| 学音色和节奏 · 0.6B | `--mode icl --ref 参考.wav --ref-text "逐字原文"` | 只学音色的音色不够像时 |
| 1.7B Base（xvec / icl） | 换模型目录 | 0.6B 都不够像时；先问用户能不能下载 |

`--ref-text` 必须和录音逐字一致。可以先用 `transcribe` 识别一遍再人工校对：识别把「海权」听成了「海泉」。

### 4. 测量和试听

```bash
swiftc -O $S/transcribe.swift -o "$SCRATCH/transcribe"              # 编译一次，要 macOS 26
for r in runs/A runs/B runs/D; do "$SCRATCH/transcribe" "$r"; done     # 可选：算错字率
"$PY" -B $S/measure_voice.py runs/A runs/B runs/D --ref 参考.wav --encoder "$ENC"
python3 $S/listening_page.py runs/A runs/B runs/D --out 试听/音色对比.html --title "…" --intro "…" --note "…"
open 试听/音色对比.html
```

- `--encoder` 只是借 Base 模型里的声纹编码器打分，不生成声音。要统一用 0.6B Base，因为 `assets/speaker_background.json` 是给它的 1024 维编码器做的。
- 不同参考的对比要分开跑 measure，每次只给一个 `--ref`。
- 试听页把候选放在最后，按音高排列，不标"偏了"。

脚本按下面的标准标出偏了的段（门槛已用桌宠和读书 app 的中文实测数据校过），给用户讲结果时也用这些话。最后以耳朵为准：

| 看什么 | 稳的样子 | 偏了 |
|---|---|---|
| 单段音高 | 和整篇中位相差 3.5 个半音以内（正常朗读的起伏） | 超过 4 个半音，听起来像换了年纪 |
| 声纹相似度（去掉共同成分后，1 最像） | 每段对整篇平均 0.90–0.97 | 比中位低 0.08 以上（有参考时对参考算），像换了个人 |
| 整篇比参考 | ±2 个半音以内（最好 ±1） | 超过 2 个半音，克隆把嗓子整体抬高或压低了 |
| 像参考（对参考的声纹相似度） | 每段 0.7 以上，整篇中位 0.75 以上（只学音色实测 0.81–0.89） | 某段低于 0.7 就算偏；整篇中位低于 0.75 会标"不太像参考" |
| 语速 | 各段相差 25% 以内 | 忽快忽慢 |
| 错字率 | 每段一般 0–10% | 超过 15%：漏读、重复、乱念 |
| 撞到时长上限 | 0 | 有就是念跑了 |
| 速度、内存 | 比实时快（RTF < 1）；流式时 0.6B 约 3.3 GB | 朗读追不上播放 |

- 同一段在几种做法里一起偏低或偏高，是那段内容本身的语调，不算漂移。
- 音高用自相关法估计：同一个声音之间比较很可靠，不同声音的绝对值只当参考。
- 这些门槛只在中文上校过。别的语言先照常量一遍，把"正常朗读"的起伏范围看清楚再判断。

### 5. 落到 app 里

照 `references/runtime.md` 的清单改朗读进程。完整的参考实现在 `references/desktop-companion/tts_worker.py`（流式、可取消、每段重设种子、父进程看门狗），带校验的安装做法见同目录的 `install.py`。最小改动：
- 模型换成 Base；
- 启动时用 `load_audio` 把参考录音加载一次；
- 每段调用 `model.generate(text=…, ref_audio=参考, lang_code="chinese", max_tokens=…)`，每段前重设同一个种子；
- 新 app 的文字处理和切段用 `tts_text.py`。已有 app 保留自己的分段（朗读进度和缓存都靠段号），只补上文字清理那几条；
- 设置 `mx.set_cache_limit(256 MB)`（要配合流式才能明显省内存）；
- 把参考录音的 sha256 加进朗读缓存的键和进程指纹，换参考时旧缓存才会失效、进程才会重启；
- 安装脚本固定模型 revision 并校验哈希，配置文件记录每个声音的参考录音路径和 sha256；
- 参考录音和它的 JSON 跟 app 一起打包；
- 加声纹守门：每段念完用 `scripts/voice_guard.py` 的 `VoiceGuard` 对参考打分，低于 0.7 就换种子重念一次，留更像的那版。这个类可以整段复制进 app，但一定要连同 `assets/speaker_background.json` 一起复制，并用绝对路径传给它。文件不在时它会直接报错，不会悄悄放行：没有这个背景，完全不同的两个人也能打出 0.9。

要第一声更快时，再上流式和取消。改完跑项目自己的测试。

### 6. 验收

- 拿 app 里一章真书（30 段以上），用 app 自己的分段写成一行一段，再用改好后的参数跑 `render_passage.py --lines`（加 `transcribe`、`measure_voice`）。
  - 要求：没有偏了的段，每段像参考 0.7 以上、整篇中位 0.75 以上，整篇比参考在 ±2 个半音以内，错字率不比原来差，速度和内存达标。
  - app 的朗读缓存通常按哈希命名、没有段号，不适合直接拿来测。
- 让用户亲耳听一段，并在 app 里试暂停、翻页、切换声音、读完重开。
- 有整点报时或固定提示音的，用同一个参考预先录好，播放时不临时生成。
- 做成视频或公开发布的，提醒用户按平台规定标注"AI 合成声音"。

### 7. 记下来

- 参考录音旁的 JSON 写清楚：模型和 revision、描述或说话人、种子、原句、谁在哪天怎么选的。
- 结论和数字写进项目的进度表或说明文件。
- 有记忆系统就记一条：这个 app 用哪段参考，为什么这样选。

## 脚本速查（都在 `scripts/`）

| 脚本 | 作用 | 需要 |
|---|---|---|
| `render_passage.py` | 按 app 的方式一段段念一篇，存 `part-XX.wav` 和 `manifest.json` | app 的 TTS venv |
| `make_candidates.py` | 同一句话 × 多个种子或多种描述，生成候选参考 | 同上 |
| `prep_reference.py` | 把选中的那条做成正式参考（24 kHz 单声道、去静音、−1 dB），附来历 JSON | numpy |
| `measure_voice.py` | 测音高、声纹相似度、语速、音量、错字率，标出偏了的段，写 `measure.json` | numpy；声纹要 `--encoder` |
| `transcribe.swift` | 用 macOS 26 本机识别把每段转成文字（`asr.tsv`）；`--install zh_CN` 装识别模型 | swiftc |
| `listening_page.py` | 生成中文试听页：汇总表、每段并排对比、偏了的段标黄 | afconvert |
| `make_background.py` | 换了编码器时重做 `assets/speaker_background.json` | Base 模型 |
| `voice_guard.py` | 声纹守门：给一段声音对参考打分，低于 0.7 就该重念；类可复制进 app，也能单独给 WAV 打分 | numpy + Base 模型 |
| `get_base_model.py` | 下载或核对固定版本的 0.6B Base 8bit（逐个文件 sha256） | 系统 python3 + curl |
| `tts_text.py` | 文字预处理、切段、时长上限，可直接复制进 app | 标准库 |
| `voice_audio.py` | 读写 WAV、裁静音、音高、音量 | numpy |

其他文件：
- `references/runtime.md`：朗读进程的完整清单，每条都对应一个踩过的坑。
- `references/cases.md`：桌宠和读书 app 的实测数字。
- `references/desktop-companion/`：参考实现，MIT 许可，只读不跑。
- `assets/`：
  - `speaker_background.json`：背景声纹平均；
  - `base_model_manifest.json`：模型文件清单；
  - `tts-requirements.lock.txt` / `tts-requirements.in`：Python 依赖锁文件和它的来源；
  - `test_passage.txt`：测试文字。
