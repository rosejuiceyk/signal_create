"""Phase 1 statistical report and diagnostic-figure writers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "he3sim-matplotlib"),
)
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np

from he3sim.analysis.counting_stats import ArrivalValidationArtifacts


def write_arrival_validation_report(
    output_directory: str | Path,
    artifacts: ArrivalValidationArtifacts,
) -> Path:
    """Write JSON, Markdown, count histogram, and interval-CDF diagnostics."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    report_dict = artifacts.report.to_dict()
    json_path = output / "arrival_validation.json"
    json_path.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    markdown_lines = [
        "# Phase 1 arrival validation",
        "",
        f"- Result: `{'passed' if artifacts.report.passed else 'failed'}`",
        f"- True rate: `{artifacts.report.true_rate_cps:g} cps`",
        f"- Validation duration: `{artifacts.report.validation_duration_s:g} s`",
        f"- Expected count per replicate: `{artifacts.report.expected_count:g}`",
        f"- Replicates: `{artifacts.report.replicates}`",
        f"- Seed: `{artifacts.report.seed}`",
        "",
        "| Algorithm | Count mean | Count variance | Fano | Count mean rel. error | "
        "Interval n | Interval mean (s) | Theory 1/lambda (s) | Interval mean rel. error | "
        "Exp(1) KS | KS tolerance | Pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, stats in artifacts.report.algorithms.items():
        markdown_lines.append(
            f"| `{name}` | {stats.count_mean:.6g} | {stats.count_variance:.6g} | "
            f"{stats.fano_factor:.6g} | {stats.mean_relative_error:.6g} | "
            f"{stats.interval_sample_size} | {stats.interval_mean_s:.6g} | "
            f"{stats.theoretical_interval_mean_s:.6g} | "
            f"{stats.interval_mean_relative_error:.6g} | "
            f"{stats.exponential_ks_distance:.6g} | "
            f"{stats.exponential_ks_distance_tolerance:.6g} | {stats.passed} |"
        )
    markdown_lines.extend(
        [
            "",
            "The interval checks use empirical CDF distances with deterministic tolerances; "
            "no single fragile p-value is used.",
            "",
        ]
    )
    markdown_path = output / "arrival_validation.md"
    markdown_path.write_text("\n".join(markdown_lines), encoding="utf-8")

    figure, axis = plt.subplots(figsize=(8, 5))
    count_arrays = list(artifacts.counts.values())
    minimum = min(int(np.min(values)) for values in count_arrays)
    maximum = max(int(np.max(values)) for values in count_arrays)
    bins = np.arange(minimum - 0.5, maximum + 1.5).tolist()
    for name, values in artifacts.counts.items():
        axis.hist(values, bins=bins, alpha=0.55, label=name, density=True)
    axis.axvline(artifacts.report.expected_count, color="black", linestyle="--", label="lambda*T")
    axis.set_xlabel("Event count per replicate")
    axis.set_ylabel("Probability density")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output / "count_histogram.png", dpi=150)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(8, 5))
    for name, interval_values in artifacts.scaled_intervals.items():
        sorted_values = np.sort(interval_values)
        empirical = np.arange(1, sorted_values.size + 1) / sorted_values.size
        axis.plot(sorted_values, empirical, label=name, alpha=0.8)
    grid = np.linspace(0.0, 6.0, 300)
    axis.plot(grid, -np.expm1(-grid), "k--", label="Exp(1) CDF")
    axis.set_xlim(0.0, 6.0)
    axis.set_xlabel("Scaled interval lambda*dt")
    axis.set_ylabel("CDF")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output / "interval_cdf.png", dpi=150)
    plt.close(figure)
    return json_path
