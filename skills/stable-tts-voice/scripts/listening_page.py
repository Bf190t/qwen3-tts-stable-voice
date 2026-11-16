# stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
"""Builds a Chinese listening page from measured runs, so the user can compare by ear.

  python3 listening_page.py --out 试听/音色对比.html --title 音色对比 \
      --intro "同一段文字，四种做法各念一遍。" runs/现在 runs/克隆 …

Every run needs measure.json (measure_voice.py). Audio is converted to AAC (.m4a) next to the page
in 音频/, so the page stays small. Open it with: open 试听/音色对比.html (or open -a "<browser>" …)
Runs whose manifest has kind "candidates" are shown after the passages, one grid sorted by pitch,
without "off" verdicts (candidates are meant to differ; the user picks one by ear).
"""
import argparse
import html
import json
import re
import subprocess
from pathlib import Path

E = html.escape
FLAG_TEXT = {"voice": "不太像同一个人", "rate": "语速不一样", "content": "念错字", "limited": "念跑了"}

CSS = """
:root{--bg:#f7f6f3;--card:#fff;--text:#1f1f1f;--muted:#6b6b6b;--line:#e4e2dc;--warn:#b45309;--warn-bg:#fdf1e3;--ok:#15803d;--ok-bg:#e7f6ec}
@media (prefers-color-scheme:dark){:root{--bg:#17171a;--card:#212125;--text:#ececec;--muted:#a0a0a6;--line:#34343a;--warn:#f0a35c;--warn-bg:#3a2a18;--ok:#5fd38b;--ok-bg:#183424}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 -apple-system,"PingFang SC",sans-serif}
main{max-width:1040px;margin:0 auto;padding:24px 16px 64px}h1{font-size:26px;margin:0 0 8px}h2{font-size:17px;margin:0 0 12px}
.intro{color:var(--muted);margin:0 0 20px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 16px}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
td.num{font-variant-numeric:tabular-nums}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}
.clip{border:1px solid var(--line);border-radius:10px;padding:8px 10px}.clip.off{border-color:var(--warn);background:var(--warn-bg)}
.who{font-size:13px;color:var(--muted);margin-bottom:4px}.tag{display:inline-block;font-size:12px;padding:0 6px;border-radius:6px;background:var(--warn-bg);color:var(--warn);margin:2px 4px 0 0}
.good{background:var(--ok-bg);color:var(--ok)}audio{width:100%;height:34px}.n{display:inline-block;min-width:28px;color:var(--muted)}
"""


def slug(text):
    return re.sub(r"[^\w\-]+", "-", text).strip("-") or "run"


def to_m4a(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "64000", str(src), str(dst)],
                       check=True, capture_output=True)


def tags(row):
    out = []
    if "pitch" in row["flags"]:
        out.append(f"音高偏了 {row['pitch_st']:+.1f} 半音")
    out += [FLAG_TEXT[f] for f in row["flags"] if f in FLAG_TEXT]
    return "".join(f'<span class="tag">{E(t)}</span>' for t in out)


def clip(run, row, audio_dir, page_dir, title):
    m4a = audio_dir / run["slug"] / (Path(row["file"]).stem + ".m4a")
    to_m4a(run["dir"] / row["file"], m4a)
    numbers = f"{row['f0']:.0f} Hz" + (f" · 每秒 {row['rate']} 字" if row.get("rate") else "")
    if "sim_ref" in row:
        numbers += f" · 像参考 {row['sim_ref']:.2f}"
    flagged = bool(row["flags"]) and run["kind"] != "candidates"
    return (f'<div class="clip{" off" if flagged else ""}"><div class="who">{E(title)} · {E(numbers)}</div>'
            f'<audio controls preload="none" src="{E(str(m4a.relative_to(page_dir)))}"></audio>'
            f'{tags(row) if flagged else ""}</div>')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+"); parser.add_argument("--out", required=True)
    parser.add_argument("--title", default="音色试听"); parser.add_argument("--intro", default="")
    parser.add_argument("--note", action="append", default=[], help="extra paragraph (repeatable)")
    args = parser.parse_args()
    page = Path(args.out).resolve(); page_dir = page.parent; audio_dir = page_dir / "音频"
    runs = []
    for d in args.runs:
        d = Path(d).resolve()
        measured = json.loads((d / "measure.json").read_text(encoding="utf-8"))
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8")) if (d / "manifest.json").exists() else {}
        runs.append({"dir": d, "label": measured["summary"]["label"], "summary": measured["summary"],
                     "parts": measured["parts"], "kind": manifest.get("kind"),
                     "slug": f"{len(runs) + 1:02d}-{slug(measured['summary']['label'])}"})

    rows = ""
    for run in runs:
        s = run["summary"]
        speed = f"快 {1 / s['realtime_factor']:.1f} 倍" if s.get("realtime_factor") else "—"
        if run["kind"] == "candidates":
            verdict = "候选，挑一条"
        else:
            verdict = '<span class="tag good">稳</span>' if s["steady"] else f'<span class="tag">{s["parts_off"]} 段偏了</span>'
        sim = f"{s['sim_run_median']:.2f}（最低 {s['sim_run_min']:.2f}）" if s.get("sim_run_median") is not None else "—"
        ref = f"{s['sim_ref_median']:.2f}" if "sim_ref_median" in s else "—"
        if s.get("ref_mismatch") and run["kind"] != "candidates":
            ref += '<span class="tag">不太像</span>'
        offset = f"{s['offset_from_ref_st']:+.1f}" if "offset_from_ref_st" in s else "—"
        if s.get("offset_warning"):
            offset += '<span class="tag">' + ("被抬高" if s["offset_from_ref_st"] > 0 else "被压低") + "</span>"
        rows += (f"<tr><td>{E(run['label'])}</td><td>{verdict}</td><td class=num>{s['f0_center']:.0f} Hz</td>"
                 f"<td class=num>{s['f0_min']:.0f}–{s['f0_max']:.0f}（{s['pitch_spread_st']} 半音）</td>"
                 f"<td class=num>{sim}</td><td class=num>{ref}</td><td class=num>{offset}</td>"
                 f"<td class=num>{speed}</td><td class=num>{s.get('peak_gb') or '—'} GB</td></tr>")
    summary = (f'<div class="card"><h2>一眼看结果</h2><div class="wrap"><table><tr><th>做法</th><th>结论</th><th>音高中位</th>'
               f'<th>最低–最高（跨度）</th><th>段与段像不像</th><th>像参考</th><th>比参考高/低（半音）</th><th>速度</th><th>内存峰值</th></tr>'
               f'{rows}</table></div><p class="intro">怎么看：一段的音高比整篇中位高或低 4 个半音以上，听起来就像换了年纪（正常朗读每段会自然起伏 3 个半音左右）；'
               f'「段与段像不像」和「像参考」是声纹相似度（1 最像；同一个人一般 0.8 以上，不同的人多在 0 上下），某段明显低于其他段就是嗓子变了。'
               f'半音：钢琴上相邻两个键的音高差。「比参考高/低」超过 2 个半音，说明整篇的嗓子被克隆抬高或压低了。数字只是帮你找可疑的段，最后以耳朵为准。</p></div>')

    body = ""
    candidates = [r for r in runs if r["kind"] == "candidates"]
    passages = [r for r in runs if r["kind"] != "candidates"]
    if passages:
        count = max(len(r["parts"]) for r in passages)
        for i in range(count):
            text = next((r["parts"][i]["text"] for r in passages if i < len(r["parts"]) and r["parts"][i]["text"]),
                        f"第 {i + 1} 段")
            clips = "".join(clip(r, r["parts"][i], audio_dir, page_dir, r["label"]) for r in passages if i < len(r["parts"]))
            body += f'<div class="card"><h2><span class="n">{i + 1}</span>{E(text)}</h2><div class="grid">{clips}</div></div>'
    for run in candidates:
        ordered = sorted(run["parts"], key=lambda r: r["f0"])
        clips = "".join(clip(run, row, audio_dir, page_dir, row.get("name") or f"第 {row['i']} 个") for row in ordered)
        body += f'<div class="card"><h2>{E(run["label"])}（按音高从低到高）</h2><div class="grid">{clips}</div></div>'
    notes = "".join(f'<div class="card"><p>{E(n)}</p></div>' for n in args.note)
    document = (f'<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(args.title)}</title>'
                f'<style>{CSS}</style></head><body><main><h1>{E(args.title)}</h1><p class="intro">{E(args.intro)}</p>'
                f'{summary}{notes}{body}</main></body></html>')
    page.write_text(document, encoding="utf-8")
    print(page)


if __name__ == "__main__":
    main()
