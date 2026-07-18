# Phase HIL：DT5800 硬件在环验证工具

- 阶段编号：HIL（可与 Phase C 并行；正式排在 Phase B 之后）
- 初始状态：`not_started`
- 前置阶段：Phase B 已通过人工审核（需要噪声估计器可用）
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

## 开始前必读
- `AGENTS.md`、`docs/PROJECT_SPEC.md`、`docs/STATUS.md`
- `docs/ROADMAP_v2.md`（§7）与 `docs/DT5800_HIL_integration.md`（全文）
- `docs/EXPERIMENT_DATA_COLLECTION.md`（§3 run_meta schema、§5 DT5800 交叉参照）
- 本文件

## 本阶段目标
建立**厂商无关、profile 驱动**、**可用合成 fixture 通过 CI**的 DT5800 硬件在环工具链：把孪生事件/波形导出为 DT5800 可载格式；把采集回来的波形按 profile 导入；比对"软件孪生 vs DT5800-经-真实DAQ"的边缘统计与死时间行为；验证双探测器互协方差。为 Tier 2 提供"已知真值下的电子学背书"，衔接反应堆实验。

## 入口条件
- Phase A/B 可产生相关事件与噪声估计；现有 `io/oscilloscope.py`、`io/dt5800_stub.py`、`analysis/*` 可复用。
- **不要求实体设备**：本阶段全部用合成 fixture 开发与测试；真实设备接入时只替换输入文件。

## 必须实现

### 1. 能力探测占位与文档
- 在文档/代码中留出"DT5800 能力档位"记录（是否支持 (energy,time) 序列、任意波形最长点数、堆积内存深度、DT5800D 关联参数、导入/导出文件格式）。真实单元能力以手册/软件为准；未确认的不得假设。

### 2. 导出器 `io/dt5800_export.py`
- 把孪生的事件表 / 波形导出为 DT5800 可载的**形状文件、能谱文件、(energy,time) 序列、任意波形**（按选定能力路径）。
- 采样率、时间/电压单位、量程、极性、DC 偏置显式配置，**不硬编码**任何示波器/设备列名或单位。
- 导出后可回读自检（round-trip：导出→再解析→与源一致）。

### 3. 导入器（扩展 `io/oscilloscope.py` / `io/dt5800_stub.py`）
- 按 profile 解析采集回来的连续波形（列名/单位/采样率来自 profile，不硬编码）；**无法判定单位时报错而非猜测**。
- 复用 `EXPERIMENT_DATA_COLLECTION.md` 的 `run_meta` schema；缺字段给出明确错误。

### 4. 比对器 `analysis/hil_compare.py`
- 对齐并比较：平均脉冲形状、`tau_r/tau_d`、上升/下降/电荷分布、脉冲高度谱、噪声底/基线漂移、死时间/堆积曲线。
- 档 2（死时间标定）：从"已知输入率序列"反出死时间/堆积参数，与设定比对。
- 档 3a（双探测器）：在"已知注入关联"的两通道上验证 CCF/CTM 估计器正确提取，并验证时间同步处理。
- 输出差异指标 + QC 状态 + Markdown/HTML 报告；明确标注 `measured`（DT5800 经真实 DAQ）/`simulated`（软件孪生）/`derived`。

### 5. 合成 fixture 与测试
- 用软件孪生生成"假 DT5800 输出"作为 fixture：
  - 当 fixture = 孪生同参数输出时，比对差异应在容限内（自洽）；
  - 人为注入偏差（改形状/加噪/改率）时，比对能检出并标 QC。
- 全部导入/比对/死时间/双探测器流程有合成 fixture 单测，无硬件即可 CI 通过。

## 明确不做（留后续）
- 对 DT5800 的实时硬件控制/驱动（本阶段只做文件级导出/导入/比对）。
- 声称任何未经实测确认的设备能力（写进文档，不写进假设）。
- 把 Emulation 模式随机序列当作精确事件表。
- 接入反应堆真实数据（后续数据接入阶段）。
- 连续信号 ACF/VTM/去卷积的完整实现（Phase C；但双探测器 CCF 的估计器可与 Phase C 共享）。

## 测试与验收
1. 导出器对至少一种能力路径产出可载文件，round-trip 自检通过。
2. 导入器按 ≥2 种 profile 正确解析；单位不明确时报错；run_meta 缺字段报错。
3. 比对器在合成 fixture 上：自洽用例差异在容限内；注入偏差用例被检出并标 QC。
4. 死时间标定在合成 fixture 上从已知率序列反出参数并与设定一致。
5. 双探测器 CCF 在已知注入关联的合成 fixture 上被正确提取。
6. 报告区分 measured/simulated/derived；全量 ruff/mypy/pytest 绿灯。
7. 文档记录本单元实际能力档位与档3可用性及约束。

建议命令：
```bash
pytest -q tests/unit/test_dt5800_export.py tests/unit/test_hil_compare.py tests/integration/test_hil_roundtrip.py
he3sim dt5800-export -c configs/demo_correlated.yaml -o outputs/phaseHIL_export
he3sim hil-compare --sim <sim_file> --measured <fixture_or_real> --profile <profile> -o outputs/phaseHIL_compare
```

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase HIL（DT5800 硬件在环工具）。

阅读 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/STATUS.md、@docs/ROADMAP_v2.md（§7）、@docs/DT5800_HIL_integration.md、@docs/EXPERIMENT_DATA_COLLECTION.md（§3、§5）和 @docs/phases/phase_DT5800_hil.md。

先进入计划模式，产出：io/dt5800_export.py 导出器、导入器扩展、analysis/hil_compare.py 比对器的接口与格式，能力探测占位、合成 fixture 测试方案、以及本阶段明确不做（实时硬件控制、未证实的设备能力假设、反应堆数据、连续信号完整实现）。停止等待我确认。

确认后仅实施本阶段。全部工具必须厂商无关、profile 驱动、可用合成 fixture 通过 CI；不接实体设备也要全绿。无法判定单位时必须报错而非猜测；报告须区分 measured/simulated/derived。完成后运行验收命令与全量 ruff/mypy/pytest，更新 @docs/STATUS.md，然后停止，不得进入 Phase C。
```
