# Phase 2：归一化双指数脉冲与连续波形

- 阶段编号：2
- 初始状态：`not_started`
- 前置阶段：Phase 1 已通过
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

## 开始前必须阅读

- `AGENTS.md`
- `docs/PROJECT_SPEC.md`
- `docs/STATUS.md`
- 本文件

## 本阶段目标

把真实事件转换为前置放大器连续电压波形和 ADC 波形，并正确处理脉冲叠加、跨块尾部、噪声、基线、裁剪和量化。

## 必须实现

1. 双指数核：`g(s)=exp(-s/tau_d)-exp(-s/tau_r)`，约束 `tau_d > tau_r > 0`。
2. 解析峰值时刻和归一化因子，使 `A_peak` 对应离散波形目标峰值。
3. `direct_sparse` 参考渲染器。
4. 固定时间常数的递归高效渲染器，并保存跨块状态。
5. 多事件线性叠加；所有真实事件均参与波形。
6. 常量基线、高斯白噪声、可选低频漂移。
7. 模拟电压裁剪、ADC 位数/量程/偏置和量化、饱和标记。
8. 特征提取：峰值、积分电荷、`rise_time_10_90_s`、`fall_time_90_10_s`。
9. 分块 HDF5 连续写入；同时保存软件裁剪前诊断电压和裁剪后 ADC 输入电压，支持 `100~250 MS/s`。
10. CLI `simulate-waveform`。
11. 只读 CLI `plot-waveform`，用于从 Phase 2 HDF5 导出人工审核 PNG，不改变 HDF5 内容。

## 重要实现要求

- 配置中的 `tau_r/tau_d` 是模型时间常数，不得冒充 10%–90% 上升/下降时间；
- 当时间常数相对采样间隔不可分辨时给出明确警告；
- 优化渲染器必须与参考渲染器做回归；
- 分块渲染不得在边界截断脉冲尾部。

## 明确不做

- 不实现触发与死时间；
- 不生成事件中心窗口和完整训练数据集；
- 不训练神经网络。

## 测试与验收

必须测试：

- 单脉冲峰值归一化；
- 时间平移；
- 两事件线性叠加；
- 正、负极性；
- 参考/优化渲染一致性；
- 分块/整段一致性；
- ADC 映射、裁剪与饱和标记；
- 固定 seed 下噪声可复现。
- 波形 PNG 可读，优先使用裁剪前诊断电压显示全程包络和事件附近细节，同时显示 ADC 细节，且不遗漏窄脉冲。

建议命令：

```bash
pytest -q tests/test_pulse_kernel.py tests/test_renderers.py tests/test_digitizer.py tests/test_waveform_plot.py
he3sim simulate-waveform -c configs/demo_minimal.yaml -o outputs/phase02_waveform.h5
he3sim inspect outputs/phase02_waveform.h5
he3sim plot-waveform outputs/phase02_waveform.h5 -o outputs/phase02_waveform.png
```

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase 2：实现峰值归一化双指数脉冲、连续波形、分块状态、噪声、基线、裁剪与 ADC。

阅读 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/phases/phase_02_waveform.md 和 @docs/STATUS.md。保留 direct_sparse 参考实现，再实现优化后端并做一致性测试。所有真实事件必须参与叠加。运行全部本阶段验收，更新 STATUS，然后停止，不得进入 Phase 3。
```
