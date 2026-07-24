"""Event generation page."""

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from he3sim.analysis.figures import BLUE, CHARCOAL, ORANGE, _new_figure
from he3sim.config import He3SimConfig, SourceModelKind, load_config
from he3sim.physics.events import simulate_true_events
from he3sim.ui.runtime import resource_path

SESSION_KEY = "events_data"


def _build_config(source_model, true_rate_cps, duration_s, k_eff, alpha, efficiency, seed):
    base = load_config(resource_path("configs/demo_minimal.yaml"))
    raw = base.model_dump(mode="python")
    raw["metadata"]["seed"]["value"] = seed
    raw["simulation"]["true_rate_cps"]["value"] = true_rate_cps
    raw["observation"]["mode"] = "fixed_duration"
    raw["observation"]["duration_s"] = {
        "value": duration_s,
        "status": "synthetic_demo",
        "notes": "UI-configured duration.",
    }
    if source_model == "correlated":
        raw["source_model"]["kind"] = "correlated"
        raw["source_model"]["k_eff"]["value"] = k_eff
        raw["source_model"]["alpha"]["value"] = alpha
        raw["source_model"]["detection_efficiency"]["value"] = efficiency
        rate = raw["simulation"]["true_rate_cps"]["value"]
        raw["source_model"]["source_rate_cps"]["value"] = rate * (1.0 - k_eff) / efficiency
        raw["source_model"]["max_total_reactions"] = 2_000_000
    else:
        raw["source_model"]["kind"] = "poisson"
    raw["observation"].pop("target_event_count", None)
    raw["observation"].pop("min_duration_s", None)
    raw["observation"].pop("max_duration_s", None)
    return He3SimConfig.model_validate(raw)


def _plot_event_raster(p_times, c_times, dur, rate):
    fig, ax = _new_figure("事件时序分布", f"预期率 {rate:.1f} cps，时长 {dur:.2f} s", (10, 3.5))
    if p_times.size:
        ax.vlines(p_times, 1.1, 1.9, color=BLUE, linewidth=0.8, label="Poisson")
    if c_times.size:
        ax.vlines(c_times, 0.1, 0.9, color=ORANGE, linewidth=0.8, label="Correlated")
    ax.set_xlim(0, dur)
    ax.set_ylim(0, 2)
    ax.set_yticks([0.5, 1.5], ["Correlated", "Poisson"])
    ax.set_xlabel("时间 (s)")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    return fig


def _plot_interval_loglog(times, rate, label):
    if times.size < 2:
        return None
    intervals = np.diff(times)
    intervals = intervals[intervals > 0]
    if intervals.size < 2:
        return None
    fig, ax = _new_figure("间隔分布", f"{label}，平均率 {rate:.1f} cps")
    bins = np.geomspace(intervals.min() * 0.5, intervals.max() * 2, 60)
    ax.hist(intervals, bins=bins, density=True, alpha=0.7, color=ORANGE)
    x = np.geomspace(intervals.min(), intervals.max(), 200)
    ax.plot(x, rate * np.exp(-rate * x), "--", color=CHARCOAL, label=f"Exp({rate:.1f})")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("间隔 (s)")
    ax.set_ylabel("概率密度")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


st.title("事件生成与统计")
st.caption("生成泊松（非相关）或纯瞬发分支过程相关中子事件")

col1, col2, col3 = st.columns(3)
with col1:
    source_model = st.selectbox("源模型", ["poisson", "correlated"], index=0)
with col2:
    true_rate_cps = st.number_input("真实计数率 (cps)", 10.0, 1000000.0, 2000.0, 100.0)
with col3:
    duration_s = st.number_input("观察时长 (s)", 0.01, 100.0, 1.0, 0.1)

k_eff = 0.7
alpha_per_s = 1000.0
efficiency = 0.3
if source_model == "correlated":
    c1, c2, c3 = st.columns(3)
    with c1:
        k_eff = st.number_input(
            "k_eff",
            0.05,
            0.95,
            0.70,
            0.01,
            key="evt_k_input",
            help="可直接键入，也可使用输入框右侧的加减按钮微调。",
        )
    with c2:
        alpha_per_s = st.number_input("prompt α (s⁻¹)", 100.0, 10000.0, 1000.0, 100.0)
    with c3:
        efficiency = st.number_input(
            "探测效率 ε",
            0.05,
            0.95,
            0.30,
            0.01,
            key="evt_e_input",
            help="可直接键入，也可使用输入框右侧的加减按钮微调。",
        )

seed = st.number_input("随机种子", 0, 99999999, 20260720)

if st.button("生成事件", type="primary", use_container_width=True):
    with st.spinner("正在生成事件..."):
        try:
            config = _build_config(
                source_model, true_rate_cps, duration_s, k_eff, alpha_per_s, efficiency, seed
            )
            source_kind = (
                SourceModelKind.CORRELATED
                if source_model == "correlated"
                else SourceModelKind.POISSON
            )
            sim = simulate_true_events(
                config,
                max_expected_events=max(10000, int(true_rate_cps * duration_s * 2)),
                source_model=source_kind,
            )
            poisson_times = np.array([], dtype=np.float64)
            if source_model == "correlated":
                poisson_config = _build_config(
                    "poisson",
                    true_rate_cps,
                    sim.duration_s,
                    k_eff,
                    alpha_per_s,
                    efficiency,
                    seed + 1,
                )
                poisson_sim = simulate_true_events(
                    poisson_config,
                    max_expected_events=max(10000, int(true_rate_cps * sim.duration_s * 2)),
                    source_model=SourceModelKind.POISSON,
                )
                poisson_times = poisson_sim.events["t_s"].astype(np.float64)

            lineage = sim.lineage
            st.session_state[SESSION_KEY] = {
                "times": sim.events["t_s"].astype(np.float64),
                "poisson_times": poisson_times,
                "duration_s": sim.duration_s,
                "rate_cps": sim.true_rate_cps,
                "source_model": source_model,
                "chain_count": (
                    int(np.max(lineage["chain_id"]) + 1)
                    if lineage is not None and lineage.size
                    else 0
                ),
                "max_generation": (
                    int(np.max(lineage["generation"]))
                    if lineage is not None and lineage.size
                    else 0
                ),
            }
        except Exception as e:
            st.error(f"生成失败：{e}")
            st.stop()

if SESSION_KEY in st.session_state:
    data = st.session_state[SESSION_KEY]
    times = data["times"]
    stored_rate = data["rate_cps"]
    stored_model = data["source_model"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("事件数", int(times.size))
    m2.metric("实际时长", f"{data['duration_s']:.3f} s")
    m3.metric("实际率", f"{times.size / data['duration_s']:.1f} cps")
    m4.metric("源模型", stored_model)

    if stored_model == "poisson":
        fig = _plot_event_raster(times, np.array([]), data["duration_s"], stored_rate)
        if fig:
            st.pyplot(fig)
            plt.close(fig)
        fig2 = _plot_interval_loglog(times, times.size / data["duration_s"], "Poisson")
        if fig2:
            st.pyplot(fig2)
            plt.close(fig2)
    else:
        poisson_times = data["poisson_times"]
        fig = _plot_event_raster(poisson_times, times, data["duration_s"], stored_rate)
        if fig:
            st.pyplot(fig)
            plt.close(fig)
        c1, c2 = st.columns(2)
        with c1:
            fig2 = _plot_interval_loglog(
                poisson_times, poisson_times.size / data["duration_s"], "Poisson"
            )
            if fig2:
                st.pyplot(fig2)
                plt.close(fig2)
        with c2:
            fig3 = _plot_interval_loglog(times, times.size / data["duration_s"], "Correlated")
            if fig3:
                st.pyplot(fig3)
                plt.close(fig3)

        st.subheader("裂变链统计")
        cc1, cc2 = st.columns(2)
        cc1.metric("总链数", data["chain_count"])
        cc2.metric("最大代数", data["max_generation"])
