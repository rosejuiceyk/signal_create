#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""比赛用 · 计数率演化画廊出图脚本.

用途
----
固定随机种子,在同一采样率与观察时间下,批量生成若干个真实计数率工况的
连续波形,并绘制成一张适合投影/答辩的"计数率演化画廊"图,以及一张
高计数率"裁剪前堆积 vs ADC 饱和"对比图。

依赖
----
- 必须在项目 signal_create 环境、项目根目录 (含 pyproject.toml) 下运行。
- 复用 he3sim.app.web_backend.generate_interactive_waveform,不复制物理核心。

运行示例 (PowerShell)
--------------------
conda run -n signal_create python make_gallery.py `
    --base-config configs/demo_minimal.yaml `
    --output-root outputs/gallery `
    --sample-rate-msps 100 `
    --duration-ms 0.05 `
    --seed 20260714

说明
----
- 画廊默认工况为 10 / 1e3 / 1e5 / 1e7 cps,可用 --rates 覆盖。
- 观察时间需同时满足采样点上限与预期事件上限;脚本会对每个工况自动
  收紧到该工况允许的最大观察时间,避免高计数率工况因事件数超限而失败。
- 所有参数均为 synthetic_demo 演示配置,图注中会明确标注,不得解释为
  真实设备标定结果。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import h5py  # type: ignore[import-untyped]
import numpy as np

import matplotlib

matplotlib.use("Agg")  # 无显示环境安全后端
import matplotlib.pyplot as plt
from matplotlib import font_manager

# ---- 复用项目后端(不复制物理核心) ---------------------------------------
try:
    from he3sim.app.web_backend import (
        InteractiveWaveformRequest,
        generate_interactive_waveform,
        maximum_interactive_duration,
    )
except ImportError as exc:  # pragma: no cover - 环境未安装 he3sim 时的清晰提示
    print(
        "无法导入 he3sim.app.web_backend。请确认:\n"
        "  1. 已在 signal_create 环境中;\n"
        "  2. 当前目录为项目根目录 (含 pyproject.toml、src/he3sim);\n"
        "  3. 已执行 pip install -e .\n"
        f"原始错误: {exc}",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


DEFAULT_RATES_CPS = (1.0e3, 1.0e4, 1.0e5, 1.0e7)
MSPS_TO_HZ = 1.0e6
DEFAULT_TARGET_EVENTS_PER_PANEL = 8.0


# ---- 中文字体处理 --------------------------------------------------------
def configure_chinese_font() -> None:
    """尽力启用中文字体;失败时回退英文标签由 LABELS_EN 兜底。"""
    candidates = [
        "Microsoft YaHei",
        "SimHei",
        "Source Han Sans SC",
        "Noto Sans CJK SC",
        "WenQuanYi Zen Hei",
        "PingFang SC",
        "Arial Unicode MS",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return
    # 未找到中文字体:保持默认,后续用英文标签,避免出现方块乱码
    plt.rcParams["axes.unicode_minus"] = False


def _cn(zh: str, en: str) -> str:
    """根据是否有可用中文字体返回中文或英文标签。"""
    fonts = plt.rcParams.get("font.sans-serif", [])
    chinese_fonts = {
        "Microsoft YaHei",
        "SimHei",
        "Source Han Sans SC",
        "Noto Sans CJK SC",
        "WenQuanYi Zen Hei",
        "PingFang SC",
        "Arial Unicode MS",
    }
    if fonts and fonts[0] in chinese_fonts:
        return zh
    return en


# ---- 数据结构 ------------------------------------------------------------
@dataclass(frozen=True)
class PanelData:
    """一个工况面板所需的绘图数据。"""

    true_rate_cps: float
    duration_s: float
    sample_rate_hz: float
    times_s: np.ndarray
    preclip_V: np.ndarray
    analog_V: np.ndarray
    adc_codes: np.ndarray
    saturation: np.ndarray
    actual_event_count: int
    renderer: str
    config_hash: str
    target_events: float
    window_limited: bool


def _fmt_rate(rate_cps: float) -> str:
    """人类友好的计数率标签,如 10 cps / 1e3 cps / 1e7 cps。"""
    if rate_cps >= 1.0e3:
        exponent = int(round(np.log10(rate_cps)))
        if abs(rate_cps - 10**exponent) < 1e-6 * rate_cps:
            return f"1e{exponent} cps"
    return f"{rate_cps:g} cps"


def generate_panel(
    rate_cps: float,
    *,
    base_config: Path,
    output_root: Path,
    sample_rate_hz: float,
    target_events: float,
    seed: int,
    max_points_to_plot: int,
) -> PanelData:
    """为单个计数率生成波形并读取绘图所需数组。

    方案 A:观察时间由"目标显示事件数"反推,使每格都恰好显示若干个脉冲,
    从稀疏孤立脉冲到完全堆积形成清晰演化。若反推窗口超过采样点/事件安全
    上限,则收紧到该工况允许的最大窗口并标记 window_limited。
    """
    # 目标窗口:让期望事件数约等于 target_events
    desired_duration_s = target_events / rate_cps
    # 该工况允许的最大安全窗口(采样点上限与事件上限的较小者)
    limit = maximum_interactive_duration(rate_cps, sample_rate_hz)
    duration_s = min(desired_duration_s, limit.maximum_duration_s)
    window_limited = desired_duration_s > limit.maximum_duration_s

    request = InteractiveWaveformRequest(
        true_rate_cps=rate_cps,
        sample_rate_hz=sample_rate_hz,
        duration_s=duration_s,
        seed=seed,
    )
    result = generate_interactive_waveform(
        request,
        base_config_path=base_config,
        output_root=output_root,
    )

    with h5py.File(result.waveform_path, "r") as handle:
        n_total = int(handle["blocks/analog_samples"].shape[0])
        # 为绘图限制点数(高采样率下几十万点直接绘制既慢又糊)。
        # 均匀抽取而非只取前段,保证整窗演化都可见。
        if n_total > max_points_to_plot:
            idx = np.linspace(0, n_total - 1, max_points_to_plot).astype(np.int64)
        else:
            idx = np.arange(n_total, dtype=np.int64)
        preclip = np.asarray(
            handle["blocks/preclip_analog_samples"][:][idx], dtype=np.float64
        )
        analog = np.asarray(handle["blocks/analog_samples"][:][idx], dtype=np.float64)
        adc = np.asarray(handle["blocks/adc_samples"][:][idx], dtype=np.float64)
        sat = np.asarray(handle["blocks/saturation_mask"][:][idx], dtype=bool)

    times_s = idx.astype(np.float64) / sample_rate_hz
    return PanelData(
        true_rate_cps=rate_cps,
        duration_s=duration_s,
        sample_rate_hz=sample_rate_hz,
        times_s=times_s,
        preclip_V=preclip,
        analog_V=analog,
        adc_codes=adc,
        saturation=sat,
        actual_event_count=result.actual_event_count,
        renderer=result.renderer,
        config_hash=result.config_hash,
        target_events=target_events,
        window_limited=window_limited,
    )


def draw_gallery(
    panels: list[PanelData],
    *,
    output_path: Path,
    seed: int,
) -> None:
    """绘制计数率演化画廊图 (每工况一行,显示裁剪前电压)。

    方案 A:每格观察时间不同,故横轴各自独立,并按窗口长短自动选择
    µs 或 ms 单位。标题显示真实计数率、实际事件数、窗口时长;若窗口
    因资源上限被收紧,附加"窗口受限"提示。
    """
    n = len(panels)
    fig, axes = plt.subplots(
        n, 1, figsize=(11, 2.6 * n + 1.2), sharex=False, constrained_layout=True
    )
    if n == 1:
        axes = [axes]

    color = "#1f4e79"
    for ax, panel in zip(axes, panels):
        # 按窗口长度自动选时间单位
        if panel.duration_s >= 1.0e-3:
            t_axis = panel.times_s * 1.0e3
            unit_zh, unit_en = "时间 (ms)", "Time (ms)"
            window_txt = f"{panel.duration_s * 1e3:.4g} ms"
        else:
            t_axis = panel.times_s * 1.0e6
            unit_zh, unit_en = "时间 (μs)", "Time (μs)"
            window_txt = f"{panel.duration_s * 1e6:.4g} μs"

        ax.plot(t_axis, panel.preclip_V, color=color, linewidth=0.6)
        ax.set_ylabel(_cn("电压 (V)", "Voltage (V)"), fontsize=11)
        ax.set_xlabel(_cn(unit_zh, unit_en), fontsize=10)

        rate_label = _fmt_rate(panel.true_rate_cps)
        limited_zh = "  ·  窗口受限" if panel.window_limited else ""
        limited_en = "  ·  window-limited" if panel.window_limited else ""
        title = _cn(
            f"真实计数率 {rate_label}   |   实际事件数 {panel.actual_event_count}   "
            f"|   观察窗口 {window_txt}{limited_zh}",
            f"True rate {rate_label}   |   events {panel.actual_event_count}   "
            f"|   window {window_txt}{limited_en}",
        )
        ax.set_title(title, fontsize=12, loc="left")
        ax.grid(True, alpha=0.25, linewidth=0.5)
        ax.margins(x=0.01)

    fig.suptitle(
        _cn(
            "He-3 探测器前放波形 · 计数率演化画廊(裁剪前模拟电压)",
            "He-3 Preamplifier Waveform · Count-Rate Evolution (pre-clip analog)",
        ),
        fontsize=15,
        fontweight="bold",
    )
    target = panels[0].target_events
    footer = _cn(
        f"每格观察窗口按目标显示约 {target:g} 个事件反推 · 固定种子 seed={seed} · "
        f"采样率 {panels[0].sample_rate_hz / 1e6:g} MS/s · 渲染后端 "
        f"{panels[0].renderer} · synthetic_demo(演示配置,非真实设备标定)",
        f"per-panel window sized for ~{target:g} events · seed={seed} · "
        f"{panels[0].sample_rate_hz / 1e6:g} MS/s · renderer "
        f"{panels[0].renderer} · synthetic_demo (not a calibrated device)",
    )
    fig.text(0.5, -0.01, footer, ha="center", fontsize=8.5, color="#555555")
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[画廊图] 已保存: {output_path}")


def draw_saturation_contrast(
    panel: PanelData,
    *,
    output_path: Path,
    seed: int,
    clip_min_v: float,
    clip_max_v: float,
    adc_bits: int,
) -> None:
    """绘制高计数率裁剪对比图。

    为保证答辩图中差异清晰，本图使用“对比图专用演示量程”对裁剪前波形
    重新执行一次可视化裁剪和 ADC 映射。该处理只影响本张图，不修改 HDF5
    中由物理后端生成的原始数据。
    """
    if not np.isfinite(clip_min_v) or not np.isfinite(clip_max_v):
        raise ValueError("裁剪上下限必须是有限数值")
    if clip_max_v <= clip_min_v:
        raise ValueError("--contrast-clip-max-v 必须大于 --contrast-clip-min-v")
    if not 2 <= adc_bits <= 32:
        raise ValueError("--contrast-adc-bits 必须在 2~32 之间")

    t_us = panel.times_s * 1.0e6

    # 对比图专用演示量程：直接由裁剪前波形得到裁剪后电压。
    clipped_v = np.clip(panel.preclip_V, clip_min_v, clip_max_v)
    sat_mask = (panel.preclip_V < clip_min_v) | (panel.preclip_V > clip_max_v)
    sat_frac = float(np.count_nonzero(sat_mask)) / max(sat_mask.size, 1)

    adc_max = float((1 << adc_bits) - 1)
    normalized = (clipped_v - clip_min_v) / (clip_max_v - clip_min_v)
    demo_adc = np.rint(np.clip(normalized, 0.0, 1.0) * adc_max)

    fig, axes = plt.subplots(
        3, 1, figsize=(11, 8.8), sharex=True, constrained_layout=True
    )

    # 两个电压面板使用相同纵轴，更直观地显示“继续上升”与“平顶”。
    y_span = max(float(np.ptp(panel.preclip_V)), clip_max_v - clip_min_v, 1e-9)
    y_low = min(float(np.min(panel.preclip_V)), clip_min_v) - 0.05 * y_span
    y_high = max(float(np.max(panel.preclip_V)), clip_max_v) + 0.05 * y_span

    # 面板 1：裁剪前模拟电压。
    axes[0].plot(t_us, panel.preclip_V, color="#1f4e79", linewidth=0.9)
    axes[0].axhline(
        clip_max_v, color="#c0504d", linestyle="--", linewidth=1.2,
        label=_cn(f"演示量程上限 {clip_max_v:g} V", f"Demo upper limit {clip_max_v:g} V"),
    )
    axes[0].fill_between(
        t_us, clip_max_v, panel.preclip_V,
        where=panel.preclip_V > clip_max_v, interpolate=True,
        color="#c0504d", alpha=0.18,
    )
    axes[0].set_ylim(y_low, y_high)
    axes[0].set_ylabel(_cn("裁剪前电压 (V)", "Pre-clip (V)"), fontsize=11)
    axes[0].set_title(
        _cn(
            "① 裁剪前：真实堆积波形仍可继续上升，虚线以上将超出量程",
            "① Pre-clip: pile-up keeps rising above the demo range",
        ),
        fontsize=12, loc="left",
    )
    axes[0].legend(loc="upper left", fontsize=9)
    axes[0].grid(True, alpha=0.25, linewidth=0.5)

    # 面板 2：裁剪后模拟电压，超过上限处形成明显平顶。
    axes[1].plot(t_us, clipped_v, color="#c0504d", linewidth=1.0)
    axes[1].axhline(clip_max_v, color="#7f0000", linestyle="--", linewidth=1.0)
    axes[1].fill_between(
        t_us, y_low, y_high, where=sat_mask, step="mid",
        color="#c0504d", alpha=0.10,
        label=_cn("发生裁剪的时间区间", "Clipped intervals"),
    )
    axes[1].set_ylim(y_low, y_high)
    axes[1].set_ylabel(_cn("裁剪后电压 (V)", "Clipped (V)"), fontsize=11)
    axes[1].set_title(
        _cn(
            f"② 裁剪后：超过 {clip_max_v:g} V 的部分被压成平顶",
            f"② Clipped: values above {clip_max_v:g} V become a flat top",
        ),
        fontsize=12, loc="left",
    )
    axes[1].legend(loc="upper left", fontsize=9)
    axes[1].grid(True, alpha=0.25, linewidth=0.5)

    # 面板 3：按同一演示量程映射到 ADC，饱和区达到满量程码。
    axes[2].plot(t_us, demo_adc, color="#4f6228", linewidth=1.0)
    axes[2].axhline(
        adc_max, color="#7f0000", linestyle="--", linewidth=1.0,
        label=_cn(f"{adc_bits} 位 ADC 满量程码 {int(adc_max)}",
                  f"{adc_bits}-bit ADC full scale {int(adc_max)}"),
    )
    axes[2].fill_between(
        t_us, 0.0, adc_max, where=sat_mask, step="mid",
        color="#c0504d", alpha=0.10,
    )
    axes[2].set_ylim(-0.03 * adc_max, 1.05 * adc_max)
    axes[2].set_ylabel(_cn("ADC 码", "ADC code"), fontsize=11)
    axes[2].set_xlabel(_cn("时间 (μs)", "Time (μs)"), fontsize=11)
    axes[2].set_title(
        _cn(
            f"③ ADC：饱和区达到满量程码，饱和采样点比例 {sat_frac * 100:.1f}%",
            f"③ ADC: saturated at full scale; {sat_frac * 100:.1f}% samples saturated",
        ),
        fontsize=12, loc="left",
    )
    axes[2].legend(loc="upper left", fontsize=9)
    axes[2].grid(True, alpha=0.25, linewidth=0.5)

    rate_label = _fmt_rate(panel.true_rate_cps)
    fig.suptitle(
        _cn(
            f"高计数率 {rate_label} · 真实堆积与量程裁剪的直观对比",
            f"High rate {rate_label} · Pile-up versus range clipping",
        ),
        fontsize=15, fontweight="bold",
    )
    footer = _cn(
        f"对比图专用演示量程 [{clip_min_v:g}, {clip_max_v:g}] V · "
        f"{adc_bits} 位 ADC · seed={seed} · 事件数 {panel.actual_event_count} · "
        f"采样率 {panel.sample_rate_hz / 1e6:g} MS/s · "
        "仅用于展示裁剪机理，不改变后端原始 HDF5 数据",
        f"demo range [{clip_min_v:g}, {clip_max_v:g}] V · {adc_bits}-bit ADC · "
        f"seed={seed} · events {panel.actual_event_count} · "
        f"{panel.sample_rate_hz / 1e6:g} MS/s · visualization only; raw HDF5 unchanged",
    )
    fig.text(0.5, -0.01, footer, ha="center", fontsize=8.5, color="#555555")
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(
        f"[饱和对比图] 已保存: {output_path} "
        f"(演示量程 {clip_min_v:g}~{clip_max_v:g} V, 饱和比例 {sat_frac * 100:.1f}%)"
    )

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="比赛用计数率演化画廊出图脚本")
    parser.add_argument(
        "--base-config",
        type=Path,
        default=Path("configs/demo_minimal.yaml"),
        help="基础演示配置 YAML (默认 configs/demo_minimal.yaml)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/gallery"),
        help="波形与图片输出根目录",
    )
    parser.add_argument(
        "--rates",
        type=float,
        nargs="+",
        default=list(DEFAULT_RATES_CPS),
        help="计数率列表 (cps),默认 1000 10000 100000 10000000",
    )
    parser.add_argument(
        "--sample-rate-msps",
        type=float,
        default=100.0,
        help="采样率 (MS/s),范围 100~250,默认 100",
    )
    parser.add_argument(
        "--target-events",
        type=float,
        default=DEFAULT_TARGET_EVENTS_PER_PANEL,
        help="每格目标显示事件数;观察窗口据此反推,默认 8",
    )
    parser.add_argument("--seed", type=int, default=20260714, help="随机种子")
    parser.add_argument(
        "--max-plot-points",
        type=int,
        default=40_000,
        help="每个面板最多绘制的采样点数 (仅影响绘图密度,不影响生成)",
    )
    parser.add_argument(
        "--contrast-clip-min-v",
        type=float,
        default=-0.02,
        help="饱和对比图专用演示量程下限 (V),默认 -0.02",
    )
    parser.add_argument(
        "--contrast-clip-max-v",
        type=float,
        default=0.20,
        help="饱和对比图专用演示量程上限 (V),默认 0.20",
    )
    parser.add_argument(
        "--contrast-adc-bits",
        type=int,
        default=16,
        help="饱和对比图使用的演示 ADC 位数,默认 16",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_chinese_font()

    sample_rate_hz = args.sample_rate_msps * MSPS_TO_HZ
    args.output_root.mkdir(parents=True, exist_ok=True)

    panels: list[PanelData] = []
    for rate in args.rates:
        print(f"[生成] 计数率 {_fmt_rate(rate)} ...")
        panel = generate_panel(
            rate,
            base_config=args.base_config,
            output_root=args.output_root,
            sample_rate_hz=sample_rate_hz,
            target_events=args.target_events,
            seed=args.seed,
            max_points_to_plot=args.max_plot_points,
        )
        panels.append(panel)
        if panel.duration_s >= 1.0e-3:
            window_txt = f"{panel.duration_s * 1e3:.4g} ms"
        else:
            window_txt = f"{panel.duration_s * 1e6:.4g} μs"
        limited = " (窗口受限)" if panel.window_limited else ""
        print(
            f"        实际事件数={panel.actual_event_count} "
            f"观察窗口={window_txt}{limited} 后端={panel.renderer}"
        )

    gallery_path = args.output_root / "gallery_count_rate_evolution.png"
    draw_gallery(panels, output_path=gallery_path, seed=args.seed)

    # 用最高计数率工况做饱和对比图
    highest = max(panels, key=lambda p: p.true_rate_cps)
    contrast_path = args.output_root / "high_rate_saturation_contrast.png"
    draw_saturation_contrast(
        highest,
        output_path=contrast_path,
        seed=args.seed,
        clip_min_v=args.contrast_clip_min_v,
        clip_max_v=args.contrast_clip_max_v,
        adc_bits=args.contrast_adc_bits,
    )

    print("\n完成。两张比赛主图已生成:")
    print(f"  1. 计数率演化画廊: {gallery_path}")
    print(f"  2. 高计数率饱和对比: {contrast_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
