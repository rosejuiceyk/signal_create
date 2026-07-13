# Phase 5：神经网络 A——条件事件参数生成

- 阶段编号：5
- 初始状态：`not_started`
- 前置阶段：Phase 1~3 物理基线已通过；最好已有 Phase 4 标定分布
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

## 开始前必须阅读

- `AGENTS.md`
- `docs/PROJECT_SPEC.md`
- `docs/STATUS.md`
- 本文件

## 研究定位

网络 A 是条件标记时间点过程研究对照。对于首版非相关中子，精确泊松采样器仍是默认基线；除非量化评价证明网络有明确价值，否则网络 A 不进入默认生成链路。

## 本阶段目标

输入计数率、时间窗和探测器配置，生成可变长度事件序列及 marks，并与精确物理生成器进行严格统计比较。

## 必须实现

1. `ConditionalMarkedEventGenerator` 接口。
2. 条件输入：
   - `log10(true_rate_cps)`；
   - window duration；
   - detector/config 编码；
   - 随机潜变量。
3. 输出：
   - 可变事件数；
   - 单调递增到达时间；
   - `energy/amplitude/tau_r/tau_d/event_type` 等 marks。
4. 事件数分布头，可从 Poisson 或 Negative-Binomial 基线开始。
5. 正值时间间隔的混合分布或 normalizing-flow 头。
6. mark 条件密度头；使用似然训练，不能只用 MSE。
7. 物理约束：间隔正、时间有序、能量/幅值/时间常数合法。
8. 训练、验证、断点、推理、配置、seed 和模型卡。
9. CPU smoke test 与 CUDA 支持；适配 RTX 5060 Laptop 8 GB。
10. 与 exact Poisson + parametric spectrum 的准确度和速度对比。

## 数据划分

- 训练计数率从 `log-uniform(10,1e7)` 抽样；
- 验证/测试使用固定标准点；
- 另保留未直接训练的中间计数率做插值测试；
- 不得让同一底层事件或相邻切片跨集合。

## 评价与验收

至少评价：

- 平均计数率偏差；
- Fano factor；
- 间隔分布与自相关；
- mark 边缘和联合分布；
- 留出计数率泛化；
- 推理速度和资源占用。

通过条件：

- 在纯泊松合成数据上能恢复目标统计；
- 不产生无序时间或非法参数；
- 报告与精确物理基线的差距；
- 若不优于或不能匹配基线，默认配置仍使用物理生成器，并明确将网络标记为 `experimental`。

建议命令：

```bash
pytest -q tests/ml/test_event_model_smoke.py
he3sim train-event-model -c configs/ml_event.yaml
he3sim compare-event-model -c configs/ml_event_eval.yaml -o outputs/phase05_comparison
```

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase 5：实现条件标记事件生成网络 A，作为精确泊松物理生成器的研究对照。

阅读 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/phases/phase_05_network_a.md 和 @docs/STATUS.md。先写清研究假设和基线，不得为了使用 AI 而替代精确采样。实现可变长度事件、正值间隔、合法 marks、似然训练、CPU/CUDA 流程和严格统计对比。若未优于基线，保持 experimental。更新 STATUS 后停止，不得进入 Phase 6。
```
