# Phase 6：神经网络 C——物理残差与受约束比较

- 阶段编号：6
- 初始状态：`not_started`
- 前置阶段：Phase 4Q、4C、4V 已通过并获得可用真实连续波形和标定
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

> Phase 6S 合成工程预演不满足本阶段入口。其人工干扰 checkpoint 不能作为 B1～B4、真实泛化或
> 硬件就绪证据。

## 开始前必须阅读

- `AGENTS.md`
- `docs/PROJECT_SPEC.md`
- `docs/STATUS.md`
- 本文件

## 研究定位

物理模拟器负责事件、能谱、脉冲和叠加；网络 C 只学习实测波形中物理模型未覆盖的噪声、基线和形状残差。网络不得随意新增、删除或移动事件。

## 本阶段目标

采用伪配对监督策略训练轻量一维残差网络，并比较校准物理、经验模板、无约束 TCN 和受约束 TCN。

## 伪配对流程

1. 从实测波形提取事件参数；
2. 使用相同事件参数重建对应物理波形；
3. `residual_target = real - physical`；
4. 网络输入物理波形、`log10(rate)` 和 detector config；
5. 输出残差，最终 `y = physical + residual`。

## 必须实现

1. 轻量 1D dilated TCN 基线；用 FiLM 或条件归一化注入计数率和配置。
2. patch 数据加载，能在 8 GB 显存上运行。
3. 损失至少包含：
   - Huber/L1；
   - 多分辨率 STFT/频谱损失；
   - 无事件区基线/PSD 损失；
   - 事件保持损失；
   - 残差能量正则；
   - 可选幅值、上升时间和电荷统计损失。
4. 训练、断点、推理、seed、模型卡和失败案例记录。
5. 按采集 run 和计数率划分训练/验证/测试。
6. B1～B4 对比：
   - B1 校准物理；
   - B2 校准物理 + 经验模板重采样；
   - B3 校准物理 + 无约束小 TCN；
   - B4 校准物理 + 受约束异方差 TCN。
7. 生成最终评价报告。

## 明确不做

- 不直接上大型扩散模型；
- 不直接使用无配对 GAN/CycleGAN；
- 伪配对基线未通过前，不把非配对方法加入主实现。

## 评价与验收

- 输入和输出的事件到达率、间隔分布不得显著改变；
- 不无故新增/删除脉冲；
- 在留出 run 和留出计数率上改善：基线 RMS、PSD、平均脉冲形状、幅值/上升时间/电荷联合分布；
- 单独报告饱和和强堆积工况；
- 仅视觉变好但物理统计变差时判定失败；
- 输出是否值得进入未来 DT5800/实时接口阶段的结论。

建议命令：

```bash
pytest -q tests/ml/test_residual_model_smoke.py
he3sim train-residual-model -c configs/ml_residual.yaml
he3sim compare-models -c configs/evaluation.yaml -o outputs/phase06_comparison
```

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase 6：实现物理残差网络 C 和三条生成链路的最终比较。

阅读 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/phases/phase_06_network_c.md 和 @docs/STATUS.md。先采用伪配对与轻量 1D TCN，不得直接使用大型扩散或无配对 GAN。残差网络必须受事件保持约束，不得破坏计数率、到达间隔和能谱。完成留出 run/计数率评估、失败案例和模型卡，更新 STATUS 后停止，并给出是否具备进入未来硬件阶段的证据。
```
