"""Generate an offline, self-contained HTML dashboard from an outputs directory."""

# ruff: noqa: E501

import base64
import datetime
import json
import sys
from pathlib import Path


def _img_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def generate_offline_dashboard(
    output_dir: str | Path, out_path: str | Path | None = None
) -> Path | None:
    root = Path(output_dir)
    if not root.exists():
        print(f"目录不存在: {root}")
        return

    sections: list[str] = []
    for d in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not d.is_dir() or d.name.startswith("_"):
            continue

        pngs = sorted(d.glob("*.png"))
        jsons = list(d.glob("*.json"))
        if not pngs and not jsons:
            continue

        section = f"<div class='section'><h2>{d.name}</h2>"

        # JSON metrics
        for jf in jsons[:1]:
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                result = data.get("result", "?")
                chash = data.get("config_hash", "")[:16]
                section += (
                    f"<div class='meta'>"
                    f"<span class='badge {'pass' if result == 'passed' else 'fail'}'>"
                    f"{result}</span>"
                    f"<span class='hash'>hash: {chash}...</span>"
                    f"</div>"
                )
                if "metrics" in data:
                    section += "<table><tr><th>指标</th><th>值</th></tr>"
                    for k, v in data["metrics"].items():
                        if isinstance(v, (int, float, bool, str)):
                            section += f"<tr><td>{k}</td><td>{v}</td></tr>"
                    section += "</table>"
            except Exception:
                pass

        # Embedded PNGs
        for png in pngs:
            try:
                b64 = _img_to_b64(png)
                section += (
                    f"<div class='figure'>"
                    f"<img src='data:image/png;base64,{b64}' "
                    f"alt='{png.name}' loading='lazy'>"
                    f"<p>{png.name}</p></div>"
                )
            except Exception:
                section += f"<div class='figure'><p>无法加载: {png.name}</p></div>"

        section += "</div>"
        sections.append(section)

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>He-3 脉冲信号模拟 — 离线报告面板</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Microsoft YaHei",SimHei,sans-serif;background:#f5f7fa;color:#2f3437;line-height:1.6}}
header{{background:linear-gradient(135deg,#1a3a4a,#244a68);color:#fff;padding:32px 24px;text-align:center}}
header h1{{font-size:1.6em;font-weight:600}}
header p{{opacity:0.75;margin-top:8px;font-size:0.95em}}
.container{{max-width:1100px;margin:0 auto;padding:24px 16px}}
.section{{background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.06);padding:24px;margin-bottom:24px}}
.section h2{{color:#244a68;margin-bottom:16px;font-size:1.25em}}
.meta{{display:flex;gap:12px;align-items:center;margin-bottom:14px}}
.badge{{padding:3px 12px;border-radius:12px;font-size:0.85em;font-weight:700}}
.badge.pass{{background:#d4edda;color:#155724}}
.badge.fail{{background:#f8d7da;color:#721c24}}
.hash{{font-family:monospace;font-size:0.85em;color:#8a9298}}
table{{border-collapse:collapse;width:100%;margin-bottom:20px}}
th,td{{border:1px solid #d9dee2;padding:8px 12px;text-align:left;font-size:0.9em}}
th{{background:#eef3f6;font-weight:600}}
.figure{{margin:20px 0}}
.figure img{{width:100%;height:auto;border:1px solid #d9dee2;border-radius:6px}}
.figure p{{font-size:0.85em;color:#8a9298;margin-top:6px}}
footer{{text-align:center;padding:32px;color:#8a9298;font-size:0.85em}}
footer a{{color:#356b9a}}
</style>
</head>
<body>
<header>
<h1>⚛ He-3 脉冲信号模拟系统</h1>
<p>零功率反应堆中子噪声数字孪生 · 离线报告面板</p>
<p style="margin-top:4px">生成时间: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
</header>
<div class="container">
{"".join(sections) if sections else '<div class="section"><p>未找到分析结果。请先运行 he3sim 命令生成报告。输出目录: ' + str(root) + "</p></div>"}
</div>
<footer>
<p>synthetic_demo 演示参数，非实测设备标定 | <a href="https://github.com/rosejuiceyk/signal_create">GitHub</a></p>
</footer>
</body>
</html>"""

    out = Path(out_path) if out_path else root / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"离线面板: {out} ({len(sections)} 个结果目录)")
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "outputs"
    generate_offline_dashboard(path)
