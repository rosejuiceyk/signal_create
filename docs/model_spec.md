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

Phase 2/Web HDF5 同时保存软件裁剪前的 `/blocks/preclip_analog_samples` 与裁剪后的
`/blocks/analog_samples`。前者只用于检查高堆积下的合成波形变化，后者才是 CSV 输出与 ADC
量化的输入；这两份数据不能被解释为已标定前放的饱和恢复模型。

孤立脉冲特征从离散样本测量 `peak_V`、`integral_V_s`、`rise_time_10_90_s` 和
`fall_time_90_10_s`，阈值交点使用线性插值。它们不是由 `tau_r_s` 或 `tau_d_s` 重命名得到。

## 随机性与并行约定

所有随机过程必须显式接收 `numpy.random.Generator`。根 seed 经
`numpy.random.SeedSequence` 创建根生成器；未来并行任务使用 `SeedSequence.spawn()` 派生子流。
不得使用 NumPy 全局随机状态。未来多进程入口必须位于 `if __name__ == "__main__"` 保护下，
并兼容 Windows `spawn`。

## Phase 5 条件标记事件研究模型

网络 A 只拟合由既有精确物理生成器产生的 `synthetic_demo` 事件窗口。给定计数率
`lambda`、窗口长度 `T` 和配置编码 `c`，计数头为：

$$
N \sim \operatorname{Poisson}\!\left(\exp\left[\log(\lambda T)+r_N(\lambda,T,c)\right]\right),
$$

其中神经网络残差 `r_N` 被限制在有限范围。间隔头是正值指数混合：

$$
p(\Delta t\mid\lambda,T,c)=\sum_{k=1}^{K}\pi_k\rho_k
\exp(-\rho_k\Delta t),\qquad \Delta t>0.
$$

推理时抽取 `N+1` 个正间隔 `d_j`，再构造窗口内严格有序时间：

$$
t_i=T\frac{\sum_{j=1}^{i}d_j}{\sum_{j=1}^{N+1}d_j},\qquad i=1,\ldots,N.
$$

事件类型使用 categorical likelihood。给定类型 `z` 后，能量通过该类型配置支持域
`[E_{min,z},E_{max,z}]` 上的 logistic-normal 密度生成；零权重类型被屏蔽。幅值、`tau_r` 和
正衰减差 `tau_d-tau_r` 使用 log-normal 条件密度，因此输出始终满足：

$$
E\ge 0,\qquad A_{peak}>0,\qquad \tau_d>\tau_r>0.
$$

训练目标是各分布头负对数似然之和，不以 MSE 代替密度学习。模型状态固定为
`experimental`；即使统计门槛通过，也不自动替代 exact Poisson + parametric spectrum 基线。

## 外部接口边界

MCNP、示波器和 DT5800 在 Phase 0 只有 Protocol 和明确抛出 `NotImplementedError` 的 stub；
电子学恢复模型也只有处理有界波形块的 `RecoveryModel` Protocol。这些接口不读取厂商文件、
不导入设备 SDK、不访问硬件、不分配大规模连续波形，也不产生物理数据。
