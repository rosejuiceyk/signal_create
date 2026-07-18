"""Phase A statistical validation data and static PNG/HTML report generation."""

from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt

from he3sim.analysis.counting_stats import exponential_ks_distance
from he3sim.analysis.figures import (
    phase_a_chain_tree_figure,
    phase_a_degeneracy_figure,
    phase_a_event_raster_figure,
    phase_a_fano_figure,
    phase_a_interval_distribution_figure,
    phase_a_rate_sweep_figure,
)
from he3sim.config import He3SimConfig, SourceModelConfig, SourceModelKind, config_hash
from he3sim.physics.arrivals import PoissonUniformArrivalGenerator
from he3sim.physics.chains import BranchingChainGenerator, ChainTraceNode
from he3sim.physics.rate_profiles import ConstantRateProfile
from he3sim.physics.source_model import PromptSourceModel

DEFAULT_VALIDATION_EVENTS = 12_000
DEFAULT_RATE_SWEEP_EVENTS = 5_000
DEFAULT_TRACE_CHAIN_LIMIT = 512
PNG_DPI = 160


@dataclass(frozen=True, slots=True)
class PhaseAValidationMetrics:
    """Decision metrics displayed in the Phase A validation report."""

    expected_rate_cps: float
    observed_correlated_rate_cps: float
    observed_rate_relative_error: float
    short_interval_threshold_s: float
    short_interval_excess: float
    maximum_correlated_fano: float
    maximum_rate_sweep_relative_error: float
    degeneracy_k_eff: float
    degeneracy_ks_distance: float
    degeneracy_ks_tolerance: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible metric mapping."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PhaseAValidationArtifacts:
    """Precomputed plot data and metrics; figure functions do no statistics."""

    metrics: PhaseAValidationMetrics
    seed: int
    k_eff: float
    alpha_per_s: float
    raster_duration_s: float
    poisson_raster_times_s: npt.NDArray[np.float64]
    correlated_raster_times_s: npt.NDArray[np.float64]
    interval_centers_s: npt.NDArray[np.float64]
    poisson_interval_density: npt.NDArray[np.float64]
    correlated_interval_density: npt.NDArray[np.float64]
    exponential_interval_density: npt.NDArray[np.float64]
    gate_widths_s: npt.NDArray[np.float64]
    poisson_fano: npt.NDArray[np.float64]
    correlated_fano: npt.NDArray[np.float64]
    k_eff_values: npt.NDArray[np.float64]
    observed_rates_cps: npt.NDArray[np.float64]
    analytic_rates_cps: npt.NDArray[np.float64]
    trace_chain_id: int
    trace_nodes: tuple[ChainTraceNode, ...]
    degeneracy_interval_centers: npt.NDArray[np.float64]
    degeneracy_density: npt.NDArray[np.float64]
    degeneracy_exponential_density: npt.NDArray[np.float64]


def count_fano_by_gate(
    times_s: npt.NDArray[np.float64],
    duration_s: float,
    gate_widths_s: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Compute count variance-to-mean for non-overlapping gates."""
    values = np.asarray(times_s, dtype=np.float64)
    gates = np.asarray(gate_widths_s, dtype=np.float64)
    if values.ndim != 1 or gates.ndim != 1:
        raise ValueError("times and gate widths must be one-dimensional")
    if not np.isfinite(duration_s) or duration_s <= 0.0:
        raise ValueError("duration_s must be finite and positive")
    if np.any(~np.isfinite(gates)) or np.any(gates <= 0.0):
        raise ValueError("gate widths must be finite and positive")
    factors = np.empty(gates.size, dtype=np.float64)
    for index, gate_width_s in enumerate(gates):
        gate_count = int(np.floor(duration_s / gate_width_s))
        if gate_count < 2:
            raise ValueError("each gate width requires at least two complete gates")
        edges = np.arange(gate_count + 1, dtype=np.float64) * gate_width_s
        counts, _ = np.histogram(values, bins=edges)
        mean = float(np.mean(counts))
        factors[index] = float(np.var(counts, ddof=1) / mean) if mean > 0.0 else np.nan
    return factors


def interval_density(
    intervals_s: npt.NDArray[np.float64],
    bin_edges_s: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Return bin midpoints and normalized interval density."""
    intervals = np.asarray(intervals_s, dtype=np.float64)
    edges = np.asarray(bin_edges_s, dtype=np.float64)
    if intervals.ndim != 1 or edges.ndim != 1:
        raise ValueError("intervals and bin edges must be one-dimensional")
    if edges.size < 2 or np.any(~np.isfinite(edges)) or np.any(np.diff(edges) <= 0.0):
        raise ValueError("bin edges must be finite and strictly increasing")
    if np.any(~np.isfinite(intervals)) or np.any(intervals <= 0.0):
        raise ValueError("intervals must be finite and positive")
    density, _ = np.histogram(intervals, bins=edges, density=True)
    centers = 0.5 * (edges[:-1] + edges[1:])
    density = density.astype(np.float64, copy=False)
    density[density <= 0.0] = np.nan
    return centers, density


def _source_config_with_k(config: SourceModelConfig, k_eff: float) -> SourceModelConfig:
    raw = config.model_dump(mode="python")
    status_source = config.k_eff or config.reactivity
    if status_source is None:
        raise ValueError("source_model requires k_eff or reactivity for Phase A validation")
    raw["kind"] = SourceModelKind.CORRELATED.value
    raw["k_eff"] = {
        "value": k_eff,
        "status": status_source.status.value,
        "source": status_source.source,
        "reviewed_by": status_source.reviewed_by,
        "reviewed_at": status_source.reviewed_at,
        "notes": "Derived validation sweep from the configured source model.",
    }
    raw["reactivity"] = None
    return SourceModelConfig.model_validate(raw)


def _sample_correlated(
    model: PromptSourceModel,
    duration_s: float,
    rng: np.random.Generator,
    source_config: SourceModelConfig,
    trace_chain_limit: int = 0,
) -> tuple[npt.NDArray[np.float64], tuple[ChainTraceNode, ...]]:
    expected_reactions = model.source_rate_cps * duration_s / (1.0 - model.k_eff)
    if expected_reactions > source_config.max_total_reactions:
        raise ValueError(
            "Phase A validation exceeds source_model.max_total_reactions; "
            "raise the explicit guard or reduce validation_events"
        )
    generator = BranchingChainGenerator(
        model,
        max_events=max(1, int(np.ceil(model.expected_detected_rate_cps * duration_s * 3.0))),
        max_chain_generation=source_config.max_chain_generation,
        max_total_reactions=source_config.max_total_reactions,
        trace_chain_limit=trace_chain_limit,
    )
    batch = generator.sample_with_lineage(
        ConstantRateProfile(model.source_rate_cps),
        0.0,
        duration_s,
        rng,
    )
    return batch.times_s, batch.trace_nodes


def _analysis_times(
    times_s: npt.NDArray[np.float64],
    trim_s: float,
    duration_s: float,
) -> npt.NDArray[np.float64]:
    selected = times_s[(times_s >= trim_s) & (times_s < duration_s)] - trim_s
    if selected.size < 2:
        raise RuntimeError("Phase A validation produced too few post-transient events")
    return selected


def _select_trace(nodes: tuple[ChainTraceNode, ...]) -> tuple[int, tuple[ChainTraceNode, ...]]:
    grouped: dict[int, list[ChainTraceNode]] = {}
    for node in nodes:
        grouped.setdefault(node.chain_id, []).append(node)
    if not grouped:
        raise RuntimeError("Phase A validation did not capture a traceable chain")

    def score(item: tuple[int, list[ChainTraceNode]]) -> tuple[bool, bool, int]:
        _, chain_nodes = item
        reactions = {node.reaction for node in chain_nodes}
        return (
            "detection" in reactions and "fission" in reactions,
            "detection" in reactions,
            len(chain_nodes),
        )

    chain_id, selected = max(grouped.items(), key=score)
    return chain_id, tuple(selected)


def build_phase_a_validation(
    config: He3SimConfig,
    validation_events: int = DEFAULT_VALIDATION_EVENTS,
    rate_sweep_events: int = DEFAULT_RATE_SWEEP_EVENTS,
) -> PhaseAValidationArtifacts:
    """Compute deterministic Phase A evidence for all required static figures."""
    if validation_events < 1_000 or rate_sweep_events < 1_000:
        raise ValueError("Phase A validation requires at least 1000 events per statistical view")
    if config.metadata.seed.value is None:
        raise ValueError("Phase A validation requires an explicit seed")
    if not config.source_model.has_correlated_parameters():
        raise ValueError("Phase A validation requires correlated source_model parameters")
    model = PromptSourceModel.from_config(config.source_model)
    seed = int(config.metadata.seed.value)
    rngs = tuple(np.random.default_rng(child) for child in np.random.SeedSequence(seed).spawn(10))

    trim_s = 10.0 / model.alpha_per_s
    analysis_duration_s = validation_events / model.expected_detected_rate_cps
    total_duration_s = trim_s + analysis_duration_s
    correlated_raw, trace_nodes = _sample_correlated(
        model,
        total_duration_s,
        rngs[0],
        config.source_model,
        trace_chain_limit=DEFAULT_TRACE_CHAIN_LIMIT,
    )
    poisson_raw = PoissonUniformArrivalGenerator().sample(
        ConstantRateProfile(model.expected_detected_rate_cps),
        0.0,
        total_duration_s,
        rngs[1],
    )
    correlated_times = _analysis_times(correlated_raw, trim_s, total_duration_s)
    poisson_times = _analysis_times(poisson_raw, trim_s, total_duration_s)
    observed_rate = correlated_times.size / analysis_duration_s
    observed_rate_error = (
        abs(observed_rate - model.expected_detected_rate_cps) / model.expected_detected_rate_cps
    )

    raster_duration_s = min(analysis_duration_s, max(50.0 / model.expected_detected_rate_cps, 0.02))
    poisson_raster = poisson_times[poisson_times < raster_duration_s]
    correlated_raster = correlated_times[correlated_times < raster_duration_s]

    poisson_intervals = np.diff(poisson_times)
    correlated_intervals = np.diff(correlated_times)
    combined_intervals = np.concatenate((poisson_intervals, correlated_intervals))
    upper = float(np.quantile(combined_intervals, 0.997))
    interval_edges = np.linspace(0.0, upper, 70)
    interval_centers, poisson_density = interval_density(poisson_intervals, interval_edges)
    _, correlated_density = interval_density(correlated_intervals, interval_edges)
    exponential_density = model.expected_detected_rate_cps * np.exp(
        -model.expected_detected_rate_cps * interval_centers
    )
    short_threshold_s = 0.2 / model.expected_detected_rate_cps
    short_expected = -np.expm1(-model.expected_detected_rate_cps * short_threshold_s)
    short_observed = float(np.mean(correlated_intervals <= short_threshold_s))
    short_interval_excess = short_observed / short_expected - 1.0

    minimum_gate_s = 0.2 / model.expected_detected_rate_cps
    maximum_gate_s = min(40.0 / model.expected_detected_rate_cps, analysis_duration_s / 50.0)
    gate_widths = np.geomspace(minimum_gate_s, maximum_gate_s, 14)
    poisson_fano = count_fano_by_gate(poisson_times, analysis_duration_s, gate_widths)
    correlated_fano = count_fano_by_gate(correlated_times, analysis_duration_s, gate_widths)
    maximum_correlated_fano = float(np.nanmax(correlated_fano))

    k_candidates = np.asarray([1.0e-6, 0.1, model.k_eff, 0.4, 0.6], dtype=np.float64)
    k_values = np.unique(k_candidates[(k_candidates > 0.0) & (k_candidates < 1.0)])
    observed_rates = np.empty(k_values.size, dtype=np.float64)
    analytic_rates = np.empty(k_values.size, dtype=np.float64)
    sweep_rngs = rngs[2 : 2 + k_values.size]
    for index, (k_eff, rng) in enumerate(zip(k_values, sweep_rngs, strict=True)):
        sweep_config = _source_config_with_k(config.source_model, float(k_eff))
        sweep_model = PromptSourceModel.from_config(sweep_config)
        sweep_trim_s = 10.0 / sweep_model.alpha_per_s
        sweep_analysis_s = rate_sweep_events / sweep_model.expected_detected_rate_cps
        sweep_total_s = sweep_trim_s + sweep_analysis_s
        sweep_raw, _ = _sample_correlated(
            sweep_model,
            sweep_total_s,
            rng,
            sweep_config,
        )
        sweep_times = _analysis_times(sweep_raw, sweep_trim_s, sweep_total_s)
        observed_rates[index] = sweep_times.size / sweep_analysis_s
        analytic_rates[index] = sweep_model.expected_detected_rate_cps
    rate_sweep_relative_errors = np.abs(observed_rates - analytic_rates) / analytic_rates
    maximum_rate_sweep_error = float(np.max(rate_sweep_relative_errors))

    degeneracy_k = 1.0e-9
    degeneracy_config = _source_config_with_k(config.source_model, degeneracy_k)
    degeneracy_model = PromptSourceModel.from_config(degeneracy_config)
    degeneracy_trim_s = 10.0 / degeneracy_model.alpha_per_s
    degeneracy_analysis_s = validation_events / degeneracy_model.expected_detected_rate_cps
    degeneracy_total_s = degeneracy_trim_s + degeneracy_analysis_s
    degeneracy_raw, _ = _sample_correlated(
        degeneracy_model,
        degeneracy_total_s,
        rngs[7],
        degeneracy_config,
    )
    degeneracy_times = _analysis_times(
        degeneracy_raw,
        degeneracy_trim_s,
        degeneracy_total_s,
    )
    scaled_degeneracy_intervals = (
        np.diff(degeneracy_times) * degeneracy_model.expected_detected_rate_cps
    )
    degeneracy_edges = np.geomspace(1.0e-3, 8.0, 55)
    degeneracy_centers, degeneracy_density = interval_density(
        scaled_degeneracy_intervals,
        degeneracy_edges,
    )
    degeneracy_exponential = np.exp(-degeneracy_centers)
    degeneracy_ks = exponential_ks_distance(scaled_degeneracy_intervals)
    degeneracy_tolerance = float(max(0.03, 4.0 / np.sqrt(scaled_degeneracy_intervals.size)))

    trace_chain_id, selected_trace = _select_trace(trace_nodes)
    passed = bool(
        observed_rate_error <= 0.03
        and maximum_rate_sweep_error <= 0.05
        and maximum_correlated_fano > 1.05
        and degeneracy_ks <= degeneracy_tolerance
    )
    metrics = PhaseAValidationMetrics(
        expected_rate_cps=model.expected_detected_rate_cps,
        observed_correlated_rate_cps=observed_rate,
        observed_rate_relative_error=observed_rate_error,
        short_interval_threshold_s=short_threshold_s,
        short_interval_excess=short_interval_excess,
        maximum_correlated_fano=maximum_correlated_fano,
        maximum_rate_sweep_relative_error=maximum_rate_sweep_error,
        degeneracy_k_eff=degeneracy_k,
        degeneracy_ks_distance=degeneracy_ks,
        degeneracy_ks_tolerance=degeneracy_tolerance,
        passed=passed,
    )
    return PhaseAValidationArtifacts(
        metrics=metrics,
        seed=seed,
        k_eff=model.k_eff,
        alpha_per_s=model.alpha_per_s,
        raster_duration_s=raster_duration_s,
        poisson_raster_times_s=poisson_raster,
        correlated_raster_times_s=correlated_raster,
        interval_centers_s=interval_centers,
        poisson_interval_density=poisson_density,
        correlated_interval_density=correlated_density,
        exponential_interval_density=exponential_density,
        gate_widths_s=gate_widths,
        poisson_fano=poisson_fano,
        correlated_fano=correlated_fano,
        k_eff_values=k_values,
        observed_rates_cps=observed_rates,
        analytic_rates_cps=analytic_rates,
        trace_chain_id=trace_chain_id,
        trace_nodes=selected_trace,
        degeneracy_interval_centers=degeneracy_centers,
        degeneracy_density=degeneracy_density,
        degeneracy_exponential_density=degeneracy_exponential,
    )


def _phase_a_html(config: He3SimConfig, artifacts: PhaseAValidationArtifacts) -> str:
    metrics = artifacts.metrics
    result = "PASSED" if metrics.passed else "FAILED"
    result_class = "pass" if metrics.passed else "fail"
    figures = [
        (
            "Event clustering is visible at fixed first-moment rate",
            "event_raster.png",
            "The aligned raster compares equal expected rates. Local bursts in the "
            "correlated row are physical chain clustering, not a rate mismatch.",
        ),
        (
            "Short intervals exceed the exponential baseline",
            "interval_distribution.png",
            "The log-density comparison exposes the short-lag excess while retaining "
            "the same exponential reference used for the Poisson baseline.",
        ),
        (
            "Gate counts are super-Poisson",
            "fano_vs_gate.png",
            "Fano factors are computed before plotting. Values above one quantify "
            "chain-driven count covariance over gate width.",
        ),
        (
            "The simulated mean follows S*epsilon/(1-k_eff)",
            "mean_rate_vs_k.png",
            "The rate sweep tests the first-moment mapping independently at several "
            "subcritical multiplication factors.",
        ),
        (
            "A traced source neutron produces a physical prompt chain",
            "chain_tree.png",
            "This tree uses parent-child records captured directly by the generator; "
            "no schematic nodes or reactions are invented by the figure.",
        ),
        (
            "The branching process returns to the Poisson limit",
            "degeneracy_limit.png",
            "At near-zero multiplication, scaled intervals are compared with Exp(1); "
            "the annotated KS distance is computed in the validation layer.",
        ),
    ]
    figure_sections = "\n".join(
        (
            f"<section><h2>{html.escape(title)}</h2>"
            f"<p>{html.escape(description)}</p>"
            f'<img src="{name}" alt="{html.escape(title)}"></section>'
        )
        for title, name, description in figures
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phase A correlated-neutron validation</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;max-width:1100px;margin:0 auto;
padding:32px;color:#2f3437;background:#fafafa;line-height:1.55}}
h1,h2{{line-height:1.2}}
.summary,section{{background:white;border:1px solid #d9dee2;padding:20px;margin:18px 0}}
.pass{{color:#356b9a}} .fail{{color:#b34234}}
table{{border-collapse:collapse;width:100%}}
th,td{{padding:8px;border-bottom:1px solid #d9dee2;text-align:left}}
img{{display:block;width:100%;height:auto;margin-top:12px}}
code{{background:#eef1f3;padding:2px 4px}}
</style></head><body>
<h1>Phase A pure-prompt correlated-neutron validation</h1>
<div class="summary"><h2 class="{result_class}">Technical summary: {result}</h2>
<p>The configured source-on pure-prompt model is checked against an equal-rate Poisson
baseline, the analytic first moment, gate-count dispersion, a traced physical chain,
and the near-zero multiplication limit.</p>
<table><tr><th>Metric</th><th>Value</th><th>Acceptance</th></tr>
<tr><td>Observed rate relative difference</td>
<td>{metrics.observed_rate_relative_error:.3%}</td><td>&le; 3%</td></tr>
<tr><td>Maximum rate-sweep relative difference</td>
<td>{metrics.maximum_rate_sweep_relative_error:.3%}</td><td>&le; 5%</td></tr>
<tr><td>Maximum correlated Fano</td>
<td>{metrics.maximum_correlated_fano:.4f}</td><td>&gt; 1.05</td></tr>
<tr><td>Near-zero-limit KS distance</td>
<td>{metrics.degeneracy_ks_distance:.4f}</td>
<td>&le; {metrics.degeneracy_ks_tolerance:.4f}</td></tr></table></div>
{figure_sections}
<section><h2>Scope, definitions, and method</h2><p>Expected detector rate is
<code>S*epsilon/(1-k_eff)</code>. Statistics exclude the first
<code>10/alpha</code> seconds only for post-startup validation; production events still
follow the approved source-on-window convention. Fano factors use non-overlapping
gates, and all random streams derive from seed {artifacts.seed}.</p></section>
<section><h2>Limitations and next review</h2><p>This report validates a one-speed
pure-prompt point model with synthetic demonstration parameters. It does not establish
delayed-neutron, transport, reactor-data, Phase B noise-inversion, DT5800, or
hardware-control validity. No interactive dashboard is included.</p></section>
<section><h2>Provenance</h2><p>Configuration hash:
<code>{config_hash(config)}</code>. k_eff={artifacts.k_eff:.6g};
alpha={artifacts.alpha_per_s:.6g} s^-1; parameter evidence remains recorded in the
configuration.</p></section>
</body></html>"""


def write_phase_a_validation_report(
    output_directory: str | Path,
    config: He3SimConfig,
    artifacts: PhaseAValidationArtifacts,
) -> Path:
    """Write six PNG figures, metrics JSON, and one offline technical HTML report."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    figure_map = {
        "event_raster.png": phase_a_event_raster_figure(
            artifacts.poisson_raster_times_s,
            artifacts.correlated_raster_times_s,
            artifacts.raster_duration_s,
            artifacts.metrics.expected_rate_cps,
            artifacts.k_eff,
            artifacts.alpha_per_s,
        ),
        "interval_distribution.png": phase_a_interval_distribution_figure(
            artifacts.interval_centers_s,
            artifacts.poisson_interval_density,
            artifacts.correlated_interval_density,
            artifacts.exponential_interval_density,
            artifacts.metrics.expected_rate_cps,
            artifacts.metrics.short_interval_excess,
        ),
        "fano_vs_gate.png": phase_a_fano_figure(
            artifacts.gate_widths_s,
            artifacts.poisson_fano,
            artifacts.correlated_fano,
            artifacts.metrics.maximum_correlated_fano,
        ),
        "mean_rate_vs_k.png": phase_a_rate_sweep_figure(
            artifacts.k_eff_values,
            artifacts.observed_rates_cps,
            artifacts.analytic_rates_cps,
            artifacts.metrics.maximum_rate_sweep_relative_error,
        ),
        "chain_tree.png": phase_a_chain_tree_figure(
            artifacts.trace_nodes,
            artifacts.trace_chain_id,
        ),
        "degeneracy_limit.png": phase_a_degeneracy_figure(
            artifacts.degeneracy_interval_centers,
            artifacts.degeneracy_density,
            artifacts.degeneracy_exponential_density,
            artifacts.metrics.degeneracy_k_eff,
            artifacts.metrics.degeneracy_ks_distance,
        ),
    }
    for name, figure in figure_map.items():
        figure.savefig(output / name, dpi=PNG_DPI, bbox_inches="tight")
        plt.close(figure)
    payload = {
        "result": "passed" if artifacts.metrics.passed else "failed",
        "seed": artifacts.seed,
        "config_hash": config_hash(config),
        "metrics": artifacts.metrics.to_dict(),
        "figures": list(figure_map),
        "scope": "Phase A pure-prompt source-on validation; no interactive dashboard",
    }
    (output / "phase_a_validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    html_path = output / "phase_a_validation.html"
    html_path.write_text(_phase_a_html(config, artifacts), encoding="utf-8")
    return html_path
