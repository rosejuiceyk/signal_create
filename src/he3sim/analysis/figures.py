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
