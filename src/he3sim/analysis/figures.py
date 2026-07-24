"""Reusable pure Matplotlib figures for phase validation reports."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "he3sim-matplotlib"),
)
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import numpy.typing as npt  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from he3sim.physics.chains import ChainTraceNode  # noqa: E402

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

BLUE = "#356B9A"
ORANGE = "#D9822B"
GOLD = "#B58B24"
CHARCOAL = "#2F3437"
GREY = "#8A9298"
LIGHT_GREY = "#D9DEE2"


def _new_figure(
    title: str, subtitle: str, figsize: tuple[float, float] = (9.0, 5.5)
) -> tuple[Figure, Axes]:
    """Create one consistently styled validation figure and axis."""
    figure, axis = plt.subplots(figsize=figsize)
    figure.suptitle(title, x=0.08, y=0.98, ha="left", fontsize=14, color=CHARCOAL)
    axis.set_title(subtitle, loc="left", fontsize=9, color=GREY, pad=10)
    axis.grid(True, color=LIGHT_GREY, linewidth=0.7, alpha=0.65)
    axis.spines[["top", "right"]].set_visible(False)
    return figure, axis


def phase_a_event_raster_figure(
    poisson_times_s: npt.NDArray[np.float64],
    correlated_times_s: npt.NDArray[np.float64],
    duration_s: float,
    rate_cps: float,
    k_eff: float,
    alpha_per_s: float,
) -> Figure:
    """Plot same-rate Poisson and correlated event rasters in aligned rows."""
    figure, axis = _new_figure(
        "Phase A event raster: Poisson vs correlated",
        f"Same expected rate {rate_cps:.1f} cps; k_eff={k_eff:.3f}; α={alpha_per_s:.1f} s^-1",
        (10.0, 4.2),
    )
    axis.vlines(poisson_times_s, 1.1, 1.9, color=BLUE, linewidth=1.0, label="Poisson")
    axis.vlines(correlated_times_s, 0.1, 0.9, color=ORANGE, linewidth=1.0, label="Correlated")
    axis.set_xlim(0.0, duration_s)
    axis.set_ylim(0.0, 2.0)
    axis.set_yticks([0.5, 1.5], ["Correlated", "Poisson"])
    axis.set_xlabel("Time in review window (s)")
    axis.set_ylabel("Arrival model")
    axis.text(
        0.99,
        0.98,
        f"events: {correlated_times_s.size} correlated / {poisson_times_s.size} Poisson",
        transform=axis.transAxes,
        ha="right",
        va="top",
        color=CHARCOAL,
        fontsize=9,
        bbox={"facecolor": "white", "edgecolor": LIGHT_GREY, "alpha": 0.9},
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_a_interval_distribution_figure(
    interval_centers_s: npt.NDArray[np.float64],
    poisson_density: npt.NDArray[np.float64],
    correlated_density: npt.NDArray[np.float64],
    exponential_density: npt.NDArray[np.float64],
    rate_cps: float,
    short_interval_excess: float,
) -> Figure:
    """Plot interval densities against the same-rate exponential reference."""
    figure, axis = _new_figure(
        "Phase A inter-arrival distribution",
        f"Log density; exponential reference uses lambda={rate_cps:.1f} s^-1",
    )
    axis.plot(interval_centers_s, exponential_density, "--", color=CHARCOAL, label="Exp(lambda)")
    axis.plot(interval_centers_s, poisson_density, color=BLUE, label="Poisson")
    axis.plot(interval_centers_s, correlated_density, color=ORANGE, label="Correlated")
    axis.set_yscale("log")
    axis.set_xlabel("Inter-arrival interval (s)")
    axis.set_ylabel("Probability density (s^-1)")
    axis.legend(frameon=False, loc="lower left")
    axis.text(
        0.98,
        0.96,
        f"short-interval excess: {short_interval_excess:+.1%}",
        transform=axis.transAxes,
        ha="right",
        va="top",
        color=ORANGE,
        fontsize=10,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_a_fano_figure(
    gate_widths_s: npt.NDArray[np.float64],
    poisson_fano: npt.NDArray[np.float64],
    correlated_fano: npt.NDArray[np.float64],
    maximum_correlated_fano: float,
) -> Figure:
    """Plot precomputed Fano factors over gate width for both processes."""
    figure, axis = _new_figure(
        "Phase A Fano factor vs gate width",
        "Variance-to-mean of non-overlapping gate counts; Poisson reference is one",
    )
    axis.axhline(1.0, color=CHARCOAL, linestyle="--", linewidth=1.0, label="Poisson theory")
    axis.plot(gate_widths_s, poisson_fano, "o-", color=BLUE, label="Poisson sample")
    axis.plot(gate_widths_s, correlated_fano, "o-", color=ORANGE, label="Correlated sample")
    axis.set_xscale("log")
    axis.set_xlabel("Gate width (s)")
    axis.set_ylabel("Fano factor")
    axis.legend(frameon=False)
    axis.text(
        0.98,
        0.12,
        f"max correlated Fano = {maximum_correlated_fano:.3f}",
        transform=axis.transAxes,
        ha="right",
        va="top",
        color=ORANGE,
        fontsize=10,
        bbox={"facecolor": "white", "edgecolor": LIGHT_GREY, "alpha": 0.9},
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_a_rate_sweep_figure(
    k_eff_values: npt.NDArray[np.float64],
    observed_rates_cps: npt.NDArray[np.float64],
    analytic_rates_cps: npt.NDArray[np.float64],
    maximum_relative_error: float,
) -> Figure:
    """Plot simulated mean rates against the branching first-moment curve."""
    figure, axis = _new_figure(
        "Phase A mean detected rate vs k_eff",
        "Simulation points compared with S*epsilon/(1-k_eff)",
    )
    axis.plot(k_eff_values, analytic_rates_cps, color=CHARCOAL, linestyle="--", label="Analytic")
    axis.scatter(k_eff_values, observed_rates_cps, color=ORANGE, s=42, label="Simulated")
    axis.set_xlabel("k_eff")
    axis.set_ylabel("Mean detected rate (cps)")
    axis.legend(frameon=False)
    axis.text(
        0.98,
        0.05,
        f"max relative difference = {maximum_relative_error:.2%}",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        color=CHARCOAL,
        fontsize=10,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_a_chain_tree_figure(nodes: Sequence[ChainTraceNode], chain_id: int) -> Figure:
    """Plot one traced physical neutron chain with reaction-type markers."""
    figure, axis = _new_figure(
        "Phase A traced prompt-neutron chain",
        f"Physical parent-child trace for source chain {chain_id}; detections are highlighted",
        (9.0, 6.0),
    )
    ordered = sorted(
        nodes, key=lambda node: (node.generation, node.reaction_time_s, node.neutron_id)
    )
    positions: dict[int, tuple[float, float]] = {}
    generation_counts: dict[int, int] = {}
    for node in ordered:
        index = generation_counts.get(node.generation, 0)
        generation_counts[node.generation] = index + 1
        positions[node.neutron_id] = (float(node.generation), float(index))
    for node in ordered:
        if node.parent_id in positions:
            parent_x, parent_y = positions[node.parent_id]
            child_x, child_y = positions[node.neutron_id]
            axis.plot([parent_x, child_x], [parent_y, child_y], color=GREY, linewidth=1.0, zorder=1)
    styles = {
        "fission": (GOLD, "o", "Fission"),
        "capture": (GREY, "x", "Capture"),
        "detection": (ORANGE, "*", "Detection"),
    }
    for reaction, (color, marker, label) in styles.items():
        selected = [node for node in ordered if node.reaction == reaction]
        if selected:
            axis.scatter(
                [positions[node.neutron_id][0] for node in selected],
                [positions[node.neutron_id][1] for node in selected],
                color=color,
                marker=marker,
                s=90 if reaction == "detection" else 48,
                label=label,
                zorder=2,
            )
    axis.set_xlabel("Generation")
    axis.set_ylabel("Neutron index within generation")
    axis.xaxis.set_major_locator(MaxNLocator(integer=True))
    axis.yaxis.set_major_locator(MaxNLocator(integer=True))
    axis.legend(frameon=False)
    axis.text(
        0.98,
        0.72,
        f"nodes={len(ordered)}; detections={sum(node.reaction == 'detection' for node in ordered)}",
        transform=axis.transAxes,
        ha="right",
        va="top",
        color=CHARCOAL,
        fontsize=9,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_a_degeneracy_figure(
    scaled_interval_centers: npt.NDArray[np.float64],
    degenerate_density: npt.NDArray[np.float64],
    exponential_density: npt.NDArray[np.float64],
    k_eff: float,
    ks_distance: float,
) -> Figure:
    """Plot the near-zero multiplication interval law against Exp(1)."""
    figure, axis = _new_figure(
        "Phase A near-zero multiplication limit",
        f"Scaled intervals at k_eff={k_eff:.1e}; Poisson limit is Exp(1)",
    )
    axis.plot(scaled_interval_centers, exponential_density, "--", color=CHARCOAL, label="Exp(1)")
    axis.plot(scaled_interval_centers, degenerate_density, color=BLUE, label="Branching k->0")
    axis.set_yscale("log")
    axis.set_xlabel("Scaled interval R_d * delta-t")
    axis.set_ylabel("Probability density")
    axis.legend(frameon=False)
    axis.text(
        0.98,
        0.76,
        f"KS distance = {ks_distance:.4f}",
        transform=axis.transAxes,
        ha="right",
        va="top",
        color=CHARCOAL,
        fontsize=10,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_b_rossi_figure(
    lag_s: npt.NDArray[np.float64],
    density: npt.NDArray[np.float64],
    fitted: npt.NDArray[np.float64],
    alpha_hat_per_s: float,
    alpha_true_per_s: float,
    amplitude: float,
    baseline: float,
) -> Figure:
    """Plot precomputed Rossi-alpha pair density and its exponential fit."""
    figure, axis = _new_figure(
        "Phase B：Rossi-α 时间差拟合",
        "关联指数项与偶然符合平台分离；α 为专业参数名",
    )
    axis.scatter(lag_s * 1.0e3, density, s=18, color=BLUE, alpha=0.75, label="时间差统计")
    axis.plot(lag_s * 1.0e3, fitted, color=ORANGE, linewidth=2.0, label="指数拟合")
    axis.set_xlabel("时间差 τ（ms）")
    axis.set_ylabel("探测对密度（s^-2）")
    axis.legend(frameon=False, loc="upper center")
    axis.text(
        0.98,
        0.95,
        f"α 估计 = {alpha_hat_per_s:.1f} s^-1\nα 真值 = {alpha_true_per_s:.1f} s^-1\n"
        f"A = {amplitude:.3g}\nB = {baseline:.3g}",
        transform=axis.transAxes,
        ha="right",
        va="top",
        color=CHARCOAL,
        bbox={"facecolor": "white", "edgecolor": LIGHT_GREY, "alpha": 0.9},
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_b_feynman_figure(
    gate_width_s: npt.NDArray[np.float64],
    y_values: npt.NDArray[np.float64],
    fitted: npt.NDArray[np.float64],
    alpha_hat_per_s: float,
    alpha_true_per_s: float,
    y_inf: float,
) -> Figure:
    """Plot a precomputed Feynman-Y curve and pure-prompt fit."""
    figure, axis = _new_figure(
        "Phase B：Feynman-α 方差均值比拟合",
        "Y(T) 随门宽上升并趋向 Y∞",
    )
    axis.scatter(gate_width_s * 1.0e3, y_values, s=24, color=BLUE, label="门计数统计")
    axis.plot(gate_width_s * 1.0e3, fitted, color=ORANGE, linewidth=2.0, label="单指数拟合")
    axis.set_xscale("log")
    axis.set_xlabel("门宽 T（ms）")
    axis.set_ylabel("Feynman Y(T)")
    axis.legend(frameon=False)
    axis.text(
        0.98,
        0.95,
        f"α 估计 = {alpha_hat_per_s:.1f} s^-1\nα 真值 = {alpha_true_per_s:.1f} s^-1\n"
        f"Y∞ = {y_inf:.3f}",
        transform=axis.transAxes,
        ha="right",
        va="top",
        color=CHARCOAL,
        bbox={"facecolor": "white", "edgecolor": LIGHT_GREY, "alpha": 0.9},
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_b_psd_figure(
    frequency_hz: npt.NDArray[np.float64],
    power: npt.NDArray[np.float64],
    fitted: npt.NDArray[np.float64],
    alpha_hat_per_s: float,
    alpha_true_per_s: float,
    y_inf: float,
) -> Figure:
    """Plot a precomputed count PSD and Lorentzian fit."""
    figure, axis = _new_figure(
        "Phase B：PSD 洛伦兹拟合",
        "频域拐点为 α/2π；横纵轴均为对数尺度",
    )
    axis.scatter(frequency_hz, power, s=16, color=BLUE, alpha=0.65, label="Welch PSD")
    axis.plot(frequency_hz, fitted, color=ORANGE, linewidth=2.0, label="洛伦兹拟合")
    corner = alpha_hat_per_s / (2.0 * np.pi)
    axis.axvline(corner, color=GOLD, linestyle="--", label="拟合拐点 α/2π")
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("频率（Hz）")
    axis.set_ylabel("功率谱密度（计数²/Hz）")
    axis.legend(frameon=False, loc="lower left")
    axis.text(
        0.98,
        0.95,
        f"α 估计 = {alpha_hat_per_s:.1f} s^-1\nα 真值 = {alpha_true_per_s:.1f} s^-1\n"
        f"拐点 = {corner:.1f} Hz\nY∞ = {y_inf:.3f}",
        transform=axis.transAxes,
        ha="right",
        va="top",
        color=CHARCOAL,
        bbox={"facecolor": "white", "edgecolor": LIGHT_GREY, "alpha": 0.9},
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_b_alpha_parity_figure(
    alpha_true_per_s: npt.NDArray[np.float64],
    alpha_hat_per_s: npt.NDArray[np.float64],
    alpha_std_per_s: npt.NDArray[np.float64],
    methods: Sequence[str],
) -> Figure:
    """Plot recovered versus true alpha for the three estimators."""
    figure, axis = _new_figure(
        "Phase B：α 复原一致性",
        "阴影表示相对真值 ±5% 的自动验收带",
        (7.0, 6.2),
    )
    minimum = float(np.min(alpha_true_per_s)) * 0.85
    maximum = float(np.max(alpha_true_per_s)) * 1.15
    line = np.linspace(minimum, maximum, 200)
    axis.fill_between(
        line, 0.95 * line, 1.05 * line, color=LIGHT_GREY, alpha=0.7, label="±5% 验收带"
    )
    axis.plot(line, line, color=CHARCOAL, linestyle="--", label="理想复原")
    colors = {"Rossi-α": BLUE, "Feynman-α": ORANGE, "PSD": GOLD}
    for method in dict.fromkeys(methods):
        selected = np.array([value == method for value in methods])
        axis.errorbar(
            alpha_true_per_s[selected],
            alpha_hat_per_s[selected],
            yerr=alpha_std_per_s[selected],
            fmt="o",
            capsize=3,
            color=colors.get(method, GREY),
            label=method,
        )
    axis.set_xlim(minimum, maximum)
    axis.set_ylim(minimum, maximum)
    axis.set_xlabel("设定 α 真值（s^-1）")
    axis.set_ylabel("反演 α（s^-1）")
    axis.legend(frameon=False)
    axis.set_aspect("equal", adjustable="box")
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_b_method_agreement_figure(
    case_labels: Sequence[str],
    relative_errors: npt.NDArray[np.float64],
    methods: Sequence[str],
) -> Figure:
    """Compare relative alpha errors for all methods and recovery cases."""
    figure, axis = _new_figure(
        "Phase B：三种方法交叉一致性",
        "相对误差均以各工况设定 α 为基准",
        (9.2, 5.5),
    )
    x_values = np.arange(len(case_labels), dtype=np.float64)
    width = 0.23
    colors = [BLUE, ORANGE, GOLD]
    for index, method in enumerate(methods):
        axis.bar(
            x_values + (index - 1) * width,
            relative_errors[:, index] * 100.0,
            width,
            label=method,
            color=colors[index],
        )
    axis.axhspan(-5.0, 5.0, color=LIGHT_GREY, alpha=0.55, label="±5% 验收带")
    axis.axhline(0.0, color=CHARCOAL, linewidth=0.8)
    axis.set_xticks(x_values, case_labels)
    axis.set_xlabel("闭环工况")
    axis.set_ylabel("α 相对误差（%）")
    axis.legend(frameon=False, ncols=2)
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_b_deadtime_bias_figure(
    rates_cps: npt.NDArray[np.float64],
    raw_ratios: npt.NDArray[np.float64],
    corrected_ratios: npt.NDArray[np.float64],
    alpha_labels: Sequence[str],
    usable_rate_cps: float,
) -> Figure:
    """Plot raw and corrected Feynman-alpha dead-time bias."""
    figure, axis = _new_figure(
        "Phase B：死时间偏置与脉冲计数可用边界",
        "实线为 Hazama 一阶 VTM 修正；灰带为 ±5% 可用区",
        (9.4, 5.8),
    )
    axis.axhspan(0.95, 1.05, color=LIGHT_GREY, alpha=0.65, label="±5% 可用区")
    colors = [BLUE, ORANGE, GOLD, GREY]
    for index, label in enumerate(alpha_labels):
        color = colors[index % len(colors)]
        axis.plot(
            rates_cps, raw_ratios[index], "o--", color=color, alpha=0.6, label=f"{label} 修正前"
        )
        axis.plot(rates_cps, corrected_ratios[index], "o-", color=color, label=f"{label} 修正后")
    if np.isfinite(usable_rate_cps):
        axis.axvline(usable_rate_cps, color=CHARCOAL, linestyle=":")
        axis.text(
            usable_rate_cps,
            0.55,
            f"共同可用上限\n≈ {usable_rate_cps:.0f} cps",
            ha="right",
            va="bottom",
            color=CHARCOAL,
        )
    axis.set_xscale("log")
    axis.set_xlabel("真计数率（cps）")
    axis.set_ylabel("α 估计 / α 真值")
    axis.legend(frameon=False, ncols=2, fontsize=8)
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_b_bootstrap_figure(
    bootstrap_alpha_per_s: npt.NDArray[np.float64],
    alpha_hat_per_s: float,
    naive_std_per_s: float,
    corrected_std_per_s: float,
    alpha_true_per_s: float,
    method: str,
) -> Figure:
    """Plot a bootstrap alpha distribution against naive and corrected errors."""
    figure, axis = _new_figure(
        "Phase B：bootstrap 不确定度",
        f"{method}；时间块重采样保留曲线各 bin 的共同波动",
    )
    axis.hist(bootstrap_alpha_per_s, bins="auto", color=BLUE, alpha=0.72, label="bootstrap α")
    axis.axvline(alpha_true_per_s, color=CHARCOAL, linestyle="--", label="α 真值")
    axis.axvspan(
        alpha_hat_per_s - naive_std_per_s,
        alpha_hat_per_s + naive_std_per_s,
        color=GOLD,
        alpha=0.28,
        label="朴素拟合 ±1σ",
    )
    axis.axvspan(
        alpha_hat_per_s - corrected_std_per_s,
        alpha_hat_per_s + corrected_std_per_s,
        color=ORANGE,
        alpha=0.2,
        label="相关性修正 ±1σ",
    )
    axis.set_xlabel("反演 α（s^-1）")
    axis.set_ylabel("重采样次数")
    axis.legend(frameon=False, loc="upper left")
    axis.text(
        0.98,
        0.94,
        f"朴素 σ = {naive_std_per_s:.1f} s^-1\n修正 σ = {corrected_std_per_s:.1f} s^-1",
        transform=axis.transAxes,
        ha="right",
        va="top",
        color=CHARCOAL,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


# ----------------------------------------------------------------- Phase C


def phase_c_acf_fit_figure(
    lags_s: npt.NDArray[np.float64],
    acf_values: npt.NDArray[np.float64],
    fitted: npt.NDArray[np.float64],
    alpha_hat_per_s: float,
    alpha_true_per_s: float,
    alpha_e_per_s: float,
) -> Figure:
    """Plot the continuous-voltage ACF and its alpha_e-aware exponential fit."""
    figure, axis = _new_figure(
        "Phase C：连续信号自协方差拟合",
        "含探测器脉冲衰减常数 α_e 项的 ACF 模型",
    )
    axis.plot(lags_s * 1.0e3, acf_values, color=BLUE, linewidth=1.0, alpha=0.85, label="ACF(θ)")
    axis.plot(lags_s * 1.0e3, fitted, color=ORANGE, linewidth=2.0, label="拟合")
    axis.set_xlabel("时间差 θ（ms）")
    axis.set_ylabel("归一化自协方差")
    axis.legend(frameon=False)
    axis.text(
        0.98,
        0.95,
        f"α 估计 = {alpha_hat_per_s:.1f} s^-1\nα 真值 = {alpha_true_per_s:.1f} s^-1\n"
        f"α_e = {alpha_e_per_s:.1f} s^-1",
        transform=axis.transAxes,
        ha="right",
        va="top",
        color=CHARCOAL,
        bbox={"facecolor": "white", "edgecolor": LIGHT_GREY, "alpha": 0.9},
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_c_vtm_fit_figure(
    gate_width_s: npt.NDArray[np.float64],
    vtm_values: npt.NDArray[np.float64],
    fitted: npt.NDArray[np.float64],
    alpha_hat_per_s: float,
    alpha_true_per_s: float,
) -> Figure:
    """Plot the continuous-voltage VTM and its fitted model."""
    figure, axis = _new_figure(
        "Phase C：连续信号 VTM 拟合",
        "电压方差均值比随门宽的变化",
    )
    axis.scatter(gate_width_s * 1.0e3, vtm_values, s=20, color=BLUE, alpha=0.75, label="VTM(T)")
    axis.plot(gate_width_s * 1.0e3, fitted, color=ORANGE, linewidth=2.0, label="拟合")
    axis.set_xscale("log")
    axis.set_xlabel("门宽 T（ms）")
    axis.set_ylabel("连续 VTM")
    axis.legend(frameon=False)
    axis.text(
        0.98,
        0.95,
        f"α 估计 = {alpha_hat_per_s:.1f} s^-1\nα 真值 = {alpha_true_per_s:.1f} s^-1",
        transform=axis.transAxes,
        ha="right",
        va="top",
        color=CHARCOAL,
        bbox={"facecolor": "white", "edgecolor": LIGHT_GREY, "alpha": 0.9},
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_c_deconvolution_figure(
    original: npt.NDArray[np.float64],
    deconvolved: npt.NDArray[np.float64],
    thresholded: npt.NDArray[np.float64],
    sample_rate_hz: float,
    gamma: float,
    residual_ratio: float,
) -> Figure:
    """Plot original waveform, Wiener-deconvolved, and thresholded versions."""
    figure, axes = plt.subplots(3, 1, figsize=(10.0, 7.5), sharex=True)
    figure.suptitle(
        "Phase C：Wiener 去卷积比较", x=0.08, y=0.98, ha="left", fontsize=14, color=CHARCOAL
    )
    time_ms = np.arange(original.size, dtype=np.float64) / sample_rate_hz * 1.0e3
    plot_slice = slice(None, min(original.size, 5000))
    axes[0].plot(time_ms[plot_slice], original[plot_slice], color=BLUE, linewidth=0.8)
    axes[0].set_ylabel("原始波形 (V)")
    axes[0].grid(True, color=LIGHT_GREY, linewidth=0.7, alpha=0.65)
    axes[1].plot(time_ms[plot_slice], deconvolved[plot_slice], color=ORANGE, linewidth=0.8)
    axes[1].set_ylabel("去卷积输出")
    axes[1].grid(True, color=LIGHT_GREY, linewidth=0.7, alpha=0.65)
    axes[2].vlines(
        time_ms[np.abs(thresholded) > 0][:200],
        0,
        1,
        color=GOLD,
        linewidth=1.0,
        label="阈值化脉冲",
    )
    axes[2].set_ylabel("阈值化脉冲位置")
    axes[2].set_xlabel("时间（ms）")
    axes[2].set_ylim(0, 1.5)
    axes[2].grid(True, color=LIGHT_GREY, linewidth=0.7, alpha=0.65)
    axes[2].legend(frameon=False, loc="upper right")
    axes[1].text(
        0.98,
        0.94,
        f"γ = {gamma:.4f}\n残差比 = {residual_ratio:.4f}",
        transform=axes[1].transAxes,
        ha="right",
        va="top",
        color=CHARCOAL,
        fontsize=8,
        bbox={"facecolor": "white", "edgecolor": LIGHT_GREY, "alpha": 0.9},
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_c_gamma_nsr_heatmap(
    gamma_grid: npt.NDArray[np.float64],
    nsr_grid: npt.NDArray[np.float64],
    residual_map: npt.NDArray[np.float64],
) -> Figure:
    """Plot the gamma-NSR residual heatmap for Wiener deconvolution."""
    figure, axis = _new_figure(
        "Phase C：γ–NSR 稳定域",
        "Wiener 去卷积在不同正则化和噪信比下的残差热力图",
        (8.5, 6.0),
    )
    masked = np.where(np.isfinite(residual_map), residual_map, np.nan)
    extent = [
        float(nsr_grid[0]),
        float(nsr_grid[-1]),
        float(gamma_grid[0]),
        float(gamma_grid[-1]),
    ]
    image = axis.imshow(
        masked,
        aspect="auto",
        origin="lower",
        extent=(extent[0], extent[1], extent[2], extent[3]),
        cmap="YlOrRd",
    )
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("NSR（噪信比）")
    axis.set_ylabel("γ（正则化强度）")
    figure.colorbar(image, ax=axis, label="重构残差比")
    axis.text(
        0.98,
        0.96,
        "浅色 = 低残差（优）\n深色 = 高残差（劣）",
        transform=axis.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        color=CHARCOAL,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_c_ccf_ctm_figure(
    ccf_lags: npt.NDArray[np.float64],
    ccf_values: npt.NDArray[np.float64],
    ctm_gates: npt.NDArray[np.float64],
    ctm_values: npt.NDArray[np.float64],
    alpha_hat_per_s: float,
    alpha_true_per_s: float,
) -> Figure:
    """Plot the dual-detector CCF and CTM results."""
    figure, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.5))
    figure.suptitle(
        "Phase C：双探测器互协方差 CCF/CTM",
        x=0.08,
        y=0.98,
        ha="left",
        fontsize=14,
        color=CHARCOAL,
    )
    ax1.plot(ccf_lags * 1.0e3, ccf_values, color=BLUE, linewidth=1.2)
    ax1.set_xlabel("时间差（ms）")
    ax1.set_ylabel("归一化 CCF")
    ax1.set_title("互协方差 CCF", loc="left", fontsize=9, color=GREY, pad=8)
    ax1.grid(True, color=LIGHT_GREY, linewidth=0.7, alpha=0.65)
    ax2.scatter(ctm_gates * 1.0e3, ctm_values, s=18, color=ORANGE, alpha=0.8)
    ax2.set_xscale("log")
    ax2.set_xlabel("门宽 T（ms）")
    ax2.set_ylabel("CTM")
    ax2.set_title("互协方差均值比 CTM", loc="left", fontsize=9, color=GREY, pad=8)
    ax2.grid(True, color=LIGHT_GREY, linewidth=0.7, alpha=0.65)
    ax2.text(
        0.98,
        0.92,
        f"α 估计 ≈ {alpha_hat_per_s:.1f} s^-1\nα 真值 = {alpha_true_per_s:.1f}",
        transform=ax2.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        color=CHARCOAL,
        bbox={"facecolor": "white", "edgecolor": LIGHT_GREY, "alpha": 0.9},
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.92))
    return figure


def phase_c_usability_frontier_figure(
    rates_cps: npt.NDArray[np.float64],
    alphas_per_s: npt.NDArray[np.float64],
    error_map: npt.NDArray[np.float64],
    usable_rate_cps: float,
) -> Figure:
    """Plot the usability frontier as a relative-error heatmap."""
    figure, axis = _new_figure(
        "Phase C：连续信号可用边界",
        "各 (α, 计数率) 网格点的 α 复原相对误差",
        (9.0, 6.0),
    )
    masked = np.where(np.isfinite(error_map), np.clip(error_map, 0.0, 0.5), np.nan)
    im = axis.imshow(
        masked,
        aspect="auto",
        origin="lower",
        extent=(
            float(rates_cps[0]),
            float(rates_cps[-1]),
            float(alphas_per_s[0]),
            float(alphas_per_s[-1]),
        ),
        cmap="RdYlGn_r",
        vmin=0.0,
        vmax=0.15,
    )
    axis.set_xscale("log")
    axis.set_xlabel("真计数率（cps）")
    axis.set_ylabel("α 真值（s^-1）")
    figure.colorbar(im, ax=axis, label="α 相对误差")
    if np.isfinite(usable_rate_cps):
        axis.axvline(usable_rate_cps, color=CHARCOAL, linestyle=":", linewidth=2)
        axis.text(
            usable_rate_cps,
            float(alphas_per_s[-1]),
            f"共同可用≈{usable_rate_cps:.0f} cps",
            ha="right",
            va="top",
            color=CHARCOAL,
            fontsize=9,
        )
    axis.text(
        0.98,
        0.04,
        "绿 = 低误差（优）\n红 = 高误差",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color=CHARCOAL,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure


def phase_c_wall_effect_figure(
    alphas_per_s: npt.NDArray[np.float64],
    wall_weights: npt.NDArray[np.float64],
    error_map: npt.NDArray[np.float64],
) -> Figure:
    """Plot wall-effect sensitivity: alpha recovery error vs wall fraction."""
    figure, axis = _new_figure(
        "Phase C：壁效应敏感性",
        "壁效应分量权重对连续 ACF α 反演误差的影响",
    )
    colors = [BLUE, ORANGE, GOLD]
    for ai, (alpha, color) in enumerate(zip(alphas_per_s, colors, strict=False)):
        if ai < error_map.shape[0]:
            errors = error_map[ai, :]
            valid = np.isfinite(errors)
            if np.any(valid):
                axis.plot(
                    wall_weights[valid] * 100.0,
                    errors[valid] * 100.0,
                    "o-",
                    color=color,
                    label=f"α = {alpha:.0f} s^-1",
                )
    axis.axhline(5.0, color=CHARCOAL, linestyle="--", alpha=0.6, label="±5% 门限")
    axis.set_xlabel("壁效应权重（%）")
    axis.set_ylabel("α 相对误差（%）")
    axis.legend(frameon=False)
    axis.text(
        0.98,
        0.94,
        "壁效应增大导致\n幅值分布展宽",
        transform=axis.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        color=CHARCOAL,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    return figure
