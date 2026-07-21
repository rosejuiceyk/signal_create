
# he3-pulse-sim 分阶段人工审核指南

## 1. 文档用途

本文档只用于记录每个 Phase 的人工审核步骤、清单和结论，不作为完整软件用户手册。
完整的软件操作、物理原型、数据格式和后端模块说明见 `docs/SOFTWARE_USER_MANUAL.md`。

阶段状态必须区分：

- **自动验收通过**：格式、类型、单元测试、集成测试和阶段 CLI 验收均已通过；
- **等待人工审核**：自动验收已经通过，但用户尚未按照本文档确认功能；
- **人工审核通过**：用户明确确认本阶段功能和边界符合预期；
- **人工审核不通过**：用户发现问题，必须修复并重新执行对应审核。

自动测试通过不等于人工审核通过。每完成一个新 Phase，必须先更新本文档，再停止并等待用户审核；
未经用户明确确认，不得进入下一 Phase。

## 2. 当前可审核阶段

| Phase | 功能 | 自动验收 | 人工审核 |
|---|---|---|---|
| 0 | 工程、配置、类型、随机性和 CLI 基础 | 已通过 | 已通过（2026-07-13） |
| 1 | 泊松到达、参数化 He-3 能谱、幅值和真值事件 HDF5 | 已通过 | 已通过（2026-07-13） |
| 2 | 双指数脉冲、连续波形、分块状态、噪声、裁剪和 ADC | 已通过 | 已通过（2026-07-13） |
| 3 | 触发、死时间、多尺度流式 HDF5 数据集和计数率扫描 | 已通过 | 已通过（2026-07-13） |
| 3.5 | 本地 Web 路线 | 已归档 | 不再审核 |
| 4 | 示波器标定 | deferred | 等待实测数据 |
| 4Q | 数据资格与采样轴确认 | 核心实现通过 | 等待人工审核；科学出口仍 blocked |
| 5 | 条件标记事件网络 A | 已归档 | 不再审核 |
| 6/6S | 残差网络路线 | 已归档 | 不再审核 |
| A | 纯瞬发相关事件、lineage 与静态验证图 | 已通过 | 已通过（2026-07-19） |
| B | 脉冲模式噪声分析、三法 α 复原与死时间偏置 | 已通过 | 已通过（2026-07-20） |
| C | 连续信号 ACF/VTM/去卷积/CCF 与可用边界 | 已通过 | 等待人工审核 |

## 3. 环境与通用约定

### 3.1 工作目录和 Conda 环境

所有项目命令必须在包含 `pyproject.toml`、`src/`、`tests/` 和 `configs/` 的项目根目录执行。
当前项目根目录不是外层的 `he-3-signal`，而是其下的 `he3_codex_context`。

在 PowerShell 中进入正确目录：

```powershell
conda activate signal_create
Set-Location C:\Users\rosejuice\Desktop\he-3-signal\he3_codex_context
```

如果当前提示符是：

```text
PS C:\Users\rosejuice\Desktop\he-3-signal>
```

也可以直接执行：

```powershell
Set-Location .\he3_codex_context
```

运行以下自检；三个结果都必须为 `True`：

```powershell
Test-Path .\pyproject.toml
Test-Path .\src
Test-Path .\tests
```

正确的命令提示符应以 `he3_codex_context>` 结尾。如果在外层目录执行 `python -m mypy src`，
`mypy` 会寻找外层目录中的 `src`，并报 `No such file or directory`。Ruff 和 pytest 有时会递归发现
嵌套项目并偶然通过，但它们可能使用错误的配置发现规则，因此不能据此认为工作目录正确。

也可以不激活环境，在每条命令前使用：

```powershell
conda run -n signal_create <command>
```

首次安装或代码依赖变化后执行：

```powershell
python -m pip install -e ".[dev]"
```

### 3.2 参数真实性

`configs/demo_minimal.yaml` 中的数值全部标记为 `synthetic_demo`，仅用于验证软件功能，不能解释为
真实 He-3 探测器、前置放大器、ADC、DT5790、DT5800 或示波器参数。

`configs/provisional_he3.yaml` 用于保存待标定结构，其中允许存在 `provisional/null`。它可以通过
结构校验，但在缺少必要标定值时必须拒绝事件或波形模拟。

### 3.3 通用质量检查

```powershell
python -m ruff format --check .
python -m ruff check .
python -m mypy src
python -m pytest -q
```

各命令用途：

| 命令 | 目的 | 是否修改文件 | 通过时的典型含义 |
|---|---|---|---|
| `python -m ruff format --check .` | 检查所有 Python 文件是否符合统一格式 | 否 | 文件已经按 Ruff 规则格式化 |
| `python -m ruff check .` | 检查未使用导入、明显错误和代码质量规则 | 否 | 未发现已启用的 lint 问题 |
| `python -m mypy src` | 对 `src/` 中的生产代码执行静态类型检查 | 否 | 类型注解和调用关系未发现类型错误 |
| `python -m pytest -q` | 运行单元、集成、统计和回归测试；`-q` 表示精简输出 | 测试可能创建临时文件 | 当前测试集全部通过 |

`ruff format --check` 只检查排版，`ruff check` 检查代码问题，两者不能相互替代。`mypy` 不运行程序，
主要检查类型契约；`pytest` 会实际执行测试代码。四项全部通过，才构成通用自动质量检查通过。

如果任一命令失败，本次人工审核应记录为“不通过”，先修复再重新审核。

### 3.4 输出目录

建议把人工审核产物统一写入：

```text
outputs/manual_review/
```

`outputs/` 已被版本控制忽略。重新运行相同输出路径会覆盖此前产物，重要审核结果应另行备份。

## 4. Phase 0 人工审核：工程基础

### 4.1 审核目标

确认项目可以在 `signal_create` 环境安装和启动；演示配置与待标定配置均能进行结构校验；配置哈希、
参数状态、单位和随机 seed 的基础约定可用；外部设备相关内容仍然只是明确失败的接口或 stub。

### 4.2 操作步骤

安装项目：

```powershell
python -m pip install -e ".[dev]"
```

查看 CLI：

```powershell
he3sim --help
```

校验两份配置：

```powershell
he3sim validate-config -c configs/demo_minimal.yaml
he3sim validate-config -c configs/provisional_he3.yaml
```

运行基础测试和全量测试：

```powershell
python -m pytest -q tests/unit
python -m pytest -q
```

### 4.3 预期结果

- 安装命令成功，不需要把依赖安装到 Anaconda `base` 环境；
- `he3sim --help` 至少显示 `validate-config`，并列出当前阶段已经实现的其他命令；
- 两份 YAML 均显示 `valid configuration`；
- 每次配置校验输出一个 64 位十六进制 `config_hash`；
- `provisional_he3.yaml` 通过只表示结构合法，不表示参数已经标定或可以运行物理模拟；
- 测试命令无失败项；
- MCNP、示波器和 DT5800 接口不得读取真实文件、连接硬件或虚构设备能力。

### 4.4 人工审核清单

- [x] 项目可在 `signal_create` 环境安装；
- [x] CLI 帮助可正常显示；
- [x] 演示配置校验成功；
- [x] provisional 配置校验成功且仍保留待标定空值；
- [x] 配置哈希稳定显示；
- [x] 全量测试通过；
- [x] 没有把 `synthetic_demo` 描述为真实设备参数；
- [x] 没有实际执行 MCNP、示波器导入或 DT5800 控制。

### 4.5 审核记录

| 项目 | 填写内容 |
|---|---|
| 审核人 | 用户（本线程确认） |
| 审核时间（含时区） | 2026-07-13（Asia/Shanghai） |
| 使用的配置哈希 | demo：`97e2e7e17a89786daafe3f9d6884ae2bf6a4142804e31eed1a4942a8703b9455`；provisional：`70f4528de050d98f9e667779ead42dbd6974e55000dd4cc1e7cce38db56b9a8f` |
| 结论 | 通过 |
| 问题与备注 | 通用质量检查的工作目录说明已在手册 1.1 中修正；复验通过 |

## 5. Phase 1 人工审核：真实事件、能谱和幅值

### 5.1 审核目标

确认两种齐次泊松到达算法可运行且统计验证通过；真值事件时间严格有序；能量和正幅值合法；极性单独
保存；最小 HDF5 只包含真值事件和元数据，不包含连续波形、ADC、触发或死时间结果。

参数化能谱的混合比例、形状和展宽均是演示参数，不是实际 He-3 管标定结果。

### 5.2 两种泊松抽样方法介绍

Phase 1 的两种方法都精确生成恒定计数率齐次泊松过程，不是近似算法。它们的统计分布相同，生成
路径和工程用途不同。

#### 方法一：泊松计数加排序均匀时刻

CLI 名称：`poisson_uniform`，也是默认方法。

1. 在观察时间窗 `T` 内，先抽取事件总数 `N ~ Poisson(lambda*T)`；
2. 在该时间窗内独立抽取 `N` 个均匀时刻；
3. 对所有时刻排序，得到严格递增的事件序列。

原理是：齐次泊松过程在已知窗口内事件总数为 `N` 的条件下，事件位置等价于 `N` 个独立均匀
随机变量的顺序统计量。

优点：固定时间窗下向量化程度高、速度快，先知道数组长度，适合作为默认离线批量生成器。限制是
需要一次保存并排序窗口内全部事件，不适合不知道终点的实时流式生成。

#### 方法二：累积指数间隔

CLI 名称：`cumulative_exponential`。

1. 反复抽取相邻事件间隔 `delta_t ~ Exponential(lambda)`；
2. 从窗口起点开始累加这些正间隔；
3. 累积时刻达到窗口终点后停止，并丢弃窗口外的最后一个时刻。

原理是齐次泊松过程的相邻到达间隔相互独立，并服从参数为 `lambda` 的指数分布。

优点：生成顺序天然有序，适合流式事件和与理论间隔分布直接核对。限制是事先不知道最终事件数；
工程实现需要分块抽取间隔来控制临时内存。

| 对比项 | `poisson_uniform` | `cumulative_exponential` |
|---|---|---|
| 数学正确性 | 精确 | 精确 |
| 固定窗口批量速度 | 通常更快 | 通常稍慢 |
| 是否需要排序 | 需要 | 不需要 |
| 是否预先知道事件数 | 是 | 否 |
| 流式扩展 | 不自然 | 自然 |
| 项目用途 | 默认生成器 | 交叉验证和未来流式入口 |

相同配置和相同根 seed 下，每种算法各自重复运行应完全复现；但两种算法消耗随机数的方式不同，
不应期待它们生成逐事件相同的时间序列。验收目标是计数均值、Fano、指数间隔分布等统计量一致。
当前两种方法都只支持恒定计数率，不实现非齐次泊松过程。

### 5.3 操作步骤

创建审核目录并运行统计验证：

```powershell
New-Item -ItemType Directory -Force outputs/manual_review/phase01 | Out-Null
he3sim validate-arrivals `
  -c configs/demo_minimal.yaml `
  -o outputs/manual_review/phase01/arrival_validation
```

生成默认泊松算法的真值事件：

```powershell
he3sim simulate-events `
  -c configs/demo_minimal.yaml `
  -o outputs/manual_review/phase01/events_poisson_uniform.h5
```

生成累积指数间隔算法的真值事件：

```powershell
he3sim simulate-events `
  -c configs/demo_minimal.yaml `
  -o outputs/manual_review/phase01/events_cumulative_exponential.h5 `
  --algorithm cumulative_exponential
```

检查 HDF5 结构：

```powershell
he3sim inspect outputs/manual_review/phase01/events_poisson_uniform.h5
```

读取真值表并检查排序、能量、幅值和极性：

```powershell
python -c "import h5py,numpy as np; f=h5py.File(r'outputs/manual_review/phase01/events_poisson_uniform.h5','r'); e=f['events/true'][:]; print('events=',len(e)); print('strictly_ordered=',bool(len(e)<2 or np.all(np.diff(e['t_s'])>0))); print('energy_nonnegative=',bool(np.all(e['energy_dep_keV']>=0))); print('amplitude_positive=',bool(np.all(e['amplitude_peak_V']>0))); print('polarities=',sorted(set(e['polarity'].tolist()))); f.close()"
```

运行 Phase 1 指定测试：

```powershell
python -m pytest -q tests/test_arrivals.py tests/test_spectrum.py tests/test_amplitude.py
```

### 5.4 需要查看的产物

```text
outputs/manual_review/phase01/
├── arrival_validation/
│   ├── arrival_validation.json
│   ├── arrival_validation.md
│   ├── count_histogram.png
│   └── interval_cdf.png
├── events_poisson_uniform.h5
└── events_cumulative_exponential.h5
```

重点查看 `arrival_validation.md`、计数直方图和间隔 CDF。固定 seed 下结果应可复现，但单次生成的
事件数不要求恰好等于理论均值。
短观察窗在某个固定 seed 下生成零事件也是合法的泊松结果，应结合统计验证报告判断算法，而不是把
单次事件数作为通过条件。

HDF5 的 `/events/true` 至少应包含：

```text
event_id, t_s, energy_dep_keV, spectrum_component_id,
amplitude_peak_V, tau_r_s, tau_d_s, polarity,
block_id, sample_index, pileup_group_id, parameter_status
```

Phase 1 文件顶层只应出现 `/events` 和 `/metadata`，`/events` 中只应有 `/events/true`。

### 5.5 人工审核清单

- [x] `validate-arrivals` 输出 `result: passed`；
- [x] 两种泊松算法均可生成 HDF5；
- [x] 固定配置和 seed 重复运行时结果一致；
- [x] 到达时间位于观察窗内并严格递增；
- [x] 沉积能量非负，`amplitude_peak_V` 为正；
- [x] `polarity` 只取 `-1` 或 `+1`；
- [x] 报告中的计数均值、Fano、间隔均值和 KS 指标均通过；
- [x] 参数化能谱被明确标记为演示模型而非真实标定；
- [x] Phase 1 HDF5 不包含连续波形、ADC、触发、死时间或观测事件。

### 5.6 审核记录

| 项目 | 填写内容 |
|---|---|
| 审核人 | 用户（本线程确认） |
| 审核时间（含时区） | 2026-07-13（Asia/Shanghai） |
| 使用的配置哈希 | `97e2e7e17a89786daafe3f9d6884ae2bf6a4142804e31eed1a4942a8703b9455` |
| 到达统计报告路径 | `outputs/manual_review/phase01/arrival_validation/arrival_validation.md` |
| 结论 | 通过 |
| 问题与备注 | 用户要求补充两种泊松抽样方法介绍，已在手册 5.2 中完成 |

## 6. Phase 2 人工审核：连续波形和 ADC

### 6.1 审核目标

确认每个真值事件参与连续双指数波形叠加；孤立脉冲的离散峰值等于目标 `A_peak`；参考实现与递推
实现一致；脉冲尾部和低频漂移状态跨块连续；基线、白噪声、裁剪、ADC 码和饱和标记能够输出；
文件中不存在 Phase 3 的触发、死时间、观测事件或事件窗口。

### 6.2 操作步骤

生成默认 `auto` 后端波形：

```powershell
New-Item -ItemType Directory -Force outputs/manual_review/phase02 | Out-Null
he3sim simulate-waveform `
  -c configs/demo_minimal.yaml `
  -o outputs/manual_review/phase02/waveform_auto.h5
```

检查文件结构：

```powershell
he3sim inspect outputs/manual_review/phase02/waveform_auto.h5
```

生成便于人工审核的波形图片：

```powershell
he3sim plot-waveform `
  outputs/manual_review/phase02/waveform_auto.h5 `
  -o outputs/manual_review/phase02/waveform_overview.png
```

该命令只读 HDF5，不会改写波形或生成新的物理事件。PNG 包含全程模拟电压/ADC 包络、所选真值事件
附近的模拟电压细节和 ADC 细节。竖直虚线表示真值事件时刻，红色叉号（若存在）表示饱和样本。默认选择
`amplitude_peak_V` 最大的事件；可用 `--event-id <编号>` 指定其他事件。图题和页脚会显示渲染后端、
seed、配置哈希及参数状态；`synthetic_demo` 明确表示图中数值不是实测设备参数。

核对块索引覆盖、事件注入数和饱和样本数：

```powershell
python -c "import h5py,numpy as np; f=h5py.File(r'outputs/manual_review/phase02/waveform_auto.h5','r'); e=f['events/true']; i=f['blocks/index'][:]; print('truth_events=',len(e)); print('indexed_events=',int(np.sum(i['event_count']))); print('indexed_samples=',int(np.sum(i['length']))); print('stored_samples=',len(f['blocks/saturation_mask'])); print('saturated_samples=',int(np.count_nonzero(f['blocks/saturation_mask']))); f.close()"
```

分别运行参考与递推后端：

```powershell
he3sim simulate-waveform `
  -c configs/demo_minimal.yaml `
  -o outputs/manual_review/phase02/waveform_direct_sparse.h5 `
  --renderer direct_sparse

he3sim simulate-waveform `
  -c configs/demo_minimal.yaml `
  -o outputs/manual_review/phase02/waveform_recursive.h5 `
  --renderer recursive_fixed_tau
```

`direct_sparse` 是逐事件参考实现，较大配置下可能明显慢于递推后端；它主要用于正确性审核，不是默认
大规模渲染路径。


运行 Phase 2 指定测试和完整集成测试：

```powershell
python -m pytest -q tests/test_pulse_kernel.py tests/test_renderers.py tests/test_digitizer.py tests/test_waveform_plot.py
python -m pytest -q tests/integration/test_phase2.py
```

### 6.3 HDF5 结构

`inspect` 应显示：

```text
/
├── metadata/
│   └── config_json
├── events/
│   └── true
└── blocks/
    ├── index
    ├── preclip_analog_samples
    ├── analog_samples
    ├── adc_samples
    └── saturation_mask
```

关键约定：

- `preclip_analog_samples` 为软件裁剪前的 float32 诊断波形，用于辨认高堆积下仍然存在的波形变化；
- `analog_samples` 为软件量程裁剪后的 float32 波形，内部合成使用 float64；
- `adc_samples` 为 uint16，当前支持 1–16 位有效 ADC 码；
- `saturation_mask` 同时标记模拟裁剪和 ADC 输入越界；
- `/blocks/index` 保存块偏移、长度、起始时间、采样率和首次注入到该块的事件数；
- `/events/true` 中的 `sample_index` 与 `block_id` 已赋值；
- 顶层不得出现 `windows`、触发关联表或观测事件表。

演示配置通常由 `auto` 选择 `recursive_fixed_tau`。事件数由随机过程决定，不应把某次运行的具体事件
数当作硬编码验收值。

### 6.4 人工审核清单

- [x] `simulate-waveform` 成功并报告样本数、真值事件数、后端和配置哈希；
- [x] `inspect` 显示连续模拟电压、ADC、块索引和饱和掩码；
- [x] `direct_sparse` 和 `recursive_fixed_tau` 均可运行；
- [x] 峰值归一化、时间平移、线性叠加和正负极性测试通过；
- [x] 参考/递推一致性测试通过；
- [x] 分块/整段一致性和跨块尾部测试通过；
- [x] 固定 seed 噪声复现测试通过；
- [x] ADC 映射、裁剪和饱和标记测试通过；
- [x] 块索引事件数之和等于真值事件数，所有事件均参与叠加；
- [x] 文件中没有触发、死时间、观测事件或事件窗口；
- [x] 演示噪声、时间常数、裁剪范围和 ADC 参数未被描述为真实设备参数。

### 6.5 已知限制

- `recursive_fixed_tau` 只支持所有事件共享相同时间常数；不同时间常数回退 `direct_sparse`；
- Phase 2 的真值事件表仍在内存中；连续样本默认上限为 10,000,000；
- 最终观察边界之后的脉冲尾部不继续保存；
- AR(1) 漂移是可复现的软件基线，不代表实测电子学；
- 当前没有波形触发、死时间、事件窗口或完整训练数据集。

### 6.6 审核记录

| 项目 | 填写内容 |
|---|---|
| 审核人 | 用户（本线程确认） |
| 审核时间（含时区） | 2026-07-13（Asia/Shanghai） |
| 使用的配置哈希 | `97e2e7e17a89786daafe3f9d6884ae2bf6a4142804e31eed1a4942a8703b9455` |
| 波形 HDF5 路径 | `outputs/manual_review/phase02/waveform_auto.h5` |
| 参考/递推审核结果 | 通过 |
| 结论 | Phase 2 核心功能通过 |
| 问题与备注 | 用户要求增加波形图片；只读可视化补充按 6.7 单独等待审核 |

### 6.7 波形可视化补充审核

审核图片：`outputs/manual_review/phase02/waveform_overview.png`。

- [x] `plot-waveform` 成功输出可正常打开的 PNG；
- [x] 全程包络能够显示窄脉冲，不因降采样而遗漏明显峰值；
- [x] 模拟电压细节中的真值事件时刻和双指数脉冲形状清晰；
- [x] ADC 细节与模拟电压变化一致，饱和样本标记规则清晰；
- [x] 图中显示 `synthetic_demo` 提示，且原 HDF5 未被修改；
- [x] 图中没有触发、死时间、观测事件或事件窗口等 Phase 3 内容。

| 项目 | 填写内容 |
|---|---|
| 审核人 | 用户（以本线程明确执行 Phase 3 的指令作为阶段转换授权） |
| 审核时间（含时区） | 2026-07-13（Asia/Shanghai） |
| 波形图片路径 | `outputs/manual_review/phase02/waveform_overview.png` |
| 结论 | 通过 |
| 问题与备注 | 用户查看图片并核对事件数原因后，明确要求执行 Phase 3 |

## 7. Phase 3 人工审核：触发、死时间和多尺度数据集

### 7.1 审核目标

确认三个数据层严格分离：全部真实事件写入 `/events/true`；连续区内全部真实事件参与双指数波形；
阈值触发和死时间只改变 `/events/observed` 的接受状态。确认正/负阈值、滞回、最小保持时间、
`none/nonparalyzable/paralyzable`、多对多关联、固定窗口、HDF5 压缩和 13 个标准计数率扫描可用。

本阶段所有触发、窗口和死时间数值仍为 `synthetic_demo`，不是任何实际采集设备参数。

### 7.2 操作步骤

生成 Phase 3 完整数据集：

```powershell
New-Item -ItemType Directory -Force outputs/manual_review/phase03 | Out-Null
he3sim generate-dataset `
  -c configs/demo_minimal.yaml `
  -o outputs/manual_review/phase03
```

查看 HDF5 结构：

```powershell
he3sim inspect outputs/manual_review/phase03/dataset.h5
```

运行两种理想死时间关系、13 个标准计数率和内存上限分析：

```powershell
he3sim validate-physics `
  -c configs/demo_minimal.yaml `
  -o outputs/manual_review/phase03/validation
```

运行 Phase 3 指定测试：

```powershell
python -m pytest -q tests/test_trigger.py tests/test_deadtime.py tests/test_dataset_io.py
python -m pytest -q tests/integration/test_phase3.py
```

当前固定 seed 的演示运行输出 14 个真值事件，其中 8 个位于 5 ms 连续区内并全部参与波形，产生
8 个接受触发。事件数是泊松随机结果，不得硬编码为通用验收值。

### 7.3 多尺度时间和流式边界

演示配置把以下时间明确分开：

- `observation.duration_s = 0.01 s`：事件统计视界；该范围内全部真值事件写入 HDF5；
- `dataset.continuous_duration_s = 0.005 s`：实际渲染的有限连续波形前缀；
- `trigger.pre_trigger_s/post_trigger_s`：围绕接受触发保存的固定 ADC 窗口。

连续区外的真值事件仍保留，但 `block_id` 和 `sample_index` 为 `-1`，明确表示没有为它们伪造连续
样本。连续区内事件按时间块抽取并立即写入可扩展 HDF5 表；递推脉冲状态、噪声状态和触发状态跨块
延续。事件视界剩余部分使用最多约 32,768 个事件的临时块流式写盘。

### 7.4 HDF5 结构和追溯关系

```text
dataset.h5
├── metadata/config_json
├── events/
│   ├── true
│   ├── observed
│   └── trigger_event_links
├── blocks/
│   ├── index
│   ├── analog_samples
│   ├── adc_samples
│   └── saturation_mask
├── windows/
│   ├── adc
│   └── metadata
├── calibration/
└── statistics/
```

- `/events/observed` 保存所有阈值触发候选；死时间内候选仍保留，但 `accepted=false` 且原因为
  `dead_time`；
- `/events/trigger_event_links` 以多行表达多对多关系，一个触发窗口可关联多个真值事件；
- `/windows/adc` 只保存能够取得完整前后区间的已接受触发，并受 `max_windows` 限制；
- `/statistics` 保存真值数、连续区事件数、触发数、死时间损失、误触发、堆积、饱和和窗口数；
- `/calibration` 明确声明没有嵌入实测标定。

### 7.5 死时间和统计验证

- `none`：所有触发候选均接受；
- `nonparalyzable`：死时间内候选被拒绝，但不会延长忙状态；
- `paralyzable`：死时间内候选被拒绝，同时把忙状态延长到该候选之后一个死时间长度。

`validate-physics` 使用事件级理想死时间路径，与解析关系比较；数据集生成则对波形阈值触发候选应用
死时间。两条路径分离，事件级验证不会替代波形触发。

当前报告覆盖 `10, 30, 100, 300, 1e3, 3e3, 1e4, 3e4, 1e5, 3e5, 1e6, 3e6, 1e7 cps`，
两种模式共 26 个点全部通过。验证死时间 `1e-7 s` 是演示统计参数，不是设备规格。

### 7.6 内存分析

`phase03_validation.md` 给出基于默认安全上限的保守工作集分析：约 `179,028,160 bytes`。其中包括
有限波形块、HDF5 压缩缓冲、真值事件临时块、连续区关联事件和最坏情况下的触发索引上限。

该数字是保守分配边界，不是跨机器固定 RSS 性能指标。文件大小和 HDF5 行数会随事件视界增长；真值
事件临时块与波形块不会在内存中按整个视界累积。连续区关联表仍受 `max_expected_events` 限制，连续
样本仍受 `max_waveform_samples` 限制，超过上限会明确失败而不是尝试无限分配。

报告同时记录本机本次扫描的墙钟时间和事件处理吞吐率，仅用于性能追踪，不设置跨机器固定秒数门槛，
也不作为物理正确性的替代条件。

### 7.7 人工审核清单

- [x] `generate-dataset` 成功并显示真值数、连续区事件数、接受触发数和两个时间视界；
- [x] HDF5 包含真值、连续块、ADC、观测事件、关联表、窗口、标定声明和统计；
- [x] 连续区块索引事件数之和等于连续区真值事件数；
- [x] 死时间拒绝只改变观测表，不删除真值或连续样本；
- [x] 正、负阈值、滞回和跨块最小保持时间测试通过；
- [x] 非延长型和延长型死时间测试与解析关系一致；
- [x] 至少一个测试证明单触发能够关联多个堆积真值事件；
- [x] 连续区外事件保留且使用 `-1` 明确表示未渲染；
- [x] 13 个标准计数率均运行，验证报告显示 `result: passed`；
- [x] 内存报告区分工作集上限与随视界增长的磁盘文件；
- [x] 所有新增数值均标为 `synthetic_demo`，没有虚构设备参数；
- [x] 没有实现示波器标定、真实恢复模型、神经网络或硬件控制。

### 7.8 已知限制

- Phase 3 流式波形路径当前要求固定 `tau_r/tau_d`，使用 `recursive_fixed_tau`；
- 高堆积下一个触发可能对应许多真值事件，也可能无法逐事件触发，这是预期行为；
- 触发关联定义为真值事件是否位于配置的前后窗口，不是因果贡献反演；
- 若窗口不含完整的 10%/90% 交点，观测表的上升/下降时间为 NaN，并在统计中计数；
- 目前保存连续区内用于关联的真值事件，内存仍受显式事件上限约束；
- 没有实测空间电荷、前放非线性、饱和恢复或真实采集死时间标定；
- 不包含 Phase 4 示波器导入和标定功能。

### 7.9 审核记录

| 项目 | 填写内容 |
|---|---|
| 审核人 | 用户（本线程明确确认） |
| 审核时间（含时区） | 2026-07-13（Asia/Shanghai） |
| 配置哈希 | `aef387ee946e33f4bd090a56d70c109e82f6a0371bbb737615ef3b13d3d0e58b` |
| 数据集路径 | `outputs/manual_review/phase03/dataset.h5` |
| 验证报告 | `outputs/manual_review/phase03/validation/phase03_validation.md` |
| 结论 | 通过 |
| 问题与备注 | 用户明确要求只更新审核记录，不自动进入下一阶段 |

## 8. 已归档阶段记录

Phase 3.5 Web、Phase 5 网络 A、Phase 6 网络 C 与 Phase 6S 的完整历史审核记录已随代码移入
`archive/`。这些路线不再提供活动命令、依赖或人工审核入口。

## 9. Phase 4Q 人工审核：数据资格与采样轴确认

### 9.1 审核目标

确认软件只读扫描 DT5790 `run3_X` 导出，为原始文件计算 SHA-256，明确区分
RAW/FILTERED/UNFILTERED，对抽样事件执行四态 QC，并如实报告采样轴和独立 run 不足。Phase 4Q 不做
去重、时间换算、能量标定、双指数拟合或网络训练。

### 9.2 运行命令

在内层项目根目录逐行运行：

```powershell
conda run -n signal_create python -m he3sim qualify-acquisition --input "C:\Users\rosejuice\Desktop\7.9-data\4\DAQ" --profile configs/acquisition_profiles/dt5790_run3.yaml -o outputs/phase04q
conda run -n signal_create python -m pytest -q tests/calibration/test_phase4q.py
```

默认每个 run 最多处理256条事件记录，但会哈希全部发现的源文件。完整流式事件普查只能在明确接受
长时间运行时增加 `--max-events-per-run 0`；有限扫描必须在报告中写为不完整，不得冒充全量 QC。

### 9.3 产物与预期结果

```text
outputs/phase04q/
├── provenance.json
├── file_manifest.csv
├── run_manifest.csv
├── event_qc.jsonl
├── qc_summary.csv
├── sampling_axis_report.json
├── sampling_axis_report.md
├── split_feasibility.json
└── data_gap_report.md
```

预期结果：15个 run 被清点，11个含事件记录、4个为空；每个源文件具有大小、修改时间和 SHA-256；
`sample_interval_s` 保持 `null`；粒子标签状态为 `unknown`；严格相邻重复样本被标记但未删除；
`split_feasible=false`；最终科学状态为 `blocked`。

### 9.4 人工审核清单

- [ ] 原始目录内没有新增、删除或修改文件；
- [ ] `file_manifest.csv` 覆盖 info、XML 和三种波形版本；
- [ ] RAW 是主 QC 来源，其他版本没有静默替代；
- [ ] QC 同时支持 `pass/fail/not_evaluable/unknown`；
- [ ] 缺少 ADC 轨道时 saturation 为 `not_evaluable`；
- [ ] 重复样本只统计，没有自动去重；
- [ ] 采样轴确认前没有秒制时间常数、频谱轴或积分电荷；
- [ ] `ENERGY` 没有被解释为已验证 keV；
- [ ] 软件 neutron/gamma 标签没有被当作外部真值；
- [ ] 同一 run 的三种版本不会跨 train/validation/test；
- [ ] 当前每计数率只有一个 run，因此明确保持 blocked；
- [ ] `he3sim --help` 不包含网络 A 命令；
- [ ] 未进入 Phase 4C、4V 或 Phase 6。

### 9.5 审核记录

| 项目 | 填写内容 |
|---|---|
| 审核人 | 待用户填写 |
| 审核时间（含时区） | 待填写 |
| 产物目录 | `outputs/phase04q/` |
| 自动验收 | 已通过 |
| 科学出口 | `blocked` |
| 结论 | 等待人工审核 |
| 阻塞原因 | 采样轴未确认；每计数率独立 run 不足；当前审查为每 run 最多256条事件 |



## 10. Phase A 人工审核：纯瞬发相关中子事件

### 10.1 审核目标

确认泊松仍是默认基线；相关模式能产生可复现、严格有序的探测时刻；裂变链标签通过独立旁表保存，
不占用 `pileup_group_id`；相关事件能够继续通过现有波形、ADC、触发、死时间和数据集流水线。

本阶段采用用户确认的“源开启窗口”：只在观察窗内生成外源中子，不预置稳态中子布居。因此窗口开头
存在约 `1/alpha` 的启动暂态；一阶解析率验收使用远长于该时间尺度的观察窗。

### 10.2 操作步骤

生成默认泊松事件：

```powershell
he3sim simulate-events -c configs/demo_minimal.yaml -o outputs/manual_review/phaseA/poisson.h5
```

使用同一演示配置内的相关参数预设生成纯瞬发相关事件：

```powershell
he3sim simulate-events --source-model correlated -c configs/demo_minimal.yaml -o outputs/manual_review/phaseA/correlated.h5
he3sim inspect outputs/manual_review/phaseA/correlated.h5
```

生成本阶段静态验收报告：

```powershell
he3sim validate-correlated -c configs/demo_minimal.yaml -o outputs/phaseA_report
```

浏览器打开 `outputs/phaseA_report/phase_a_validation.html`，并可逐张查看同目录六个 PNG。报告必须
可以离线打开，不依赖 JavaScript；`phase_a_validation.json` 保存与图面标注相同的门禁指标。

执行专项与全量验收：

```powershell
python -m pytest -q tests/unit/test_source_model.py tests/unit/test_chains.py tests/unit/test_phase_a_visualization.py
python -m pytest -q tests/integration/test_phase1.py tests/integration/test_phase3.py
python -m ruff format --check .
python -m ruff check .
python -m mypy src
python -m pytest -q
```

### 10.3 预期结果和数据契约

- 默认命令输出 `source_model: poisson`；显式覆盖输出 `source_model: correlated`；
- 两次使用相同 seed 的相关模拟产生完全相同的真值与 lineage；
- `events/true` 的 dtype 与 Phase 1–3 完全相同；
- 相关 HDF5 额外包含 `events/lineage`，字段为 `event_id/chain_id/generation`；
- `metadata/source_model` 为 `correlated`，`source_model_derived_json` 保存派生物理量；
- `pileup_group_id` 仍由波形流式层按脉冲重叠关系计算，不解释为裂变链编号。
- 静态报告包含同率 raster、log-y 间隔分布、Fano-门宽、平均率-`k_eff`、真实链树和退化极限；
- 图面关键量来自 JSON/验证层预计算结果，图函数只渲染并返回 `matplotlib.figure.Figure`；
- 报告没有交互仪表盘，也没有恢复已归档 Web 路线。

### 10.4 人工审核清单

- [x] 泊松默认路径和旧命令保持可用；
- [x] 相关 CLI 成功生成带 lineage 的 HDF5；
- [x] 同 seed 输出可复现，时刻严格递增且位于观察窗内；
- [x] `TRUE_EVENT_DTYPE` 未改变，lineage 与 `event_id` 一一对齐；
- [x] 派生探测率为 `S*epsilon/(1-k_eff)`，配置不一致时明确拒绝；
- [x] 全量 160 项测试、Ruff 和 mypy 均通过；
- [x] 所有演示参数仍标记 `synthetic_demo`；
- [x] 未实现延迟中子、近临界 Gillespie、Phase B 噪声分析、DT5800 或硬件控制。
- [x] 六张 PNG 均可读，图例、坐标、`α` 与差异指标标注清晰且无遮挡；
- [x] 离线 HTML 的技术摘要、图面结论和 `phase_a_validation.json` 数值一致；
- [x] 未实现交互仪表盘，报告仅为静态 PNG/HTML 薄层。

### 10.5 审核记录

| 项目 | 填写内容 |
|---|---|
| 审核人 | 用户（本线程确认） |
| 审核时间（含时区） | 2026-07-19（Asia/Shanghai） |
| 自动验收 | 155 项测试通过；Ruff/mypy 通过 |
| 物理窗口约定 | 源开启窗口；无预热历史 |
| 结论 | 通过 |
| 问题与备注 | Phase B 未开始；必须等待单独授权 |

### 10.6 静态可视化增量审核记录

| 项目 | 填写内容 |
|---|---|
| 自动验收时间（含时区） | 2026-07-19（Asia/Shanghai） |
| 自动验收 | 160 项测试通过；Ruff/mypy 通过；正式 CLI 报告门禁通过 |
| 正式产物 | `outputs/phaseA_report/`：6 PNG + HTML + JSON |
| 审核人 | 用户（本线程确认） |
| 人工审核时间（含时区） | 2026-07-19（Asia/Shanghai） |
| 结论 | 通过 |
| 问题与备注 | 原核心生成器审核记录保留；Phase B 仍须单独授权 |

### 10.7 Phase B 脉冲模式噪声分析与人工审核

Phase B 使用 Phase A 相关事件的理想探测时刻作为触发候选，分别执行 Rossi-α、Feynman-α 和
PSD 拟合，并用固定 seed 闭合“设定 α → 反演 α → 与真值比较”。全部演示参数仍为
`synthetic_demo`，不能解释为真实探测器或反应堆结果。

从仓库内层根目录运行：

```powershell
conda activate signal_create
he3sim analyze-noise -c configs/demo_minimal.yaml -o outputs/phaseB_noise
he3sim validate-alpha-recovery -c configs/demo_minimal.yaml -o outputs/phaseB_recovery
```

第一条命令生成单工况三张拟合图、`phase_b_noise.html` 和 `phase_b_noise.json`。第二条是正式阶段
门禁，生成以下七张中文普通说明静态图：

1. Rossi-α 时间差直方图与指数拟合；
2. Feynman-α `Y(T)` 曲线与单指数拟合；
3. PSD 与洛伦兹拟合、拐点 `α/2π`；
4. 三方法 α 复原 parity 图；
5. 三方法相对误差并排图；
6. Hazama 一阶 VTM 修正前后的死时间偏置与可用边界；
7. 时间块 bootstrap α 分布与朴素误差对比。

报告中的 α 单位为 `s^-1`，计数率单位为 `cps`，时间为秒或毫秒，频率为 `Hz`。图片里普通标题、
坐标说明和解释尽量使用中文；Rossi-α、Feynman-α、PSD、VTM、Y∞ 等专业名词保留。

正式自动验收结果：三组 `(alpha, epsilon, 计数率)` 的最大 α 相对误差为 `3.94%`，三方法最大
差异为 `2.37%`；时间块 bootstrap 的报告误差比朴素独立-bin 拟合更保守。`4 us` 非延长型
synthetic_demo 死时间的 `2 × 4` 网格中，Hazama 一阶修正使至少 75% 工况的偏置减小，共同
`5%` 连续可用上限约为 `10000 cps`。

人工审核清单：

- 打开 `outputs/phaseB_recovery/phase_b_validation.html`，确认结果显示“通过”；
- 查看 parity 图的九个点是否均落在 ±5% 灰带内，误差棒是否可见；
- 查看 Rossi、Feynman 和 PSD 拟合是否贴合数据，且 α、Y∞、A/B 或拐点标注清楚；
- 查看死时间图中修正后曲线是否比修正前更接近 1，并确认高率失效区没有被写成可用；
- 查看 bootstrap 图是否同时显示朴素误差和相关性修正误差；
- 确认七张图的普通说明为中文，且没有遮挡、乱码或裁切。

已知限制：Hazama 实现是非延长型死时间的弱损失一阶 VTM lift，超过已报告可用边界后不保证
无偏；没有连续信号 ACF/VTM、去卷积、双探测器 CCF、DT5800 HIL、缓发平台、反应堆数据或
交互仪表盘。自动验收通过后状态为 `awaiting_human_review`，必须等待用户结论。

| 项目 | 填写内容 |
|---|---|
| 自动验收时间（含时区） | 2026-07-19（Asia/Shanghai） |
| 自动验收 | 167 项测试、Ruff、mypy 通过；最大复原误差 3.94%；最大方法差异 2.37% |
| 正式产物 | `outputs/phaseB_recovery/`：7 PNG + HTML + JSON |
| 审核人 | 用户 |
| 人工审核时间（含时区） | 2026-07-20（Asia/Shanghai） |
| 结论 | 通过 |
| 问题与备注 | Phase HIL 被跳过；Phase C 已授权 |

### 10.8 Phase C 连续信号噪声分析与人工审核

Phase C 对连续电压波形直接计算自协方差 ACF(θ)、方差均值比 VTM(T)、Wiener
去卷积，以及双探测器互协方差 CCF/CTM。ACF/VTM 拟合含探测器脉冲衰减常数 α_e
项的模型，去卷积扫描 γ–NSR 稳定域。可用边界在 3×4 的 (α, 率) 网格上评估。

从仓库内层根目录运行：

```powershell
conda activate signal_create
he3sim analyze-continuous-noise -c configs/demo_correlated.yaml -o outputs/phaseC_continuous
he3sim scan-usability-frontier -c configs/demo_correlated.yaml -o outputs/phaseC_frontier
```

`analyze-continuous-noise` 生成 7 张静态图：

1. 连续 ACF 及其含 α_e 项的双指数拟合；
2. 连续 VTM 拟合；
3. Wiener 去卷积原始/去卷积/阈值化三面板；
4. γ–NSR 稳定域热力图；
5. 双探测器 CCF/CTM 双子图；
6. 可用边界 (α, 率) 相对误差热力图；
7. 壁效应敏感性曲线。

同时生成离线 `phase_c_validation.html` 和 `phase_c_validation.json`。
所有普通说明使用中文，专业名词保留。

已知限制：CCF/CTM 使用同一中子场数字孪生，未经过 DT5800 或真实电子学验证
（Phase HIL 已跳过）。壁效应敏感性仍为 synthetic_demo 参数化谱。
自动验收通过后状态为 `awaiting_human_review`，必须等待用户结论。

| 项目 | 填写内容 |
|---|---|
| 自动验收时间（含时区） | 2026-07-20（Asia/Shanghai） |
| 自动验收 | 196 项测试、Ruff、mypy 通过 |
| 正式产物 | `outputs/phaseC_frontier/` 或 `outputs/phaseC_continuous/`：7 PNG + HTML + JSON |
| 审核人 | 待用户填写 |
| 人工审核时间（含时区） | 待填写 |
| 结论 | `awaiting_human_review` |
| 问题与备注 | Phase HIL 已跳过；不含交互仪表盘 |

## 11. 如何提交人工审核结论

完成某一 Phase 的检查后，向 Codex 明确发送以下任一结论：

```text
Phase X 人工审核通过，可以更新审核记录。不要自动进入下一阶段。
```

或：

```text
Phase X 人工审核不通过。问题如下：……。只修复这些问题并重新运行该阶段验收。
```

收到“人工审核通过”后，Codex 应更新本文档对应审核记录和 `docs/STATUS.md`。只有用户随后明确要求
执行下一 Phase，才允许开始下一阶段。

## 12. 后续 Phase 的手册更新要求

每个 Phase 自动验收完成后，必须在停止前更新本文档，至少补充：

1. 本阶段用户可见功能；
2. 前置条件和所需输入；
3. 可复制执行的操作命令；
4. 预期 CLI 输出和产物目录；
5. 数据格式、单位和参数状态说明；
6. 人工审核清单；
7. 已知限制和明确未实现内容；
8. 审核人、时间、结论和问题记录表。

若新阶段修改了旧功能，也必须同步更新旧章节。没有更新用户手册的 Phase 不得标记为等待人工审核，
更不得进入下一阶段。

## 13. 文档变更记录

| 日期 | 版本 | 内容 |
|---|---|---|
| 2026-07-13 | 1.0 | 补充 Phase 0、Phase 1、Phase 2 操作说明和追溯性人工审核清单 |
| 2026-07-13 | 1.1 | 明确嵌套项目根目录、自检命令，并解释四项通用质量检查的目的 |
| 2026-07-13 | 1.2 | 记录 Phase 0–2 审核结论，介绍 Phase 1 两种泊松抽样方法，并增加 Phase 2 波形图片审核 |
| 2026-07-13 | 1.3 | 记录 Phase 2 阶段转换授权，并增加 Phase 3 流式数据集、验证、内存分析和人工审核指南 |
| 2026-07-13 | 1.4 | 记录 Phase 3 人工审核通过；保持 Phase 4 阻塞 |
| 2026-07-13 | 1.5 | 新增 Phase 3.5 本地 Web 启动、操作、产物、限制和人工审核指南 |
| 2026-07-13 | 1.6 | 移除页面参数状态提示，解释采样点上限，并新增两列连续波形 CSV 导出 |
| 2026-07-13 | 1.7 | 增加高计数率自适应绘图、动态观察时间上限，以及完整原理和后端模块说明 |
| 2026-07-14 | 1.8 | 将完整软件说明迁移到独立手册，并更新裁剪前高计数率波形审核项 |
| 2026-07-14 | 1.9 | 新增 Phase 5 网络 A 的似然模型、CPU/CUDA、统计比较、产物和人工审核指南 |
| 2026-07-14 | 2.0 | 修复 Phase 5 审核命令的工作目录、Conda 环境、全局入口和 PowerShell 续行问题 |
| 2026-07-14 | 2.1 | 记录 Phase 5 人工审核通过；Phase 6 因真实连续波形与多计数率 run 不足而仅做入口评估 |
| 2026-07-14 | 2.2 | 退役网络 A；新增 Phase 4Q 只读数据资格、QC、采样轴和人工审核说明 |
| 2026-07-15 | 2.3 | 新增Phase 6S人工干扰、事件保护TCN、CUDA预演、产物和人工审核说明 |
| 2026-07-18 | 3.0 | 归档 Web/ML 路线，保留 Phase 0–3 与 Phase 4Q 审核入口，并切换至相关中子噪声路线图 |
| 2026-07-18 | 3.1 | 新增 Phase A 纯瞬发相关事件、lineage 旁表、源开启窗口和人工审核步骤 |
| 2026-07-19 | 3.2 | 记录 Phase A 人工审核通过；保持 Phase B 未授权 |
| 2026-07-19 | 3.3 | 新增 Phase A 六图静态 PNG/HTML 报告及数据级测试；重新等待人工复核 |
| 2026-07-19 | 3.4 | 记录 Phase A 可视化增量人工审核通过；保持 Phase B 未授权 |
| 2026-07-19 | 3.5 | 新增 Phase B 三法 α 复原、bootstrap、死时间修正、七图报告与人工审核清单 |
