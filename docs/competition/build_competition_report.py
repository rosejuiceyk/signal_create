"""Build the portable competition report artifact from reviewed project evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = Path(__file__).resolve().parent
SOURCE_MARKDOWN = REPORT_DIR / "competition_registration_report_draft.md"
ARTIFACT_JSON = REPORT_DIR / "competition_registration_report_artifact.json"
HIGH_RATE_HDF5 = (
    ROOT
    / "outputs"
    / "manual_review"
    / "phase03_5"
    / "preclip_high_rate"
    / "web-20260713T161050.699272Z-acbd6468"
    / "waveform.h5"
)

GENERATED_AT = "2026-07-14T00:00:00+08:00"
TITLE = "面向高计数率 He-3 探测信号的可复现连续波形仿真平台"


def _parse_markdown() -> tuple[str, str, dict[str, str]]:
    text = SOURCE_MARKDOWN.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0].removeprefix("# ").strip()
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[1:]:
        if line.startswith("## "):
            current = line.removeprefix("## ").strip()
            sections[current] = []
        elif current is None:
            preamble.append(line)
        else:
            sections[current].append(line)
    return (
        title,
        "\n".join(preamble).strip(),
        {heading: "\n".join(body).strip() for heading, body in sections.items()},
    )


def _high_rate_rows() -> list[dict[str, object]]:
    with h5py.File(HIGH_RATE_HDF5, "r") as handle:
        event = handle["events/true"][4635]
        sample_rate_hz = float(handle["metadata"].attrs["sample_rate_hz"])
        center = int(event["sample_index"])
        offsets = np.arange(-300, 8001, 200, dtype=np.int64)
        indices = center + offsets
        preclip = handle["blocks/preclip_analog_samples"][indices]
        clipped = handle["blocks/analog_samples"][indices]
        saturation = handle["blocks/saturation_mask"][indices]

    rows: list[dict[str, object]] = []
    for offset, index, raw_value, clipped_value, saturated in zip(
        offsets,
        indices,
        preclip,
        clipped,
        saturation,
        strict=True,
    ):
        common = {
            "time_us": round(float(offset / sample_rate_hz * 1.0e6), 2),
            "sample_index": int(index),
            "saturated": bool(saturated),
            "event_id": int(event["event_id"]),
            "event_time_us": round(float(event["t_s"] * 1.0e6), 6),
            "true_rate_cps": 10_000_000,
            "sample_rate_msps": 100,
            "duration_ms": 15,
            "seed": 20_260_303,
        }
        rows.append(
            {
                **common,
                "signal": "裁剪前诊断电压",
                "voltage_V": round(float(raw_value), 6),
            }
        )
        rows.append(
            {
                **common,
                "signal": "裁剪后 ADC 输入",
                "voltage_V": round(float(clipped_value), 6),
            }
        )
    return rows


def _section_block(
    block_id: str,
    heading: str,
    sections: dict[str, str],
    *,
    source_id: str | None = None,
    preamble: str = "",
) -> dict[str, object]:
    body_parts = [f"## {heading}"]
    if preamble:
        body_parts.append(preamble)
    body_parts.append(sections[heading])
    block: dict[str, object] = {
        "id": block_id,
        "type": "markdown",
        "body": "\n\n".join(part for part in body_parts if part),
    }
    if source_id is not None:
        block["sourceId"] = source_id
    return block


def build_artifact() -> dict[str, object]:
    title, preamble, sections = _parse_markdown()
    if title != TITLE:
        raise ValueError(f"unexpected report title: {title!r}")

    source_rows = _high_rate_rows()
    metric_rows = [
        {
            "human_reviewed_phases": 4,
            "full_regression_tests": 137,
            "standard_rate_points": 13,
            "maximum_true_rate_cps": 10_000_000,
            "current_phase": "Phase 3.5",
            "current_status": "awaiting_human_review",
        }
    ]
    phase_rows = [
        {
            "phase_order": 0,
            "phase": "Phase 0",
            "result": "工程骨架、配置、类型、随机性和 CLI",
            "automatic_acceptance": "通过",
            "human_review": "通过",
        },
        {
            "phase_order": 1,
            "phase": "Phase 1",
            "result": "两种泊松到达、参数化能谱、幅值和真值事件",
            "automatic_acceptance": "通过",
            "human_review": "通过",
        },
        {
            "phase_order": 2,
            "phase": "Phase 2",
            "result": "双指数脉冲、连续波形、噪声、裁剪和 ADC",
            "automatic_acceptance": "通过",
            "human_review": "通过",
        },
        {
            "phase_order": 3,
            "phase": "Phase 3",
            "result": "触发、死时间、多尺度 HDF5 和统计验证",
            "automatic_acceptance": "通过",
            "human_review": "通过",
        },
        {
            "phase_order": 4,
            "phase": "Phase 3.5",
            "result": "本地 Web 工况输入、波形、CSV 和图片",
            "automatic_acceptance": "通过",
            "human_review": "等待审核",
        },
        {
            "phase_order": 5,
            "phase": "Phase 4～6",
            "result": "实测标定、条件事件模型和物理残差模型",
            "automatic_acceptance": "尚未实施",
            "human_review": "不适用",
        },
    ]

    manifest_sources = [
        {"id": "project_spec", "label": "项目总规范", "path": "docs/PROJECT_SPEC.md"},
        {"id": "project_status", "label": "项目验收状态", "path": "docs/STATUS.md"},
        {
            "id": "software_manual",
            "label": "软件用户手册",
            "path": "docs/SOFTWARE_USER_MANUAL.md",
        },
        {
            "id": "headline_metrics_sql",
            "label": "比赛报告头部指标快照",
            "path": "docs/competition/headline_metrics.csv",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_csv_auto('docs/competition/headline_metrics.csv')",
                "description": "读取由项目规范与状态记录复核后生成的头部指标快照。",
                "executed_at": GENERATED_AT,
                "tables_used": ["docs/competition/headline_metrics.csv"],
                "filters": ["截至 2026-07-14 的已复核项目状态"],
                "metric_definitions": [
                    "人工审核通过阶段数只计 Phase 0、1、2、3。",
                    "全量测试通过数取最近一次 pytest 全量验收。",
                    "标准计数率点取 Phase 3 死时间扫描的固定验证点数量。",
                    "最高真实计数率取项目规范明确给出的输入上限，单位 cps。",
                ],
            },
        },
        {
            "id": "high_rate_waveform_sql",
            "label": "高计数率裁剪前后电压快照",
            "path": "docs/competition/high_rate_focus_waveform.csv",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": (
                    "SELECT * FROM read_csv_auto("
                    "'docs/competition/high_rate_focus_waveform.csv') "
                    "ORDER BY time_us, signal"
                ),
                "description": "读取由固定 seed 高计数率 HDF5 抽取的事件中心裁剪前后电压。",
                "executed_at": GENERATED_AT,
                "tables_used": ["docs/competition/high_rate_focus_waveform.csv"],
                "filters": [
                    "true_rate_cps=10000000",
                    "sample_rate_msps=100",
                    "duration_ms=15",
                    "seed=20260303",
                    "event_id=4635",
                    "relative_time_us=-3..79",
                    "sample_stride_us=2",
                ],
                "metric_definitions": [
                    "time_us 为相对事件 4635 的采样时刻。",
                    "voltage_V 分别来自裁剪前诊断数组和裁剪后 ADC 输入数组。",
                ],
            },
        },
        {
            "id": "phase_status_sql",
            "label": "阶段成果与审核状态快照",
            "path": "docs/competition/phase_status.csv",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": (
                    "SELECT * FROM read_csv_auto('docs/competition/phase_status.csv') "
                    "ORDER BY phase_order"
                ),
                "description": "读取由项目状态表复核后生成的阶段成果快照。",
                "executed_at": GENERATED_AT,
                "tables_used": ["docs/competition/phase_status.csv"],
                "filters": ["截至 2026-07-14", "自动验收与人工审核分开记录"],
            },
        },
    ]

    blocks: list[dict[str, object]] = [
        {"id": "report_title", "type": "markdown", "body": f"# {TITLE}"},
        _section_block(
            "technical_summary",
            "技术摘要",
            sections,
            preamble=preamble,
        ),
        {
            "id": "headline_metrics",
            "type": "metric-strip",
            "cardIds": [
                "reviewed_phases_card",
                "regression_tests_card",
                "rate_points_card",
                "maximum_rate_card",
            ],
        },
        _section_block(
            "problem_statement",
            "项目要解决的是“数据稀缺、强堆积和模型可信度”三重问题",
            sections,
            source_id="project_spec",
        ),
        _section_block(
            "current_results",
            "当前成果已经形成从工况输入到数据产物的完整闭环",
            sections,
            source_id="project_status",
        ),
        {
            "id": "high_rate_chart",
            "type": "chart",
            "chartId": "high_rate_waveform_chart",
        },
        _section_block(
            "methodology",
            "方法设计以可解释物理模型和可回归实现为核心",
            sections,
            source_id="software_manual",
        ),
        _section_block(
            "validation",
            "验证结果支持当前合成基线的工程可用性",
            sections,
            source_id="project_status",
        ),
        {"id": "phase_table", "type": "table", "tableId": "phase_status_table"},
        _section_block(
            "innovation",
            "项目创新集中在可信分层、强堆积处理和可追溯工程化",
            sections,
        ),
        _section_block(
            "limitations",
            "当前边界决定了报告只能主张“合成基线完成”",
            sections,
            source_id="project_status",
        ),
        _section_block(
            "final_goal",
            "最终目标是形成实测约束下的可解释信号生成与评价平台",
            sections,
            source_id="project_spec",
        ),
        _section_block(
            "next_steps",
            "比赛报名后的近期工作应优先补足实测证据和演示叙事",
            sections,
        ),
        _section_block(
            "further_questions",
            "仍需由团队和比赛要求共同回答的问题",
            sections,
        ),
    ]

    cards = [
        {
            "id": "reviewed_phases_card",
            "description": "Phase 0～3 已完成自动验收和用户人工审核。",
            "dataset": "headline_metrics",
            "sourceId": "headline_metrics_sql",
            "metrics": [
                {"label": "人工审核通过阶段", "field": "human_reviewed_phases", "format": "number"}
            ],
        },
        {
            "id": "regression_tests_card",
            "description": "最新全量 pytest 回归，0 失败、0 跳过。",
            "dataset": "headline_metrics",
            "sourceId": "headline_metrics_sql",
            "metrics": [
                {"label": "全量测试通过", "field": "full_regression_tests", "format": "number"}
            ],
        },
        {
            "id": "rate_points_card",
            "description": "覆盖 10～10^7 cps 的标准死时间统计验证点。",
            "dataset": "headline_metrics",
            "sourceId": "headline_metrics_sql",
            "metrics": [
                {"label": "标准计数率点", "field": "standard_rate_points", "format": "number"}
            ],
        },
        {
            "id": "maximum_rate_card",
            "description": "当前软件支持的死时间前真实到达率上限。",
            "dataset": "headline_metrics",
            "sourceId": "headline_metrics_sql",
            "metrics": [
                {"label": "最高真实计数率", "field": "maximum_true_rate_cps", "format": "number"}
            ],
        },
    ]

    charts = [
        {
            "id": "high_rate_waveform_chart",
            "title": "高计数率事件窗口中的裁剪前后模拟电压",
            "subtitle": "10^7 cps、100 MS/s、15 ms；以事件 4635 为中心，每 2 µs 抽取一个点",
            "headerMarkdown": (
                "**读图结论：** 裁剪前电压仍随堆积事件变化，而裁剪后 ADC 输入固定在 1 V。"
                "这证明当前工况是量程饱和，不是波形生成失败。"
            ),
            "question": "强堆积波形在软件量程饱和后是否仍可被诊断？",
            "rationale": "时间序列包含 42 个有序采样位置，使用双系列折线展示形态与量程结果。",
            "type": "line",
            "dataset": "high_rate_focus_waveform",
            "sourceId": "high_rate_waveform_sql",
            "encodings": {
                "x": {"field": "time_us", "type": "quantitative", "label": "相对时间 (µs)"},
                "y": {"field": "voltage_V", "type": "quantitative", "label": "电压 (V)"},
                "color": {"field": "signal", "type": "nominal", "label": "信号层"},
                "tooltip": [
                    {"field": "sample_index", "type": "quantitative", "label": "采样点索引"},
                    {"field": "saturated", "type": "nominal", "label": "饱和标记"},
                ],
            },
            "xAxisTitle": "相对选定事件时间 (µs)",
            "yAxisTitle": "模拟电压 (V)",
            "valueFormat": "number",
            "unit": "V",
            "layout": "full",
        }
    ]

    tables = [
        {
            "id": "phase_status_table",
            "title": "阶段成果与审核状态",
            "subtitle": "截至 2026-07-14；自动验收与人工审核分别记录",
            "dataset": "phase_status",
            "sourceId": "phase_status_sql",
            "defaultSort": {"field": "phase_order", "direction": "asc"},
            "columns": [
                {"field": "phase_order", "label": "顺序", "type": "number"},
                {"field": "phase", "label": "阶段", "type": "text"},
                {"field": "result", "label": "主要成果", "type": "text"},
                {"field": "automatic_acceptance", "label": "自动验收", "type": "text"},
                {"field": "human_review", "label": "人工审核", "type": "text"},
            ],
        }
    ]

    return {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": TITLE,
            "description": "He-3 连续脉冲信号仿真项目比赛报名技术报告初稿。",
            "generatedAt": GENERATED_AT,
            "cards": cards,
            "charts": charts,
            "tables": tables,
            "sources": manifest_sources,
            "blocks": blocks,
        },
        "snapshot": {
            "version": 1,
            "generatedAt": GENERATED_AT,
            "status": "ready",
            "datasets": {
                "headline_metrics": metric_rows,
                "high_rate_focus_waveform": source_rows,
                "phase_status": phase_rows,
            },
        },
        "sources": manifest_sources,
    }


def _write_dataset_csv(name: str, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"dataset {name!r} cannot be empty")
    output = REPORT_DIR / f"{name}.csv"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    artifact = build_artifact()
    snapshot = artifact["snapshot"]
    if not isinstance(snapshot, dict):
        raise TypeError("artifact snapshot must be a dictionary")
    datasets = snapshot["datasets"]
    if not isinstance(datasets, dict):
        raise TypeError("artifact datasets must be a dictionary")
    for name in ("headline_metrics", "high_rate_focus_waveform", "phase_status"):
        rows = datasets[name]
        if not isinstance(rows, list):
            raise TypeError(f"dataset {name!r} must be a list")
        _write_dataset_csv(name, rows)
    ARTIFACT_JSON.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(ARTIFACT_JSON)


if __name__ == "__main__":
    main()
