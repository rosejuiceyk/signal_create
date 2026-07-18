# Phase A：相关中子事件生成器（纯瞬发）

- 阶段编号：A（相关中子主线第一阶段）
- 当前状态：`human_review_passed`（2026-07-19 用户确认）
- 前置阶段：代码库精简（`00_CLEANUP_PROMPT.md`）已完成；Phase 0–3 物理核心保留可用
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

## 开始前必读
- `AGENTS.md`、`docs/PROJECT_SPEC.md`、`docs/STATUS.md`
- `docs/ROADMAP_v2.md`（尤其 §4、§5）
- 本文件

## 本阶段目标
在保持现有 Protocol 抽象与 `TRUE_EVENT_DTYPE` 契约不变的前提下，新增一个**基于一速点模型/分支过程蒙特卡洛**的**纯瞬发**相关中子事件生成器：产出带真实裂变链关联的探测事件时间戳，并使现有"波形合成 → ADC → 触发 → 死时间 → 数据集 → 画图"全栈**无需改动**即可运行于相关数据。保留原泊松生成器为默认基线与回归对照。

## 入口条件
- 现有 `physics/arrivals.py` 的 `EventArrivalGenerator` 协议、`events.py:simulate_true_events()` 的调用点、`types.py:TRUE_EVENT_DTYPE` 可用。

## 必须实现

### 1. 参数与配置
- 新增配置段 `source_model`，字段（全部先标 `synthetic_demo`）：
  - 物理输入：`k_eff`（或 `reactivity`，二选一并互算）、`alpha`（prompt 衰减常数，1/s）、`detection_efficiency`（每中子探测概率 ε）、`nu_bar`、`nu_pmf`（裂变多重性 pν 列表）、`source_rate_cps`（外源强度 S）。
  - 派生量（作为 `derived` 计算并断言自洽）：`lambda_f/lambda_c/lambda_d/lambda_t`、`generation_time_s (Λ)`、`diven_factor (D_ν)`。
- 参数映射（纯瞬发，写进 `physics/source_model.py` 并做校验）：
  ```
  lambda_t = alpha / (1 - k_eff)
  lambda_f = k_eff * lambda_t / nu_bar
  lambda_d = epsilon * lambda_t
  lambda_c = lambda_t - lambda_f - lambda_d        # 必须 >= 0，否则报错并提示 (k/nu_bar + eps) 越界
  D_nu     = <ν(ν-1)> / <ν>^2  （由 nu_pmf 计算）
  ```
  - 校验：pν 非负且和为 1；`nu_bar` 与 pν 一致（容差内）；`0 < k_eff < 1`（纯瞬发次临界为主）；`alpha > 0`；`0 < epsilon`；`lambda_c >= 0`。

### 2. 生成器
- 新增 `physics/chains.py`：`BranchingChainGenerator`，实现 `EventArrivalGenerator` 协议（`sample(profile, t_start_s, duration_s, rng) -> 排序探测时刻`）。
- 算法：**逐链源驱动，纯瞬发**（见 ROADMAP §5.3）：
  - 外源时刻用现有泊松采样器在 `[t_start, t_start+duration)` 上抽样（复用，不重造）；
  - 每个源中子跑一条分支链：指数寿命 `Exp(lambda_t)` → 按 `(lambda_f:lambda_c:lambda_d)` 抽反应 → 探测则记录时刻、裂变则把 ν 个瞬发子代入栈；
  - 汇总所有链探测时刻，排序返回。
- 输出对齐现有真值表：探测时刻写入 `t_s`，其余字段（能谱/幅值/脉冲参数）仍由现有下游（`ParametricHe3Spectrum → LinearAmplitudeMapper → FixedPulseParameterProvider`）填充——**本阶段只负责产生正确关联的时间戳**。
- 真值标签：将 `chain_id`、`generation` 写入（复用 `pileup_group_id` 存 `chain_id`，或新增 `chain_id/generation` 字段，旧数据填 -1，保持向后兼容）。
- 安全护栏：承既有风格，设显式"预期事件上限 / 单链最大代数 / 总事件上限"，超限报错而非静默。
- 可复现：同 seed 完全可复现；探测时刻严格递增（排序后）。

### 3. 接线
- `events.py:simulate_true_events()` 增加生成器选择（如 `--source-model {poisson,correlated}` 经 CLI/配置），**默认仍为 poisson**；`correlated` 走 `BranchingChainGenerator`。
- CLI：`he3sim simulate-events --source-model correlated -c <cfg> -o <out>`。

## 明确不做（留后续）
- **延迟中子 / 先驱核**（Phase A2）。
- **近临界 k→1 的布居跟踪 Gillespie**（Phase A2；本阶段以次临界为主，近临界报错或警告即可）。
- **噪声分析（Rossi/Feynman/PSD）**（Phase B）。
- DT5800 / 连续信号 / 反应堆数据。
- 任何空间/能量多群效应（一速点模型近似，文档标注）。

## 测试与验收
1. **退化测试**：令 `lambda_f→0`（`k_eff→0` 或裂变关闭）时，输出过程在 KS 检验、间隔一阶自相关、Fano 因子上与齐次泊松（率 `S·ε`）不可区分。
2. **一阶解析靶**：长时平均探测率 = `S·ε/(1-k_eff)`，相对偏差 < 容限（如 2%，足够统计下）。
3. **关联存在性**：相邻探测间隔分布相对同率泊松出现可测的短时超出（正关联），且关联强度随 `k_eff` 增大而单调增强。
4. **确定性/契约**：同 seed 可复现；`t_s` 严格递增；`TRUE_EVENT_DTYPE` 契约不破；安全上限生效。
5. **回归**：泊松默认路径与既有测试全部不变；下游波形/ADC/触发/死时间/数据集在 `correlated` 输入下能跑通（冒烟测试）。
6. 全量 `ruff format --check`、`ruff check`、`mypy src`、`pytest -q` 绿灯。

建议命令：
```bash
pytest -q tests/unit/test_chains.py tests/unit/test_source_model.py
he3sim simulate-events --source-model correlated -c configs/demo_minimal.yaml -o outputs/phaseA_events.h5
he3sim inspect outputs/phaseA_events.h5
```

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase A（纯瞬发相关中子事件生成器）。

阅读 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/STATUS.md、@docs/ROADMAP_v2.md（§4、§5）和 @docs/phases/phase_A_prompt_generator.md。

先进入计划模式，产出：新增 physics/chains.py 与 physics/source_model.py 的职责与公共接口、source_model 配置段字段与校验、参数映射与派生量计算、events.py 接线点、退化/一阶/关联三类验收测试清单、安全护栏、以及本阶段明确不做（延迟中子、近临界 Gillespie、噪声分析、DT5800、连续信号）。停止等待我确认。

确认后仅实施本阶段：实现纯瞬发逐链源驱动生成器，复用现有泊松采样器抽外源、复用现有下游填充能谱/幅值/脉冲参数，只负责产生正确关联的探测时间戳；保留 poisson 为默认。所有新参数标 synthetic_demo，不虚构核数据。完成后运行本阶段验收命令与全量 ruff/mypy/pytest，更新 @docs/STATUS.md，然后停止，不得进入 Phase B。
```
