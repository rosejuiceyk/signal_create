# He-3 核反应堆探测器脉冲信号模拟系统
## Codex 总方案、阶段计划与验收提示词

> 文档状态：需求已确认，可作为项目总规范直接交给 Codex。  
> 当前范围：先完成软件仿真、数据集、验证与神经网络研究原型；不实现 DT5800 控制，不依赖 DT5790，不实现 GUI。  
> 设备真实参数尚不完整：所有临时数值必须标记为 `synthetic_demo` 或 `provisional`，严禁描述为真实探测器标定参数。

---

# 一、项目目标

从零建立一个可运行、可测试、可扩展的科研软件工程，用于模拟零功率反应堆场景下 He-3 正比计数管及其前置放大器输出的脉冲信号。

系统以死时间之前的真实中子到达率为主要工况输入：

- 计数率范围：`10 cps ~ 10,000,000 cps`；
- 首版仅研究非相关热中子，采用齐次泊松过程；
- 采样率支持 `100 MS/s ~ 250 MS/s`，默认演示配置可使用 `250 MS/s`；
- 单段持续时间可配置，同时支持按目标事件数确定虚拟观测时间；
- 输出真实事件列表、连续前放波形、ADC 波形、触发/死时间后的观测事件列表和事件中心窗口；
- 保留脉冲叠加，不得用死时间直接删除连续波形中的真实事件；
- 首版使用参数化 He-3 理论能谱，后续接入 MCNP 输出；
- 首版脉冲形状使用归一化双指数模型；
- 后续使用示波器采集的孤立脉冲和多个已知计数率下的连续波形进行标定；
- 神经网络研究路线包括：
  1. 条件事件参数生成模型 A；
  2. 物理波形残差生成模型 C。

最终软件应能回答：给定真实计数率、采样率、时间窗和探测器/电子学配置，系统能否生成统计正确、可解释、可复现，并逐步接近实测前放输出的连续脉冲波形？

---

# 二、必须坚持的科学原则

## 2.1 不混淆真实事件、连续波形与观测事件

必须分为三个层级：

1. **真实事件层**：泊松过程产生的全部中子俘获事件；
2. **模拟电子学层**：全部真实事件经过脉冲响应后叠加形成连续前放波形；
3. **观测层**：连续波形经过阈值、触发、死时间、饱和和 ADC 后得到的可记录事件。

死时间影响观测事件，不得默认从真实事件流或连续波形中删除事件。

## 2.2 物理模型是基线，神经网络不能替代已知的精确采样器

当前非相关中子到达过程已有精确的泊松采样方法。网络 A 只能作为研究对照或未来非理想/相关事件模型，不能默认替代泊松生成器。

若神经网络不能在物理统计、实测一致性或生成效率上优于相应基线，则必须保持关闭，不得为了“使用 AI”而进入默认链路。

## 2.3 所有临时参数显式标记

参数状态至少分为：

- `synthetic_demo`：仅保证程序演示可运行；
- `provisional`：由有限数据或文献估计，等待人工确认；
- `validated`：由明确实验、设备配置或标定结果确认。

输出文件必须保存参数状态和配置哈希。

## 2.4 先验收物理，再验收实测一致性，最后验收神经网络

阶段顺序不可颠倒：

1. 泊松事件、能谱和波形数学正确；
2. 堆积、触发、死时间和数据格式正确；
3. 与示波器数据比较；
4. 再训练和评价神经网络。

---

# 三、理论模型

## 3.1 中子到达过程

首版为计数率恒定的齐次泊松过程，输入为真实到达率 `lambda_true`。

在时间窗 `T` 内：

$$
N(T)\sim\operatorname{Poisson}(\lambda T)
$$

相邻事件间隔：

$$
\Delta t_i\sim\operatorname{Exponential}(\lambda)
$$

固定时间窗下推荐的精确、高效实现：

1. 先抽样 `N ~ Poisson(lambda * T)`；
2. 再抽样 `N` 个 `Uniform(0,T)` 时间并排序。

同时保留累积指数间隔算法用于交叉验证和流式事件生成。

必须定义统一接口：

```python
class RateProfile(Protocol):
    def rate(self, t_s: float | np.ndarray) -> float | np.ndarray: ...

class EventArrivalGenerator(Protocol):
    def sample(self, profile: RateProfile, t_start_s: float, duration_s: float, rng: np.random.Generator) -> EventTimes: ...
```

首版只实现 `ConstantRateProfile`；预留非齐次泊松过程接口，不在首版实现时变工况。

## 3.2 He-3 参数化沉积能谱

热中子反应：

$$
{}^3\mathrm{He}+n\rightarrow p+{}^3\mathrm{H}+764\ \mathrm{keV}
$$

质子和氚的动能约为 573 keV 与 191 keV。首版参数化谱至少包含：

- `full_energy`：764 keV 全能峰；
- `proton_wall`：质子壁效应连续区；
- `triton_wall`：氚壁效应连续区；
- `double_wall`：可选的更低能连续区。

建议实现为可配置混合分布：

```text
p(E) = w_full p_full(E)
     + w_pwall p_pwall(E)
     + w_twall p_twall(E)
     + w_dwall p_dwall(E)
```

实现约束：

- 混合权重非负且和为 1；
- 全能峰使用截断高斯或先抽样真值后施加分辨展宽；
- 壁效应连续区使用定义域受限的 Beta 分布或分段密度；
- 所有形状和权重仅为可调参数，不宣称代表真实管体；
- 后续可用示波器/能谱数据拟合，也可被 MCNP 沉积能量分布替换。

统一接口：

```python
class EnergySpectrumProvider(Protocol):
    def sample(self, n: int, rng: np.random.Generator) -> EnergySamples: ...

# 首版
ParametricHe3Spectrum
EmpiricalSpectrum

# 仅预留接口
MCNPSpectrumImporter
```

MCNP 导入器未来至少支持两种形式：

- 事件级沉积能量列表；
- `energy_bin_keV, probability` 归一化直方图。

## 3.3 能量到峰值幅值

首版采用线性映射：

$$
A_{\mathrm{peak}}=G_E E_{\mathrm{dep}}+\epsilon_A
$$

约定：

- `A_peak` 始终保存为正的峰值幅度大小；
- 脉冲正负由独立的 `polarity ∈ {-1,+1}` 决定；
- `G_E`、偏置、幅值展宽参数均在标定文件中；
- 当前演示参数标记为 `synthetic_demo`；
- 幅值抽样结果不得为负，采用合理截断或重采样。

## 3.4 归一化双指数前放脉冲

对 `s=t-t0 >= 0`：

$$
g(s)=e^{-s/\tau_d}-e^{-s/\tau_r}, \qquad \tau_d>\tau_r>0
$$

峰值时刻：

$$
t_{\mathrm{peak}}=
\frac{\tau_r\tau_d}{\tau_d-\tau_r}
\ln\left(\frac{\tau_d}{\tau_r}\right)
$$

归一化核：

$$
h(s)=\frac{g(s)}{g(t_{\mathrm{peak}})}
$$

单脉冲：

$$
v_i(t)=\mathrm{polarity}\cdot A_{\mathrm{peak},i}\cdot h(t-t_i)
$$

要求：

- `A_peak` 必须等于最终离散波形的目标峰值，数值误差需有测试；
- 配置中的 `tau_r`、`tau_d` 是模型时间常数，不得直接错误命名为 10%–90% 上升时间；
- 同时计算并输出离散波形测得的 `rise_time_10_90`、`fall_time_90_10`；
- 初始可固定 `tau_r`、`tau_d`；接口需支持未来条件联合分布：
  `p(tau_r, tau_d | A, event_type, detector_config)`；
- 当时间常数相对采样间隔过小时输出分辨率警告。

## 3.5 连续波形与堆积

连续模拟电压：

$$
v(t)=b(t)+n(t)+\sum_i v_i(t)
$$

其中 `b(t)` 为基线，`n(t)` 为噪声。所有事件都参与求和，因此自然产生堆积。

实现至少提供：

- `direct_sparse`：逐事件局部加核，作为参考实现；
- `recursive_fixed_tau`：固定时间常数时，使用两个指数递推状态实现高效双指数响应，并跨块保存状态；
- `kernel_bank`：未来时间常数变化时按参数分箱或模板库处理；
- `auto`：根据事件数、样本数和时间常数模式选择后端。

必须做参考实现与优化实现的一致性测试。

## 3.6 噪声、基线与数字化

首版物理软件至少支持：

- 常量基线；
- 高斯白噪声；
- 可选低频漂移（AR(1)、随机游走或有限个低频正弦分量）；
- 模拟电压上下限裁剪；
- ADC 位数、输入范围、偏置和量化；
- 饱和样本标记。

注意：简单裁剪不等于真实前放恢复模型。探测器空间电荷、前放非线性恢复、饱和恢复仅预留插件接口，等待高计数率实测标定。

## 3.7 触发与死时间

必须分别实现：

- `none`；
- `nonparalyzable`；
- `paralyzable`。

理想非延长型关系：

$$
m=\frac{\lambda}{1+\lambda\tau_d}
$$

理想延长型关系：

$$
m=\lambda e^{-\lambda\tau_d}
$$

实现两条路径：

1. **事件级理想死时间**：用于和理论公式对照；
2. **波形触发死时间**：对阈值触发结果施加死时间，更接近实际采集。

触发器至少支持：

- 正/负脉冲阈值；
- 滞回；
- 最小保持时间；
- 触发前后窗口；
- 触发事件与真实事件的多对多关联表。

## 3.8 多尺度时长与数据量控制

不得在 10 cps 下为了获得大量事件而默认渲染数十秒的 250 MS/s 连续波形。

必须区分：

- `event_horizon`：用于生成事件统计的虚拟观察时间；
- `continuous_blocks`：实际渲染的有限连续波形块；
- `event_windows`：围绕事件渲染的固定长度窗口。

支持：

- `fixed_duration`；
- `target_event_count`；
- `min_duration`、`max_duration`；
- `max_samples_per_block`；
- 低计数率主要保存事件列表和事件窗口；
- 高计数率主要保存连续块；
- 块边界必须保持双指数尾部和基线状态连续。

---

# 四、软件架构

```text
he3-pulse-sim/
├── pyproject.toml
├── README.md
├── LICENSE
├── CHANGELOG.md
├── configs/
│   ├── demo_minimal.yaml
│   ├── provisional_he3.yaml
│   └── schemas/
├── src/he3sim/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── logging.py
│   ├── types.py
│   ├── physics/
│   │   ├── rate_profiles.py
│   │   ├── arrivals.py
│   │   ├── spectra.py
│   │   ├── amplitude.py
│   │   └── pulse_models.py
│   ├── synthesis/
│   │   ├── renderers.py
│   │   ├── streaming.py
│   │   ├── noise.py
│   │   ├── baseline.py
│   │   └── digitizer.py
│   ├── acquisition/
│   │   ├── trigger.py
│   │   ├── dead_time.py
│   │   └── event_matching.py
│   ├── io/
│   │   ├── hdf5.py
│   │   ├── zarr_adapter.py
│   │   ├── oscilloscope.py
│   │   ├── mcnp.py
│   │   └── dt5800_stub.py
│   ├── analysis/
│   │   ├── pulse_features.py
│   │   ├── counting_stats.py
│   │   ├── spectrum_metrics.py
│   │   ├── waveform_metrics.py
│   │   └── reports.py
│   └── ml/
│       ├── datasets.py
│       ├── event_generator/
│       ├── residual_generator/
│       └── evaluation.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── statistical/
│   └── regression/
├── notebooks/
├── scripts/
├── docs/
└── outputs/  # gitignore
```

技术要求：

- Python 包采用 `src/` 布局和 `pyproject.toml`；
- 核心代码使用类型标注；
- 配置使用 YAML + Pydantic 校验；
- 随机数统一使用 `numpy.random.Generator`，禁止散落使用全局随机状态；
- Windows 多进程代码必须 `spawn` 安全；
- CPU 算力机使用进程级并行，但工作进程数根据 32 GB 内存受控；
- PyTorch 自动检测 CUDA，CPU 仍能运行小规模测试；
- 物理仿真核心不得依赖 PyTorch；
- GUI、Web、DT5800 SDK、实时硬件输出均不在当前阶段实现；
- `dt5800_stub.py` 只定义未来适配器协议和明确的 `NotImplementedError`。

---

# 五、数据格式

首版主格式：HDF5；Zarr 仅做可选适配器，不阻塞核心交付。

推荐避免大量 HDF5 可变长对象，使用“拼接数组 + 索引表”：

```text
run.h5
├── metadata/
│   ├── config_yaml
│   ├── config_hash
│   ├── code_version
│   ├── parameter_status
│   └── units
├── blocks/
│   ├── adc_samples          # 1D 拼接 int16/uint16
│   ├── analog_samples       # 可选 float32，仅验证/小样本
│   └── index                # block_id, offset, length, t_start, fs, rate...
├── events/
│   ├── true
│   ├── observed
│   └── trigger_event_links
├── windows/
│   ├── adc                  # 固定长度二维数组
│   └── metadata
├── calibration/
└── statistics/
```

真实事件表至少包含：

```text
event_id
t_s
energy_dep_keV
spectrum_component_id
amplitude_peak_V
tau_r_s
tau_d_s
polarity
block_id
sample_index
pileup_group_id
parameter_status
```

观测事件表至少包含：

```text
trigger_id
trigger_time_s
accepted
rejection_reason
peak_adc
peak_V
integral
rise_time_10_90_s
fall_time_90_10_s
is_pileup
is_saturated
```

默认保存 ADC 整数和标定元数据；模拟电压 float32 仅按配置保存，避免文件膨胀。

---

# 六、统一 CLI

最终至少提供：

```bash
he3sim validate-config -c configs/demo_minimal.yaml
he3sim simulate -c configs/demo_minimal.yaml -o outputs/demo.h5
he3sim inspect outputs/demo.h5
he3sim validate-physics -c configs/demo_minimal.yaml -o outputs/validation/
he3sim generate-dataset -c configs/provisional_he3.yaml -o outputs/dataset/
he3sim analyze-scope --input <path> --profile generic_csv -o outputs/calibration/
he3sim train-event-model -c configs/ml_event.yaml
he3sim train-residual-model -c configs/ml_residual.yaml
he3sim compare-models -c configs/evaluation.yaml -o outputs/comparison/
```

---

# 七、阶段交付与强制门禁

## 阶段 0：工程骨架与数学基线

交付：

- 可安装 Python 包；
- 配置系统、数据类型、日志、CLI；
- 数学公式文档；
- 最小演示配置；
- 基础 CI/pytest；
- 不实现完整模拟器。

通过条件：

- `pip install -e .` 成功；
- `pytest` 成功；
- `he3sim validate-config` 成功；
- Windows 路径和多进程入口无明显问题。

## 阶段 1：真实事件与能谱

交付：

- 泊松到达生成器两种实现；
- 参数化 He-3 能谱；
- 能量到幅值映射；
- HDF5 事件表最小写入；
- 统计验证报告。

通过条件：

- 事件数均值接近 `lambda*T`；
- 方差/均值接近 1；
- 间隔分布通过固定随机种子的统计检验；
- 两种泊松实现分布一致；
- 能谱权重、定义域和峰位测试通过；
- 不出现负能量、负幅值或无序时间。

## 阶段 2：连续双指数波形

交付：

- 归一化双指数核；
- 参考渲染器和高效渲染器；
- 脉冲叠加；
- 跨块尾部状态；
- 噪声、基线、裁剪、ADC；
- 波形特征提取。

通过条件：

- 单脉冲峰值与 `A_peak` 相对误差满足数值容限；
- 单事件时间平移正确；
- 两事件叠加满足线性叠加测试；
- 优化渲染器与参考实现一致；
- 分块与一次性渲染在边界处一致；
- ADC 量化和饱和标记正确。

## 阶段 3：触发、死时间、完整数据集与性能

交付：

- 正/负脉冲触发；
- 延长型、非延长型死时间；
- 真值事件、连续波形、观测事件、窗口关联；
- 多尺度数据集生成；
- HDF5 分块压缩；
- 计数率扫描报告。

通过条件：

- 理想事件级死时间仿真与解析关系在统计误差内一致；
- 真实事件不因死时间从连续波形消失；
- 触发与真实事件关联可追溯；
- 从 10 到 1e7 cps 的固定验证点均能运行；
- 高计数率使用分块流式处理，内存不会随总时长线性无限增长；
- 提供性能报告，但首版不设置跨机器固定秒数门槛。

## 阶段 4：示波器数据标定与真实模板

入口条件：用户提供孤立单脉冲和多个已知计数率下的连续波形。

交付：

- 通用示波器 CSV/NPZ 导入接口；
- 基线、噪声、极性、脉冲检测；
- 孤立脉冲筛选和对齐；
- 双指数拟合；
- 幅值、上升/下降、积分电荷联合分布；
- `provisional` 标定配置与人工审核报告；
- 实测模板库接口。

通过条件：

- 不硬编码某一示波器列名；
- 无法识别单位时明确报错或要求 profile；
- 拟合失败事件有 QC 标记，不静默纳入模板；
- 训练、验证、测试按采集 run 划分，防止相邻片段泄漏。

## 阶段 5：神经网络 A——条件事件参数生成

定位：研究对照，不替代精确泊松基线。

建议基线架构：条件标记时间点过程或强度无关的时间间隔模型。

输入：

- `log10(true_rate_cps)`；
- 时间窗长度；
- 探测器配置编码；
- 随机潜变量。

输出：

- 可变事件数；
- 单调递增到达时间；
- `energy/amplitude, tau_r, tau_d, event_type` 等 marks。

最低实现：

- 事件数头：Poisson/Negative-Binomial 分布参数；
- 时间间隔头：正值分布混合模型或 normalizing flow；
- mark 头：条件混合密度网络或 flow；
- 使用似然训练，不只用 MSE；
- 物理约束：时间有序、间隔正、能量和时间常数合法。

通过条件：

- 在纯泊松合成数据上恢复目标计数率；
- 计数 Fano factor、间隔分布和自相关不劣于设定阈值；
- 幅值与时间参数边缘分布、联合分布通过比较；
- 对保留的中间计数率进行插值测试；
- 与精确物理生成器对比速度和准确度；
- 若不优于物理基线，模型保持实验状态，不进入默认链路。

## 阶段 6：神经网络 C——物理残差生成与最终比较

训练策略：先伪配对，后续才考虑非配对。

伪配对流程：

1. 从实测波形提取事件参数；
2. 使用相同事件参数重建物理波形；
3. 以 `real - physical` 作为残差目标；
4. 网络输入物理波形、计数率和配置，输出受约束残差；
5. 最终波形 `y = physical + residual`。

首选基线：轻量 1D 膨胀卷积 TCN，使用 FiLM 或条件归一化注入计数率；后续可比较 1D U-Net。不要一开始使用大型扩散模型。

损失至少包含：

- 时域 Huber/L1；
- 多分辨率频谱或 STFT 损失；
- 无事件区基线/PSD 损失；
- 事件保持损失；
- 残差能量正则；
- 可选幅值、上升时间和积分电荷统计损失。

通过条件：

- 不显著改变输入的事件到达率和间隔分布；
- 不无故新增或删除真实事件；
- 在留出采集 run 与留出计数率上改善基线噪声、PSD、脉冲形状和联合参数分布；
- 与三条链路对比：
  1. 纯物理；
  2. 物理事件 + 残差 C；
  3. 网络 A 事件 + 物理合成 + 残差 C；
- 若模型只改善视觉效果而破坏物理统计，判定失败。

---

# 八、评价指标

## 8.1 事件统计

- 平均计数率误差；
- Fano factor；
- 时间间隔 KS/AD 距离；
- 自相关；
- 堆积比例；
- 死时间损失比例；
- 触发效率和误触发率。

## 8.2 能谱和脉冲参数

- 全能峰位置、宽度；
- 各谱成分权重；
- Wasserstein distance；
- 幅值、积分电荷、上升/下降时间的边缘分布；
- 幅值—上升时间等二维联合分布；
- 饱和比例。

## 8.3 连续波形

- 基线均值与 RMS；
- PSD 和多尺度频谱差异；
- 自相关；
- 脉冲模板相关系数；
- 事件中心平均波形；
- 高计数率基线抬升和堆积形态；
- 分块边界连续性。

## 8.4 泛化

训练计数率从 `log-uniform(10,1e7)` 抽样；验证与测试使用固定标准点及未直接训练的中间点。必须按采集 run 和底层事件来源切分，禁止同一长波形的相邻切片跨集合。

---

# 九、给 Codex 的总控提示词

下面内容可整体复制给 Codex：

```text
你要从零创建一个名为 he3-pulse-sim 的科研级 Python 工程。目标是模拟零功率反应堆热中子场中 He-3 正比计数管及前置放大器的脉冲信号。

硬性需求：
1. 输入是死时间之前的真实计数率，范围 10~1e7 cps；首版为恒定计数率齐次泊松过程。
2. 输出必须分为真实事件列表、所有事件叠加后的连续前放波形、ADC 波形、触发和死时间后的观测事件列表、事件中心窗口。
3. 死时间不能删除连续波形里的真实事件，只影响观测层。
4. He-3 能谱首版使用参数化混合模型，含 764 keV 全能峰、质子壁效应、氚壁效应和可选双壁效应；所有权重和形状可配置，均标记参数状态。
5. 能量到峰值使用 A_peak = G_E * E_dep + epsilon；A_peak 是正的峰值幅度，极性独立配置。
6. 单脉冲使用峰值归一化双指数模型，tau_d > tau_r > 0；同时输出模型时间常数和从离散波形测得的 10%-90% 上升/下降时间。
7. 支持 100~250 MS/s，持续时间可配置；必须分块流式生成并保持脉冲尾部跨块连续。
8. 支持白噪声、基线、低频漂移、裁剪、ADC 量化、正负脉冲触发、延长型和非延长型死时间。
9. 主数据格式为 HDF5，使用分块、压缩和拼接数组+索引表，不要大量使用可变长对象。
10. 工程必须使用 pyproject.toml、src 布局、YAML+Pydantic、类型标注、pytest、结构化日志和统一 CLI。
11. Windows 11 + NVIDIA GPU 是开发和训练主环境；无 GPU 的多核算力机用于批量 CPU 仿真。物理核心不得依赖 PyTorch，多进程必须 Windows spawn 安全。
12. 当前不实现 GUI、Web、DT5800 控制、实时硬件输出；只保留明确的接口 stub。DT5790 文件不是核心依赖。
13. 当前所有设备参数不完整。演示值必须标记 synthetic_demo；有限数据拟合值标记 provisional；只有人工确认后才是 validated。
14. 神经网络分两条研究路线：A 为条件标记时间点过程生成事件参数，C 为在物理波形上学习残差。A 不得替代精确泊松基线，除非量化评价证明有价值；C 不得改变事件统计。
15. 严格按阶段交付。每一阶段完成后停止，输出变更摘要、目录树、运行命令、测试结果、已知限制和下一阶段入口条件。未经用户确认不得自动进入下一阶段。

代码质量要求：
- 不使用魔法数字；
- 所有物理量内部使用 SI 单位，字段名显式带单位；
- 随机数使用 numpy.random.Generator，并记录 seed；
- 配置、代码版本、参数状态、单位和随机种子写入输出；
- 所有优化实现必须有简单参考实现作回归对照；
- 随机统计测试使用固定 seed 和稳健容限，避免脆弱 p-value；
- 错误不得静默吞掉；
- 先正确、再优化，性能优化前提供 profile/benchmark；
- 文档中不得把临时参数说成真实探测器参数。

先只执行我随后指定的阶段提示词。
```

---

# 十、分阶段 Codex 提示词

## 阶段 0 提示词

```text
执行阶段 0：只搭建 he3-pulse-sim 工程骨架、配置和数学基线，不实现完整波形模拟。

必须创建：
- pyproject.toml、src/he3sim、tests、configs、docs、notebooks、scripts；
- Pydantic 配置模型；
- dataclass/structured dtype 数据类型；
- numpy.random.Generator 随机上下文；
- Typer 或 argparse CLI；
- validate-config 命令；
- demo_minimal.yaml 与 provisional_he3.yaml；
- docs/model_spec.md，写明泊松过程、能谱接口、归一化双指数公式、死时间分层和单位约定；
- pytest 基础测试和安装说明。

参数状态必须支持 synthetic_demo/provisional/validated。
DT5800、MCNP、示波器导入只定义 Protocol/stub，不实现业务。

完成后运行安装与测试，并停止。输出：目录树、关键设计、命令、测试结果、未完成项。不要进入阶段 1。
```

## 阶段 1 提示词

```text
执行阶段 1：实现真实事件到达、He-3 参数化能谱和能量到幅值，不生成连续波形。

要求：
- ConstantRateProfile；
- 两个齐次泊松实现：Poisson-count+sorted-uniform、cumulative-exponential；
- ParametricHe3Spectrum，支持 full_energy/proton_wall/triton_wall/double_wall；
- 混合权重校验、定义域校验、分辨展宽；
- A_peak = G_E E_dep + epsilon，幅值非负，极性单独保存；
- 输出 HDF5 最小真实事件表；
- CLI simulate-events 与 validate-arrivals；
- 统计报告和图；
- 单元、统计和回归测试。

验收至少覆盖：事件数均值、方差/均值、间隔分布、两种算法一致性、谱峰位置、混合比例和可复现性。
完成后停止，不进入阶段 2。
```

## 阶段 2 提示词

```text
执行阶段 2：实现归一化双指数脉冲和连续波形合成。

要求：
- 实现解析 t_peak 和归一化因子；
- A_peak 必须代表实际目标峰值；
- direct_sparse 参考渲染器；
- 固定 tau 的递归高效渲染器，并保存跨块状态；
- 多脉冲线性叠加；
- 白噪声、常量基线、可选低频漂移；
- 电压裁剪、ADC 量化、饱和标记；
- 计算 peak、charge、rise_time_10_90、fall_time_90_10；
- CLI simulate-waveform；
- HDF5 连续块写入。

必须测试：峰值归一化、时间平移、线性叠加、参考/优化一致性、分块/整段一致性、ADC 映射和饱和。
完成后停止，不进入阶段 3。
```

## 阶段 3 提示词

```text
执行阶段 3：实现触发、死时间、完整数据集、多尺度生成和计数率扫描。

要求：
- 正/负脉冲阈值触发、滞回、最小保持时间；
- none/nonparalyzable/paralyzable；
- 事件级理想死时间和波形触发死时间分开；
- trigger_event_links 多对多关系；
- true_events、continuous_blocks、adc、observed_events、event_windows；
- fixed_duration 与 target_event_count；
- event_horizon 和实际连续渲染区分；
- max_samples_per_block 和流式 HDF5；
- 从 10 到 1e7 cps 的标准对数验证点；
- 输出计数率、堆积、死时间损失、饱和和触发统计报告。

验收：理想死时间关系与解析公式一致；死时间拒绝事件仍存在于真值和连续波形；高计数率内存有界；所有关联可追踪。
完成后停止，不进入阶段 4。
```

## 阶段 4 提示词

```text
执行阶段 4：建立示波器数据标定流水线。若当前没有真实示波器文件，先用合成 fixture 完成代码和测试，真实标定结果不得伪造。

要求：
- profile 驱动的 CSV/NPZ 导入，不硬编码厂商格式；
- 采样率、时间列、电压列、单位、极性配置；
- 基线和噪声估计；
- 脉冲检测、孤立脉冲筛选、对齐和归一化；
- scipy 双指数拟合，输出不确定度/QC；
- 统计 amplitude/tau_r/tau_d/rise/fall/charge 的边缘和联合分布；
- 生成 provisional calibration YAML 和 HTML/Markdown 报告；
- 人工确认流程，不自动转 validated；
- 预留模板库生成器。

按 acquisition run 划分训练/验证/测试，避免相邻片段泄漏。
完成后停止，不进入阶段 5。
```

## 阶段 5 提示词

```text
执行阶段 5：实现神经网络 A，作为条件事件参数生成的研究对照。

先写清研究假设：当前非相关中子已有精确泊松生成器，网络目标是验证能否学习有标记的事件联合分布和未来实测偏离，而不是为了替代公式。

实现：
- ConditionalMarkedEventGenerator 接口；
- 输入 log10(rate)、window duration、detector config；
- 事件数分布头；
- 正值时间间隔的混合分布或 normalizing-flow 头；
- energy/amplitude/tau_r/tau_d 的条件 mark 头；
- 保证时间单调、参数合法；
- 似然损失；
- 训练、断点、推理、配置和 seed 记录；
- CPU smoke test 与 CUDA 训练支持；
- 与 exact Poisson + parametric spectrum 基线比较。

评估：计数率偏差、Fano factor、间隔分布、自相关、mark 边缘/联合分布、留出计数率泛化和速度。
若不优于或不能匹配物理基线，默认配置必须继续使用物理生成器。
完成后停止，不进入阶段 6。
```

## 阶段 6 提示词

```text
执行阶段 6：实现神经网络 C 的伪配对物理残差学习，并完成三链路对比。

实现：
- 由实测事件提取参数并重建对应物理波形；
- residual_target = real - physical；
- 轻量 1D dilated TCN 基线，FiLM 条件为 log10(rate) 和 detector config；
- 输入物理波形，输出残差，最终 y=physical+residual；
- patch 数据加载，支持 8GB 显存；
- Huber/L1、多分辨率 STFT、无事件区 PSD、事件保持和残差能量正则；
- 保持事件时间、计数率、幅值和间隔统计；
- 留出采集 run 和留出计数率评估；
- 比较纯物理、物理+C、A+物理+C 三条链路；
- 生成最终报告、模型卡和失败案例。

不要在此阶段直接上大型扩散模型或无配对 GAN。只有伪配对基线通过后，才在文档中列为未来工作。
完成后停止，并给出是否值得继续 DT5800/实时接口阶段的结论。
```

---

# 十一、建议的首批标准工况

固定验证点：

```text
10, 30, 100, 300,
1e3, 3e3, 1e4, 3e4,
1e5, 3e5, 1e6, 3e6, 1e7 cps
```

训练工况：`log10(rate)` 连续均匀抽样；另保留若干未参与训练的中间值作为插值测试。

250 MS/s 时，1e7 cps 的平均相邻事件间隔约为 100 ns，即约 25 个采样点，因此此区间应视为强堆积工况；不要期待每个事件都能被独立触发。

---

# 十二、当前不做的内容

- 反应堆功率/中子通量到计数率的物理换算；
- 相关中子、裂变链时间相关性；
- 快中子与超热中子响应；
- 真实探测器空间电荷和恢复曲线；
- 真实前放饱和恢复；
- GUI/Web；
- DT5800 硬件控制与波形下发；
- 实时数字流；
- MCNP 自动运行。

但必须保留：`RateProfile`、`EnergySpectrumProvider`、恢复模型、示波器导入、MCNP 导入和 DT5800 适配器接口。

---

# 十三、理论与方法参考

1. T. J. Langford et al., “Event Identification in 3He Proportional Counters Using Risetime Discrimination,” Nuclear Instruments and Methods in Physics Research A, 2013；同时有 NIST 公开版本与 arXiv:1212.4724。
2. B. Beltran et al., “A Monte Carlo Simulation of the Sudbury Neutrino Observatory Proportional Counters,” New Journal of Physics, 2011，arXiv:1104.2573。
3. S. Usman and A. Patil, “Radiation Detector Deadtime and Pile Up: A Review of the Status of Science,” Nuclear Engineering and Technology, 2018。
4. O. Shchur, M. Biloš, S. Günnemann, “Intensity-Free Learning of Temporal Point Processes,” ICLR 2020，arXiv:1909.12127。
5. O. Shchur et al., “Fast and Flexible Temporal Point Processes with Triangular Maps,” NeurIPS 2020。
6. Y. Yang and P. Perdikaris, “Physics-Informed Deep Generative Models,” 2018。
7. Geant4 Collaboration, Book for Application Developers：Detector Response 与 Digitization 章节。
8. h5py 官方文档：Datasets、chunked storage、compression。
9. CAEN DT5800 官方产品说明：未来硬件阶段参考；当前阶段不实现。
