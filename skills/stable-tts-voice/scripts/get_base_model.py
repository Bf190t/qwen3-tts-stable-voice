# stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
"""下载或核对 Qwen3-TTS 0.6B Base 8bit（14 个文件，共约 2 GB）：固定版本，逐个文件核对大小和 sha256。

它是声纹打分（measure_voice --encoder、voice_guard）和"只学音色"朗读要用的模型。
文件清单在 assets/base_model_manifest.json，版本和 assets/speaker_background.json 是同一个。
下载前先问用户：说清楚名字、约 2 GB、用途。

  python3 get_base_model.py --check <已有的模型目录>     # 只核对，不下载、不改任何文件
  python3 get_base_model.py <新目录>                     # 只下载缺的文件；断了再运行一次会接着下

目录里已有、但和清单对不上的文件（比如别的 app 装的不同版本）默认不动，直接停下；
确定要换成这个固定版本，才加 --replace。只用系统自带的 python3 和 /usr/bin/curl，不需要 numpy。
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath

MANIFEST = Path(__file__).resolve().parent.parent / "assets" / "base_model_manifest.json"
MARGIN = 1_000_000_000   # 下载后磁盘至少还要剩这么多


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def size(count):
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if count >= scale:
            return f"{count / scale:.2f} {unit}" if unit == "GB" else f"{count / scale:.1f} {unit}"
    return f"{count} 字节"


def matches(path, entry):
    return path.is_file() and path.stat().st_size == entry["bytes"] and digest(path) == entry["sha256"]


def safe_name(name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith("/") or any(part in ("..", "") for part in parts):
        raise SystemExit(f"清单里有不安全的文件名：{name!r}")
    return Path(*parts)


def free_bytes(folder):
    probe = folder
    while not probe.exists():
        probe = probe.parent
    return shutil.disk_usage(probe).free


def fetch(url, partial, entry):
    """下载到 .part；能接着上次断的地方下。成功返回，失败退出并说明原因。"""
    if partial.exists() and partial.stat().st_size >= entry["bytes"]:
        if matches(partial, entry):
            return
        partial.unlink()   # 下满了却对不上：重下
    try:
        subprocess.run(["/usr/bin/curl", "--fail", "--location", "--proto", "=https", "--proto-redir", "=https",
                        "--silent", "--show-error", "--connect-timeout", "30", "--retry", "2",
                        "--speed-limit", "1024", "--speed-time", "60",   # 一分钟不到 1 KB/s 就算卡住
                        "--continue-at", "-", url, "-o", str(partial)], check=True)
    except subprocess.CalledProcessError as error:
        kept = f"已下的部分留在 {partial.name}，" if partial.exists() and partial.stat().st_size else ""
        raise SystemExit(f"下载 {entry['name']} 没成功（curl 退出码 {error.returncode}，多半是网络断了或卡住）。"
                         f"{kept}再运行一次会接着下。")
    if not matches(partial, entry):
        partial.unlink(missing_ok=True)
        raise SystemExit(f"下载的 {entry['name']} 大小或 sha256 对不上，已删掉，没有装进去。再运行一次会重下。")


def main():
    parser = argparse.ArgumentParser(description="下载或核对固定版本的 Qwen3-TTS 0.6B Base 8bit")
    parser.add_argument("folder", help="模型目录")
    parser.add_argument("--check", action="store_true", help="只核对，不下载")
    parser.add_argument("--replace", action="store_true", help="目录里已有但对不上的文件，也换成固定版本")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    folder = Path(args.folder).expanduser()
    files = manifest["files"]
    print(f"{manifest['repo']} @ {manifest['revision'][:12]}，{len(files)} 个文件，共 {size(sum(e['bytes'] for e in files))}")

    missing, conflicts = [], []
    for entry in files:
        target = folder / safe_name(entry["name"])
        if matches(target, entry):
            print(f"  对   {entry['name']}")
        elif target.exists():
            print(f"  ✗   {entry['name']}（大小或哈希不对）")
            conflicts.append(entry)
        else:
            print(f"  缺   {entry['name']}")
            missing.append(entry)
    if args.check:
        if missing or conflicts:
            raise SystemExit(f"有 {len(missing) + len(conflicts)} 个文件对不上（缺 {len(missing)}，不同 {len(conflicts)}）。")
        print(f"全部对上。模型目录：{folder}")
        return
    if conflicts and not args.replace:
        raise SystemExit(f"目录里有 {len(conflicts)} 个文件和固定版本不一样，可能是别的 app 装的别的版本，没有动它们。"
                         "换个空目录下载；确定要覆盖成这个版本，再加 --replace。")
    todo = missing + conflicts
    if not todo:
        print(f"全部对上，不用下载。模型目录：{folder}")
        return
    need = 0
    for entry in todo:
        partial = (folder / safe_name(entry["name"])).with_name(Path(entry["name"]).name + ".part")
        have = partial.stat().st_size if partial.exists() and partial.stat().st_size < entry["bytes"] else 0
        need += entry["bytes"] - have
    if free_bytes(folder) < need + MARGIN:
        raise SystemExit(f"磁盘空间不够：还要下 {size(need)}，下完至少还得剩 {size(MARGIN)}，"
                         f"现在只剩 {size(free_bytes(folder))}。")

    fetched = 0
    for entry in todo:
        target = folder / safe_name(entry["name"])
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        url = f"https://huggingface.co/{manifest['repo']}/resolve/{manifest['revision']}/{entry['name']}?download=true"
        print(f"  下载 {entry['name']}（{size(entry['bytes'])}）", flush=True)
        fetch(url, partial, entry)
        partial.replace(target)
        fetched += entry["bytes"]
    print(f"全部对上。这次下载了 {size(fetched)}。模型目录：{folder}")


if __name__ == "__main__":
    main()
