#!/usr/bin/env python
"""比赛用 · 死时间传输曲线出图脚本.

用途
----
读取 Phase 3 验证输出 phase03_validation.json,绘制"观测计数率 vs 真实
计数率"传输曲线:仿真散点(非延长型/延长型)叠加解析理论曲线,直观证明
仿真与理论在 13 个标准计数率点完全吻合。

依赖
----
- 仅需 numpy 与 matplotlib,不依赖 he3sim 包,可在任意环境运行。
- 数据来源为 he3sim validate-physics 生成的 phase03_validation.json。

先生成数据 (若还没有)
---------------------
conda run -n signal_create he3sim validate-physics `
    -c configs/demo_minimal.yaml `
    -o outputs/manual_review/phase03/validation

再出图
------
python make_transmission_curve.py `
    --json outputs/manual_review/phase03/validation/phase03_validation.json `
    --output outputs/gallery/dead_time_transmission_curve.png

说明
----
JSON 结构 (来自 phase3_validation.py Phase3ValidationReport.to_dict):
  {
    "seed": int,
    "dead_time_duration_s": float,
    "points": [
      {"true_rate_cps": ..., "mode": "nonparalyzable"/"paralyzable",
       "observed_rate_cps": ..., "theoretical_rate_cps": ...,
       "relative_error": ..., "passed": bool}, ...
    ],
    "passed": bool, ...
  }
所有参数为 synthetic_demo 演示配置,图注中明确标注。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

CHINESE_FONTS = {
    "Microsoft YaHei",
    "SimHei",
    "Source Han Sans SC",
    "Noto Sans CJK SC",
    "WenQuanYi Zen Hei",
    "PingFang SC",
    "Arial Unicode MS",
}


def configure_chinese_font() -> None:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in CHINESE_FONTS:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            break
    plt.rcParams["axes.unicode_minus"] = False


def _cn(zh: str, en: str) -> str:
    fonts = plt.rcParams.get("font.sans-serif", [])
    if fonts and fonts[0] in CHINESE_FONTS:
        return zh
    return en


def load_points(json_path: Path) -> tuple[dict, float, bool, int]:
    """读取 JSON,按模式聚合点。返回 (按模式分组的点, 死时间, 是否全通过, seed)。"""
    with json_path.open("r", encoding="utf-8") as stream:
        report = json.load(stream)
    points = report.get("points", [])
    if not points:
        raise ValueError("JSON 中没有 points 字段或为空,请确认这是 validate-physics 的输出")

    grouped: dict[str, list[dict]] = {}
    for point in points:
        mode = point["mode"]
        grouped.setdefault(mode, []).append(point)
    for mode in grouped:
        grouped[mode].sort(key=lambda p: p["true_rate_cps"])

    dead_time_s = float(report.get("dead_time_duration_s", float("nan")))
    passed = bool(report.get("passed", False))
    seed = int(report.get("seed", -1))
    return grouped, dead_time_s, passed, seed


def draw_transmission_curve(
    grouped: dict[str, list[dict]],
    *,
    dead_time_s: float,
    all_passed: bool,
    seed: int,
    output_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 7.0), constrained_layout=True)

    # 理想参考线:观测率 = 真实率 (无死时间损失)
    all_rates = sorted({p["true_rate_cps"] for pts in grouped.values() for p in pts})
    rate_min, rate_max = min(all_rates), max(all_rates)
    ideal_x = np.logspace(np.log10(rate_min), np.log10(rate_max), 200)
    ax.plot(
        ideal_x,
        ideal_x,
        linestyle=":",
        color="#999999",
        linewidth=1.3,
        label=_cn("理想无损 (观测=真实)", "Ideal lossless (obs = true)"),
    )

    style = {
        "nonparalyzable": {
            "color": "#1f4e79",
            "marker": "o",
            "zh": "非延长型 · 仿真",
            "en": "Non-paralyzable · sim",
            "zh_theory": "非延长型 · 理论",
            "en_theory": "Non-paralyzable · theory",
        },
        "paralyzable": {
            "color": "#c0504d",
            "marker": "s",
            "zh": "延长型 · 仿真",
            "en": "Paralyzable · sim",
            "zh_theory": "延长型 · 理论",
            "en_theory": "Paralyzable · theory",
        },
    }

    for mode, pts in grouped.items():
        s = style.get(mode, style["nonparalyzable"])
        true_rates = np.array([p["true_rate_cps"] for p in pts], dtype=float)
        observed = np.array([p["observed_rate_cps"] for p in pts], dtype=float)
        theory = np.array([p["theoretical_rate_cps"] for p in pts], dtype=float)

        # 理论曲线(平滑):用同样公式在密网格上画线更好看,这里直接连点即可
        order = np.argsort(true_rates)
        ax.plot(
            true_rates[order],
            theory[order],
            color=s["color"],
            linewidth=1.8,
            alpha=0.55,
            label=_cn(s["zh_theory"], s["en_theory"]),
        )
        ax.scatter(
            true_rates,
            observed,
            color=s["color"],
            marker=s["marker"],
            s=55,
            edgecolors="white",
            linewidths=0.8,
            zorder=5,
            label=_cn(s["zh"], s["en"]),
        )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(_cn("真实计数率 (cps)", "True count rate (cps)"), fontsize=12)
    ax.set_ylabel(_cn("观测计数率 (cps)", "Observed count rate (cps)"), fontsize=12)

    n_points = sum(len(v) for v in grouped.values())
    n_rates = len(all_rates)
    result_zh = "全部通过" if all_passed else "存在未通过点"
    result_en = "all passed" if all_passed else "some failed"
    ax.set_title(
        _cn(
            f"死时间传输曲线:仿真与解析理论在 {n_rates} 个计数率点{result_zh}",
            f"Dead-time transmission: sim vs theory at {n_rates} rates ({result_en})",
        ),
        fontsize=14,
        fontweight="bold",
    )
    ax.grid(True, which="both", alpha=0.25, linewidth=0.5)
    ax.legend(fontsize=10, loc="upper left", framealpha=0.9)

    footer = _cn(
        f"死时间 τ = {dead_time_s:g} s(synthetic_demo)· seed={seed} · "
        f"共 {n_points} 个验证点 · 演示配置,非真实设备标定",
        f"dead time τ = {dead_time_s:g} s (synthetic_demo) · seed={seed} · "
        f"{n_points} points · not a calibrated device",
    )
    fig.text(0.5, -0.02, footer, ha="center", fontsize=8.5, color="#555555")

    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[传输曲线图] 已保存: {output_path}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="死时间传输曲线出图脚本")
    parser.add_argument(
        "--json",
        type=Path,
        required=True,
        help="phase03_validation.json 路径",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/gallery/dead_time_transmission_curve.png"),
        help="输出 PNG 路径",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.json.exists():
        print(
            f"找不到 JSON: {args.json}\n请先运行: he3sim validate-physics -c <config> -o <dir>",
            file=sys.stderr,
        )
        return 2
    configure_chinese_font()
    grouped, dead_time_s, all_passed, seed = load_points(args.json)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    draw_transmission_curve(
        grouped,
        dead_time_s=dead_time_s,
        all_passed=all_passed,
        seed=seed,
        output_path=args.output,
    )
    print("\n完成。传输曲线图已生成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
