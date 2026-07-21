"""Phase B alpha-recovery, dead-time-bias, and static-report workflow."""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from matplotlib.figure import Figure

from he3sim.acquisition.dead_time import apply_dead_time
from he3sim.analysis.figures import (
    phase_b_alpha_parity_figure,
    phase_b_bootstrap_figure,
    phase_b_deadtime_bias_figure,
    phase_b_feynman_figure,
    phase_b_method_agreement_figure,
    phase_b_psd_figure,
    phase_b_rossi_figure,
)
from he3sim.analysis.noise import (
    NoiseAnalysis,
    analyze_event_noise,
    feynman_alpha,
    hazama_vtm_correction,
    refit_feynman_curve,
)
from he3sim.config import DeadTimeMode, He3SimConfig, SourceModelKind, config_hash
from he3sim.physics.events import simulate_true_events

DEFAULT_ALPHA_TOLERANCE = 0.05
DEFAULT_BOOTSTRAP_REPLICATES = 16
DEFAULT_RECOVERY_EVENTS = 220_000
DEFAULT_DEADTIME_EVENTS = 150_000
PHASE_B_DEAD_TIME_S = 4.0e-6
PNG_DPI = 160
METHODS = ("Rossi-α", "Feynman-α", "PSD")


@dataclass(frozen=True, slots=True)
class RecoveryPoint:
    """One closed-loop synthetic operating point."""

    alpha_true_per_s: float
    detection_efficiency: float
    true_rate_cps: float
    duration_s: float
    event_count: int
    rossi_alpha_per_s: float
    feynman_alpha_per_s: float
    psd_alpha_per_s: float
    rossi_std_per_s: float
    feynman_std_per_s: float
    psd_std_per_s: float

    @property
    def estimates(self) -> tuple[float, float, float]:
        """Return estimates in the canonical report order."""
        return (
            self.rossi_alpha_per_s,
            self.feynman_alpha_per_s,
            self.psd_alpha_per_s,
        )

    @property
    def standard_deviations(self) -> tuple[float, float, float]:
        """Return standard deviations in the canonical report order."""
        return (self.rossi_std_per_s, self.feynman_std_per_s, self.psd_std_per_s)


@dataclass(frozen=True, slots=True)
class DeadTimePoint:
    """One Feynman-alpha point before and after VTM correction."""

    alpha_true_per_s: float
    true_rate_cps: float
    observed_rate_cps: float
    count_loss_fraction: float
    raw_alpha_per_s: float
    corrected_alpha_per_s: float


@dataclass(frozen=True, slots=True)
class PhaseBMetrics:
    """Decision metrics for the Phase B automated gate."""

    maximum_recovery_relative_error: float
    maximum_inter_method_difference: float
    bootstrap_is_conservative: bool
    deadtime_correction_improvement_fraction: float
    usable_rate_cps: float
    alpha_tolerance: float
    passed: bool


@dataclass(frozen=True, slots=True)
class PhaseBArtifacts:
    """All precomputed data needed by the pure Phase B figure functions."""

    primary_analysis: NoiseAnalysis
    primary_alpha_true_per_s: float
    recovery_points: tuple[RecoveryPoint, ...]
    deadtime_points: tuple[DeadTimePoint, ...]
    metrics: PhaseBMetrics
    seed: int


def _validation_config(
    base: He3SimConfig,
    *,
    alpha_per_s: float,
    detection_efficiency: float,
    true_rate_cps: float,
    target_events: int,
    seed: int,
    k_eff: float = 0.7,
) -> He3SimConfig:
    raw = base.model_dump(mode="python")
    raw["metadata"]["seed"]["value"] = seed
    raw["metadata"]["run_name"] = f"phaseB-alpha-{alpha_per_s:g}-rate-{true_rate_cps:g}"
    raw["source_model"]["kind"] = SourceModelKind.CORRELATED.value
    raw["source_model"]["k_eff"]["value"] = k_eff
    raw["source_model"]["alpha"]["value"] = alpha_per_s
    raw["source_model"]["detection_efficiency"]["value"] = detection_efficiency
    raw["source_model"]["source_rate_cps"]["value"] = (
        true_rate_cps * (1.0 - k_eff) / detection_efficiency
    )
    raw["source_model"]["max_total_reactions"] = max(
        1_000_000, int(np.ceil(target_events / detection_efficiency * 1.5))
    )
    raw["simulation"]["true_rate_cps"]["value"] = true_rate_cps
    raw["observation"]["mode"] = "fixed_duration"
    raw["observation"]["duration_s"] = {
        "value": target_events / true_rate_cps,
        "status": "synthetic_demo",
        "notes": "Derived Phase B validation horizon; not an instrument setting.",
    }
    raw["observation"].pop("target_event_count", None)
    raw["observation"].pop("min_duration_s", None)
    raw["observation"].pop("max_duration_s", None)
    return He3SimConfig.model_validate(raw)


def _simulate_times(config: He3SimConfig) -> tuple[npt.NDArray[np.float64], float]:
    target = config.simulation.true_rate_cps.value
    duration = config.observation.duration_s.value if config.observation.duration_s else None
    if target is None or duration is None or config.metadata.seed.value is None:
        raise ValueError("Phase B validation requires rate, fixed duration, and seed")
    maximum_events = int(np.ceil(target * duration * 1.5))
    simulation = simulate_true_events(
        config,
        max_expected_events=maximum_events,
        source_model=SourceModelKind.CORRELATED,
    )
    times = simulation.events["t_s"].astype(np.float64, copy=False)
    return times, simulation.duration_s


def _simulate_analysis(
    config: He3SimConfig, bootstrap_replicates: int
) -> tuple[NoiseAnalysis, npt.NDArray[np.float64]]:
    times, duration_s = _simulate_times(config)
    if config.metadata.seed.value is None:
        raise ValueError("Phase B validation requires a seed")
    analysis = analyze_event_noise(
        times,
        duration_s,
        bootstrap_replicates=bootstrap_replicates,
        seed=config.metadata.seed.value + 10_000,
    )
    return analysis, times


def analyze_phase_b_config(
    base_config: He3SimConfig,
    *,
    target_events: int = DEFAULT_RECOVERY_EVENTS,
    bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
) -> tuple[He3SimConfig, NoiseAnalysis]:
    """Analyze the base configuration's alpha using a strong synthetic review case."""
    source = base_config.source_model
    alpha = float(source.alpha.value) if source.alpha and source.alpha.value else 1_000.0
    seed = int(base_config.metadata.seed.value or 0)
    config = _validation_config(
        base_config,
        alpha_per_s=alpha,
        detection_efficiency=0.35,
        true_rate_cps=5_000.0,
        target_events=target_events,
        seed=seed,
    )
    analysis, _ = _simulate_analysis(config, bootstrap_replicates)
    return config, analysis


def _recovery_point(
    config: He3SimConfig, analysis: NoiseAnalysis, alpha_true_per_s: float
) -> RecoveryPoint:
    efficiency = config.source_model.detection_efficiency
    rate = config.simulation.true_rate_cps.value
    if efficiency is None or efficiency.value is None or rate is None:
        raise ValueError("recovery configuration is incomplete")
    return RecoveryPoint(
        alpha_true_per_s=alpha_true_per_s,
        detection_efficiency=float(efficiency.value),
        true_rate_cps=float(rate),
        duration_s=analysis.duration_s,
        event_count=analysis.event_count,
        rossi_alpha_per_s=analysis.rossi.fit.alpha_per_s,
        feynman_alpha_per_s=analysis.feynman.fit.alpha_per_s,
        psd_alpha_per_s=analysis.psd.fit.alpha_per_s,
        rossi_std_per_s=analysis.rossi.fit.alpha_std_per_s,
        feynman_std_per_s=analysis.feynman.fit.alpha_std_per_s,
        psd_std_per_s=analysis.psd.fit.alpha_std_per_s,
    )


def _deadtime_grid(base: He3SimConfig, target_events: int, seed: int) -> tuple[DeadTimePoint, ...]:
    points: list[DeadTimePoint] = []
    for alpha_index, alpha in enumerate((500.0, 2_000.0)):
        for rate_index, rate in enumerate((2_000.0, 10_000.0, 30_000.0, 60_000.0)):
            config = _validation_config(
                base,
                alpha_per_s=alpha,
                detection_efficiency=0.35,
                true_rate_cps=rate,
                target_events=target_events,
                seed=seed + 100 + alpha_index * 10 + rate_index,
            )
            times, duration = _simulate_times(config)
            deadtime = apply_dead_time(times, PHASE_B_DEAD_TIME_S, DeadTimeMode.NONPARALYZABLE)
            observed = times[deadtime.accepted]
            raw = feynman_alpha(observed, duration)
            corrected_y = hazama_vtm_correction(
                raw.observed, observed.size / duration, PHASE_B_DEAD_TIME_S
            )
            corrected = refit_feynman_curve(raw.x, corrected_y)
            points.append(
                DeadTimePoint(
                    alpha_true_per_s=alpha,
                    true_rate_cps=rate,
                    observed_rate_cps=float(observed.size / duration),
                    count_loss_fraction=float(1.0 - observed.size / times.size),
                    raw_alpha_per_s=raw.fit.alpha_per_s,
                    corrected_alpha_per_s=corrected.fit.alpha_per_s,
                )
            )
    return tuple(points)


def build_phase_b_validation(
    base_config: He3SimConfig,
    *,
    recovery_events: int = DEFAULT_RECOVERY_EVENTS,
    deadtime_events: int = DEFAULT_DEADTIME_EVENTS,
    bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    alpha_tolerance: float = DEFAULT_ALPHA_TOLERANCE,
) -> PhaseBArtifacts:
    """Build the multi-case alpha recovery and dead-time validation grid."""
    if recovery_events < 20_000 or deadtime_events < 20_000:
        raise ValueError("Phase B validation requires at least 20,000 events per case")
    seed = int(base_config.metadata.seed.value or 0)
    case_specs = (
        (500.0, 0.30, 3_000.0),
        (1_000.0, 0.35, 5_000.0),
        (2_000.0, 0.40, 8_000.0),
    )
    points: list[RecoveryPoint] = []
    primary: NoiseAnalysis | None = None
    primary_alpha = 1_000.0
    for index, (alpha, efficiency, rate) in enumerate(case_specs):
        config = _validation_config(
            base_config,
            alpha_per_s=alpha,
            detection_efficiency=efficiency,
            true_rate_cps=rate,
            target_events=recovery_events,
            seed=seed + index,
        )
        analysis, _ = _simulate_analysis(config, bootstrap_replicates)
        points.append(_recovery_point(config, analysis, alpha))
        if alpha == primary_alpha:
            primary = analysis
    if primary is None:
        raise RuntimeError("Phase B primary analysis was not generated")
    deadtime_points = _deadtime_grid(base_config, deadtime_events, seed)
    relative_errors = [
        abs(estimate / point.alpha_true_per_s - 1.0)
        for point in points
        for estimate in point.estimates
    ]
    method_spreads = [
        (max(point.estimates) - min(point.estimates)) / point.alpha_true_per_s for point in points
    ]
    fits = (primary.rossi.fit, primary.feynman.fit, primary.psd.fit)
    conservative = all(
        np.isfinite(fit.alpha_std_per_s) and fit.alpha_std_per_s > fit.naive_alpha_std_per_s
        for fit in fits
    )
    improved = [
        abs(point.corrected_alpha_per_s / point.alpha_true_per_s - 1.0)
        < abs(point.raw_alpha_per_s / point.alpha_true_per_s - 1.0)
        for point in deadtime_points
    ]
    rates = sorted({point.true_rate_cps for point in deadtime_points})
    usable_rates: list[float] = []
    for rate in rates:
        if all(
            abs(point.corrected_alpha_per_s / point.alpha_true_per_s - 1.0) <= alpha_tolerance
            for point in deadtime_points
            if point.true_rate_cps == rate
        ):
            usable_rates.append(rate)
        else:
            break
    usable_rate = max(usable_rates, default=float("nan"))
    metrics = PhaseBMetrics(
        maximum_recovery_relative_error=max(relative_errors),
        maximum_inter_method_difference=max(method_spreads),
        bootstrap_is_conservative=conservative,
        deadtime_correction_improvement_fraction=float(np.mean(improved)),
        usable_rate_cps=usable_rate,
        alpha_tolerance=alpha_tolerance,
        passed=(
            max(relative_errors) <= alpha_tolerance
            and max(method_spreads) <= alpha_tolerance
            and conservative
            and float(np.mean(improved)) >= 0.75
            and bool(usable_rates)
        ),
    )
    return PhaseBArtifacts(
        primary_analysis=primary,
        primary_alpha_true_per_s=primary_alpha,
        recovery_points=tuple(points),
        deadtime_points=deadtime_points,
        metrics=metrics,
        seed=seed,
    )


def _figure_map(artifacts: PhaseBArtifacts) -> dict[str, Figure]:
    analysis = artifacts.primary_analysis
    true_alpha = artifacts.primary_alpha_true_per_s
    points = artifacts.recovery_points
    true_values = np.asarray(
        [point.alpha_true_per_s for point in points for _ in METHODS], dtype=np.float64
    )
    estimates = np.asarray(
        [estimate for point in points for estimate in point.estimates], dtype=np.float64
    )
    deviations = np.asarray(
        [value for point in points for value in point.standard_deviations], dtype=np.float64
    )
    method_values = [method for _ in points for method in METHODS]
    relative = np.asarray(
        [
            [estimate / point.alpha_true_per_s - 1.0 for estimate in point.estimates]
            for point in points
        ],
        dtype=np.float64,
    )
    deadtime_alphas = sorted({point.alpha_true_per_s for point in artifacts.deadtime_points})
    deadtime_rates = np.asarray(
        sorted({point.true_rate_cps for point in artifacts.deadtime_points}), dtype=np.float64
    )
    raw = np.asarray(
        [
            [
                next(
                    point.raw_alpha_per_s / alpha
                    for point in artifacts.deadtime_points
                    if point.alpha_true_per_s == alpha and point.true_rate_cps == rate
                )
                for rate in deadtime_rates
            ]
            for alpha in deadtime_alphas
        ],
        dtype=np.float64,
    )
    corrected = np.asarray(
        [
            [
                next(
                    point.corrected_alpha_per_s / alpha
                    for point in artifacts.deadtime_points
                    if point.alpha_true_per_s == alpha and point.true_rate_cps == rate
                )
                for rate in deadtime_rates
            ]
            for alpha in deadtime_alphas
        ],
        dtype=np.float64,
    )
    bootstrap_fit = analysis.feynman.fit
    return {
        "rossi_alpha_fit.png": phase_b_rossi_figure(
            analysis.rossi.x,
            analysis.rossi.observed,
            analysis.rossi.fitted,
            analysis.rossi.fit.alpha_per_s,
            true_alpha,
            analysis.rossi.fit.amplitude,
            analysis.rossi.fit.baseline,
        ),
        "feynman_alpha_fit.png": phase_b_feynman_figure(
            analysis.feynman.x,
            analysis.feynman.observed,
            analysis.feynman.fitted,
            analysis.feynman.fit.alpha_per_s,
            true_alpha,
            analysis.feynman.fit.amplitude,
        ),
        "psd_lorentzian_fit.png": phase_b_psd_figure(
            analysis.psd.x,
            analysis.psd.observed,
            analysis.psd.fitted,
            analysis.psd.fit.alpha_per_s,
            true_alpha,
            analysis.psd.fit.amplitude,
        ),
        "alpha_recovery_parity.png": phase_b_alpha_parity_figure(
            true_values, estimates, deviations, method_values
        ),
        "method_agreement.png": phase_b_method_agreement_figure(
            [f"工况 {index + 1}" for index in range(len(points))], relative, METHODS
        ),
        "deadtime_bias.png": phase_b_deadtime_bias_figure(
            deadtime_rates,
            raw,
            corrected,
            [f"α={value:.0f} s^-1" for value in deadtime_alphas],
            artifacts.metrics.usable_rate_cps,
        ),
        "bootstrap_uncertainty.png": phase_b_bootstrap_figure(
            bootstrap_fit.bootstrap_alpha_per_s,
            bootstrap_fit.alpha_per_s,
            bootstrap_fit.naive_alpha_std_per_s,
            bootstrap_fit.alpha_std_per_s,
            true_alpha,
            "Feynman-α",
        ),
    }


def _report_html(artifacts: PhaseBArtifacts) -> str:
    metrics = artifacts.metrics
    rows = []
    for index, point in enumerate(artifacts.recovery_points, start=1):
        rows.append(
            "<tr>"
            f"<td>{index}</td><td>{point.alpha_true_per_s:.0f}</td>"
            f"<td>{point.detection_efficiency:.2f}</td><td>{point.true_rate_cps:.0f}</td>"
            f"<td>{point.rossi_alpha_per_s:.1f} ± {point.rossi_std_per_s:.1f}</td>"
            f"<td>{point.feynman_alpha_per_s:.1f} ± {point.feynman_std_per_s:.1f}</td>"
            f"<td>{point.psd_alpha_per_s:.1f} ± {point.psd_std_per_s:.1f}</td></tr>"
        )
    cards = [
        (
            "α 复原",
            f"最大相对误差 {metrics.maximum_recovery_relative_error:.2%}",
            "alpha_recovery_parity.png",
            "三种独立估计器在多组 α、探测效率与计数率下与设定真值比较。灰带是自动验收的 ±5% 范围。",
        ),
        (
            "Rossi-α",
            "时间域关联",
            "rossi_alpha_fit.png",
            "短时间差的指数关联项与长时间差的偶然符合平台同时拟合，A、B 与 α 在图内标注。",
        ),
        (
            "Feynman-α",
            "门计数方差均值比",
            "feynman_alpha_fit.png",
            "Y(T) 的上升形状给出 α，平台给出 Y∞；中心值计算与绘图逻辑分离。",
        ),
        (
            "PSD",
            "频域独立复原",
            "psd_lorentzian_fit.png",
            "计数序列的 Welch PSD 用洛伦兹函数拟合，拐点 α/2π 在图中明确标注。",
        ),
        (
            "方法一致性",
            f"最大方法间差异 {metrics.maximum_inter_method_difference:.2%}",
            "method_agreement.png",
            "并列误差用于识别方法依赖偏置；验收要求每种方法及方法间差异同时小于 5%。",
        ),
        (
            "死时间偏置",
            f"共同可用上限约 {metrics.usable_rate_cps:.0f} cps",
            "deadtime_bias.png",
            "非延长型死时间首先破坏短滞后关联。Hazama 一阶 VTM 修正明显扩大"
            "可用范围，但高损失区仍不可外推。",
        ),
        (
            "不确定度",
            "时间块 bootstrap",
            "bootstrap_uncertainty.png",
            "整段时间块重采样使各门宽/bin 同时变化，避免把相关曲线点误当作"
            "独立观测。报告值取 bootstrap 与朴素误差的保守上界。",
        ),
    ]
    figures = "".join(
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
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #d9dee2;"
        "padding:7px;text-align:right}th:first-child,td:first-child{text-align:center}"
        "code{background:#f3f5f6;padding:2px 5px}</style>"
    )
    summary = (
        f'<div class="summary"><strong>自动验收：{result}</strong><br>'
        f"最大 α 相对误差：{metrics.maximum_recovery_relative_error:.2%}；"
        f"最大方法间差异：{metrics.maximum_inter_method_difference:.2%}；"
        f"bootstrap 更保守：{metrics.bootstrap_is_conservative}。<br>"
        "本报告仅使用 synthetic_demo 纯瞬发模型，不代表反应堆或仪器标定结果。</div>"
    )
    table = (
        "<h2>闭环结果</h2><table><thead><tr><th>工况</th><th>α 真值</th>"
        "<th>效率</th><th>真率</th><th>Rossi-α</th><th>Feynman-α</th>"
        f"<th>PSD</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>Phase B 验收报告</title>{style}</head><body>"
        "<h1>Phase B：脉冲模式噪声分析与 α 复原</h1>"
        f"{summary}<h2>技术摘要</h2><p>同一事件流分别进入 Rossi-α、Feynman-α 和 "
        "PSD 估计器。拟合边界固定为 100–5000 s^-1，不读取 α 真值作为初值。"
        f"观测层把真值探测时刻视为理想触发候选，再施加现有非延长型死时间模型。</p>{table}"
        f"{figures}<h2>方法与限制</h2><p>Rossi 曲线使用离散计数互相关；Feynman 曲线"
        "使用非重叠门计数；PSD 使用 Welch 平均及对数谱拟合。Hazama 修正采用弱损失"
        "一阶形式 <code>Y_corr = Y_obs + 2 R_obs d</code>。超过可用边界后，一阶近似"
        "不应被解释为无偏校正。</p><h2>参考依据</h2><p>死时间修正：Hazama, Annals "
        "of Nuclear Energy 30 (2003), DOI 10.1016/S0306-4549(02)00091-9。"
        "不确定度处理：Endo &amp; Yamamoto, Annals of Nuclear Energy 125 (2019), "
        "DOI 10.1016/j.anucene.2018.10.032。</p><h2>范围边界</h2><p>未实现连续信号 "
        "ACF/VTM、去卷积、双探测器 CCF、DT5800 HIL、缓发平台、反应堆数据或"
        "交互仪表盘。</p></body></html>"
    )


def write_phase_b_validation_report(
    output_directory: str | Path,
    base_config: He3SimConfig,
    artifacts: PhaseBArtifacts,
) -> Path:
    """Write seven PNG figures plus offline HTML and machine-readable JSON."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    figures = _figure_map(artifacts)
    for name, figure in figures.items():
        figure.savefig(output / name, dpi=PNG_DPI, bbox_inches="tight")
        plt.close(figure)
    payload: dict[str, Any] = {
        "result": "passed" if artifacts.metrics.passed else "failed",
        "config_hash": config_hash(base_config),
        "seed": artifacts.seed,
        "metrics": asdict(artifacts.metrics),
        "recovery_points": [asdict(point) for point in artifacts.recovery_points],
        "deadtime_points": [asdict(point) for point in artifacts.deadtime_points],
        "figures": list(figures),
        "scope": "Phase B synthetic pure-prompt pulse counting; no interactive dashboard",
    }
    (output / "phase_b_validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = output / "phase_b_validation.html"
    report.write_text(_report_html(artifacts), encoding="utf-8")
    return report


def write_phase_b_analysis_report(
    output_directory: str | Path,
    config: He3SimConfig,
    analysis: NoiseAnalysis,
) -> Path:
    """Write the three single-stream fit figures and a compact JSON/HTML report."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    alpha_parameter = config.source_model.alpha
    if alpha_parameter is None or alpha_parameter.value is None:
        raise ValueError("analysis configuration requires alpha")
    true_alpha = float(alpha_parameter.value)
    figures = {
        "rossi_alpha_fit.png": phase_b_rossi_figure(
            analysis.rossi.x,
            analysis.rossi.observed,
            analysis.rossi.fitted,
            analysis.rossi.fit.alpha_per_s,
            true_alpha,
            analysis.rossi.fit.amplitude,
            analysis.rossi.fit.baseline,
        ),
        "feynman_alpha_fit.png": phase_b_feynman_figure(
            analysis.feynman.x,
            analysis.feynman.observed,
            analysis.feynman.fitted,
            analysis.feynman.fit.alpha_per_s,
            true_alpha,
            analysis.feynman.fit.amplitude,
        ),
        "psd_lorentzian_fit.png": phase_b_psd_figure(
            analysis.psd.x,
            analysis.psd.observed,
            analysis.psd.fitted,
            analysis.psd.fit.alpha_per_s,
            true_alpha,
            analysis.psd.fit.amplitude,
        ),
    }
    for name, figure in figures.items():
        figure.savefig(output / name, dpi=PNG_DPI, bbox_inches="tight")
        plt.close(figure)
    fits = (analysis.rossi.fit, analysis.feynman.fit, analysis.psd.fit)
    payload = {
        "alpha_true_per_s": true_alpha,
        "event_count": analysis.event_count,
        "observed_rate_cps": analysis.observed_rate_cps,
        "fits": {
            fit.method: {
                "alpha_per_s": fit.alpha_per_s,
                "alpha_std_per_s": fit.alpha_std_per_s,
                "naive_alpha_std_per_s": fit.naive_alpha_std_per_s,
                "amplitude": fit.amplitude,
                "baseline": fit.baseline,
                "r_squared": fit.r_squared,
            }
            for fit in fits
        },
        "figures": list(figures),
    }
    (output / "phase_b_noise.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    cards = "".join(
        f"<h2>{html.escape(fit.method)}</h2><p>α 估计 = {fit.alpha_per_s:.1f} ± "
        f"{fit.alpha_std_per_s:.1f} s^-1</p><img style='width:100%' src='{name}'>"
        for fit, name in zip(fits, figures, strict=True)
    )
    report = output / "phase_b_noise.html"
    report.write_text(
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>Phase B 噪声分析</title>"
        "<body style='font-family:Microsoft YaHei,sans-serif;max-width:1000px;margin:30px auto'>"
        f"<h1>Phase B 单工况噪声分析</h1><p>α 真值 = {true_alpha:.1f} s^-1；"
        f"事件数 = {analysis.event_count}。普通图注使用中文，专业名词保留。</p>{cards}"
        "<p>synthetic_demo；不含交互仪表盘。</p></body></html>",
        encoding="utf-8",
    )
    return report
