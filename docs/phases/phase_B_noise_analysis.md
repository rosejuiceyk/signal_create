# Phase B：脉冲模式噪声分析与 α 复原闭环

- 阶段编号：B
- 当前状态：`human_review_passed`
- 前置阶段：Phase A（纯瞬发）已通过人工审核
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

## 开始前必读
- `AGENTS.md`、`docs/PROJECT_SPEC.md`、`docs/STATUS.md`
- `docs/ROADMAP_v2.md`（§6）
- 本文件

## 本阶段目标
在 Phase A 产生的相关事件（及其经现有触发/死时间得到的观测事件）之上，实现三种经典中子噪声估计器（Rossi-α、Feynman-α、PSD），并闭合**"设定已知 α → 反演 α_hat → 复原"** 的自洽验证回路。这一步同时证明 Phase A 的关联结构正确与本阶段估计器正确，是整条主线的科学正确性判据。

## 入口条件
- `correlated` 生成器可产出已知 α 的事件；现有 `acquisition/trigger.py`、`dead_time.py` 可将真值事件转为观测事件。

## 必须实现

### 1. 估计器（新增 `analysis/noise.py`）
- **Rossi-α（自相关/时间差直方图）**：统计探测对的时间差 τ 直方图，拟合
  ```
  p(τ) = B + A·exp(-alpha·|τ|)
  ```
  支持"全对法"或分档法；输出 `alpha`、`A`、`B` 及拟合优度。
- **Feynman-α（方差-均值比 VTM）**：对一组门宽 T，计算 `Y(T)=Var(C)/⟨C⟩ - 1`，拟合
  ```
  Y(T) = Y_inf · [1 - (1 - exp(-alpha·T))/(alpha·T)]      # 纯瞬发=单指数，无缓发平台
  ```
  输出 `alpha`、`Y_inf` 及拟合优度。
- **PSD（Cohn-α）**：由计数序列 FFT 估计功率谱，拟合
  ```
  F(omega) = C · [1 + Y_inf · alpha^2 / (alpha^2 + omega^2)]
  ```
  输出 `alpha`（拐点）及 `Y_inf`。

### 2. 统计严谨性
- 实现 bin 间相关的处理：Feynman/Rossi 估计量存在显著 bin-to-bin 相关（Endo & Yamamoto 2019），必须用 **bootstrap** 或解析误差传播给出可信的 α 不确定度，而非朴素最小二乘误差。
- 报告中心值与不确定度分别列出。

### 3. α 复原闭环（本阶段核心交付）
- 提供一个自动化流程/报告：给定若干 `source_model`（各自已知 `alpha_true`）→ 跑 `correlated` 生成 → 触发 → 三估计器 → 得 `alpha_hat` → 判定
  ```
  |alpha_hat - alpha_true| / alpha_true < 容限（默认 5%），且 Rossi/Feynman/PSD 三法互相一致（差异 < 容限）。
  ```
- 覆盖多组 (alpha, epsilon, 计数率)。

### 4. 死时间/堆积偏置研究
- 扫描 (真计数率 × alpha) 网格，量化死时间/堆积对 Rossi/Feynman 的**偏置**（不仅是计数损失），说明短滞后关联受影响远大于长滞后。
- 复现 Hazama(2003) 的 variance-to-mean 死时间修正，验证修正后偏置减小。
- 产出"脉冲计数法可用上限"曲线（作为 Phase C 的对照基线）。
- 注：真实电子学的死时间量值/类型在 Phase HIL 用 DT5800 标定；本阶段用现有观测层死时间模型即可。

## 明确不做（留后续）
- 连续信号 ACF/VTM、去卷积、双探测器 CCF（Phase C）。
- DT5800 硬件在环（Phase HIL）。
- 缓发平台（延迟中子在 Phase A2 后才出现）。
- 反应堆数据接入。

## 测试与验收
1. 三估计器在多组 (alpha, epsilon, 计数率) 下复原 alpha，满足容限且互相一致（闭环通过）。
2. 退化：泊松输入（无关联）时 Rossi 的关联项 A→0、Feynman 的 Y_inf→0（在统计涨落内）。
3. 不确定度报告包含 bin 相关修正（bootstrap 或解析），且比朴素最小二乘误差更大（更保守）。
4. 死时间偏置被定量刻画；Hazama 修正复现并减小偏置。
5. 全量 ruff/mypy/pytest 绿灯。

建议命令：
```bash
pytest -q tests/unit/test_noise_estimators.py tests/integration/test_alpha_recovery.py
he3sim analyze-noise -c configs/demo_minimal.yaml -o outputs/phaseB_noise
he3sim validate-alpha-recovery -c configs/demo_minimal.yaml -o outputs/phaseB_recovery
```

## 2026-07-19 实施与自动验收记录

- `analysis/noise.py` 已实现 Rossi-α、Feynman-α、PSD 三估计器；拟合边界固定为
  `100–5000 s^-1`，不读取真值作为初值。
- Feynman/Rossi 的 bin 相关不确定度使用时间块 bootstrap；报告标准差取 bootstrap 与朴素
  曲线拟合误差的保守上界，并分别保存二者。
- 闭环覆盖三组 `(alpha, epsilon, 真计数率)`；正式报告最大 α 相对误差 `3.94%`，三方法最大
  差异 `2.37%`，均小于默认 `5%` 门限。
- 非延长型 `4 us` synthetic_demo 死时间扫描覆盖 `2 × 4` 个 `(alpha, 真率)` 点；实现并标明
  Hazama/Mueller 弱损失一阶 VTM 修正 `Y_corr = Y_obs + 2 R_obs d`。共同 `5%` 可用上限为
  `10000 cps`；该上限从最低扫描率连续满足门限的工况得到，超过边界不声称无偏。
- `validate-alpha-recovery` 生成 7 张 PNG、离线 HTML 和 JSON。所有新增图片普通说明使用中文，
  Rossi-α、Feynman-α、PSD、VTM、Y∞ 等专业名词保留。
- 未实现交互仪表盘，以及连续信号、HIL、缓发平台或反应堆数据。

### 2026-07-20 人工审核记录

| 项目 | 填写内容 |
|---|---|
| 审核人 | 用户 |
| 审核时间（含时区） | 2026-07-20（Asia/Shanghai） |
| 正式产物 | `outputs/phaseB_recovery/`：7 PNG + HTML + JSON |
| 结论 | 通过 |
| 备注 | Phase HIL 被明确跳过；Phase C 已授权开始
- 指定环境全量验收：Ruff 与 mypy 通过，`pytest -q` 为 `167 passed`；正式 CLI 报告通过。
- 自动验收已通过；2026-07-20 用户人工审核通过。Phase HIL 已被用户跳过；Phase C 已授权。

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase B（脉冲模式噪声分析与 α 复原闭环）。

阅读 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/STATUS.md、@docs/ROADMAP_v2.md（§6）和 @docs/phases/phase_B_noise_analysis.md。

先进入计划模式，产出：analysis/noise.py 的 Rossi-α/Feynman-α/PSD 估计器接口与拟合模型、bin 相关的 bootstrap/解析误差方案、α 复原闭环的自动化流程与判据、死时间偏置研究与 Hazama 修正、测试清单，以及本阶段明确不做（连续信号、DT5800、缓发平台、反应堆数据）。停止等待我确认。

确认后仅实施本阶段。三估计器必须在"设定已知 alpha → 反演 → 复原"上闭环通过并互相一致；不确定度必须包含 bin 相关修正。完成后运行验收命令与全量 ruff/mypy/pytest，更新 @docs/STATUS.md，然后停止，不得进入 Phase HIL。
```
