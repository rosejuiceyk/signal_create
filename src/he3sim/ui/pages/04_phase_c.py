"""Phase C continuous-signal noise analysis page."""

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from he3sim.analysis.continuous_noise import (
    analyze_continuous_noise,
    pulse_kernel_samples,
    wiener_deconvolution,
)
from he3sim.analysis.figures import (
    BLUE,
    GOLD,
    ORANGE,
    _new_figure,
)
from he3sim.config import He3SimConfig, SourceModelKind, load_config
from he3sim.physics.events import simulate_true_events
from he3sim.physics.pulse_models import double_exponential_peak_value
from he3sim.ui.runtime import resource_path

SESSION_KEY = "phase_c_data"


def _gen_voltage(rate, dur, alpha, k_eff, efficiency, seed, tau_r, tau_d):
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

    sr = 2_000_000.0
    samples = int(np.round(sim.duration_s * sr))
    voltage = np.zeros(samples, dtype=np.float64)
    peak_val = double_exponential_peak_value(tau_r, tau_d)
    klen = int(np.ceil(8.0 * tau_d * sr))
    delays = np.arange(klen, dtype=np.float64) / sr
    kernel = (np.exp(-delays / tau_d) - np.exp(-delays / tau_r)) / peak_val * 0.15
    for t in times:
        onset = int(np.floor(t * sr))
        if onset < 0:
            continue
        end = min(onset + klen, samples)
        length = end - onset
        if length > 0:
            voltage[onset:end] += kernel[:length]
    rng = np.random.default_rng(seed or 0)
    voltage += rng.normal(0.0, 0.001, samples)
    return voltage, times, sim.duration_s, sr


st.title("连续信号噪声分析")
st.caption("连续 ACF / VTM / Wiener 去卷积")

with st.form("phase_c_form"):
    c1, c2, c3 = st.columns(3)
    with c1:
        rate = st.number_input("计数率 (cps)", 100.0, 50000.0, 3000.0, 100.0)
    with c2:
        alpha_true = st.number_input("α 真值 (s⁻¹)", 100.0, 10000.0, 1000.0, 100.0)
    with c3:
        duration = st.number_input("观察时长 (s)", 0.1, 20.0, 3.0, 0.5)

    c4, c5 = st.columns(2)
    with c4:
        k_eff = st.number_input(
            "k_eff",
            0.05,
            0.95,
            0.85,
            0.01,
            key="pc_k_input",
            help="可直接键入，也可使用输入框右侧的加减按钮微调。",
        )
    with c5:
        efficiency = st.number_input(
            "探测效率 ε",
            0.10,
            0.90,
            0.30,
            0.01,
            key="pc_e_input",
            help="可直接键入，也可使用输入框右侧的加减按钮微调。",
        )

    c6, c7 = st.columns(2)
    with c6:
        tau_r = st.number_input("脉冲 τ_r (s)", 1e-7, 1e-3, 1e-6, 1e-6, format="%.1e")
    with c7:
        tau_d = st.number_input("脉冲 τ_d (s)", 1e-6, 1e-2, 1e-5, 1e-6, format="%.1e")

    seed = st.number_input("随机种子", 0, 99999999, 20260720)

    deconv_gamma = st.number_input(
        "Wiener 正则化 γ",
        0.0,
        1.0,
        0.01,
        0.001,
        format="%.4f",
        help="值越大，去卷积越平滑；可直接键入精确值。",
    )
    submitted = st.form_submit_button("运行分析", type="primary", use_container_width=True)

if submitted:
    with st.spinner("生成电压波形..."):
        voltage, times, dur, sr = _gen_voltage(
            rate,
            duration,
            alpha_true,
            k_eff,
            efficiency,
            seed,
            tau_r,
            tau_d,
        )
    with st.spinner("分析连续 ACF / VTM / 去卷积..."):
        analysis = analyze_continuous_noise(
            voltage,
            sr,
            tau_r,
            tau_d,
            alpha_true,
            max_lag_s=0.01,
            deconv_gamma=deconv_gamma,
        )

        kernel = pulse_kernel_samples(sr, tau_r, tau_d)
        deconv = wiener_deconvolution(voltage, kernel, gamma=deconv_gamma, nsr=0.01)
        threshold = 2.0 * np.std(deconv.deconvolved)
        plot_end = min(5000, len(voltage))
        deconvolved = deconv.deconvolved[:plot_end].copy()
        peaks = np.flatnonzero(np.abs(deconvolved) >= threshold)[:200]
        st.session_state[SESSION_KEY] = {
            "event_count": int(times.size),
            "sample_count": len(voltage),
            "duration_s": dur,
            "sample_rate_hz": sr,
            "alpha_true": alpha_true,
            "gamma": deconv_gamma,
            "acf_lags_s": analysis.acf_lags_s.copy(),
            "acf_values": analysis.acf_values.copy(),
            "acf_fit": analysis.acf_fit,
            "voltage": voltage[:plot_end].copy(),
            "deconvolved": deconvolved,
            "peak_indices": peaks,
            "residual_ratio": deconv.residual_ratio,
        }

if SESSION_KEY in st.session_state:
    data = st.session_state[SESSION_KEY]
    acf_fit = data["acf_fit"]
    alpha_true = data["alpha_true"]
    sr = data["sample_rate_hz"]
    st.info(
        f"{data['event_count']} 个事件，{data['sample_count']} 采样点，"
        f"{data['duration_s']:.1f}s"
    )

    st.subheader("连续 ACF 拟合")
    m1, m2 = st.columns(2)
    m1.metric("ACF α 估计", f"{acf_fit.alpha_per_s:.1f} s⁻¹")
    m2.metric("相对误差", f"{(acf_fit.alpha_per_s / alpha_true - 1.0) * 100:+.1f}%")

    fig, ax = _new_figure("连续 ACF", "含 α_e 截断的纯指数拟合")
    ax.plot(
        data["acf_lags_s"] * 1e3,
        data["acf_values"],
        color=BLUE,
        linewidth=0.8,
        label="ACF(θ)",
    )
    fitted_acf = acf_fit.baseline + acf_fit.phi * np.exp(
        -acf_fit.alpha_per_s * data["acf_lags_s"]
    )
    ax.plot(
        data["acf_lags_s"] * 1e3,
        fitted_acf,
        color=ORANGE,
        linewidth=1.5,
        label="拟合",
    )
    ax.set_xlabel("时间差 θ (ms)")
    ax.set_ylabel("归一化 ACF")
    ax.legend(frameon=False)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    st.subheader("Wiener 去卷积")
    plot_end = len(data["voltage"])
    t_axis = np.arange(plot_end) / sr * 1e3

    f2, axes = plt.subplots(3, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(t_axis, data["voltage"], color=BLUE, linewidth=0.6)
    axes[0].set_ylabel("原始 (V)")
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(t_axis, data["deconvolved"], color=ORANGE, linewidth=0.6)
    axes[1].set_ylabel("去卷积")
    axes[1].grid(True, alpha=0.3)
    peaks = data["peak_indices"]
    if peaks.size:
        axes[2].vlines(t_axis[peaks[:200]], 0, 1, color=GOLD, linewidth=0.8)
    axes[2].set_ylabel("阈值化脉冲")
    axes[2].set_xlabel("时间 (ms)")
    axes[2].set_ylim(0, 1.5)
    axes[2].grid(True, alpha=0.3)
    f2.suptitle(
        f"Wiener 去卷积 (γ={data['gamma']}, 残差={data['residual_ratio']:.6f})",
        fontsize=10,
    )
    f2.tight_layout()
    st.pyplot(f2)
    plt.close(f2)
