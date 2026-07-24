"""Pulse-counting noise analysis page (Rossi-alpha / Feynman-alpha / PSD)."""

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from he3sim.analysis.figures import (
    BLUE,
    GREY,
    LIGHT_GREY,
    ORANGE,
    phase_b_feynman_figure,
    phase_b_psd_figure,
    phase_b_rossi_figure,
)
from he3sim.analysis.noise import analyze_event_noise
from he3sim.config import He3SimConfig, SourceModelKind, load_config
from he3sim.physics.events import simulate_true_events
from he3sim.physics.pulse_models import double_exponential_peak_value
from he3sim.ui.runtime import resource_path

SESSION_KEY = "phase_b_data"


def _gen_events_and_waveform(rate, dur, alpha, k_eff, efficiency, seed):
    base = load_config(resource_path("configs/demo_minimal.yaml"))
    raw = base.model_dump(mode="python")
    raw["metadata"]["seed"]["value"] = seed
    raw["simulation"]["true_rate_cps"]["value"] = rate
    raw["observation"]["mode"] = "fixed_duration"
    raw["observation"]["duration_s"] = {"value": dur, "status": "synthetic_demo"}
    raw["source_model"]["kind"] = "correlated"
    raw["source_model"]["k_eff"]["value"] = k_eff
    raw["source_model"]["alpha"]["value"] = alpha
    raw["source_model"]["detection_efficiency"]["value"] = efficiency
    raw["source_model"]["source_rate_cps"]["value"] = rate * (1.0 - k_eff) / efficiency
    raw["source_model"]["max_total_reactions"] = 2_000_000
    raw["observation"].pop("target_event_count", None)
    raw["observation"].pop("min_duration_s", None)
    raw["observation"].pop("max_duration_s", None)
    config = He3SimConfig.model_validate(raw)
    sim = simulate_true_events(
        config, max_expected_events=500000, source_model=SourceModelKind.CORRELATED
    )
    times = sim.events["t_s"].astype(np.float64)
    # Generate waveform snippet for display
    effective_rate = 2_000_000.0  # capped at 2 MS/s
    show_dur = min(dur, 0.05)
    samples = int(show_dur * effective_rate)
    voltage = np.zeros(samples, dtype=np.float64)
    peak_val = double_exponential_peak_value(1e-6, 1e-5)
    klen = int(np.ceil(8.0 * 1e-5 * effective_rate))
    delays = np.arange(klen, dtype=np.float64) / effective_rate
    kernel = (np.exp(-delays / 1e-5) - np.exp(-delays / 1e-6)) / peak_val * 0.15
    for t in times[times < show_dur]:
        onset = int(np.floor(t * effective_rate))
        if onset < 0:
            continue
        end = min(onset + klen, samples)
        if end - onset > 0:
            voltage[onset:end] += kernel[: end - onset]
    rng = np.random.default_rng(seed or 0)
    voltage += rng.normal(0.0, 0.001, samples)
    return times, sim.duration_s, float(alpha), voltage, effective_rate


st.title("脉冲模式噪声分析")
st.caption("Rossi-α / Feynman-α / PSD（Cohn-α）三种估计器")

with st.form("phase_b_form"):
    c1, c2, c3 = st.columns(3)
    with c1:
        true_rate = st.number_input("计数率 (cps)", 100.0, 50000.0, 3000.0, 100.0)
    with c2:
        alpha_true = st.number_input("prompt α 真值 (s⁻¹)", 100.0, 10000.0, 1000.0, 100.0)
    with c3:
        duration = st.number_input("观察时长 (s)", 0.1, 50.0, 10.0, 0.5)

    c4, c5 = st.columns(2)
    with c4:
        k_eff = st.number_input(
            "k_eff",
            0.05,
            0.95,
            0.70,
            0.01,
            help="可直接键入，也可使用输入框右侧的加减按钮微调。",
        )
    with c5:
        efficiency = st.number_input(
            "探测效率 ε",
            0.05,
            0.90,
            0.30,
            0.01,
            help="可直接键入，也可使用输入框右侧的加减按钮微调。",
        )

    seed = st.number_input("随机种子", 0, 99999999, 42)
    bootstrap_reps = st.slider("bootstrap 重复次数", 0, 32, 8)
    submitted = st.form_submit_button("运行分析", type="primary", use_container_width=True)

if submitted:
    with st.spinner("生成相关事件与波形..."):
        times, dur, alpha, voltage, eff_rate = _gen_events_and_waveform(
            true_rate, duration, alpha_true, k_eff, efficiency, seed
        )

    if times.size < 100:
        st.error(f"事件数不足 ({times.size} < 100)，请增加时长或计数率")
    else:
        with st.spinner("拟合 Rossi-α / Feynman-α / PSD..."):
            analysis = analyze_event_noise(
                times,
                dur,
                bootstrap_replicates=bootstrap_reps,
                seed=seed + 10000,
            )
        samples_show = min(len(voltage), int(0.05 * eff_rate))
        st.session_state[SESSION_KEY] = {
            "event_count": int(times.size),
            "duration_s": dur,
            "alpha_true": alpha,
            "voltage": voltage[:samples_show].copy(),
            "effective_rate": eff_rate,
            "window_times": times[times < 0.05].copy(),
            "analysis": analysis,
        }

if SESSION_KEY in st.session_state:
    data = st.session_state[SESSION_KEY]
    analysis = data["analysis"]
    alpha = data["alpha_true"]
    voltage = data["voltage"]
    eff_rate = data["effective_rate"]
    st.info(
        f"生成 {data['event_count']} 个事件，"
        f"观察率 {data['event_count'] / data['duration_s']:.1f} cps"
    )

    st.subheader("连续电压波形（前 50 ms）")
    samples_show = len(voltage)
    t_axis = np.arange(samples_show) / eff_rate * 1e3
    fig_wf, ax_wf = plt.subplots(figsize=(10, 2.5))
    ax_wf.plot(t_axis, voltage, color=BLUE, linewidth=0.5)
    for t in data["window_times"][:60]:
        ax_wf.axvline(t * 1e3, color=ORANGE, alpha=0.35, linewidth=0.5)
    ax_wf.set_xlabel("时间 (ms)")
    ax_wf.set_ylabel("电压 (V)")
    ax_wf.grid(True, color=LIGHT_GREY, alpha=0.5)
    ax_wf.set_title("双指数脉冲叠加波形（橙色线 = 事件到达时刻）", fontsize=9, color=GREY)
    fig_wf.tight_layout()
    st.pyplot(fig_wf)
    plt.close(fig_wf)

    m1, m2, m3 = st.columns(3)
    m1.metric(
        "Rossi-α",
        f"{analysis.rossi.fit.alpha_per_s:.1f} s⁻¹",
        delta=f"{(analysis.rossi.fit.alpha_per_s / alpha - 1.0) * 100:+.1f}%",
    )
    m2.metric(
        "Feynman-α",
        f"{analysis.feynman.fit.alpha_per_s:.1f} s⁻¹",
        delta=f"{(analysis.feynman.fit.alpha_per_s / alpha - 1.0) * 100:+.1f}%",
    )
    m3.metric(
        "PSD",
        f"{analysis.psd.fit.alpha_per_s:.1f} s⁻¹",
        delta=f"{(analysis.psd.fit.alpha_per_s / alpha - 1.0) * 100:+.1f}%",
    )

    # Figures - vertical layout
    st.subheader("拟合结果")
    st.markdown("#### Rossi-α 时间差拟合")
    fig_r = phase_b_rossi_figure(
        analysis.rossi.x,
        analysis.rossi.observed,
        analysis.rossi.fitted,
        analysis.rossi.fit.alpha_per_s,
        alpha,
        analysis.rossi.fit.amplitude,
        analysis.rossi.fit.baseline,
    )
    st.pyplot(fig_r)
    plt.close(fig_r)

    st.markdown("#### Feynman-α 方差均值比拟合")
    fig_f = phase_b_feynman_figure(
        analysis.feynman.x,
        analysis.feynman.observed,
        analysis.feynman.fitted,
        analysis.feynman.fit.alpha_per_s,
        alpha,
        analysis.feynman.fit.amplitude,
    )
    st.pyplot(fig_f)
    plt.close(fig_f)

    st.markdown("#### PSD 洛伦兹拟合")
    fig_p = phase_b_psd_figure(
        analysis.psd.x,
        analysis.psd.observed,
        analysis.psd.fitted,
        analysis.psd.fit.alpha_per_s,
        alpha,
        analysis.psd.fit.amplitude,
    )
    st.pyplot(fig_p)
    plt.close(fig_p)
