
# He-3 连续脉冲信号模拟软件用户手册

## 1. 手册用途

本文档是软件功能、操作方法、物理原型、后端模块和数据格式的独立用户手册。
阶段人工审核步骤与审核记录另见 `docs/USER_MANUAL.md`。

当前软件用于：给定死时间之前的真实计数率、采样率、观察时间和随机种子，生成可复现的
He-3 热中子探测器前置放大器连续合成波形，并输出 HDF5、CSV、PNG、YAML 和 JSON。

当前参数尚未由真实探测器、前放、ADC 或示波器标定。输出适合算法开发、软件验证和合成数据研究，
不能直接作为某一台真实设备的定量预测。

## 2. 环境与活动工作流
项目统一使用 Python 3.11+ 的 `signal_create` Conda 环境：

```powershell
conda activate signal_create
python -m pip install -e ".[dev]"
```

活动 CLI 只提供配置校验、事件/波形/数据集生成、HDF5 检查与绘图、物理验证，以及只读采集数据
资格审查。查看完整命令：

```powershell
he3sim --help
```

常用工作流：

```powershell
he3sim validate-config -c configs/demo_minimal.yaml
he3sim simulate-events -c configs/demo_minimal.yaml -o outputs/events.h5
he3sim simulate-waveform -c configs/demo_minimal.yaml -o outputs/waveform.h5
he3sim plot-waveform outputs/waveform.h5 -o outputs/waveform.png
he3sim generate-dataset -c configs/demo_minimal.yaml -o outputs/dataset
he3sim validate-physics -c configs/demo_minimal.yaml -o outputs/physics_validation
he3sim qualify-acquisition --input <DAQ目录> --profile configs/acquisition_profiles/dt5790_run3.yaml -o outputs/phase04q
```

波形和数据集 HDF5 保存真值事件、分块索引、裁剪前/后的模拟电压、ADC 和饱和标记。Phase 3
数据集另外保存触发、死时间、事件关联和固定窗口。所有派生产物写入 `outputs/`，原始采集目录保持只读。

## 3. 物理原型

### 3.1 齐次泊松事件到达

当前非相关热中子使用恒定真实到达率 `lambda_true` 的齐次泊松过程：

$$
N(T)\sim\operatorname{Poisson}(\lambda_{\mathrm{true}}T)
$$

相邻事件间隔：

$$
\Delta t_i\sim\operatorname{Exponential}(\lambda_{\mathrm{true}})
$$

软件保留两种精确算法：固定窗口主路径使用“泊松计数加排序均匀时刻”，交叉验证和流式扩展使用
“累积指数间隔”。随机数统一使用 `numpy.random.Generator` 和 `SeedSequence` 子流。

### 3.2 参数化 He-3 沉积能谱

物理原型来自：

$$
{}^3\mathrm{He}+n\rightarrow p+{}^3\mathrm{H}+764\ \mathrm{keV}
$$

能谱由 764 keV 全能峰、质子壁效应、氚壁效应和可选双壁效应组成。全能峰使用正值截断高斯，
壁效应使用有界 Beta 分布。混合权重非负且和为 1。这些是参数化演示分布，不是真实管体标定结果。

### 3.3 能量到峰值幅值

$$
A_{\mathrm{peak}}=G_EE_{\mathrm{dep}}+\epsilon_A
$$

`A_peak` 保存正的目标峰值幅度，脉冲正负由独立的 `polarity` 保存。当前增益、偏置和展宽参数均为
演示值。

### 3.4 峰值归一化双指数脉冲

令 `s=t-t_i`，当 `s>=0`：

$$
g(s)=e^{-s/\tau_d}-e^{-s/\tau_r},\qquad \tau_d>\tau_r>0
$$

$$
t_{\mathrm{peak}}=
\frac{\tau_r\tau_d}{\tau_d-\tau_r}
\ln\left(\frac{\tau_d}{\tau_r}\right)
$$

$$
v_i(t)=\mathrm{polarity}_i\,A_{\mathrm{peak},i}
\frac{g(t-t_i)}{g(t_{\mathrm{peak}})}
$$

离散实现按事件相对采样网格的分数相位校正峰值，使孤立脉冲在离散波形上的峰值保持为
配置的 `A_peak`。

### 3.5 连续波形和堆积

$$
v(t)=b(t)+n(t)+\sum_i v_i(t)
$$

所有真实事件都参与求和，因此高计数率自然产生堆积。`direct_sparse` 是逐事件参考实现；
`recursive_fixed_tau` 使用两个指数递推状态实现高效固定时间常数波形，并保持跨块尾部连续；
`auto` 自动选择后端。

### 3.6 基线、噪声、裁剪和 ADC

当前支持常量基线、高斯白噪声、可选 AR(1) 低频漂移、模拟电压裁剪、ADC 输入范围与位数量化，
以及每点饱和标记。处理顺序为：

```text
脉冲叠加 → 基线/噪声 → 保存裁剪前电压 → 模拟裁剪 → 保存裁剪后电压 → ADC
```

简单裁剪不是空间电荷、气体增益变化或真实前放饱和恢复模型。真实恢复行为必须等待示波器数据标定。

### 3.7 触发与死时间

Phase 3 数据集支持 `none`、`nonparalyzable` 和 `paralyzable`：

$$
m_{\mathrm{nonparalyzable}}=\frac{\lambda}{1+\lambda\tau_d}
$$

$$
m_{\mathrm{paralyzable}}=\lambda e^{-\lambda\tau_d}
$$

死时间只改变观测候选的接受状态，不能删除真值事件或它们的连续波形贡献。

## 4. 后端模块对应表

| 模块 | 职责 |
|---|---|
| `he3sim/config.py`、`random.py` | 配置、单位、参数状态、seed 和独立随机子流 |
| `physics/` | 泊松到达、He-3 能谱、幅值、脉冲参数和真值事件 |
| `synthesis/` | 连续波形、噪声、基线、裁剪、ADC 和多尺度数据集 |
| `acquisition/` | 触发、死时间和真值事件关联 |
| `analysis/` | 统计验证、脉冲特征、报告和波形绘图 |
| `io/` | HDF5、MCNP、示波器、DT5800 stub 和数据集持久化 |
| `calibration/` | 只读采集探针、四态 QC、来源追溯和 Phase 4Q 门禁 |
| `he3sim/cli.py` | 活动命令入口，不导入归档 Web/ML 模块 |

## 5. 命令行功能

```powershell
he3sim validate-config -c configs/demo_minimal.yaml
he3sim simulate-events -c configs/demo_minimal.yaml -o outputs/events.h5
he3sim validate-arrivals -c configs/demo_minimal.yaml -o outputs/arrival_validation
he3sim simulate-waveform -c configs/demo_minimal.yaml -o outputs/waveform.h5
he3sim plot-waveform outputs/waveform.h5 -o outputs/waveform.png
he3sim generate-dataset -c configs/demo_minimal.yaml -o outputs/dataset
he3sim validate-physics -c configs/demo_minimal.yaml -o outputs/physics_validation
he3sim inspect outputs/waveform.h5
he3sim qualify-acquisition --input <DAQ目录> --profile configs/acquisition_profiles/dt5790_run3.yaml -o outputs/phase04q
```

## 6. 已归档路线

原 Phase 3.5 本地 Web、Phase 5 网络 A、Phase 6 网络 C 和 Phase 6S 合成预演已移入
`archive/`。相关依赖、配置、CLI 和活动测试均已移除；归档内容只用于审计，不能作为当前软件功能调用。
项目主线见 `docs/ROADMAP_v2.md`。

## 7. Phase 4Q 数据资格功能

Phase 4Q 命令只读扫描采集目录，并把派生清单写入 `outputs/phase04q/`。它逐文件计算 SHA-256，明确
保存 RAW/FILTERED/UNFILTERED 版本，对 RAW 事件逐行执行 QC，因此内存只随单条事件记录增长。

QC 状态为 `pass`、`fail`、`not_evaluable` 或 `unknown`。当前 profile 的阈值为 `provisional`；ADC
轨道未独立确认，因此 saturation 保持 `not_evaluable`。严格相邻重复样本只计算比例和候选去重长度，
不会改写样本。独立已知频率实验完成前：

- `sample_interval_s` 必须为 `null`；
- 波形只使用导出索引和 `ADC_counts`；
- `ENERGY` 只作为原始 channel；
- 软件粒子标签保持 `unknown/candidate`；
- 不允许拟合物理时间常数或生成标定 YAML。

默认每个 run 最多处理256条事件以便有界人工审查。`--max-events-per-run 0` 可执行完整流式普查，
但不会解除采样轴和独立 run 数量造成的科学阻塞。



## 8. 当前限制

- 仅模拟恒定计数率、非相关热中子的齐次泊松过程；
- 能谱、增益、时间常数、噪声、量程和 ADC 尚未真实标定；
- 没有空间电荷、气体增益随计数率变化、前放非线性恢复或真实饱和恢复；
- 不包含示波器导入、真实标定、MCNP 自动运行或硬件控制；
- Web 与生成式 ML 路线已归档，活动环境不安装 Streamlit 或 PyTorch。

完整数学合同见 `docs/model_spec.md`，项目范围与阶段门禁见 `docs/PROJECT_SPEC.md`。
