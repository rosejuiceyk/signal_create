# Phase C：连续信号中子噪声分析（He-3 前沿）

- 阶段编号：C（论文/竞赛核心贡献）
- 初始状态：`not_started`
- 前置阶段：Phase B 已通过；Phase HIL 已通过（双探测器 CCF 估计器与电子学背书就绪）
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

## 开始前必读
- `AGENTS.md`、`docs/PROJECT_SPEC.md`、`docs/STATUS.md`
- `docs/ROADMAP_v2.md`（§8）
- 本文件

## 研究定位
连续信号中子噪声法 2015 后由 Pál–Pázsit / Kitamura 谱系成熟，2026（Boros 等 arXiv:2606.10950）才做完可行性实证，且用的是**裂变室**，明确把 **He-3 探测器列为未来工作**。本项目已能端到端生成 He-3 连续波形 → "He-3 连续信号噪声法的数字孪生验证与适用性边界"是有明确出处、尚无人系统做过的题目。**允许出现负结果（给出不适用工况本身即贡献）。**

## 本阶段目标
直接在现有连续波形上实现连续信号噪声分析三件套，并给出"脉冲计数 vs 连续信号 vs 去卷积"的可用边界，量化 He-3 特有的壁效应/幅值分布对方法的影响。

## 必须实现

### 1. 连续信号 ACF/VTM（含脉冲衰减项）
- 对连续电压信号计算自协方差 ACF(θ) 与方差-均值 VTM(T)，拟合含脉冲衰减常数 α_e 的模型：
  ```
  ACF(θ) = φ·e^{-alpha·|θ|} + ψ1·e^{-alpha_e·|θ|} + ψ2·|θ|·e^{-alpha_e·|θ|}
  VTM(T) = Φ·f1(alpha·T) + Ψ1·f1(alpha_e·T) + Ψ2·f2(alpha_e·T)
    f1(x) = 1 - (1 - e^{-x})/x
    f2(x) = 1 + e^{-x} - 2*(1 - e^{-x})/x
  ```
  其中 alpha 是系统 prompt 衰减常数，alpha_e 对应探测器脉冲衰减（≈ 1/tau_d）。
- 处理 alpha 与 alpha_e 分离度：alpha ≪ alpha_e 时附加项只污染极短滞后段（可截除）；两者可比时给出偏差分析。

### 2. 平均脉冲去卷积（逆傅里叶 + Wiener）
- 已知平均脉冲 f(t)（即双指数核，或从数据/Phase HIL 测得），频域去卷积近似还原 Dirac 序列：
  ```
  d = F^{-1}{ F{c} · W(omega) },   W(omega) = F*{f} / (|F{f}|^2 + gamma · NSR(omega))
  ```
  gamma=0 为纯逆傅里叶，gamma 增大为 Wiener 抑噪（脉冲展宽为代价）。
- **系统扫描 gamma–NSR 稳定域**：给出在何种噪信比下逆傅里叶稳定、何时必须 Wiener、gamma 的经验最优。这是仿真独有、实测难做的贡献。
- 去卷积后可再阈值化为脉冲信号，回灌 Phase B 估计器对比。

### 3. 双探测器互协方差 CCF/CTM
- 模拟两探测器观测**同一中子场**：Phase A 输出探测时刻时按各自 ε 分裂到两个探测器通道（同链关联共享、各自自项/电子噪声不共享）。
- 计算互协方差 CCF 与互协方差-均值 CTM，自动消掉单探测器脉冲形状自项与非关联电子噪声，恢复干净 alpha。
- 复用 Phase HIL 已验证的 CCF/CTM 估计器实现。

### 4. 可用边界（本阶段头条产物）
- 在孪生里扫描 (真计数率 × alpha) 网格，画出三条可用/精度边界：
  - 脉冲计数法（受死时间/堆积限制，来自 Phase B）；
  - 连续信号法；
  - 去卷积后脉冲法。
- 证明在脉冲计数崩溃的高速率、高 alpha 区，连续信号/去卷积仍能复原 alpha（允许轻微系统低估，须如实报告）。

### 5. He-3 特殊性量化
- 壁效应/幅值分布 w(η) 对去卷积假设（脉冲=形状×随机幅值）的偏差影响：量化壁效应连续谱导致的幅值展宽对 ACF/VTM/去卷积精度的作用。
- 讨论 He-3（正比计数器、脉冲更大更慢）与裂变室在 alpha_e 分离度、去卷积难度上的差异。

## 明确不做（留后续）
- 缓发中子（Phase A2 后才有缓发平台；本阶段仍纯瞬发单指数）。
- 全输运交叉验证 Phase D。
- 逆问题 ML Phase E。
- 反应堆真实数据接入（后续数据接入阶段；但本阶段方法应能直接作用于未来真实连续波形）。

## 测试与验收
1. 连续 ACF/VTM 在 alpha ≪ alpha_e 区复原 alpha，与 Phase B 脉冲法一致（容限内）。
2. 去卷积在给定 NSR 下还原可计数准 Dirac 序列；产出 gamma–NSR 稳定域；高 NSR 下 Wiener 优于纯逆傅里叶。
3. 双探测器 CCF/CTM 消除脉冲形状自项，单/双探测器 alpha 一致。
4. 产出"脉冲计数 vs 连续信号 vs 去卷积"三条可用边界图，明确标注 He-3 参数下高速率/高 alpha 区的增益。
5. 壁效应/幅值分布对去卷积偏差的敏感性有定量报告。
6. 全量 ruff/mypy/pytest 绿灯。

建议命令：
```bash
pytest -q tests/unit/test_continuous_noise.py tests/unit/test_deconvolution.py tests/integration/test_usability_frontier.py
he3sim analyze-continuous-noise -c configs/demo_correlated.yaml -o outputs/phaseC_continuous
he3sim scan-usability-frontier -c configs/frontier_scan.yaml -o outputs/phaseC_frontier
```

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase C（He-3 连续信号中子噪声分析）。

阅读 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/STATUS.md、@docs/ROADMAP_v2.md（§8）和 @docs/phases/phase_C_continuous_signal.md。

先进入计划模式，产出：连续 ACF/VTM（含 alpha_e 项）估计与拟合、逆傅里叶+Wiener 去卷积与 gamma–NSR 稳定域扫描、双探测器 CCF/CTM（复用 Phase HIL 估计器）、可用边界扫描、He-3 壁效应/幅值分布敏感性分析、测试清单，以及本阶段明确不做（缓发、Phase D、Phase E、反应堆数据接入）。停止等待我确认。

确认后仅实施本阶段。目标是给出 He-3 情形下"脉冲计数 vs 连续信号 vs 去卷积"的可用边界，允许并如实报告负结果与系统低估。完成后运行验收命令与全量 ruff/mypy/pytest，更新 @docs/STATUS.md，然后停止。
```
