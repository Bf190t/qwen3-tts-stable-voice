# Qwen3-TTS Stable Voice

**Keep a local Qwen3-TTS narrator sounding like the same person from the first paragraph to the last.**

A skill for Claude Code and Codex. You can also run its scripts by hand. Everything runs locally and offline, with no cloud API.

> 💡 **Idea and workflow: [@Bf190t](https://github.com/Bf190t)**
> While adding a reading voice to a desktop pet, the author found that fixing the voice as one reference recording and letting the Base model clone *only the timbre* cures Qwen3-TTS voice drift. The scripts and measurements were then written up with help from Claude Code. Use, change and share freely; please keep the credit (MIT license).

> ⚠️ **Tested with Mandarin Chinese only.** Qwen3-TTS supports English, Japanese and other languages, but every threshold, text-cleanup rule, test passage and the speaker background here were tuned on Chinese. **English and other languages are untested.** If you try them, please share your numbers in Issues.

The skill itself (SKILL.md, the listening page, most docs) is written in Chinese. Claude and Codex read it fine and will answer in your language.

[中文说明](README.md)

---

## The problem

Read a long text with open-source Qwen3-TTS one part at a time (explainer videos, audiobooks, a reading app), and:

- one part is a deep middle-aged voice, the next a young man;
- the same sentence read with six different seeds ranges from 110 Hz to 189 Hz (9 semitones);
- prompts like "the same narrator throughout, keep the pitch" or a lower temperature do not fix it, and sometimes make it worse.

**Why**: CustomVoice preset speakers re-sample the voice on every call, and VoiceDesign builds a new person from the description on every call. The more parts, the more you hear it.

## The idea, in one line

**Fix the voice as one reference recording, then read every part with the 0.6B Base model cloning that recording's speaker embedding (timbre only, not rhythm).**

Plus:

| Tool | What it does |
|---|---|
| Measurement | Pitch, speaker similarity, speaking rate and error rate for every part; flags the parts that drifted |
| Voice guard | A scoring class you copy into your app: it scores each part against the reference, and below 0.7 your app re-reads once with another seed and keeps the closer take (run on its own it only scores WAVs) |
| Listening page | Side-by-side comparison of several setups, drifted parts highlighted; you decide by ear |
| Reference runtime | A shipped TTS worker: streaming, cancellable, first sound in about 0.12 s |

## Results

Mandarin Chinese, Apple Silicon Mac mini with 16 GB. One original story of about 1,150 characters, read in 9 parts:

| Setup | Parts off | Pitch range | Peak memory | Speed |
|---|---|---|---|---|
| Preset speaker uncle_fu (1.7B CustomVoice + narrator prompt + temperature 0.6) | **3 / 9** | 106–153 Hz | 10.5 GB | 2.8× real time |
| 0.6B Base, timbre only, cloning one uncle_fu reference | **0 / 9** | 133–158 Hz | 7.5 GB* | 3.4× real time |

\* Peak when each part is generated in one go. With streaming (about 0.32 s per chunk) the desktop pet's voice measured about 3.3 GB; streaming was not measured in this uncle_fu round. This round ran on mlx-audio 0.6.4; the lock file pins 0.6.5 (the version the desktop pet was measured with).

In a real reading app with the voice guard on, two chapters (66 parts) had no part off. The female voice Serena's chapter was 2.1 semitones below its reference overall, just past the script's ±2 warning line, and was accepted by ear. Numbers and method: [cases.md](skills/stable-tts-voice/references/cases.md) (Chinese).

### Listen

In [`demo/`](demo/) (open a file, then "View raw" or download):

| File | What |
|---|---|
| `reference-uncle_fu.wav` | The reference: one sentence by uncle_fu, 9 s |
| `1-customvoice-same-sentence-6-seeds.m4a` | The old way: one sentence, six seeds, clearly different voices |
| `2-before-customvoice-parts-5-7.m4a` | The old way, parts 5–7: parts 5 and 6 sound like someone else, part 7 jumps up in pitch |
| `3-after-base-xvec-parts-5-7.m4a` | Timbre-only cloning, the same parts: one person throughout |

Every voice is Qwen3-TTS's own preset speaker uncle_fu; no human recording was used. Files 1–3 read the original test story; the reference reads one narration line for a history book, paraphrasing the opening of Mahan's public-domain 1890 book *The Influence of Sea Power upon History*.

## Requirements

- Apple Silicon Mac (M1 or later), macOS 14+ (on-device recognition for error rates needs macOS 26)
- Python 3.12 and mlx-audio 0.6.5 (a hash-pinned lock file is included)
- Qwen3-TTS 0.6B Base 8bit, about 2 GB (the script downloads a pinned revision and checks every file's sha256)
- 16 GB of memory recommended
- As a skill: Claude Code or Codex

The scripts need Apple's MLX, so they do not run on Windows, Linux or Intel Macs. The idea itself (a fixed reference + Base timbre-only cloning) carries over to the PyTorch Qwen3-TTS.

## Install

**Claude Code plugin** (type in Claude Code):

```
/plugin marketplace add Bf190t/qwen3-tts-stable-voice
/plugin install stable-tts-voice@bf190t-voice
```

**Clone and run the installer**:

```bash
git clone https://github.com/Bf190t/qwen3-tts-stable-voice.git
cd qwen3-tts-stable-voice
./install.sh            # Claude Code (~/.claude/skills/)
./install.sh --codex    # Codex (~/.codex/skills/)
```

An existing copy is moved to `~/.claude/skill-backups/` (or `~/.codex/skill-backups/`) first, never deleted or overwritten.

**By hand**: copy the `skills/stable-tts-voice/` folder into `~/.claude/skills/` or `~/.codex/skills/`.

Then just ask, for example: "My app's reading voice keeps changing. Find out why." The assistant measures first, builds a listening page for you to choose by ear, and asks before downloading any model.

## Run the scripts without an assistant

```bash
cd skills/stable-tts-voice
M="$HOME/tts-models/Qwen3-TTS-12Hz-0.6B-Base-8bit"

# 1. Download the model (about 2 GB, pinned, every file checked)
python3 scripts/get_base_model.py "$M"

# 2. Python environment (install Python 3.12 first)
python3.12 -m venv ~/tts-venv
~/tts-venv/bin/pip install --only-binary=:all: --require-hashes --no-deps -r assets/tts-requirements.lock.txt

# 3. Read the test story part by part, cloning only the reference's timbre
~/tts-venv/bin/python -B scripts/render_passage.py --model "$M" --mode xvec \
    --ref ../../demo/reference-uncle_fu.wav --text assets/test_passage.txt --label "timbre only" --out runs/clone

# 4. Measure every part and build the listening page
~/tts-venv/bin/python -B scripts/measure_voice.py runs/clone --ref ../../demo/reference-uncle_fu.wav --encoder "$M"
python3 scripts/listening_page.py runs/clone --out listen/compare.html --title "Voice check"
open listen/compare.html
```

This command uses the default 80-character split (17 parts), so the numbers will not match the 9-part table exactly. Use any reference you have the right to use: one or two calm sentences, 5–12 seconds, no noise or long pauses. The full workflow is in [SKILL.md](skills/stable-tts-voice/SKILL.md); the runtime checklist is in [runtime.md](skills/stable-tts-voice/references/runtime.md) (both in Chinese).

## Using voices responsibly

- **Only clone voices you have the right to use**: your own, one you have permission for, a model's preset speakers, or a new voice designed from a text description.
- Do not clone real people, actors, voice actors, or game or anime characters, and do not name them in voice descriptions.
- When publishing, label AI-generated voices as your platform requires.

## Credits and license

- **Idea and workflow**: [@Bf190t](https://github.com/Bf190t)
- **Scripts and docs**: written and measured with [Claude Code](https://claude.com/claude-code)
- [Qwen3-TTS](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base) by the Qwen team at Alibaba, Apache-2.0. No model weights are included; the script downloads a pinned revision of [mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit).
- [mlx-audio](https://github.com/Blaizzy/mlx-audio) (MIT) and Apple's [MLX](https://github.com/ml-explore/mlx) (MIT)
- This repository: [MIT](LICENSE)

Not affiliated with Alibaba, Anthropic, OpenAI or Apple.
