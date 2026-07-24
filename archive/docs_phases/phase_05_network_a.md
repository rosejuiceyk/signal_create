# Phase 5：神经网络 A——条件事件参数生成

- 阶段编号：5
- 历史状态：`human_review_passed`
- 当前状态：`retired_by_user`
- 前置阶段：Phase 1~3 物理基线已通过；Phase 4 标定分布优先，但用户可明确授权仅以
  `synthetic_demo` 数据先执行研究对照
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

> 退役说明：用户在启用新的探测器通道数字孪生路线时明确舍弃网络 A。活动代码、配置、CLI 和测试
> 已移除；精确泊松生成器继续作为唯一真值事件来源。本文件以下内容只保留历史研究与审核追溯，
> 不再是可执行阶段说明，也不得重新接入 Phase 6 或默认生成链。

## 开始前必须阅读

- `AGENTS.md`
- `docs/PROJECT_SPEC.md`
- `docs/STATUS.md`
- 本文件

## 研究定位

网络 A 是条件标记时间点过程研究对照。对于首版非相关中子，精确泊松采样器仍是默认基线；除非量化评价证明网络有明确价值，否则网络 A 不进入默认生成链路。

## 实施前研究假设与基线

本阶段先固定以下可证伪假设，不因引入神经网络而改写物理问题：

1. **零假设**：当前合成数据由齐次泊松到达、参数化 He-3 能谱、线性幅值映射和固定脉冲时间常数
   精确生成；因此 exact Poisson + parametric spectrum 是已知分布下更简单、更可解释且默认正确的基线。
2. **网络假设**：一个小型条件密度网络可以在 `log10(rate)`、窗口时长和配置编码条件下，以似然训练
   恢复可变事件数、正时间间隔和合法 marks，并在未直接训练的计数率上插值。
3. **价值假设**：网络只有在统计匹配基线且展示明确的速度或未来标定分布表达价值时才值得继续研究；
   在纯合成泊松数据上没有理由预期它比精确采样器更准确。
4. **参数假设**：Phase 4 尚未执行，因此训练目标和 detector/config 编码全部来自
   `synthetic_demo` 配置，不得称为真实 He-3 探测器、前放或采集设备分布。

研究基线固定为现有 `poisson_uniform` 到达算法、`ParametricHe3Spectrum`、
`LinearAmplitudeMapper` 与 `FixedPulseParameterProvider`。网络输出不得接入现有默认事件或 Web 生成链；
模型卡和比较报告必须标记 `experimental`。

首版网络使用：Poisson 事件数似然头、正值指数混合间隔头、事件类型分类似然、按事件类型有界的
能量条件密度，以及正值幅值/时间常数条件密度。所有头均优化负对数似然，不使用 MSE 代替分布训练。
比较至少覆盖标准计数率、未直接训练的几何中点计数率、计数偏差、Fano factor、间隔 KS 距离、
间隔一阶自相关、事件类型比例、能量/幅值边缘与能量-幅值相关、非法输出、推理时间和峰值资源。

自动比较阈值只判定“是否达到研究级统计匹配”，不自动授权替代物理基线。若任一统计门槛失败，或
未展示明确速度优势，模型继续保持 `experimental`，默认生成器保持 exact Poisson。

## 首版实现合同

- 物理核心不导入 PyTorch；机器学习代码隔离在 `he3sim.ml`，通过可选依赖 `.[ml]` 安装；
- Poisson 计数头学习 `rate × duration` 的有界对数残差；指数混合头保证原始间隔严格为正；
- 推理先抽样事件数，再抽取 `N+1` 个正间隔并按窗口归一化，得到严格递增且位于窗口内的 `N` 个时间；
- 类型头屏蔽基础配置中零权重成分；能量使用按类型支持域约束的 logistic-normal 密度；
- 幅值、`tau_r` 和 `tau_d-tau_r` 使用正值 log-normal 密度，因此保证
  `amplitude > 0` 和 `tau_d > tau_r > 0`；
- checkpoint 保存架构、配置编码、优化器、epoch、训练历史、配置哈希和 `experimental` 状态；
- `cpu`、`cuda`、`auto` 三种设备模式显式可选；请求不可用 CUDA 时直接失败，不静默回退；
- 比较报告覆盖 13 个标准计数率和 12 个训练未直接命中的几何中点，并记录统计、吞吐率、
  Python 峰值内存和 CUDA 峰值显存。

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

建议命令（在包含 `pyproject.toml` 的 `he3_codex_context` 项目根目录逐行执行）：

```powershell
conda run -n signal_create python -m pytest -q tests/ml/test_event_model_smoke.py
conda run -n signal_create python -m he3sim train-event-model -c configs/ml_event.yaml
conda run -n signal_create python -m he3sim compare-event-model -c configs/ml_event_eval.yaml -o outputs/phase05_comparison
```

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase 5：实现条件标记事件生成网络 A，作为精确泊松物理生成器的研究对照。

阅读 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/phases/phase_05_network_a.md 和 @docs/STATUS.md。先写清研究假设和基线，不得为了使用 AI 而替代精确采样。实现可变长度事件、正值间隔、合法 marks、似然训练、CPU/CUDA 流程和严格统计对比。若未优于基线，保持 experimental。更新 STATUS 后停止，不得进入 Phase 6。
```
