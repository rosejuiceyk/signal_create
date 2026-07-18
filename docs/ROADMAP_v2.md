# 技术方案与研究规划：从"非相关中子探测器模拟"到"零功率反应堆中子噪声数字孪生"

> 面向 `signal_create`（he3-pulse-sim）项目的后续发展。
> 定位：保留 Phase 0–3 物理核心，砍掉 Web(3.5)/网络A(5)/网络C(6) 路线，把课题重新锚定到有明确科学价值、且与你现有代码高度契合的方向。
> 结论先行：**你已完成的是"外源非增殖情形"的探测器信号模拟；真正的科研纵深在于跨过"中子相关性"这道边界，把它做成零功率反应堆中子噪声（Feynman-α / Rossi-α）的信号级数字孪生。**

---

## 0. 执行摘要（一页纸版本）

| 项 | 判断 |
|---|---|
| 你现在有什么 | 干净、规范、经过验收的物理链：均匀泊松到达 → He-3 沉积能谱（全能峰+壁效应）→ 双指数前放脉冲 → 噪声/基线 → ADC 量化 → 阈值触发 → 死时间 → 多尺度数据集。Protocol 化架构，下游全部消费 `TRUE_EVENT_DTYPE`。 |
| 根本边界 | `arrivals.py` 是**均匀泊松过程**（`PoissonUniformArrivalGenerator` / `CumulativeExponentialArrivalGenerator`），即"非相关中子"。这对应外源、非增殖介质。 |
| 为什么这是关键 | 零功率反应堆的全部物理精髓在于**裂变链导致的中子关联**。Feynman-α、Rossi-α、次临界度测量、多重性计数——都建立在"中子不是泊松的"之上。你的物理基线恰好停在这道门槛前。 |
| ML 路线为何停滞 | 网络A（Phase 5）结论是"统计匹配但相对精确物理基线无速度优势"→ 无净收益；网络C（Phase 6）因实测数据质量（相邻点重复、下降沿截断、每计数率仅一个 run、能量仅 ADC 道未标定 keV）而 `blocked`。生成式 ML 在这里既没赢过物理，又被数据卡死。 |
| 建议主线 | **相关中子事件生成器（点模型/分支过程蒙特卡洛）** 作为新的物理核心，替换/并列于泊松生成器；再叠加**噪声分析验证层**（Feynman-α/Rossi-α/PSD）闭合"生成→反演→复原已知 α"的验证回路。 |
| 前沿贡献点 | 你已经能生成**连续波形**。直接实现 **连续信号中子噪声分析**（Pál–Pázsit / Kitamura 谱系），并证明数字孪生能刻画"脉冲计数因死时间/堆积失效、而连续信号仍可用"的工况。**Boros 等 2026（arXiv:2606.10950）明确把 He-3 探测器列为未来工作**——你的 He-3 选型正好卡在这个空档。 |
| 集成成本 | 极低。新增一个实现 `EventArrivalGenerator` 协议的模块 + 一个 `source_model` 配置段即可；`events.py` 中 `arrival_generator_for(algorithm)` 是唯一替换点，波形/ADC/触发/死时间/数据集/画图全栈原样复用。 |
| ML 的正确复用 | 不要用 ML 去"生成信号"（已证明无优势）。若要保留 ML 投入，转向**逆问题**：由噪声曲线反演 (ρ, α, β_eff, Λ) 及其不确定度（多输出高斯过程，见 arXiv:2211.02465）。 |

---

## 1. 现状诊断

### 1.1 你已完成的物理链（Phase 0–3，均已人工审核通过）

```
ConstantRateProfile(rate_cps)
  → PoissonUniformArrivalGenerator.sample()         # 均匀泊松到达时间
  → ParametricHe3Spectrum.sample()                  # 全能峰(≈764 keV) + 质子壁 + 氚壁 + 双壁(Beta连续谱)
  → LinearAmplitudeMapper                            # 能量→峰值幅值
  → FixedPulseParameterProvider(tau_r, tau_d)        # 双指数时间常数
  → 波形合成 / 噪声 / 基线 / 裁剪 / ADC 量化
  → 阈值触发 / 观测层死时间 / 事件窗
  → 多尺度压缩数据集(HDF5)
```

这套链条的工程质量很高（严格的参数状态 `synthetic_demo/provisional/validated`、显式安全上限、Protocol 抽象、齐全的单元/集成测试）。**问题不在工程，在物理边界。**

### 1.2 根本边界：非相关 = 外源非增殖

`arrivals.py` 生成的是齐次泊松点过程。它的物理含义是：**探测事件之间统计独立**。这只在以下情形成立：
- 探测器面对的是外源（如 Am-Be、D-T 中子发生器、自发裂变源但探测效率极低到看不到多重性），且
- 周围介质**不增殖**（无裂变链），或增殖可忽略。

一旦把探测器放进**零功率反应堆 / 次临界装置**，中子来自裂变链：一次裂变放出 ν 个（ν 服从多重性分布 pν）中子，这些"同链兄弟"在时间上聚集，导致探测事件正相关。这个相关性正是全部噪声方法要测的东西。**你现在的模型在结构上无法产生这种相关性**——不是参数没调好，而是过程模型本身是泊松的。

### 1.3 ML 两条路线为何走进死胡同（来自你自己的 STATUS）

- **网络A（条件标记点过程，Phase 5）**：25/25 工况统计达标、非法事件为 0，但 `exact 基线 ≈ 53268 events/s`，`CUDA 网络 ≈ 3787 events/s`，速度比 0.071。**它在复刻一个你已经能精确采样的泊松+参数谱过程**——本质上是"用神经网络逼近一个你有解析采样器的分布"，注定没有净收益，只能保持 `experimental`。
- **网络C（物理残差网络，Phase 6）**：`blocked`。DT5790 实测数据存在严格相邻点成对重复、下降沿截断、每计数率仅一个 run（无法做同工况独立 train/val/test 划分）、能量仅为 ADC 道未标定 keV。伪配对训练与留出评价无法开展。

**关键洞察**：网络A之所以没价值，恰恰因为它学的是"非相关"分布——一个平凡分布。如果底层过程变成**相关中子**（有真正丰富的时间结构），ML 才可能有用武之地，但那时最该用 ML 的地方也不是"生成"，而是"反演"（见 Phase E）。所以砍掉现有 ML 主线是对的；未来若回归 ML，方向要换。

---

## 2. 课题的科学定位

### 2.1 一句话重新定义课题

> 从 **"He-3 探测器信号模拟器"** 升级为 **"零功率/次临界反应堆中子噪声的信号级数字孪生"**：以第一性的分支过程为事件引擎，端到端生成带有真实裂变链关联的连续探测器波形，并在其上完成 Feynman-α / Rossi-α / PSD 反演，形成"物理参数 → 波形 → 反演 → 复原物理参数"的闭环。

### 2.2 你在"数字孪生"版图里的独特生态位

调研显示，核领域的数字孪生绝大多数在**系统级 / 电厂级**：热工水力、燃耗、状态监测、ML 代理模型、图神经网络整机孪生等（如 OSTI 的虚拟传感 DT、Purdue PUR-1、SAM+GNN 整机 DT）。**"传感器/信号级"的、能刻画探测器原始输出随机关联结构的物理数字孪生，是相对空白的一层**，而且它直接对接一个成熟的应用（噪声法反应性/动力学参数测量）。这给了你清晰的差异化叙事：不是再造一个系统级 DT，而是补上"探测器信号这一层的物理孪生"，并证明它能服务于噪声诊断。

### 2.3 为什么这条路对竞赛/论文都成立

- **物理纵深**：分支过程 / Pázsit–Pál 理论 / 点堆随机动力学，是有教科书支撑的硬核方向。
- **可验证性**：噪声法有解析靶（见 §7），"复原已知 α"是一个干净、可自动化的正确性判据——这与你项目一贯的"严格验收门禁"风格天然契合。
- **前沿性**：连续信号噪声分析是 2015 年后才成熟、2026 年仍在发论文的方向，且 He-3 是被明确点名的未来工作。
- **不依赖问题数据**：整条主线（Phase A–C）可完全基于仿真自洽验证，绕开 DT5790 数据质量的死结；实测对接降级为可选的 Phase D。

---

## 3. 文献基础（按主题组织，含用途标注）

### 3.1 理论基石
- **Pázsit & Pál (2008), _Neutron Fluctuations: A Treatise on the Physics of Branching Processes_, Elsevier** —— 本领域圣经。分支过程、主方程（Pál–Bell）、Feynman/Rossi/PSD 的严格推导都在这里。**Phase A/B 的理论出处。**
- **Williams (1974), _Random Processes in Nuclear Reactors_, Pergamon** —— 经典教材，PSD/相关函数的功能形式（如 `F(ω)=C[1+Σ Yα²/(α²+ω²)]`）。
- **Feynman, de Hoffmann, Serber (1956)** —— Feynman-α 方法原始文献。

### 3.2 连续信号 / 电流模式噪声分析（你的前沿主线，谱系完整）
- **Pál, Pázsit, Elter (2014), NIMA 763:44** —— 裂变室连续信号的随机特性；把脉冲写成"确定形状 f(t) × 随机幅值 η"，给出 Campbell 定理的优雅推导。**这正是你现有模型的形式（双指数 × 幅值）。**
- **Pál & Pázsit (2015), NIMA 794:90** —— 把上面的理论推广到**增殖介质中裂变链产生的相关探测**，这是"连续信号做噪声法"的起点。
- **Kitamura, Pázsit, Misawa (2018), Ann. Nucl. Energy 120:691** —— 由探测器电流信号的时域涨落分析确定 prompt 中子衰减常数 α；给出含脉冲衰减常数 α_e 的 ACF/VTM 附加项。
- **Kitamura & Misawa (2019), Ann. Nucl. Energy 123:119** —— 加入延迟中子效应。
- **Boros, Szieberth, Klujber, Pázsit, Barth, Kitamura, Misawa (2026), arXiv:2606.10950** —— **最关键的近期论文**。连续信号噪声测量的可行性（仿真+KUCA+BME TR 实测），脉冲形状去卷积（逆傅里叶 + Wiener 滤波）、双探测器互协方差、高计数率下连续信号胜过脉冲计数。**其仿真流程 = 你的代码 + 相关中子层**；且明确写道未来将研究 "³He chambers or scintillators" 的连续信号——**这就是留给你的口子**。

> Boros 2026 的仿真三步法，请对照你的代码看：
> 1. 点模型蒙特卡洛产生**探测事件时间戳**（含裂变链关联）——**你缺这一步的关联版本**；
> 2. 用测得的平均脉冲形状 f(t) 与幅值分布 w(η) 合成连续电压信号 + 高斯噪声——**你已有**（双指数 + 幅值 + 噪声）；
> 3. 由连续信号阈值化产生脉冲计数信号——**你已有**（阈值触发）。

### 3.3 相关中子的模拟方法
- **点模型 / 分支过程蒙特卡洛（推荐核心）** —— Boros 2026 用的"1-speed point Monte Carlo"。逐中子/逐链跟踪反应（裂变/俘获/探测/泄漏），裂变按 pν 产生子代。最透明、最轻量、与你的泊松生成器同构。
- **随机点堆动力学 SDE（可选加速）** —— Hayes & Allen (2005) 的 Itô SDE（中子密度 + 延迟中子先驱核）；Saha Ray (2012) Euler–Maruyama / 1.5 阶 Taylor。适合高计数率近似，但**不直接产生离散探测时刻**，需再叠加 Cox（doubly-stochastic）探测过程。
- **Gillespie SSA（算法基础）** —— 精确随机模拟算法，含延迟反应的修正版（延迟中子先驱核 = 延迟反应）。Phase A 的算法骨架。
- **非解析/全输运参考（重型，做交叉验证用）** —— **MCNP-PoliMi**（NIMA 2003，关联裂变，逐碰撞输出）、**MORET6 + LLNL Fission Library**（arXiv:2010.01176）、**OpenMC / Serpent / McCARD**（Kong 2014 用 McCARD 做 Rossi/Feynman/PSD；Yamamoto 2011 非解析 MC 噪声法）。Phase D 用其一为特定几何标定点模型参数。
- **多重性计数理论（安全保障学科的同源方法）** —— Cifarelli/Böhnel 因子矩、Diven 因子；把 Feynman 矩推广到 singles/doubles/triples。可作为 Phase B 的自然扩展。

### 3.4 统计严谨性（做定量结论时必须）
- **Endo & Yamamoto (2019), Ann. Nucl. Energy 124:606** —— Feynman-α 统计误差；指出 Rossi/Feynman 估计量存在显著 **bin 间相关**，必须用 bootstrap 或解析误差传播，否则拟合不确定度被严重低估。
- **Hazama (2003), Ann. Nucl. Energy 30:615** —— variance-to-mean 的死时间修正。

### 3.5 ML 的正确用法（若保留 ML 投入）
- **Multi-output Gaussian processes for inverse UQ in neutron noise analysis (arXiv:2211.02465)** —— 用 GP 做**反演+不确定度量化**，而不是生成信号。这是把你 Phase 5 的 ML 经验重新变现的正道（见 Phase E）。

---

## 4. 技术方案总览

### 4.1 阶段地图

```
[保留]  Phase 0–3 物理核心（泊松生成器降级为"非增殖极限"基线 + 验证对照）
   │
   ▼
Phase A  相关中子事件生成器（点模型/分支过程 MC）        ← 新的物理核心，主线
   │        实现 EventArrivalGenerator 协议，输出 TRUE_EVENT_DTYPE 时间戳
   ▼
Phase B  脉冲模式噪声分析 + 自洽验证                      ← 闭合正确性回路
   │        Rossi-α / Feynman-α / PSD 估计器；复原已知 α
   ▼
Phase C  连续信号噪声分析（含 He-3 特有问题）            ← 前沿贡献，论文/竞赛核心
   │        连续 ACF/VTM(含 α_e 项) / 去卷积 / 双探测器互协方差 / 死时间-堆积对比
   ├───────────────► Phase D（可选）全输运交叉验证 & 参数标定（MCNP-PoliMi/OpenMC/Serpent）
   └───────────────► Phase E（可选）逆问题：噪声曲线 → (ρ,α,β_eff,Λ) + UQ（GP/贝叶斯）
```

### 4.2 集成哲学（为什么代价极低）

你的 `events.py:simulate_true_events()` 目前这样拿到到达时间：

```python
arrival_generator = arrival_generator_for(algorithm)     # ← 唯一替换点
times_s = arrival_generator.sample(profile, 0.0, duration_s, arrival_rng)
```

只要新的相关生成器**实现同一个 `EventArrivalGenerator` 协议**（或一个返回"时间 + 链元数据"的扩展协议），返回排序后的探测时刻，后续 `ParametricHe3Spectrum → LinearAmplitudeMapper → 脉冲 → 波形 → ADC → 触发 → 死时间 → 数据集` **一行不用改**就能跑在相关数据上。这是本方案最大的工程红利：**你把 3 个阶段的下游全栈无偿继承过来了。**

建议同时：
- 保留泊松生成器，作为"倍增→0 的极限"与回归基线（Phase A 的一个必过单测：当 k→0 / 无裂变时，相关生成器统计上退化为泊松）。
- `TRUE_EVENT_DTYPE` 复用 `pileup_group_id` 存 `chain_id`，或新增 `chain_id/generation/is_delayed` 字段（向后兼容，旧数据填 -1）。

---

## 5. Phase A —— 相关中子事件生成器（核心）

### 5.1 物理模型：一速点模型（one-speed point model）

系统状态 = 一个中子布居 + 一个强度为 S 的外源泊松过程（次临界必需，代替/叠加延迟中子在稳态的作用）。每个中子以以下**每中子反应率**竞争（指数时钟）：

| 反应 | 率 | 效果 |
|---|---|---|
| 裂变 fission | λ_f | 移除入射中子，产生 ν 个子代（ν~pν） |
| 俘获/吸收(含泄漏) capture | λ_c | 移除中子 |
| 探测 detection | λ_d | **记录一个探测时刻**（He-3 中即 (n,p) 反应），移除中子 |

总移除率 `λ_t = λ_f + λ_c + λ_d`。

### 5.2 参数映射（把"物理量"翻译成"率"）——请把这张表做进配置校验

设 ν̄ = 平均裂变中子数，β = 有效缓发中子份额，pν 已知。则（一速点模型，可自洽推导，建议在代码里作为 `derived` 量计算并断言）：

```
k_eff = ν̄·λ_f / λ_t                      # 增殖因子（含缓发）
ρ     = (k_eff − 1) / k_eff               # 反应性
ε     = λ_d / λ_t                          # 每中子探测效率
α     = λ_t − (1−β)·ν̄·λ_f                 # prompt 中子衰减常数（核心！）
Λ     ≈ 1 / (ν̄·λ_f)（点模型时标下的代次时间，随定义可差常数）
D_ν   = ⟨ν(ν−1)⟩ / ⟨ν⟩²                    # Diven 因子（控制关联幅度）
```

自洽性检查：prompt 临界时 α=0 ⇒ `λ_t=(1−β)ν̄λ_f`；缓发临界(ρ=0)时 α=β/Λ（量级）。**用户设定目标 (k 或 ρ, α, ε)，代码反解出 (λ_f, λ_c, λ_d)**——这让"设定一个 k_eff=0.98 的次临界堆"成为一等公民操作，而不是手调三个率。

### 5.3 推荐算法：逐链源驱动（chain-by-chain），可并行

外源中子彼此独立（泊松），因此**每个源中子诱发的裂变链可独立模拟再叠加**。这在次临界下是"尴尬并行"的、且链必然有限（会灭绝），天然终止。

```
输入: S, duration D, (λ_f, λ_c, λ_d), pν, 缓发组 {β_i, λ_i} (Σβ_i=β)
1. 采样源中子出生时刻 {t0_j} ~ 齐次泊松(S) on [0, D]           # 复用你已有的泊松采样器！
2. 对每个源中子 j（可多进程/向量化批处理）:
     stack = [t0_j]
     while stack:
         t = stack.pop()
         dt ~ Exp(λ_t);  反应时刻 = t + dt
         按 (λ_f:λ_c:λ_d) 抽反应类型:
             capture   → 中子消失
             detection → 记录探测时刻 (t+dt) 到本链列表; 中子消失
             fission   → 抽 ν ~ pν
                 对每个子代: 以概率 (1−β) 作为瞬发中子 push(t+dt)
                            以概率 β    生成先驱核, 组 i, 延时 d~Exp(λ_i),
                                        到期发射一个中子 push(t+dt+d)
3. 汇总所有链的探测时刻, 排序 → 探测事件时间数组 (喂给下游谱→幅值→脉冲→波形)
   同时输出每个探测事件的 chain_id / generation / is_delayed 作为真值标签
```

### 5.4 延迟中子与稳态（易踩坑，务必处理）
- 缓发中子引入长时标（1/λ_i ~ 0.1–80 s），是 Feynman/Rossi 曲线"缓发平台"的来源，也维持源驱动稳态。
- 稳态获取二选一：(a) 运行足够长并丢弃 burn-in，让先驱核达到平衡浓度；(b) 直接按平衡浓度**预置初始先驱核布居**（更省时）。建议实现 (b) 并用 (a) 交叉验证。
- 第一版可先"仅瞬发"（把外源当作缓发中子在平衡时的等效常源，正如 Boros 2026 的做法），把延迟中子作为 Phase A 的第二个里程碑。

### 5.5 近临界 / 高计数率的备选引擎
- 逐链法在 k→1 时链变长、代价升高。此时切换到**布居跟踪 Gillespie**（对全布居维护一个总事件率，逐事件推进），并设显式布居上限（承你项目一贯的安全护栏风格）。
- 极高计数率下可选 **随机点堆 SDE（Hayes–Allen）+ Cox 探测层** 作为快速近似路径，但需在文档中明确标注其为近似、且丢失部分高阶关联。

### 5.6 与现有代码集成
- 新增模块：`src/he3sim/physics/chains.py`（`BranchingChainGenerator`，实现 `EventArrivalGenerator`）与 `src/he3sim/physics/source_model.py`（参数映射与校验）。
- 新增配置段：`source_model:`（`k_eff` 或 `reactivity`, `generation_time_s`, `beta_eff`, 六组 `beta_i/lambda_i`, `nu_bar`, `nu_pmf`, `source_rate_cps`, `detection_efficiency`；派生 `alpha`）。全部按你现有 `ParameterStatus` 打 `synthetic_demo`，未标定不得升 `validated`。
- CLI：`he3sim simulate-events --source-model correlated ...`；保留 `--source-model poisson` 为默认基线。

### 5.7 Phase A 验收标准
1. **退化测试**：令 λ_f→0（无裂变）时，输出到达过程在 KS 检验、间隔一阶自相关、Fano 因子上与齐次泊松不可区分。
2. **一阶正确**：长时平均计数率 = 解析值 `S·M·ε`（M 为泄漏乘子/源乘子），相对偏差 < 阈值。
3. **关联存在性**：相邻探测的间隔分布相对泊松出现可测的短时超出（正关联），且随 k 增大而增强。
4. **确定性**：同 seed 完全可复现；事件时间严格递增；显式安全上限生效。
5. 通过 ruff/mypy/pytest 全量回归；更新 `STATUS.md` 后停止（承你的门禁流程）。

> ⚠️ Phase A 只负责"产生正确关联的时间戳"。**是否真的正确，由 Phase B 的 α 复原来判定**——这就是把两阶段设计成前后咬合的原因。

---

## 6. Phase B —— 脉冲模式噪声分析与自洽验证

### 6.1 三个估计器（作用在你已有的触发/观测事件上）

**Rossi-α（自相关 / 时间差直方图）**
对探测时刻两两时间差 τ 做直方图，拟合
```
p(τ) = B + A·exp(−α|τ|)                # B: 偶然符合平台; A·exp: 关联项
```

**Feynman-α（方差-均值比, VTM）**
对一组门宽 T，统计各门内计数 C，计算 `Y(T)=Var(C)/⟨C⟩ − 1`，拟合
```
Y(T) = Y∞ · [1 − (1−e^{−αT})/(αT)]     # T→∞ 饱和到 Y∞; T→0 归零
```
其中 `Y∞ ∝ ε·D_ν/α`（精确前因子见 Pázsit–Pál Ch.3；含缓发时为多指数和）。

**PSD（Cohn-α / 功率谱）**
对计数序列做 FFT，拟合
```
F(ω) = C·[1 + Y∞·α²/(α²+ω²)]           # 平台(散粒噪声) + 洛伦兹, 拐点在 α
```

### 6.2 验证靶（本方案的"正确性圣杯"）

**闭环判据**：用 Phase A 设定一个**已知 α**（由 λ_x 精确算得），跑生成器 → 触发 → 用三个估计器反演 α_hat，要求
```
|α_hat − α_true| / α_true < 容限（如 5%），且三种方法互相一致。
```
这一步同时验证 Phase A（关联结构对）和 Phase B（估计器对）。它可完全自动化、可写进 CI，与你项目的严格验收文化完美契合。

### 6.3 死时间 / 堆积效应研究（承接你已有的死时间模块）
- 系统扫描"真计数率 × α"网格，量化死时间/堆积如何**偏置**（而非仅损失）Feynman/Rossi——短滞后关联受影响远大于长滞后（Boros 2026 §1）。
- 复现 Hazama(2003) 的 VTM 死时间修正；给出"脉冲计数法的可用上限"曲线。**这条曲线正是 Phase C 要打破的对象。**

### 6.4 统计严谨性
- 按 Endo & Yamamoto (2019) 引入 bootstrap / 解析误差传播处理 bin 间相关，报告可信的 α 不确定度。

### 6.5 Phase B 验收标准
1. 三估计器在多组 (α, ε, 计数率) 下复原 α，满足容限且互相一致。
2. 缓发中子开启时，Feynman 曲线出现正确的缓发平台。
3. 死时间效应的偏置被定量刻画，Hazama 修正复现。
4. 不确定度报告包含 bin 相关修正。

---

## 7. Phase C —— 连续信号中子噪声分析（前沿贡献）

### 7.1 为什么这是真正的新东西
- 连续信号噪声法在 2015 年后才由 Pál–Pázsit / Kitamura 谱系成熟，2026 年（Boros 等）才做完可行性实证。
- Boros 2026 用的是**裂变室**，并**明确把 He-3 探测器列为未来工作**（"the usability of the continuous signal of gamma-sensitive neutron detectors such as ³He chambers ... is being investigated"）。
- 你已经能端到端生成 **He-3 的连续波形**。于是"**He-3 探测器连续信号噪声分析的数字孪生验证**"是一个有明确出处、且尚无人系统做过的题目。

### 7.2 直接在你的连续波形上实现的三件套

**(1) 连续信号 ACF / VTM（含脉冲形状修正项）**
Kitamura 2018 / Boros 2026 给出，对 `f(t)~t·exp(−α_e t)` 形脉冲：
```
ACF(θ) = φ·e^{−α|θ|} + ψ₁·e^{−α_e|θ|} + ψ₂·|θ|·e^{−α_e|θ|}
VTM(T) = Φ·f₁(αT) + Ψ₁·f₁(α_e T) + Ψ₂·f₂(α_e T)
  f₁(x) = 1 − (1−e^{−x})/x
  f₂(x) = 1 + e^{−x} − 2(1−e^{−x})/x
```
其中 α 是系统 prompt 衰减常数、**α_e 是探测器脉冲衰减常数**（与你的 `tau_d` 直接对应）。当 α≪α_e 时附加项只污染极短滞后段，可截除；但求高阶 α 模式时 α 与 α_e 可比，问题凸显——**这正是研究点**。

**(2) 平均脉冲形状去卷积（逆傅里叶 + Wiener）**
你精确知道平均脉冲 f(t)（就是你的双指数核），可在频域去卷积得到近似 Dirac 序列：
```
d(t) = F^{-1}{ F{c}·W(ω) },   W(ω)=F*{f}/(|F{f}|²+γ·NSR(ω))
```
γ=0 为纯逆傅里叶（对噪声敏感，NSR≲1% 才稳），γ 调大用 Wiener 抑噪（代价是脉冲展宽）。Boros 2026 证明 Wiener 去卷积在很高 NSR 下仍可用。**你的数字孪生可以系统扫描 NSR 与 γ，给出 He-3 情形的稳定域——这是仿真独有的、实测很难做的贡献。**

**(3) 双探测器互协方差（CCF / CTM）**
模拟**两个探测器观测同一中子场**（同一裂变链 → 关联部分共享；各自的自项/电子噪声不共享）。互协方差自动消掉单探测器的脉冲形状自项与非关联电子噪声，恢复干净的 α。实现上：Phase A 输出探测时刻时，按各自 ε 分裂到两个探测器通道，再各自过你的波形链。

### 7.3 头条结果（论文/竞赛的"钱图"）
在数字孪生里扫描"真计数率 × α"，画出三条可用边界：
- 脉冲计数法（受死时间/堆积限制，来自 Phase B）；
- 连续信号法；
- 去卷积后脉冲法。
**证明：在脉冲计数崩溃的高计数率/高 α 区，连续信号法仍能复原 α**——把 Boros 2026 的裂变室结论**首次系统性地扩展到 He-3**，并用一个可复现的数字孪生给出定量的适用边界。

### 7.4 He-3 的特殊性（别当成裂变室的复制品——这里有真问题）
- He-3 是正比计数器、脉冲**更大更慢**（电荷收集、离子漂移），α_e 与系统 α 的分离度、去卷积难度都与裂变室不同。
- He-3 有**壁效应**（你能谱里已建模的质子壁/氚壁），导致幅值分布 w(η) 非平凡——去卷积假设"脉冲=形状×随机幅值"在壁效应下是否仍足够好，是一个可量化的研究问题。
- He-3 对 γ 相对不敏感（相对裂变室是优点），但堆积行为、死时间机理不同。
- **诚实定位**：连续/Campbelling 模式经典上用于裂变室高通量场景；He-3 经典用脉冲模式。"连续信号噪声法能否、在何种工况下适用于 He-3"本身就是**开放问题**，不是已知结论——这让它成为货真价实的课题而非工程复刻。

### 7.5 Phase C 验收标准
1. 连续 ACF/VTM 在 α≪α_e 区复原 α，与 Phase B 脉冲法一致。
2. 去卷积在给定 NSR 下把连续信号还原为可计数的准 Dirac 序列，给出 γ–NSR 稳定域。
3. 双探测器 CCF/CTM 消除脉冲形状自项，单/双探测器结果一致。
4. 产出"脉冲计数 vs 连续信号 vs 去卷积"三条可用边界图，明确标注 He-3 参数下的高计数率增益。
5. 壁效应/幅值分布对去卷积偏差的敏感性有定量报告。

---

## 8. Phase D（可选）—— 全输运交叉验证与参数标定

用途：把点模型的 (λ_f, λ_c, λ_d, ε, pν) 锚定到**真实几何**，并独立验证数字孪生的关联结构。
- 选 **OpenMC**（开源、Python 接口，最易集成；Boros 2026 用它做了探测器邻域回散射分析）或 **MCNP-PoliMi / MORET6 + LLNL Fission Library / Serpent** 生成一段**参考关联探测列表**。
- 判据：全输运参考与点模型数字孪生在 α、Feynman Y∞、Rossi 曲线上一致（在点模型近似允许的范围内）。
- 副产物：为特定零功率装置导出 Λ、β_eff、ε，让 `source_model` 从 `synthetic_demo` 升到 `provisional/validated`。

> 注意：这一步依赖外部核数据/软件，成本较高，且**不阻塞主线**。建议作为"锦上添花"或答辩加分项，而非必经关口。

---

## 9. Phase E（可选）—— 逆问题：把 ML 投入正确变现

不要再用 ML 生成信号。改做**反演**：
- 输入：噪声曲线（Feynman Y(T) / Rossi ACF / PSD，可来自你的数字孪生批量生成）。
- 输出：(ρ, α, β_eff, Λ) 的后验分布 / 点估计 + 不确定度。
- 方法：多输出高斯过程做逆 UQ（arXiv:2211.02465）、或贝叶斯拟合 / 神经后验估计（SBI）。
- 价值：数字孪生天然是"廉价无限带标签数据"的来源，正好喂反演器；这把你 Phase 5 训练/评测框架的工程积累（YAML、seed、模型卡、留出评价）迁移到一个**有净收益**的任务上。

---

## 10. 时间线与里程碑

> 假设你继续用"计划 → 审核 → 实施 → 验收 → 更新 STATUS"的 Codex 分阶段流程；下列为相对工作量与顺序，非日历硬约束。

| 里程碑 | 内容 | 相对工作量 | 交付物 |
|---|---|---|---|
| **M0 清理** | 归档/隔离 Web(3.5)、网络A(5)、网络C(6)；泊松生成器保留为基线；文档更新范围声明 | 小 | 精简后的 repo + 更新的 `PROJECT_SPEC.md` |
| **M1 Phase A-瞬发** | 逐链源驱动生成器（仅瞬发）+ 参数映射 + 退化测试 | 大 | `chains.py`, `source_model.py`, 配置段, 单测 |
| **M2 Phase A-缓发** | 加入六组延迟中子 + 稳态预置 + 近临界 Gillespie 备选 | 中 | 缓发平台可复现 |
| **M3 Phase B** | Rossi/Feynman/PSD 估计器 + α 复原闭环 + 死时间偏置研究 + 误差修正 | 中大 | `analysis/noise.py`, 自动化 α 复原报告 |
| **M4 Phase C-核心** | 连续 ACF/VTM(含 α_e) + 去卷积 + 双探测器 CCF | 大 | 连续信号分析模块 + 三条可用边界图 |
| **M5 Phase C-He3** | He-3 特有：壁效应/幅值分布对去卷积影响 + 高计数率增益定量 | 中 | 论文/竞赛核心结果与图 |
| **M6（可选）** | Phase D 全输运交叉验证 / Phase E 逆问题 | 视野心 | 加分项 |

关键路径：**M1 → M3 → M4/M5**。M3 一旦跑通"复原已知 α"，课题的科学正确性就被证明；M4/M5 是差异化贡献。

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 逐链法在近临界 k→1 计算爆炸 | Phase A 高 k 跑不动 | 布居跟踪 Gillespie 备选 + 显式布居上限；论文聚焦次临界（本就是噪声法主战场） |
| 延迟中子稳态处理错误 → Feynman 平台不对 | Phase B 结论失真 | 平衡浓度预置 + burn-in 交叉验证；先瞬发跑通再加缓发 |
| 连续信号法对 He-3 未必适用 | Phase C 可能得到"负结果" | **负结果也是结果**：给出"在何工况适用/不适用"的边界即是贡献；不预设结论 |
| 去卷积对电子噪声敏感 | 连续法数值不稳 | Wiener 正则 + γ–NSR 稳定域扫描（仿真独有优势） |
| Phase D 依赖外部软件/核数据 | 拖慢主线 | 设为可选、不阻塞；主线全部靠仿真自洽验证 |
| 误把点模型当全输运 | 过度解读 | 全程标注一速点模型近似；空间/能谱效应留作展望 |
| 统计不确定度被低估 | 定量结论不可信 | 强制 Endo–Yamamoto bin 相关修正 / bootstrap |

---

## 12. 竞赛 / 论文叙事建议

一条清晰的故事线（可直接用于摘要/答辩）：

1. **问题**：零功率反应堆的中子噪声法（Feynman-α/Rossi-α）是测反应性与动力学参数的经典手段，但传统脉冲计数在高计数率/高 α 下因死时间与堆积失效。连续信号法是新兴出路，却尚未系统性地扩展到 He-3 探测器。
2. **方法**：构建一个**信号级数字孪生**——以分支过程点模型为事件引擎，端到端生成带真实裂变链关联的 He-3 连续波形，并在其上实现脉冲计数与连续信号两套噪声反演。
3. **验证**：以"设定已知 α → 复原 α"的闭环证明物理正确性；用全输运（OpenMC）交叉验证关联结构（可选）。
4. **结果**：定量给出 He-3 情形下脉冲计数法的失效边界，以及连续信号/去卷积法把可用工况向高计数率、高 α 扩展的增益；报告壁效应与电子噪声对去卷积的影响。
5. **意义**：为 He-3 探测器的高速率反应堆噪声诊断提供了可复现的数字孪生工具与适用性边界，填补了连续信号噪声法在 He-3 上的空白。

> 关键差异化：别人做的是**系统级** DT 或**裂变室**连续信号；你做的是 **He-3 信号级** DT + 连续信号噪声法的**首次系统适用性研究**，且有一个可自动验证正确性的闭环。

---

## 13. 参考文献（精选，按主题）

**理论基石**
- Pázsit I., Pál L. (2008). _Neutron Fluctuations: A Treatise on the Physics of Branching Processes_. Elsevier.
- Williams M.M.R. (1974). _Random Processes in Nuclear Reactors_. Pergamon.
- Feynman R.P., de Hoffmann F., Serber R. (1956). Dispersion of the neutron emission in U-235 fission. _J. Nucl. Energy_.

**连续信号 / 电流模式噪声分析（前沿主线）**
- Pál L., Pázsit I., Elter Zs. (2014). Comments on the stochastic characteristics of fission chamber signals. _NIMA_ 763:44.
- Pál L., Pázsit I. (2015). Campbelling-type theory of fission chamber signals generated by neutron chains in a multiplying medium. _NIMA_ 794:90.
- Kitamura Y., Pázsit I., Misawa T. (2018). Determination of prompt neutron decay constant by time-domain fluctuation analyses of detector current signals. _Ann. Nucl. Energy_ 120:691.
- Kitamura Y., Misawa T. (2019). Delayed neutron effect in time-domain fluctuation analyses of neutron detector current signals. _Ann. Nucl. Energy_ 123:119.
- Boros M.I., Szieberth M., Klujber G., Pázsit I., Barth I., Kitamura Y., Misawa T. (2026). Feasibility demonstration of continuous signal-based neutron noise measurements by experiments and simulations. arXiv:2606.10950. **（最贴合你项目的近期论文；明确点名 He-3 为未来工作）**
- de Izarra G. et al. (2015). SPECTRON: a neutron noise measurement system in frequency domain. _Rev. Sci. Instrum._ 86:115111.
- Pakari O. et al. (2018). Kinetic parameter measurements in the CROCUS reactor using current mode instrumentation. _IEEE TNS_ 65:2456.

**相关中子模拟方法**
- Hayes J.G., Allen E.J. (2005). Stochastic point-kinetics equations in nuclear reactor dynamics. _Ann. Nucl. Energy_.
- Saha Ray S. (2012). Numerical simulation of stochastic point kinetic equation... _Ann. Nucl. Energy_.
- Gillespie D.T. —— Stochastic Simulation Algorithm（含延迟反应修正版，用于延迟中子）。
- Pozzi S. et al. (2003). MCNP-PoliMi: a Monte-Carlo code for correlation measurements. _NIMA_ 513:550.
- MORET6 + LLNL Fission Library —— "Patchy nuclear chain reactions", arXiv:2010.01176（补充材料 D）。
- Romano P.K. et al. (2015). OpenMC. _Ann. Nucl. Energy_ 82:90.
- Kong et al. (2014). 噪声法（Rossi/Feynman/PSD）on McCARD。 Yamamoto (2011). 非解析 MC 噪声法。

**统计严谨性**
- Endo T., Yamamoto A. (2019). Comparison of theoretical formulae and bootstrap method for statistical error estimation of Feynman-α method. _Ann. Nucl. Energy_ 124:606.
- Hazama T. (2003). Practical correction of dead time effect in variance-to-mean ratio measurement. _Ann. Nucl. Energy_ 30:615.

**ML 的正确用法（逆问题）**
- Multi-output Gaussian processes for inverse uncertainty quantification in neutron noise analysis. arXiv:2211.02465.

**数字孪生背景**
- Digital twins in nuclear science and engineering: bridging AI, real-time data, and physical systems (2026). _Ann. Nucl. Energy_.（系统级综述，用于对比定位你的信号级生态位）

---

## 附：给 Codex 的 Phase A 首轮计划提示词（可直接用）

```text
请进入计划模式，本轮不要修改文件。

阅读：
- @AGENTS.md
- @docs/PROJECT_SPEC.md
- @docs/STATUS.md
- @docs/ROADMAP_v2.md 的 §5（Phase A）

只为 Phase A（相关中子事件生成器）制订实施计划：
1. 列出新增模块 physics/chains.py、physics/source_model.py 的职责与公共接口；
2. 给出新增配置段 source_model 的字段、校验规则与派生量 (k_eff/ρ/ε/α/Λ/D_ν) 的计算；
3. 说明如何实现 EventArrivalGenerator 协议以复用现有 events.py 下游全栈；
4. 列出退化测试（λ_f→0 退化为泊松）、一阶计数率、关联存在性三类验收；
5. 明确本阶段不做：延迟中子（留 M2）、近临界 Gillespie（留 M2）、噪声反演（Phase B）。

发现歧义要明确指出，不得虚构核数据或设备参数。所有新参数先标 synthetic_demo。等待我确认后再实施。
```
