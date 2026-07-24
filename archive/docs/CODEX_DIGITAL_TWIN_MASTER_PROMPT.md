# Codex 总控 Prompt：He-3 探测器通道数字孪生与论文路线

下面内容可直接投喂 Codex。正式科学路线默认仍从 `Phase 4Q` 开始，不得一次实现全部路线。

> 2026-07-15补充：用户为比赛进度单独授权了Phase 6S合成工程预演。该预演使用人工干扰并固定标记
> `synthetic_scaffold`，不等于正式Phase 6，也不改变下述Phase 4Q→4C→4V→6A顺序。

```text
你正在维护仓库 he3_codex_context。目标是将现有 He-3 随机脉冲模拟器升级为：

“面向核反应堆中子监测链路的、可校准且带不确定度的 He-3 探测器通道数字孪生”，
并以核工程领域同行评议论文为最终验收目标。

重要术语边界：
- 当前孪生对象是一条 He-3 比例计数器—前放—数字化—触发通道，不是整个核反应堆；
- 没有反应堆功率/中子通量到计数率的物理映射前，不得宣称“核反应堆数字孪生”；
- 物理模型是主体，神经网络只学习实测与物理模型之间的受约束残差；
- 真值事件账本、事件时间和事件计数只能由物理链维护，网络不得新增、删除或移动真值事件。

一、首先只读核对，不修改文件

按顺序完整阅读：
- @AGENTS.md
- @docs/PROJECT_SPEC.md
- @docs/STATUS.md
- @docs/USER_MANUAL.md 中当前阶段部分
- @docs/SOFTWARE_USER_MANUAL.md 中数据流、触发/死时间、Phase 4Q 和网络 A 退役部分
- @docs/phases/phase_04_calibration.md
- @docs/phases/phase_06_network_c.md
- @docs/HE3_DETECTOR_DIGITAL_TWIN_TECHNICAL_PLAN.md

然后检查真实 Git 根、工作树、未提交文件、现有 outputs 和测试现状。用户已有改动不得覆盖。
对文档结论、代码接口、测试和实际运行结果建立显式追踪表，不能只说“测试通过”。

二、必须继承的现状

- Phase 0、1、2、3 已人工审核通过；
- Phase 3.5 自动验收通过但仍等待人工审核；
- Phase 4 被用户推迟，尚无 validated 实测标定参数；
- Phase 5 网络 A 的历史审核已通过，但现已由用户标记为 retired_by_user；
- exact Poisson + parametric spectrum 仍是默认事件生成器；
- Phase 6S合成工程预演已完成，但正式Phase 6尚未开始，仍被数据质量和标定入口阻塞；
- 已清点的 DT5790 run 中，11 个含脉冲样信号、4 个为空；相邻采样成对重复、时间轴未确认、
  多条记录下降沿截断或存在振铃，并且每个计数率只有一个 run；
- 原始采集目录必须只读，任何派生产物只能写入仓库 outputs 或明确的新输出目录；
- 所有临时参数继续使用 synthetic_demo/provisional/validated 状态，禁止静默补值或自动晋升。

三、最终研究问题

在 10～1e7 cps 的宽计数率和堆积/死时间条件下：
1. 校准物理模型能否在留出 acquisition run 上保持事件统计并复现实测波形、PSD、触发和死时间？
2. 受物理约束的轻量残差网络能否相对校准物理基线显著改善实测一致性？
3. 这种改善能否在留出计数率、跨会话数据上泛化，并给出校准的不确定度、适用域和回退策略？

四、分阶段路线（一次只执行一个阶段）

Phase 4Q：数据资格和采样轴确认
- 原始文件只读并计算哈希；
- 建立 profile 驱动的元数据/波形读取探针，但不做正式标定；
- 解释或通过独立实验确认相邻重复样本的物理含义；
- 逐事件 QC：tail_truncated、ringing、baseline_unstable、low_amplitude、saturation、
  duplicate_samples、trigger_clipped；
- 固定 RAW/FILTERED/UNFILTERED 版本字段与选择规则；
- 粒子标签无外部真值时保持 unknown/candidate；
- 生成 run 级清单、可用性分级、独立 train/validation/test 可行性和缺口报告；
- 若没有足够独立 run，明确 blocked，不得切分同一 run 冒充独立集合。

Phase 4C：物理参数标定和不确定度（只有 Phase 4Q 人工通过后）
- 厂商无关 CSV/NPZ/profile 导入；
- 基线、噪声、漂移、极性、孤立脉冲、对齐、双指数/模板拟合；
- 先用合成 fixture 做参数回收和失败路径测试；
- 以 acquisition run 为统计单位，使用约束拟合和按 run bootstrap/后验区间；
- 输出 provisional YAML、参数来源、CI、数据哈希、QC 和人工审核报告；
- 不得自动写成 validated。

Phase 4V：校准物理孪生基线验证
- 在独立留出 run 和留出计数率上比较计数、Fano、间隔、脉冲特征、PSD、堆积、饱和、触发和死时间；
- 分开报告低/中/高计数率、堆积和饱和；
- 冻结适用域、失败案例和论文基线 B1；
- 未通过不得进入 Phase 6。

Phase 6A：物理残差网络 C
- 先实现经验模板 B2 和无约束小 TCN B3，再实现受约束异方差 TCN B4；
- 输入 physical waveform、event anchors/mask、log10(rate)、sample rate、detector config；
- 输出 residual mean 和 residual scale，最终 y=physical+residual；
- 使用 Huber/L1、多分辨率 STFT、无事件区 PSD、平均脉冲/电荷、事件保持、残差能量正则；
- 推理后执行事件时间/计数/触发/幅值边界检查；越界时回退纯物理链并记录原因；
- 8 GB 显存可训练；按 run 划分；保存 seed、配置、checkpoint、模型卡和失败案例；
- 比较 B1/B2/B3/B4；不再保留网络 A 或 B5 链路。

Phase 6B：不确定度、域外检测和孪生更新
- 评价 50%/90% 预测区间覆盖率和宽度；
- 建立适用域/域外检测、跨会话漂移告警和安全回退；
- 新 run 的参数或模型更新必须版本化、可回滚、需人工批准；
- 证明更新前后在独立留出会话上的净收益。

Phase 7：论文级验证与复现包
- 冻结 protocol、配置、split、测试集和软件版本；
- 运行完整消融、按 run bootstrap 95% CI、配对效应量、跨计数率/跨会话评价；
- 生成论文表图、数据字典、模型卡、失败案例和一键复现实验；
- 论文暂定题目：
  A Physics-Constrained Digital Twin of a He-3 Neutron Detector Channel Across Wide Count-Rate
  Regimes: Stochastic Events, Electronics Response, Residual Learning, and Uncertainty Validation

五、贯穿所有阶段的科学约束

- 真实事件、连续波形和观测事件严格分层；
- 死时间只影响观测层，不能删除真值事件或其波形贡献；
- 网络 A 已退役；exact Poisson 是唯一活动的真值事件生成器；
- 网络 C 不得拥有真值事件账本写权限；
- 不得用视觉更像作为成功标准；事件计数、时间、能谱、触发和死时间统计退化即失败；
- 所有主结果以 acquisition run 为独立单位，不把 patch 当独立实验；
- 高计数率无法实测时，必须区分实测验证范围与合成压力测试范围；
- 测试阈值在查看最终测试集之前冻结；完整测试集只在模型和阈值冻结后运行；
- 无法确认单位、采样轴、标签或参数时必须显式报错或保持 blocked，不得猜测；
- PyTorch 继续与 physics 核心隔离；默认无 ML 依赖时物理 CLI 必须可用；
- Windows spawn 安全；随机数使用 numpy.random.Generator/显式 seed；
- 优化实现必须有简单参考实现；所有产物写入配置哈希、代码版本、数据哈希、参数状态和单位。

六、论文评价矩阵

基线：
- B0 未校准物理；
- B1 校准物理；
- B2 校准物理 + 经验模板重采样；
- B3 校准物理 + 无约束 TCN；
- B4 校准物理 + 受约束异方差 TCN（主模型）；

Phase 5 网络 A 不再进入评价矩阵；其历史结果只用于审计，不构成活动基线。

指标：
- 事件：rate bias、Fano、interval KS/energy distance、lag-1 correlation、event timing、
  missed/spurious events、trigger rate、dead-time loss；
- 脉冲/能谱：event-type proportion、energy/amplitude/charge/rise/fall distributions、
  joint Wasserstein/MMD、mean pulse confidence band；
- 波形：normalized RMSE、residual autocorrelation、band-wise log-PSD error、multi-resolution STFT、
  baseline/noise distribution、saturation；
- 孪生：50%/90% coverage、interval width、calibration error、OOD detection、drift、fallback rate；
- 工程：events/s、samples/s、CPU/GPU time、peak RAM/VRAM、artifact size。

七、本轮当前任务：只做 Phase 4Q 计划

本轮先进入计划模式，不修改代码或数据。完成以下内容后停止，等待用户确认：
1. 现状追踪矩阵：要求 -> 文档 -> 代码/脚本 -> 测试 -> 现有运行证据 -> 缺口；
2. 原始数据只读审查方案和采样轴确认实验；
3. 逐事件 QC schema、run 级 split 规则和输出数据合同；
4. 预计新增/修改文件清单；
5. 单元、集成、合成回收、数据质量和文档测试；
6. 验收命令与人工审核清单；
7. 风险、blocked 条件和不属于 Phase 4Q 的内容。

明确排除：本轮不做正式参数标定、不训练网络 C、不修改默认物理生成链、不改变 Phase 1 最小 HDF5
合同、不实现远程 Web/桌面 GUI/DT5800/实时硬件，也不更新状态为完成。

计划得到用户确认后，下一轮才实施 Phase 4Q。实施完成后必须运行对应格式、类型、专项和全量测试，
更新 docs/STATUS.md、docs/USER_MANUAL.md；若软件操作发生变化，同时更新 docs/SOFTWARE_USER_MANUAL.md，
然后停止等待人工审核。未经用户明确确认不得进入 Phase 4C。
```
