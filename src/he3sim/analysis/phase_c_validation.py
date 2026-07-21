"""Phase C automated validation: continuous-signal alpha recovery and usability frontier."""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt

from he3sim.analysis.continuous_noise import (
    ContinuousNoiseAnalysis,
    analyze_continuous_noise,
    compute_acf,
    compute_ccf,
    compute_ctm,
    fit_continuous_acf,
    pulse_kernel_samples,
    scan_gamma_nsr,
)
from he3sim.analysis.figures import (
    phase_c_acf_fit_figure,
    phase_c_ccf_ctm_figure,
    phase_c_deconvolution_figure,
    phase_c_gamma_nsr_heatmap,
    phase_c_usability_frontier_figure,
    phase_c_vtm_fit_figure,
    phase_c_wall_effect_figure,
)
from he3sim.analysis.noise import rossi_alpha
from he3sim.config import He3SimConfig, SourceModelKind
from he3sim.physics.split_detector import generate_correlated_times

PNG_DPI = 160
DEFAULT_PHASEC_EVENTS = 4_000
DEFAULT_DUAL_EVENTS = 3_000
DEFAULT_FRONTIER_EVENTS = 2_000


@dataclass(frozen=True, slots=True)
class ContinuousRecoveryPoint:
    """One closed-loop continuous-method alpha recovery result."""

    alpha_true_per_s: float
    duration_s: float
    event_count: int
    continuous_acf_alpha_per_s: float
    continuous_vtm_alpha_per_s: float
    pulse_rossi_alpha_per_s: float


@dataclass(frozen=True, slots=True)
class FrontierPoint:
    """One point on the usability frontier grid (rate x alpha)."""

    alpha_true_per_s: float
    true_rate_cps: float
    continuous_alpha_hat_per_s: float
    relative_error: float
    within_tolerance: bool


@dataclass(frozen=True, slots=True)
class PhaseCMetrics:
    """Decision metrics for the Phase C automated gate."""

    maximum_continuous_acf_error: float
    maximum_continuous_vtm_error: float
    continuous_vs_pulse_max_diff: float
    deconvolution_improves_at_high_rate: bool
    usable_continuous_rate_cps: float
    frontier_passed: bool
    alpha_tolerance: float
    passed: bool


@dataclass(frozen=True, slots=True)
class PhaseCArtifacts:
    """All precomputed data for Phase C figure functions."""

    primary_analysis: ContinuousNoiseAnalysis
    primary_voltage: npt.NDArray[np.float64]
    recovery_points: tuple[ContinuousRecoveryPoint, ...]
    frontier_points: tuple[FrontierPoint, ...]
    gamma_nsr_scan: dict[str, Any]
    ccf_lags: npt.NDArray[np.float64]
    ccf_values: npt.NDArray[np.float64]
    ctm_gates: npt.NDArray[np.float64]
    ctm_values: npt.NDArray[np.float64]
    wall_effect_alphas: npt.NDArray[np.float64]
    wall_effect_weights: npt.NDArray[np.float64]
    wall_effect_errors: npt.NDArray[np.float64]
    metrics: PhaseCMetrics
    sample_rate_hz: float
    tau_r_s: float
    tau_d_s: float
    seed: int


def _validation_config(
    base: He3SimConfig,
    *,
    alpha_per_s: float,
    true_rate_cps: float,
    target_events: int,
    seed: int,
    efficiency: float = 0.3,
    k_eff: float = 0.85,
) -> He3SimConfig:
    raw = base.model_dump(mode="python")
    raw["metadata"]["seed"]["value"] = seed
    raw["metadata"]["run_name"] = f"phaseC-alpha-{alpha_per_s:g}-rate-{true_rate_cps:g}"
    raw["source_model"]["kind"] = SourceModelKind.CORRELATED.value
    raw["source_model"]["k_eff"]["value"] = k_eff
    raw["source_model"]["alpha"]["value"] = alpha_per_s
    raw["source_model"]["detection_efficiency"]["value"] = efficiency
    raw["source_model"]["source_rate_cps"]["value"] = true_rate_cps * (1.0 - k_eff) / efficiency
    raw["source_model"]["max_total_reactions"] = max(
        1_000_000, int(np.ceil(target_events / efficiency * 1.5))
    )
    raw["simulation"]["true_rate_cps"]["value"] = true_rate_cps
    raw["observation"]["mode"] = "fixed_duration"
    raw["observation"]["duration_s"] = {
        "value": target_events / true_rate_cps,
        "status": "synthetic_demo",
        "notes": "Phase C auto-computed horizon.",
    }
    raw["observation"].pop("target_event_count", None)
    raw["observation"].pop("min_duration_s", None)
    raw["observation"].pop("max_duration_s", None)
    return He3SimConfig.model_validate(raw)


def _generate_voltage(
    config: He3SimConfig, sample_rate_hz: float, tau_r_s: float, tau_d_s: float
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], float]:
    """Generate a synthetic voltage waveform from correlated detection times.

    Uses a sparse approach with a precomputed kernel capped at 2 MS/s.
    """
    effective_rate = min(sample_rate_hz, 2_000_000.0)
    times, duration_s = generate_correlated_times(config)
    sample_count = int(np.round(duration_s * effective_rate))
    if sample_count > 50_000_000:
        raise ValueError(
            f"Phase C voltage array too large ({sample_count} samples); reduce event count or rate."
        )
    voltage = np.zeros(sample_count, dtype=np.float64)
    if times.size == 0:
        return voltage, times, duration_s
    from he3sim.physics.pulse_models import (
        double_exponential_peak_value,
    )

    peak_val = double_exponential_peak_value(tau_r_s, tau_d_s)
    kernel_len = int(np.ceil(8.0 * tau_d_s * effective_rate))
    delays = np.arange(kernel_len, dtype=np.float64) / effective_rate
    kernel = (np.exp(-delays / tau_d_s) - np.exp(-delays / tau_r_s)) / peak_val * 0.15
    for t in times:
        onset = int(np.floor(t * effective_rate))
        if onset < 0:
            continue
        end = min(onset + kernel_len, sample_count)
        length = end - onset
        if length > 0:
            voltage[onset:end] += kernel[:length]
    rng = np.random.default_rng(config.metadata.seed.value or 0)
    voltage += rng.normal(0.0, 0.001, sample_count)
    return voltage, times, duration_s


def build_phase_c_validation(
    base_config: He3SimConfig,
    *,
    recovery_events: int = DEFAULT_PHASEC_EVENTS,
    dual_events: int = DEFAULT_DUAL_EVENTS,
    frontier_events: int = DEFAULT_FRONTIER_EVENTS,
    alpha_tolerance: float = 0.05,
) -> PhaseCArtifacts:
    """Build the multi-case continuous alpha recovery, frontier scan, and CCF/CTM."""
    if recovery_events < 2_000 or frontier_events < 1_000:
        raise ValueError("Phase C validation requires at least 5,000 recovery events")
    seed = int(base_config.metadata.seed.value or 0)
    tau_r_s = float(base_config.pulse_shape.tau_r_s.value or 1.0e-6)
    tau_d_s = float(base_config.pulse_shape.tau_d_s.value or 1.0e-5)
    sample_rate_hz = float(base_config.simulation.sample_rate_hz.value or 1.0e8)

    case_specs = (
        (500.0, 2_000.0, 0.25),
        (1_000.0, 3_000.0, 0.30),
        (2_000.0, 5_000.0, 0.35),
    )
    recovery_points: list[ContinuousRecoveryPoint] = []
    primary_voltage = np.array([], dtype=np.float64)
    primary_analysis = None
    for case_index, (alpha, rate, efficiency) in enumerate(case_specs):
        config = _validation_config(
            base_config,
            alpha_per_s=alpha,
            true_rate_cps=rate,
            target_events=recovery_events,
            seed=seed + case_index * 100,
            efficiency=efficiency,
        )
        voltage, times, duration_s = _generate_voltage(config, sample_rate_hz, tau_r_s, tau_d_s)
        if voltage.size < 100 or times.size < 100:
            continue
        analysis = analyze_continuous_noise(
            voltage,
            sample_rate_hz,
            tau_r_s,
            tau_d_s,
            alpha,
        )
        pulse_rossi = rossi_alpha(times, duration_s)
        recovery_points.append(
            ContinuousRecoveryPoint(
                alpha_true_per_s=alpha,
                duration_s=duration_s,
                event_count=int(times.size),
                continuous_acf_alpha_per_s=analysis.acf_fit.alpha_per_s,
                continuous_vtm_alpha_per_s=analysis.vtm.fit.alpha_per_s,
                pulse_rossi_alpha_per_s=pulse_rossi.fit.alpha_per_s,
            )
        )
        if alpha == 1_000.0:
            primary_voltage = voltage
            primary_analysis = analysis
    if primary_analysis is None or primary_voltage.size == 0:
        raise RuntimeError("Phase C primary analysis was not generated")

    kernel = pulse_kernel_samples(sample_rate_hz, tau_r_s, tau_d_s)
    gamma_nsr_data = scan_gamma_nsr(primary_voltage, kernel)

    dual_config = _validation_config(
        base_config,
        alpha_per_s=1_000.0,
        true_rate_cps=3_000.0,
        target_events=dual_events,
        seed=seed + 500,
        efficiency=0.30,
    )
    dual_times, dual_duration = generate_correlated_times(dual_config)
    rng = np.random.default_rng(seed + 600)
    from he3sim.physics.chains import CorrelatedArrivalBatch
    from he3sim.physics.split_detector import split_detections

    batch = CorrelatedArrivalBatch(
        times_s=dual_times,
        chain_ids=np.zeros(dual_times.size, dtype=np.int64),
        generations=np.zeros(dual_times.size, dtype=np.int32),
    )
    split = split_detections(batch, 0.15, 0.15, rng)
    dual_rate = min(sample_rate_hz, 2_000_000.0)
    dual_samples = int(np.round(dual_duration * dual_rate))
    if dual_samples > 50_000_000:
        dual_samples = 50_000_000
    dual_v1 = np.zeros(dual_samples, dtype=np.float64)
    dual_v2 = np.zeros(dual_samples, dtype=np.float64)
    from he3sim.physics.pulse_models import double_exponential_peak_value

    peak_val = double_exponential_peak_value(tau_r_s, tau_d_s)
    dual_kernel_len = int(np.ceil(8.0 * tau_d_s * dual_rate))
    dual_delays = np.arange(dual_kernel_len, dtype=np.float64) / dual_rate
    dual_kernel = (
        (np.exp(-dual_delays / tau_d_s) - np.exp(-dual_delays / tau_r_s)) / peak_val * 0.15
    )
    for ch_times, ch_voltage in [(split.ch1_times_s, dual_v1), (split.ch2_times_s, dual_v2)]:
        for t in ch_times:
            onset = int(np.floor(t * dual_rate))
            if onset < 0:
                continue
            end = min(onset + dual_kernel_len, dual_samples)
            length = end - onset
            if length > 0:
                ch_voltage[onset:end] += dual_kernel[:length]
    noise_rng = np.random.default_rng(seed + 700)
    dual_v1 += noise_rng.normal(0.0, 0.001, dual_samples)
    dual_v2 += noise_rng.normal(0.0, 0.001, dual_samples)
    ccf_lags, ccf_values = compute_ccf(dual_v1, dual_v2, 0.01, dual_rate)
    ctm_gates, ctm_values = compute_ctm(dual_v1, dual_v2, dual_rate)

    frontier_rates = (2_000.0, 5_000.0, 10_000.0, 30_000.0)
    frontier_alphas = (500.0, 1_000.0, 2_000.0)
    frontier_points: list[FrontierPoint] = []
    for fi, rate in enumerate(frontier_rates):
        for fj, alpha in enumerate(frontier_alphas):
            fconfig = _validation_config(
                base_config,
                alpha_per_s=alpha,
                true_rate_cps=rate,
                target_events=frontier_events,
                seed=seed + 1000 + fi * 10 + fj,
            )
            fvoltage, ftimes, fdu = _generate_voltage(fconfig, sample_rate_hz, tau_r_s, tau_d_s)
            if fvoltage.size < 100 or ftimes.size < 100:
                frontier_points.append(
                    FrontierPoint(
                        alpha_true_per_s=alpha,
                        true_rate_cps=rate,
                        continuous_alpha_hat_per_s=float("nan"),
                        relative_error=float("nan"),
                        within_tolerance=False,
                    )
                )
                continue
            fanalysis = analyze_continuous_noise(
                fvoltage,
                sample_rate_hz,
                tau_r_s,
                tau_d_s,
                alpha,
            )
            rel = abs(fanalysis.acf_fit.alpha_per_s / alpha - 1.0)
            frontier_points.append(
                FrontierPoint(
                    alpha_true_per_s=alpha,
                    true_rate_cps=rate,
                    continuous_alpha_hat_per_s=fanalysis.acf_fit.alpha_per_s,
                    relative_error=rel,
                    within_tolerance=rel <= alpha_tolerance,
                )
            )

    wall_alphas = np.array([500.0, 1_000.0, 2_000.0], dtype=np.float64)
    wall_weights = np.array([0.1, 0.3, 0.5, 0.7], dtype=np.float64)
    wall_errors = np.zeros((wall_alphas.size, wall_weights.size), dtype=np.float64)
    for wi, w_frac in enumerate(wall_weights):
        for ai, alpha in enumerate(wall_alphas):
            wall_config = _validation_config(
                base_config,
                alpha_per_s=alpha,
                true_rate_cps=3_000.0,
                target_events=recovery_events // 2,
                seed=seed + 2000 + wi * 10 + ai,
            )
            wall_raw = wall_config.model_dump(mode="python")
            wall_raw["spectrum"]["full_energy_fraction"]["value"] = 1.0 - w_frac
            wall_raw["spectrum"]["proton_wall_fraction"]["value"] = w_frac * 0.5
            wall_raw["spectrum"]["triton_wall_fraction"]["value"] = w_frac * 0.5
            wall_raw["spectrum"]["double_wall_fraction"]["value"] = 0.0
            wall_adjusted = He3SimConfig.model_validate(wall_raw)
            wvoltage, wtimes, wdu = _generate_voltage(
                wall_adjusted, sample_rate_hz, tau_r_s, tau_d_s
            )
            if wvoltage.size < 100 or wtimes.size < 100:
                wall_errors[wi, ai] = float("nan")
                continue
            wlags, wacf = compute_acf(wvoltage, sample_rate_hz, max_lag_s=0.01)
            wfit = fit_continuous_acf(wlags, wacf, 1.0 / tau_d_s)
            wall_errors[ai, wi] = abs(wfit.alpha_per_s / alpha - 1.0)

    continuous_errors = [
        p.continuous_acf_alpha_per_s / p.alpha_true_per_s - 1.0 for p in recovery_points
    ]
    vtm_errors = [p.continuous_vtm_alpha_per_s / p.alpha_true_per_s - 1.0 for p in recovery_points]
    max_acf = max(abs(e) for e in continuous_errors) if continuous_errors else 1.0
    max_vtm = max(abs(e) for e in vtm_errors) if vtm_errors else 1.0
    diff_values = [
        abs(p.continuous_acf_alpha_per_s - p.pulse_rossi_alpha_per_s) / p.alpha_true_per_s
        for p in recovery_points
    ]
    max_diff = max(diff_values) if diff_values else 1.0

    high_rate_frontier = [p for p in frontier_points if p.true_rate_cps >= 10_000.0]
    high_rate_usable = sum(1 for p in high_rate_frontier if p.within_tolerance)
    deconv_improves = high_rate_usable >= max(1, len(high_rate_frontier) // 2)

    usable_rates = []
    for rate in sorted({p.true_rate_cps for p in frontier_points}):
        rate_points = [p for p in frontier_points if p.true_rate_cps == rate]
        if all(p.within_tolerance for p in rate_points):
            usable_rates.append(rate)
        else:
            break
    usable_rate = max(usable_rates, default=float("nan"))

    frontier_passed = (
        max_acf <= alpha_tolerance
        and max_vtm <= alpha_tolerance
        and max_diff <= alpha_tolerance
        and deconv_improves
    )
    metrics = PhaseCMetrics(
        maximum_continuous_acf_error=max_acf,
        maximum_continuous_vtm_error=max_vtm,
        continuous_vs_pulse_max_diff=max_diff,
        deconvolution_improves_at_high_rate=deconv_improves,
        usable_continuous_rate_cps=usable_rate,
        frontier_passed=frontier_passed,
        alpha_tolerance=alpha_tolerance,
        passed=frontier_passed,
    )
    return PhaseCArtifacts(
        primary_analysis=primary_analysis,
        primary_voltage=primary_voltage,
        recovery_points=tuple(recovery_points),
        frontier_points=tuple(frontier_points),
        gamma_nsr_scan=gamma_nsr_data,
        ccf_lags=ccf_lags,
        ccf_values=ccf_values,
        ctm_gates=ctm_gates,
        ctm_values=ctm_values,
        wall_effect_alphas=wall_alphas,
        wall_effect_weights=wall_weights,
        wall_effect_errors=wall_errors,
        metrics=metrics,
        sample_rate_hz=sample_rate_hz,
        tau_r_s=tau_r_s,
        tau_d_s=tau_d_s,
        seed=seed,
    )


def _figure_map(artifacts: PhaseCArtifacts) -> dict[str, Any]:
    analysis = artifacts.primary_analysis
    figures: dict[str, Any] = {}

    figures["continuous_acf_fit.png"] = phase_c_acf_fit_figure(
        analysis.acf_lags_s,
        analysis.acf_values,
        _acf_fitted(analysis),
        analysis.acf_fit.alpha_per_s,
        analysis.alpha_true_per_s,
        analysis.acf_fit.alpha_e_per_s,
    )

    figures["continuous_vtm_fit.png"] = phase_c_vtm_fit_figure(
        analysis.vtm.gate_widths_s,
        analysis.vtm.vtm_values,
        analysis.vtm.fitted,
        analysis.vtm.fit.alpha_per_s,
        analysis.alpha_true_per_s,
    )

    deconv_result = analysis.deconv_result
    deconv_threshold = 3.0 * np.std(deconv_result.deconvolved)
    deconv_th = np.where(
        np.abs(deconv_result.deconvolved) >= deconv_threshold,
        deconv_result.deconvolved,
        0.0,
    )
    figures["deconvolution_comparison.png"] = phase_c_deconvolution_figure(
        artifacts.primary_voltage,
        deconv_result.deconvolved,
        deconv_th,
        analysis.sample_rate_hz,
        deconv_result.gamma,
        deconv_result.residual_ratio,
    )

    scan = artifacts.gamma_nsr_scan
    figures["gamma_nsr_heatmap.png"] = phase_c_gamma_nsr_heatmap(
        scan["gamma_grid"],
        scan["nsr_grid"],
        scan["residual_map"],
    )

    figures["ccf_ctm.png"] = phase_c_ccf_ctm_figure(
        artifacts.ccf_lags,
        artifacts.ccf_values,
        artifacts.ctm_gates,
        artifacts.ctm_values,
        analysis.acf_fit.alpha_per_s,
        analysis.alpha_true_per_s,
    )

    frontier_rates = sorted({p.true_rate_cps for p in artifacts.frontier_points})
    frontier_alphas = sorted({p.alpha_true_per_s for p in artifacts.frontier_points})
    frontier_map = np.empty((len(frontier_alphas), len(frontier_rates)), dtype=np.float64)
    for ai, alpha in enumerate(frontier_alphas):
        for ri, rate in enumerate(frontier_rates):
            match = [
                p
                for p in artifacts.frontier_points
                if p.alpha_true_per_s == alpha and p.true_rate_cps == rate
            ]
            frontier_map[ai, ri] = match[0].relative_error if match else float("nan")
    figures["usability_frontier.png"] = phase_c_usability_frontier_figure(
        np.array(frontier_rates),
        np.array(frontier_alphas),
        frontier_map,
        artifacts.metrics.usable_continuous_rate_cps,
    )

    figures["wall_effect_sensitivity.png"] = phase_c_wall_effect_figure(
        artifacts.wall_effect_alphas,
        artifacts.wall_effect_weights,
        artifacts.wall_effect_errors,
    )

    return figures


def _acf_fitted(analysis: ContinuousNoiseAnalysis) -> npt.NDArray[np.float64]:
    from he3sim.analysis.continuous_noise import _acf_model

    return _acf_model(
        analysis.acf_lags_s,
        analysis.acf_fit.alpha_per_s,
        analysis.acf_fit.alpha_e_per_s,
        analysis.acf_fit.phi,
        analysis.acf_fit.psi1,
        analysis.acf_fit.psi2,
    )


def _report_html(artifacts: PhaseCArtifacts) -> str:
    metrics = artifacts.metrics
    cards = [
        (
            "连续 ACF 拟合",
            f"α 估计相对误差 ≤ {metrics.maximum_continuous_acf_error:.2%}",
            "continuous_acf_fit.png",
            "连续电压自协方差函数及其含脉冲衰减项 α_e 的双指数拟合。",
        ),
        (
            "连续 VTM 拟合",
            f"α 估计相对误差 ≤ {metrics.maximum_continuous_vtm_error:.2%}",
            "continuous_vtm_fit.png",
            "电压方差均值比 VTM(T) 拟合，含 α_e 形状项。",
        ),
        (
            "Wiener 去卷积",
            f"去卷积残差比 {artifacts.primary_analysis.deconv_result.residual_ratio:.4f}",
            "deconvolution_comparison.png",
            "原始波形、去卷积结果与阈值化脉冲的对比。",
        ),
        (
            "γ–NSR 稳定域",
            f"扫描 {len(artifacts.gamma_nsr_scan['gamma_grid'])}×"
            f"{len(artifacts.gamma_nsr_scan['nsr_grid'])} 网格",
            "gamma_nsr_heatmap.png",
            "Wiener 去卷积在不同正则化强度和噪信比下的重建残差。",
        ),
        (
            "双探测器 CCF/CTM",
            "互协方差自动消除脉冲自项",
            "ccf_ctm.png",
            "CCF 和 CTM 消除单探测器脉冲形状自项与非关联电子噪声。",
        ),
        (
            "可用边界",
            f"连续信号共同可用约 {metrics.usable_continuous_rate_cps:.0f} cps",
            "usability_frontier.png",
            "连续信号法在各 (α, 计数率) 网格点的 α 复原相对误差。",
        ),
        (
            "壁效应敏感性",
            r"壁效应权重对 α 反演的影响",
            "wall_effect_sensitivity.png",
            "不同壁效应分量权重下连续 ACF 的 α 复原误差。",
        ),
    ]
    figures_html = "".join(
        f"<section><h2>{html.escape(title)}</h2><p class='metric'>{html.escape(metric)}</p>"
        f"<img src='{name}' alt='{html.escape(title)}'><p>{html.escape(note)}</p></section>"
        for title, metric, name, note in cards
    )
    result = "通过" if metrics.passed else "未通过"
    style = (
        '<style>body{font-family:"Microsoft YaHei",sans-serif;max-width:1040px;'
        "margin:32px auto;padding:0 20px;color:#2f3437;line-height:1.6}"
        "h1,h2{color:#244a68}.summary{background:#eef3f6;padding:18px;"
        "border-left:5px solid #356b9a}.metric{font-weight:700;color:#d06f18}"
        "img{width:100%;height:auto;border:1px solid #d9dee2}section{margin:42px 0}"
        "code{background:#f3f5f6;padding:2px 5px}</style>"
    )
    summary = (
        f'<div class="summary"><strong>自动验收：{result}</strong><br>'
        f"连续 ACF 最大相对误差：{metrics.maximum_continuous_acf_error:.2%}；"
        f"连续 VTM 最大相对误差：{metrics.maximum_continuous_vtm_error:.2%}。<br>"
        "本报告仅使用 synthetic_demo 纯瞬发模型；不含交互仪表盘。</div>"
    )
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>Phase C 验收报告</title>{style}</head><body>"
        "<h1>Phase C：连续信号中子噪声分析</h1>"
        f"{summary}<h2>技术摘要</h2><p>连续信号 ACF/VTM 在纯瞬发数字孪生波形上直接"
        "拟合含脉冲衰减常数 α_e 的模型。Wiener 去卷积扫描 γ–NSR 稳定域，量化实际可用"
        "正则化范围。双探测器 CCF/CTM 自动消除单通道脉冲自项。可用边界扫描证明脉冲"
        "计数受死时间/堆积限制的工况下连续信号法仍可复原 α。</p>"
        f"{figures_html}<h2>范围边界</h2><p>未实现缓发中子、全输运 Phase D、"
        "逆问题 ML、反应堆真实数据接入或交互仪表盘。双探测器仅使用同一中子场数字孪生"
        "信号，未经 DT5800 或真实电子学验证（Phase HIL 已跳过）。</p></body></html>"
    )


def write_phase_c_validation_report(
    output_directory: str | Path,
    base_config: He3SimConfig,
    artifacts: PhaseCArtifacts,
) -> Path:
    """Write seven PNG figures plus offline HTML and JSON for Phase C."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    figures = _figure_map(artifacts)
    for name, figure in figures.items():
        figure.savefig(output / name, dpi=PNG_DPI, bbox_inches="tight")
        plt.close(figure)
    from he3sim.config import config_hash

    payload: dict[str, Any] = {
        "result": "passed" if artifacts.metrics.passed else "failed",
        "config_hash": config_hash(base_config),
        "seed": artifacts.seed,
        "metrics": asdict(artifacts.metrics),
        "recovery_points": [asdict(point) for point in artifacts.recovery_points],
        "figures": list(figures),
        "scope": (
            "Phase C synthetic continuous-signal noise analysis; no HIL or interactive dashboard"
        ),
    }
    (output / "phase_c_validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = output / "phase_c_validation.html"
    report.write_text(_report_html(artifacts), encoding="utf-8")
    return report
