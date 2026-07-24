# Phase 4：示波器数据标定与实测模板

- 阶段编号：4
- 初始状态：`not_started`
- 前置阶段：Phase 3 已通过，且用户提供孤立脉冲及多个已知计数率的连续示波器波形
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

## 开始前必须阅读

- `AGENTS.md`
- `docs/PROJECT_SPEC.md`
- `docs/STATUS.md`
- 本文件

## 本阶段目标

建立厂商无关的示波器数据导入、脉冲检测、双指数拟合、参数统计和实测模板流水线，为物理模型校正及网络 C 准备真实数据。

## 入口条件

用户后续将提供：

- 高分辨率孤立单脉冲；
- 多个已知计数率下的连续波形；
- 尽可能完整的采样率、时间单位、电压单位、量程、极性和采集 run 信息。

若真实数据尚未提供，只可用合成 fixture 建立代码与测试，禁止伪造真实标定结论。

## 必须实现

1. profile 驱动的 CSV/NPZ 导入，不能硬编码某一示波器列名。
2. 明确配置采样率、时间列、电压列、单位、极性和 run 元数据。
3. 基线、噪声、漂移和极性估计。
4. 脉冲检测、孤立脉冲筛选、对齐和归一化。
5. 双指数拟合，输出参数、不确定度、残差和 QC 状态。
6. 统计 `amplitude/tau_r/tau_d/rise/fall/charge` 的边缘和联合分布。
7. 生成 `provisional` 标定 YAML、图表和 Markdown/HTML 人工审核报告。
8. 人工确认前不得自动转为 `validated`。
9. 实测模板库接口和质量筛选。
10. 按 acquisition run 划分 train/validation/test，禁止相邻片段泄漏。

## 测试与验收

- 多种列名和单位 profile 可正确解析；
- 无法判断单位时明确报错而非猜测；
- 合成已知参数脉冲可在容限内拟合回收；
- 拟合失败事件被 QC 标记且不静默纳入模板；
- 报告明确区分 measured、derived、provisional；
- 数据划分以 run 为单位；
- 输出配置可被前述模拟器读取。

建议命令：

```bash
pytest -q tests/test_scope_import.py tests/test_pulse_fit.py tests/test_calibration.py
he3sim analyze-scope --input <path> --profile <profile> -o outputs/phase04_calibration
```

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase 4：建立示波器数据标定和实测模板流水线。

阅读 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/phases/phase_04_calibration.md 和 @docs/STATUS.md。若尚无真实示波器文件，只使用合成 fixture 完成程序与测试，不得声称得到真实 He-3 参数。所有拟合输出先标记 provisional，并生成供人工审核的 QC 报告。运行验收、更新 STATUS 后停止；未通过 Phase 4V 不得进入 Phase 6。
```
