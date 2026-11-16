#!/bin/bash
# stable-tts-voice installer · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
#
# 把 skills/stable-tts-voice 复制到 Claude Code 和/或 Codex 的 skills 目录。
# Copies skills/stable-tts-voice into the Claude Code and/or Codex skills folder.
#
#   ./install.sh            Claude Code  (~/.claude/skills/stable-tts-voice)
#   ./install.sh --codex    Codex        (~/.codex/skills/stable-tts-voice)
#   ./install.sh --all      both
#
# 已有旧版时先移到 skills 目录外的 skill-backups/ 里备份，不删除、不覆盖。
# An existing copy is moved to skill-backups/ (outside the skills folder) first, never deleted.
set -euo pipefail

SOURCE="$(cd "$(dirname "$0")" && pwd)/skills/stable-tts-voice"
NAME="stable-tts-voice"

if [ ! -f "$SOURCE/SKILL.md" ]; then
    echo "找不到 $SOURCE/SKILL.md，请在仓库根目录运行。/ Run this from the repository root." >&2
    exit 1
fi

case "${1:-}" in
    ""|--claude) roots="$HOME/.claude" ;;
    --codex)     roots="$HOME/.codex" ;;
    --all)       roots="$HOME/.claude $HOME/.codex" ;;
    -h|--help)   sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "不认识的参数 / unknown option: $1  (用 / use --help)" >&2; exit 2 ;;
esac

for root in $roots; do
    dir="$root/skills"
    dest="$dir/$NAME"
    mkdir -p "$dir"
    if [ -e "$dest" ] || [ -L "$dest" ]; then
        # 备份放在 skills 目录外面，免得被当成第二个同名 skill 加载
        # keep backups outside the skills folder so they are not loaded as a second skill
        mkdir -p "$root/skill-backups"
        backup="$root/skill-backups/$NAME-$(date +%Y%m%d-%H%M%S)"
        n=1
        while [ -e "$backup" ] || [ -L "$backup" ]; do
            backup="$root/skill-backups/$NAME-$(date +%Y%m%d-%H%M%S)-$n"
            n=$((n + 1))
        done
        mv "$dest" "$backup"
        echo "旧版已备份 / previous copy moved to: $backup"
    fi
    mkdir -p "$dest"
    # 只复制 skill 本身，不带缓存和实验输出 / copy the skill only, no caches or experiment output
    (cd "$SOURCE" && tar --exclude='__pycache__' --exclude='.DS_Store' \
        --exclude='./runs' --exclude='./cands' --exclude='./试听' --exclude='./listen' --exclude='./voices' \
        -cf - .) | (cd "$dest" && tar -xf -)
    echo "已安装 / installed: $dest"
done

cat <<'MSG'

装好了。重开一个会话，直接说"我的 app 朗读声音忽高忽低，帮我看看"即可。
Done. Start a new session and ask, e.g. "My app's reading voice keeps changing. Find out why."
注意：只在中文上测过 / Note: tested with Mandarin Chinese only.
MSG
