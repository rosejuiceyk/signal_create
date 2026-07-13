# Phase 1：真实事件到达、He-3 能谱与幅值

- 阶段编号：1
- 初始状态：`not_started`
- 前置阶段：Phase 0 已通过
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

## 开始前必须阅读

- `AGENTS.md`
- `docs/PROJECT_SPEC.md`
- `docs/STATUS.md`
- 本文件

## 本阶段目标

生成统计正确、可复现的真实中子事件列表，包含到达时间、沉积能量、事件谱成分、目标峰值幅度和脉冲极性；本阶段不生成连续波形。

## 必须实现

1. `ConstantRateProfile`。
2. 两种齐次泊松事件生成算法：
   - `Poisson(N=λT) + sorted Uniform(0,T)`；
   - 累积指数间隔法。
3. 统一 `EventArrivalGenerator` 接口和显式 `numpy.random.Generator`。
4. `ParametricHe3Spectrum`，至少包含：
   - `full_energy`；
   - `proton_wall`；
   - `triton_wall`；
   - 可选 `double_wall`。
5. 混合权重非负且归一；能量定义域合法；支持可配置能量分辨展宽。
6. 线性能量—幅值映射：`A_peak = G_E * E_dep + epsilon`；幅值非负；极性单独保存。
7. 最小 HDF5 真值事件表，保存单位、seed、配置哈希和参数状态。
8. CLI 至少包括 `simulate-events` 和 `validate-arrivals`。
9. 输出统计报告和必要图表。

## 物理约束

- 输入计数率是死时间前真实到达率；
- 首版只处理恒定计数率非相关热中子；
- 到达时间必须位于窗口内并严格有序；
- 不得把参数化能谱权重描述成真实 He-3 管标定值；
- MCNP 只保留导入接口，不在本阶段运行。

## 明确不做

- 不生成连续电压/ADC 波形；
- 不实现触发或死时间；
- 不实现神经网络。

## 测试与验收

验收至少覆盖：

- 大样本下 `E[N]≈λT`；
- 事件计数方差/均值接近 1；
- 指数间隔分布统计一致；
- 两种泊松实现的分布一致；
- 固定 seed 可复现；
- 全能峰位置、混合比例和各分量定义域正确；
- 不出现负能量、负幅值、越界或无序时间；
- HDF5 可回读且元数据完整。

建议命令：

```bash
pytest -q tests/test_arrivals.py tests/test_spectrum.py tests/test_amplitude.py
he3sim validate-arrivals -c configs/demo_minimal.yaml -o outputs/phase01_validation
he3sim simulate-events -c configs/demo_minimal.yaml -o outputs/phase01_events.h5
```

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase 1：实现真实事件到达、参数化 He-3 能谱和能量到峰值幅值。本阶段不得生成连续波形。

阅读 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/phases/phase_01_event_generator.md 和 @docs/STATUS.md。先审查 Phase 0 的公共 API，再给计划。实现两种泊松算法、参数化谱、线性幅值映射、最小 HDF5 事件表、CLI 和统计验证。运行本阶段测试与验收，更新 STATUS，然后停止，不得进入 Phase 2。
```
