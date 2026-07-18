
# Phase 0/1/2 数学与数据契约

本文冻结 `he3-pulse-sim` 的基础数学、单位、分层和接口约定。Phase 2 已在 Phase 1 真值事件
之上生成有界分块的连续模拟电压与 ADC 码流，但仍不实现触发、死时间或观测事件。

## 参数状态与可追溯性

每个可调数值必须携带以下状态之一：

- `synthetic_demo`：仅用于证明软件链路可运行；
- `provisional`：来自有限数据、文献或待确认配置；
- `validated`：有明确证据来源，并记录人工复核者及带时区的复核时间。

配置结构校验成功不等于参数已标定，也不等于配置可以运行物理模拟。所有未来输出必须记录
规范化配置、SHA-256 配置哈希、代码版本、参数状态、单位表和根随机种子。
所有浮点配置必须是有限值；`NaN` 和正负无穷均在配置校验阶段拒绝。

## 单位与字段命名

内部时间使用秒（`*_s`），频率和采样率使用 Hz（`*_hz`），计数率使用 cps
（`*_cps`），模拟电压使用 V（`*_V`）。字段名必须显式带单位。

沉积能量按项目事件表契约保留 keV（`energy_dep_keV`）；这是核探测领域数据交换的受控例外，
不得隐式与 J 或 eV 混用。极性单独保存为 `-1` 或 `+1`，`amplitude_peak_V` 始终表示非负
峰值幅度大小。

## 三层模型

1. **真实事件层**：到达过程产生的全部中子俘获事件。
2. **模拟电子学层**：全部真实事件经过脉冲响应后叠加成连续前放波形。
3. **观测层**：连续波形经过阈值、触发、死时间、饱和与 ADC 后形成观测事件。

死时间只影响第三层。任何被死时间拒绝的事件仍必须保留在真值层，并参与连续波形叠加。

## 齐次泊松到达过程

首版真实到达率为常数 `lambda_true`。在时长 `T` 内：

$$
N(T) \sim \operatorname{Poisson}(\lambda T)
$$

相邻到达间隔满足：

$$
\Delta t_i \sim \operatorname{Exponential}(\lambda)
$$

Phase 1 已实现两条相互验证的路径：泊松计数加排序均匀时刻，以及累积指数间隔，
并继续通过 `RateProfile` 和 `EventArrivalGenerator` Protocol 保留扩展边界。

## He-3 能谱 provider

`EnergySpectrumProvider.sample(n, rng)` 的输出是沉积能量 keV 数组。后续参数化 provider 将表达
全能峰、质子壁效应、氚壁效应和可选双壁效应；MCNP importer 将来可提供事件级能量列表或
归一化能量直方图。Phase 1 使用全能峰正值截断高斯及三个有界 Beta 连续区；所有混合权重、
边界、形状和展宽均来自带参数状态的配置。演示形状不代表真实 He-3 管标定。MCNP 解析仍未实现。

## Phase 1 幅值与真值事件表

Phase 1 使用：

$$
A_{\mathrm{peak}}=G_E E_{\mathrm{dep}}+A_{\mathrm{offset}}+\epsilon_A
$$

其中 `epsilon_A` 是配置展宽，负值通过重采样截断；极性始终单独保存。
`tau_r_s` 和 `tau_d_s` 在 Phase 1 写入真值事件，并在 Phase 2 作为双指数模型时间常数使用。

Phase 1 最小 HDF5 文件只包含 `/events/true` 与 `/metadata`。Phase 2 文件在保留真值表的同时
新增 `/blocks/index`、拼接模拟电压、ADC 码和饱和掩码；仍不建立 trigger、dead-time、
observed-event 或 event-window 数据集。

## 峰值归一化双指数

对 `s = t - t0 >= 0`：

$$
g(s)=e^{-s/\tau_d}-e^{-s/\tau_r}, \qquad \tau_d>\tau_r>0
$$

峰值时刻为：

$$
t_{\mathrm{peak}}=
\frac{\tau_r\tau_d}{\tau_d-\tau_r}
\ln\left(\frac{\tau_d}{\tau_r}\right)
$$

归一化核与单脉冲定义为：

$$
h(s)=\frac{g(s)}{g(t_{\mathrm{peak}})}, \qquad
v_i(t)=\mathrm{polarity}\,A_{\mathrm{peak},i}\,h(t-t_i)
$$

`tau_r_s`、`tau_d_s` 是模型时间常数，不得命名为离散波形的 10%–90% 上升/下降时间。
Phase 2 使用解析峰值归一化，并针对事件相位在实际采样网格上再次计算离散峰值因子：

$$
c_i=\max_{k:\,t_k\geq t_i} h(t_k-t_i), \qquad
v_i[k]=\mathrm{polarity}_i\,A_{\mathrm{peak},i}\frac{h(t_k-t_i)}{c_i}
$$

因此在孤立脉冲且窗口覆盖峰值时，离散样本峰值幅度等于 `A_peak`。当任一模型时间常数少于
两个采样间隔时实现会发出分辨率警告，但不会把模型时间常数冒充测得的上升/下降时间。

## Phase 2 参考渲染与固定时间常数递推

`direct_sparse` 对每个真值事件逐项计算并相加，是优化实现的回归参考。固定时间常数时，
`recursive_fixed_tau` 分别维护衰减指数与上升指数的状态；令采样间隔为 `Delta t`，则：

$$
D_k=e^{-\Delta t/\tau_d}D_{k-1}+u_{d,k}, \qquad
R_k=e^{-\Delta t/\tau_r}R_{k-1}+u_{r,k}, \qquad
v_k=D_k-R_k
$$

事件的分数采样相位包含在 `u_d` 和 `u_r` 中。每个块结束后保存 `D_k`、`R_k` 和下一全局
样本索引，因此块边界不会截断已有脉冲尾部。事件按其第一个因果样本映射到块，但每个真实事件
只注入一次且全部参与连续叠加。`auto` 仅在时间常数一致时选择递推后端，否则回退参考实现。

## Phase 2 基线、噪声、裁剪与 ADC

模拟电压按以下顺序形成：真值脉冲叠加、常量基线、高斯白噪声、可选平稳 AR(1) 低频漂移、
模拟电压范围裁剪。AR(1) 的状态和随机流跨块连续；白噪声和漂移使用从根 seed 派生的独立
`numpy.random.Generator` 子流。随后 ADC 先施加配置偏置，再按输入范围裁剪并映射到
`0` 到 `2^bits-1` 的无符号整数码；当前存储约束为 1–16 位。饱和掩码合并模拟裁剪和 ADC
输入越界。简单裁剪不表示真实前放饱和恢复，任何此类恢复模型仍等待实测标定。

Phase 2 HDF5 同时保存软件裁剪前的 `/blocks/preclip_analog_samples` 与裁剪后的
`/blocks/analog_samples`。前者只用于检查高堆积下的合成波形变化，后者才是 CSV 输出与 ADC
量化的输入；这两份数据不能被解释为已标定前放的饱和恢复模型。

孤立脉冲特征从离散样本测量 `peak_V`、`integral_V_s`、`rise_time_10_90_s` 和
`fall_time_90_10_s`，阈值交点使用线性插值。它们不是由 `tau_r_s` 或 `tau_d_s` 重命名得到。

## 随机性与并行约定

所有随机过程必须显式接收 `numpy.random.Generator`。根 seed 经
`numpy.random.SeedSequence` 创建根生成器；未来并行任务使用 `SeedSequence.spawn()` 派生子流。
不得使用 NumPy 全局随机状态。未来多进程入口必须位于 `if __name__ == "__main__"` 保护下，
并兼容 Windows `spawn`。

## 已归档 Web/ML 合同

原 Phase 5 网络 A、Phase 6 网络 C 与 Phase 6S 合成残差合同已移入 `archive/`。活动数学合同不再
包含神经网络输入、输出或 checkpoint；齐次泊松和参数化 marks 继续由精确物理代码生成。

## Phase 4Q 数据资格边界

在采样轴得到独立确认前，DT5790 导出波形只允许使用导出样本索引和 `ADC_counts`。必须保持：

- `sample_interval_s = null`；
- 不自动删除严格相邻重复样本；
- `ENERGY` 只保存为原始 ADC channel，不解释为已验证 keV；
- 采集软件粒子标签只保存为原始字段，标准标签保持 `unknown/candidate`；
- QC 阈值标记为 `provisional`，缺少证据的项目使用 `not_evaluable`。

## 外部接口边界

MCNP、示波器和 DT5800 在 Phase 0 只有 Protocol 和明确抛出 `NotImplementedError` 的 stub；
电子学恢复模型也只有处理有界波形块的 `RecoveryModel` Protocol。这些接口不读取厂商文件、
不导入设备 SDK、不访问硬件、不分配大规模连续波形，也不产生物理数据。
