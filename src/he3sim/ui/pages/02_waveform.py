"""Continuous waveform generation page."""

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from he3sim.analysis.figures import BLUE, GREY, LIGHT_GREY, ORANGE
from he3sim.config import He3SimConfig, load_config
from he3sim.physics.events import simulate_true_events
from he3sim.physics.pulse_models import (
    double_exponential_peak_value,
)
from he3sim.ui.runtime import resource_path

SESSION_KEY = "waveform_data"


def _generate_waveform(config, sample_rate, tau_r, tau_d):
    sim = simulate_true_events(config, max_expected_events=1_000_000)
    times = sim.events["t_s"].astype(np.float64)
    if times.size == 0:
        return None, times, sim.duration_s

    effective_rate = min(sample_rate, 2_000_000.0)
    sample_count = int(np.round(sim.duration_s * effective_rate))
    if sample_count > 10_000_000:
        st.warning(f"波形过长 ({sample_count} 采样点)，截断至 1000 万点")
        sample_count = 10_000_000

    voltage = np.zeros(sample_count, dtype=np.float64)
    peak_val = double_exponential_peak_value(tau_r, tau_d)
    kernel_len = int(np.ceil(8.0 * tau_d * effective_rate))
    delays = np.arange(kernel_len, dtype=np.float64) / effective_rate
    kernel = (np.exp(-delays / tau_d) - np.exp(-delays / tau_r)) / peak_val * 0.15

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
    return voltage, times, sim.duration_s


st.title("连续波形生成")
st.caption("双指数脉冲叠加生成前放模拟电压")

c1, c2, c3, c4 = st.columns(4)
with c1:
    source_model = st.selectbox("源模型", ["poisson", "correlated"], index=0)
with c2:
    true_rate_cps = st.number_input("计数率 (cps)", 10.0, 100000.0, 2000.0, 100.0)
with c3:
    duration_s = st.number_input("时长 (s)", 0.01, 10.0, 0.5, 0.1)
with c4:
    sample_rate_hz = st.selectbox("采样率 (MS/s)", [1, 2, 5, 10, 25, 50, 100], index=2)

sample_rate = sample_rate_hz * 1_000_000.0

if source_model == "correlated":
    st.caption("相关源模型参数")
    cr1, cr2, cr3 = st.columns(3)
    with cr1:
        corr_k_eff = st.number_input(
            "k_eff",
            0.05,
            0.95,
            0.70,
            0.01,
            key="wf_k_input",
            help="可直接键入，也可使用输入框右侧的加减按钮微调。",
        )
    with cr2:
        corr_alpha = st.number_input("α (s⁻¹)", 100.0, 10000.0, 1000.0, 100.0)
    with cr3:
        corr_eff = st.number_input(
            "探测效率 ε",
            0.05,
            0.90,
            0.30,
            0.01,
            key="wf_e_input",
            help="可直接键入，也可使用输入框右侧的加减按钮微调。",
        )
else:
    corr_k_eff = 0.7
    corr_alpha = 1000.0
    corr_eff = 0.3

st.caption("脉冲形状参数")
cc1, cc2 = st.columns(2)
with cc1:
    tau_r = st.number_input("τ_r (s)", 1e-7, 1e-3, 1e-6, 1e-6, format="%.1e")
with cc2:
    tau_d = st.number_input("τ_d (s)", 1e-6, 1e-2, 1e-5, 1e-6, format="%.1e")

seed = st.number_input("随机种子", 0, 99999999, 20260720)
show_length = st.number_input(
    "显示区间 (ms)",
    0.5,
    50.0,
    10.0,
    1.0,
    key="wf_show_input",
    help="生成后保存本次选择的显示区间。",
)

if st.button("生成波形", type="primary", use_container_width=True):
    with st.spinner("生成事件..."):
        base = load_config(resource_path("configs/demo_minimal.yaml"))
        raw = base.model_dump(mode="python")
        raw["metadata"]["seed"]["value"] = seed
        raw["simulation"]["true_rate_cps"]["value"] = true_rate_cps
        raw["observation"]["mode"] = "fixed_duration"
        raw["observation"]["duration_s"] = {
            "value": duration_s,
            "status": "synthetic_demo",
            "notes": "UI-configured.",
        }
        if source_model == "correlated":
            raw["source_model"]["kind"] = "correlated"
            raw["source_model"]["k_eff"]["value"] = corr_k_eff
            raw["source_model"]["alpha"]["value"] = corr_alpha
            raw["source_model"]["detection_efficiency"]["value"] = corr_eff
            raw["source_model"]["source_rate_cps"]["value"] = (
                true_rate_cps * (1.0 - corr_k_eff) / corr_eff
            )
            raw["source_model"]["max_total_reactions"] = 2_000_000
        else:
            raw["source_model"]["kind"] = "poisson"
        raw["observation"].pop("target_event_count", None)
        raw["observation"].pop("min_duration_s", None)
        raw["observation"].pop("max_duration_s", None)
        config = He3SimConfig.model_validate(raw)

    with st.spinner("生成波形..."):
        voltage, times, dur = _generate_waveform(config, sample_rate, tau_r, tau_d)

    if voltage is None or times.size == 0:
        st.warning("未生成任何事件")
    else:
        effective_rate = min(sample_rate, 2_000_000.0)
        plot_samples = min(int(show_length * effective_rate / 1000.0), len(voltage))
        st.session_state[SESSION_KEY] = {
            "voltage": voltage[:plot_samples].copy(),
            "time_axis_ms": np.arange(plot_samples) / effective_rate * 1000.0,
            "window_times": times[times < show_length / 1000.0].copy(),
            "detail_times": times[:200].copy(),
            "event_count": int(times.size),
            "sample_count": len(voltage),
            "duration_s": dur,
            "source_model": source_model,
            "rate_cps": true_rate_cps,
            "show_length_ms": show_length,
        }

if SESSION_KEY in st.session_state:
    data = st.session_state[SESSION_KEY]
    m1, m2, m3 = st.columns(3)
    m1.metric("事件数", data["event_count"])
    m2.metric("采样点数", data["sample_count"])
    m3.metric("实际时长", f"{data['duration_s']:.3f} s")

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(data["time_axis_ms"], data["voltage"], color=BLUE, linewidth=0.6)
    for t in data["window_times"][:80]:
        ax.axvline(t * 1000.0, color=ORANGE, alpha=0.4, linewidth=0.5)
    ax.set_xlabel("时间 (ms)")
    ax.set_ylabel("模拟电压 (V)")
    ax.set_title(
        f"连续波形 ({data['source_model']}, {data['rate_cps']:.0f} cps)",
        loc="left",
        fontsize=10,
        color=GREY,
    )
    ax.grid(True, color=LIGHT_GREY, alpha=0.5)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    if data["detail_times"].size > 0:
        st.subheader("事件详情（前 200 个）")
        detail_df = {"时间 (ms)": data["detail_times"] * 1000.0}
        st.dataframe(detail_df, use_container_width=True)
