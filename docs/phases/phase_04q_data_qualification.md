# Phase 4Q：数据资格与采样轴确认

- 阶段编号：4Q
- 当前状态：`blocked`
- 前置阶段：Phase 0～3 已人工审核通过
- 执行原则：只读审查原始采集数据；不得执行正式标定或训练网络

## 目标

建立 profile 驱动的 DT5790 元数据和波形探针，为每个原始文件保存哈希，对事件执行四态 QC，固定
RAW/FILTERED/UNFILTERED 版本合同，并判断 acquisition run 是否足以形成独立的数据划分。

## 必须实现

1. 原始目录只读，SHA-256 分块计算，派生产物只写入仓库 `outputs/`。
2. CSV/XML/info 的列名、编码、分隔符和字段均由严格 YAML profile 指定。
3. RAW 是主 QC 来源；FILTERED、UNFILTERED 只作版本对应和处理影响审查，不静默替代 RAW。
4. 逐事件记录 `tail_truncated`、`ringing`、`baseline_unstable`、`low_amplitude`、`saturation`、
   `duplicate_samples`、`trigger_clipped`。
5. QC 使用 `pass/fail/not_evaluable/unknown`，缺少 ADC 轨道、极性、单位或时间轴时不得猜测。
6. 相邻重复样本只统计，不自动删除；独立已知频率实验前 `sample_interval_s` 保持空值。
7. 采集软件粒子标签保留为原始元数据，标准标签只允许 `unknown/candidate`。
8. train/validation/test 的独立单位是 acquisition run；同一 run 的所有波形版本必须同组。
9. 每个目标计数率少于3个独立 run 时输出 `blocked`，不切分事件或相邻窗口冒充独立集合。

## 输出合同

```text
outputs/phase04q/
├── provenance.json
├── file_manifest.csv
├── run_manifest.csv
├── event_qc.jsonl
├── qc_summary.csv
├── sampling_axis_report.json
├── sampling_axis_report.md
├── split_feasibility.json
└── data_gap_report.md
```

所有实测波形量在采样轴确认前只使用导出样本索引和 `ADC_counts`，不得产生 keV、电压或秒制标定值。

## 验收

```powershell
conda run -n signal_create python -m pytest -q tests/calibration/test_phase4q.py
conda run -n signal_create python -m he3sim qualify-acquisition --input "C:\Users\rosejuice\Desktop\7.9-data\4\DAQ" --profile configs/acquisition_profiles/dt5790_run3.yaml -o outputs/phase04q
conda run -n signal_create python -m ruff format --check .
conda run -n signal_create python -m ruff check .
conda run -n signal_create python -m mypy src
conda run -n signal_create python -m pytest -q
```

软件验收通过不代表科学出口通过。重复样本原因、物理采样间隔和独立 run 数量任一未满足时，阶段继续
保持 `blocked`，不得进入 Phase 4C、4V 或 Phase 6。
