# Phase 0 数学与数据契约

本文冻结 `he3-pulse-sim` 的基础数学、单位、分层和接口约定。Phase 0 仅定义这些契约，
不生成事件、能谱样本或连续波形。

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

后续 Phase 1 将实现两条相互验证的路径：泊松计数加排序均匀时刻，以及累积指数间隔。
Phase 0 仅保留 `RateProfile` 和 `EventArrivalGenerator` Protocol。

## He-3 能谱 provider

`EnergySpectrumProvider.sample(n, rng)` 的输出是沉积能量 keV 数组。后续参数化 provider 将表达
全能峰、质子壁效应、氚壁效应和可选双壁效应；MCNP importer 将来可提供事件级能量列表或
归一化能量直方图。Phase 0 不实现任何能谱抽样或 MCNP 解析。

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
公式的数值实现属于 Phase 2。

## 随机性与并行约定

所有随机过程必须显式接收 `numpy.random.Generator`。根 seed 经
`numpy.random.SeedSequence` 创建根生成器；未来并行任务使用 `SeedSequence.spawn()` 派生子流。
不得使用 NumPy 全局随机状态。未来多进程入口必须位于 `if __name__ == "__main__"` 保护下，
并兼容 Windows `spawn`。

## 外部接口边界

MCNP、示波器和 DT5800 在 Phase 0 只有 Protocol 和明确抛出 `NotImplementedError` 的 stub；
电子学恢复模型也只有处理有界波形块的 `RecoveryModel` Protocol。这些接口不读取厂商文件、
不导入设备 SDK、不访问硬件、不分配大规模连续波形，也不产生物理数据。
