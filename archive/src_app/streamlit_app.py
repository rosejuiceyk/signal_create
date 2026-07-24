"""Streamlit page for bounded local continuous-waveform generation."""

from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st

from he3sim.app.web_backend import (
    MAX_WEB_WAVEFORM_SAMPLES,
    InteractiveWaveformRequest,
    estimate_waveform_resources,
    generate_interactive_waveform,
    maximum_interactive_duration,
    read_sample_rows,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASE_CONFIG = PROJECT_ROOT / "configs" / "demo_minimal.yaml"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "web_runs"
MAX_BROWSER_CSV_DOWNLOAD_BYTES = 50 * 1024 * 1024


def _base_config_path() -> Path:
    """Return the configured base YAML path, allowing isolated UI tests."""
    return Path(os.environ.get("HE3SIM_WEB_BASE_CONFIG", DEFAULT_BASE_CONFIG))


def _output_root() -> Path:
    """Return the local run root, allowing isolated UI tests."""
    return Path(os.environ.get("HE3SIM_WEB_OUTPUT_ROOT", DEFAULT_OUTPUT_ROOT))


def _format_bytes(value: int) -> str:
    """Format a byte count for a compact metric display."""
    units = ("B", "KiB", "MiB", "GiB")
    scaled = float(value)
    for unit in units:
        if scaled < 1024.0 or unit == units[-1]:
            return f"{scaled:,.2f} {unit}"
        scaled /= 1024.0
    raise AssertionError("unreachable byte unit")


def render_app() -> None:
    """Render and execute the Phase 3.5 local Web workflow."""
    st.set_page_config(page_title="He-3 连续波形生成", layout="wide")
    st.title("He-3 连续波形生成器")

    col_rate, col_sample, col_duration = st.columns(3)
    with col_rate:
        true_rate_cps = st.number_input(
            "真实计数率 (cps)",
            min_value=10.0,
            max_value=10_000_000.0,
            value=100_000.0,
            step=1_000.0,
            help="允许范围：10～10,000,000 cps。输入的是死时间之前的真实到达率。",
        )
        st.caption("允许范围：10～10,000,000 cps")
    with col_sample:
        sample_rate_msps = st.number_input(
            "采样率 (MS/s)",
            min_value=100.0,
            max_value=250.0,
            value=250.0,
            step=10.0,
            help="允许范围：100～250 MS/s。",
        )
        st.caption("允许范围：100～250 MS/s")
    duration_limit = maximum_interactive_duration(
        float(true_rate_cps),
        float(sample_rate_msps) * 1.0e6,
    )
    maximum_duration_ms = duration_limit.maximum_duration_s * 1.0e3
    sample_limited_ms = duration_limit.sample_limited_duration_s * 1.0e3
    event_limited_ms = duration_limit.event_limited_duration_s * 1.0e3
    duration_key = "interactive_duration_ms"
    if duration_key not in st.session_state:
        st.session_state[duration_key] = min(0.1, maximum_duration_ms)
    elif float(st.session_state[duration_key]) > maximum_duration_ms:
        st.session_state[duration_key] = maximum_duration_ms
    with col_duration:
        duration_ms = st.number_input(
            "观察时间 (ms)",
            min_value=0.001,
            max_value=maximum_duration_ms,
            step=0.1,
            format="%.6f",
            key=duration_key,
            help=(
                f"当前最大 {maximum_duration_ms:.6f} ms；采样点上限对应 "
                f"{sample_limited_ms:.6f} ms，预期事件上限对应 "
                f"{event_limited_ms:.6f} ms，取两者较小值。"
            ),
        )
        limiting_name = (
            "采样点数上限"
            if duration_limit.limiting_constraint == "sample_count"
            else "预期事件数上限"
        )
        st.caption(f"当前最大：{maximum_duration_ms:.6f} ms（由{limiting_name}决定）")
        st.caption(f"允许范围：0.001～{maximum_duration_ms:.6f} ms")
    seed = st.number_input(
        "随机种子",
        min_value=0,
        max_value=2_147_483_647,
        value=20_260_711,
        step=1,
        help="允许范围：0～2,147,483,647。相同配置和 seed 可复现。",
    )
    st.caption("允许范围：0～2,147,483,647")

    request = InteractiveWaveformRequest(
        true_rate_cps=float(true_rate_cps),
        sample_rate_hz=float(sample_rate_msps) * 1.0e6,
        duration_s=float(duration_ms) * 1.0e-3,
        seed=int(seed),
    )
    st.caption(
        f"本地网页单次最多生成 {MAX_WEB_WAVEFORM_SAMPLES:,} 个采样点。"
        "采样点数约等于观察时间乘以采样率，并额外包含零时刻；"
        "这是防止内存、CSV 和绘图文件过大的软件保护，不是探测器或采集设备限制。"
    )
    try:
        estimate = estimate_waveform_resources(request)
    except ValueError as exc:
        st.error(f"资源预检未通过：{exc}")
        return

    st.subheader("生成前资源预估")
    metric_events, metric_samples, metric_interval, metric_bytes = st.columns(4)
    metric_events.metric("预期事件数", f"{estimate.expected_event_count:,.2f}")
    metric_samples.metric("采样点数", f"{estimate.sample_count:,}")
    metric_interval.metric("采样间隔", f"{estimate.sample_interval_s * 1.0e9:.3f} ns")
    metric_bytes.metric(
        "原始波形数组约占",
        _format_bytes(estimate.estimated_waveform_payload_bytes),
    )
    st.caption(
        "估算按每点 float32 裁剪前电压、float32 裁剪后电压、uint16 ADC 和 "
        "bool 饱和标记共 11 bytes 计算；"
        "HDF5 压缩、元数据和绘图过程会使实际磁盘与峰值内存不同。"
    )
    submitted = st.button("生成连续波形", type="primary")

    if not submitted:
        return

    try:
        with st.spinner("正在生成事件、连续波形和图片……"):
            result = generate_interactive_waveform(
                request,
                base_config_path=_base_config_path(),
                output_root=_output_root(),
            )
            sample_rows = read_sample_rows(result.waveform_path)
            sampling_info = json.loads(result.sampling_info_path.read_text(encoding="utf-8"))
    except (OSError, RuntimeError, ValueError) as exc:
        st.error(f"生成失败：{exc}")
        return

    st.success("连续波形生成完成")
    result_events, result_renderer = st.columns(2)
    result_events.metric("实际真值事件数", f"{result.actual_event_count:,}")
    result_renderer.metric("渲染后端", result.renderer)

    st.image(str(result.image_path), caption="连续波形总览、模拟电压细节与 ADC 细节")
    st.subheader("前 12 个采样点")
    st.dataframe(sample_rows, use_container_width=True, hide_index=True)

    st.subheader("采样与产物信息")
    st.json(sampling_info)
    st.code(str(result.run_directory), language=None)
    download_col1, download_col2, download_col3 = st.columns(3)
    with download_col1:
        st.download_button(
            "下载波形图片 PNG",
            data=result.image_path.read_bytes(),
            file_name=result.image_path.name,
            mime="image/png",
        )
    with download_col2:
        st.download_button(
            "下载采样信息 JSON",
            data=result.sampling_info_path.read_bytes(),
            file_name=result.sampling_info_path.name,
            mime="application/json",
        )
    with download_col3:
        csv_size = result.csv_path.stat().st_size
        if csv_size <= MAX_BROWSER_CSV_DOWNLOAD_BYTES:
            with result.csv_path.open("rb") as csv_stream:
                st.download_button(
                    "下载两列波形 CSV",
                    data=csv_stream,
                    file_name=result.csv_path.name,
                    mime="text/csv",
                )
        else:
            st.info(
                f"CSV 已保存到本地，大小为 {_format_bytes(csv_size)}；"
                "为避免浏览器占用过多内存，不提供页面内下载。"
            )
    st.caption(
        "waveform.csv 仅含 time_s 和 voltage_V 两列；完整 HDF5 同时保存在本地。"
        "页面不会把大型 HDF5 整体读入浏览器。"
    )


if __name__ == "__main__":
    render_app()
