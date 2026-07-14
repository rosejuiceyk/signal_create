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
| 3.5 | 本地 Web 参数输入、连续波形、采样信息和图片 | 已通过 | 等待审核 |
| 4 | 示波器标定 | 用户推迟 | 等待实测数据 |
| 5 | 条件标记事件网络 A（experimental） | 已通过 | 已通过（2026-07-14） |
| 6 | 尚未实现 | 不适用 | 不适用 |

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

## 8. Phase 3.5 人工审核：本地 Web 波形生成界面

### 8.1 审核目标

确认用户可以在本机浏览器填写真实计数率、采样率、观察时间和随机种子，生成连续波形 HDF5、
两列 CSV、采样信息 JSON、实际配置 YAML 和波形 PNG；同时确认资源超限会在生成前被拒绝。
参数状态不在页面顶部重复提示，但仍保存在各类元数据中。

### 8.2 启动步骤

在项目根目录和 `signal_create` 环境中运行：

```powershell
he3sim web
```

默认地址为：

```text
http://127.0.0.1:8501
```

命令只监听本机回环地址，不向局域网或互联网提供服务。如果不希望命令主动打开浏览器，可执行：

```powershell
he3sim web --headless
```

若 8501 端口已被占用，可指定另一个本机端口：

```powershell
he3sim web --port 8502
```

停止服务时，在运行命令的终端中按 `Ctrl+C`。

### 8.3 页面操作

页面提供四个可编辑输入：

| 输入 | 单位 | 允许范围 | 含义 |
|---|---:|---:|---|
| 真实计数率 | cps | `10～1e7` | 死时间之前的齐次泊松真实到达率 |
| 采样率 | MS/s | `100～250` | 连续波形离散采样网格 |
| 观察时间 | ms | 正数且受资源上限约束 | 本次固定连续波形时长 |
| 随机种子 | 无 | 非负整数 | 事件、能谱、幅值和噪声复现入口 |

填写数值后，页面会在生成前显示：预期事件数、实际将分配的采样点数、采样间隔，以及按每点
两个 `float32` 模拟电压、`uint16` ADC 和 `bool` 饱和标记估算的 11 bytes 原始数组大小。该数值不是
HDF5 压缩后文件大小，也不是完整峰值内存承诺。

观察时间输入框下方会直接显示当前最大值。软件分别计算：

- 采样点上限允许的最大时间；
- 当前计数率下，预期事件数上限允许的最大时间；
- 两者的较小值作为输入框最大值。

改变计数率或采样率后，该提示和输入上限会自动刷新；若原观察时间超过新上限，页面会先将其
收紧到新上限，再执行资源预检。

本地网页单次最多生成 5000000 个采样点。采样点数量按下式确定：

```text
sample_count = ceil(duration_s × sample_rate_hz) + 1
```

末尾的 `+1` 表示时间网格包含零时刻。因此，截图中 5000001 点来自约 5000000 个采样间隔加上
零时刻。该上限用于防止交互任务产生过大的内存、CSV 和绘图文件，不是探测器、前放或采集设备的
物理限制。在 `100 MS/s` 下观察时间需小于约 `50 ms`，在 `250 MS/s` 下需小于约 `20 ms`；
页面会随采样率显示当前建议上限。

点击“生成连续波形”后，等待页面显示“连续波形生成完成”。页面会显示实际真值事件数、渲染后端、
三面板 PNG、前 12 个实际采样点，以及完整采样/产物 JSON。PNG、JSON 和小于 50 MiB 的 CSV
可从页面下载；完整逐点数组同时保存在本机 HDF5。大型 CSV 仍保存到运行目录，但不送入浏览器内存。

波形 PNG 优先显示裁剪前连续电压，纵轴按当前可见数据自动缩放并留出边距。高计数率时，细节窗口最多绘制 80 条
代表性真值事件竖线和 500 个代表性饱和点，同时显示附近事件总数、绘制标记数和饱和样本比例。
这能避免事件标记把曲线涂黑。HDF5 另存裁剪后电压并用它生成 ADC；若 ADC 饱和比例接近 100%，
表示当前演示配置量程不足，但裁剪前面板仍可显示连续堆积形态。

### 8.4 产物目录和采样点定义

每次生成都会创建独立目录：

```text
outputs/web_runs/web-<UTC时间>-<随机后缀>/
├── run_config.yaml
├── waveform.h5
├── waveform.csv
├── waveform.png
└── sampling_info.json
```

`waveform.h5` 中：

- `/blocks/analog_samples`：软件量程裁剪后的完整模拟电压采样点，单位 V，类型 `float32`；
- `/blocks/preclip_analog_samples`：软件裁剪之前的完整模拟电压，单位 V，类型 `float32`；
- `/blocks/adc_samples`：完整 ADC 码，类型 `uint16`；
- `/blocks/saturation_mask`：每个采样点的饱和标记；
- `/events/true`：所有参与波形叠加的真值事件；
- 第 `i` 个采样点的时间为 `t_s = i / sample_rate_hz`。

`waveform.csv` 使用 UTF-8 文本，严格包含两列：

```text
time_s,voltage_V
0,0.000123...
...
```

- `time_s`：采样点时间，单位秒；
- `voltage_V`：对应的模拟电压，单位伏，与 HDF5 `/blocks/analog_samples` 逐点一致；
- CSV 以 65536 点为一块从 HDF5 写出，不会为了导出而一次性加载整段波形。

`sampling_info.json` 保存输入、采样间隔、采样点数、预期/实际事件数、HDF5 数据集路径、seed、
配置哈希、参数状态、渲染器和产物大小。`run_config.yaml` 是本次实际运行配置；原始
`configs/demo_minimal.yaml` 不会被修改。

### 8.5 当前自动验收演示

本次自动验收生成了一个小型人工复核样例：

```text
outputs/manual_review/phase03_5/web-20260713T141226.728734Z-11eba945/
```

其输入为 `100000 cps`、`100 MS/s`、`0.1 ms` 和 seed `20260711`；生成 10001 个采样点、
10 个实际真值事件，使用 `recursive_fixed_tau`，并包含 334445 bytes 的两列 CSV。参数状态仍在
元数据中记录为 `synthetic_demo`；该样例只验证软件链路，不代表真实设备输出。

高计数率绘图复核样例：

```text
outputs/manual_review/phase03_5/preclip_high_rate/web-20260713T161050.699272Z-acbd6468/
```

其输入与用户截图一致：`1e7 cps`、`100 MS/s`、`15 ms`、seed `20260303`。实际生成 149843 个
真值事件和 1500001 个采样点。事件中心窗口包含 876 个事件，但只绘制 80 条代表性事件线；
饱和比例为 100%，但裁剪前波形仍显示约 `7～10 V` 的连续堆积变化；裁剪后电压和 ADC 保持饱和。

### 8.6 人工审核清单

- [ ] `he3sim web` 启动成功，浏览器可打开 `http://127.0.0.1:8501`；
- [ ] 页面顶部不再显示 `synthetic_demo` 警告条，结果区不再显示“参数状态”卡片；
- [ ] 三个工况参数和 seed 可编辑，单位清晰；
- [ ] 四个输入框附近均显示允许范围，观察时间范围会随当前工况更新；
- [ ] 生成前资源预估随输入变化，过大任务会被拒绝并给出缩短建议；
- [ ] 观察时间输入框旁显示当前最大值，改变计数率或采样率后自动更新；
- [ ] 点击生成后出现三面板波形图片，而不只是 HDF5 结构；
- [ ] 高计数率图的纵轴有可见留白，密集事件标记不会覆盖整张细节图；
- [ ] 新生成的高计数率 HDF5 含 `/blocks/preclip_analog_samples`，PNG 前两个面板可见裁剪前波形变化；
- [ ] 饱和波形明确显示饱和比例，不把裁剪压平误认为绘图失败；
- [ ] 页面显示实际真值事件数和前 12 个采样点；
- [ ] HDF5 的采样点数与 `sampling_info.json` 一致；
- [ ] `waveform.csv` 只有 `time_s,voltage_V` 两列，行数与 HDF5 采样点数一致；
- [ ] CSV 时间严格递增，电压与 HDF5 `/blocks/analog_samples` 对应；
- [ ] `run_config.yaml` 记录本次输入，基础演示配置未被覆盖；
- [ ] 重复使用相同输入和 seed 时，真值事件和波形数组一致；
- [ ] 页面只监听本机，没有示波器标定、硬件控制或神经网络功能。

### 8.7 已知限制和未实现内容

- Web 单次任务最多 5000000 个采样点、1000000 个预期事件；这是交互模式安全门限，
  不是 Phase 3 流式数据集能力的上限；
- 页面暂不编辑能谱、增益、时间常数、噪声、ADC、触发和死时间参数；这些值来自基础配置；
- 完整 HDF5 只保存在本机；CSV 超过 50 MiB 时也只保存在本机，避免浏览器内存膨胀；
- 页面没有任务队列、并发隔离、账号、权限、数据库、远程部署或云端托管；
- 未实现 Phase 4 示波器导入、拟合或真实参数标定；Phase 5 网络 A 仅为独立 experimental
  研究工具且未接入本页面，Phase 6 未实现；
- 未实现 DT5800/DT5790 控制、实时采集或波形下发。

### 8.8 审核记录

| 项目 | 填写内容 |
|---|---|
| 审核人 | 用户（本线程明确确认） |
| 审核时间（含时区） | 2026-07-14（Asia/Shanghai） |
| 样例目录 | `outputs/manual_review/phase03_5/web-20260713T141226.728734Z-11eba945/` |
| 高计数率样例 | `outputs/manual_review/phase03_5/preclip_high_rate/web-20260713T161050.699272Z-acbd6468/` |
| 配置哈希 | `41136b5d4ccd94adf114a4d9113a3270eeca18fbf1c31e26df994536ddd49416` |
| 高计数率配置哈希 | `1444759b4199b77f8ed43c1ee5b553214487db5d0a98a94aae9e6e9c75e415c0` |
| 结论 | 等待人工审核 |
| 问题与备注 | 自动验收通过后停止；Phase 4 保持阻塞 |

## 9. Phase 5 人工审核：条件标记事件网络 A

### 9.1 审核目标和边界

确认网络 A 能以计数率、窗口时长、配置编码和随机潜变量为条件，生成可变长度、时间严格递增、
marks 合法的事件表；训练使用似然而不是 MSE，并能在 CPU/CUDA 上运行、保存断点和输出严格比较。

本阶段由用户明确授权推迟 Phase 4 后执行，因此所有训练目标仍来自 `synthetic_demo` 精确物理生成器。
网络只作研究对照，状态必须为 `experimental`，不得进入默认事件、波形或 Web 生成链。

### 9.2 环境与命令

截图中的 PowerShell 提示符位于外层目录 `...\he-3-signal`。必须先进入包含 `pyproject.toml`、
`configs` 和 `tests` 的内层项目根目录。以下命令逐行执行；如果提示符已经位于
`...\he-3-signal\he3_codex_context`，则跳过 `Set-Location`。使用 `conda run -n signal_create`
强制每条命令在统一环境中运行，因此即使提示符仍显示 `(base)` 也不会误用 base 环境：

```powershell
Set-Location .\he3_codex_context
if (-not (Test-Path .\pyproject.toml)) { throw "当前目录不是 he3_codex_context 项目根目录" }
conda run -n signal_create python -c "import sys; print(sys.executable)"
conda run -n signal_create python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

第一条 Python 输出的路径必须包含 `envs\signal_create`，不能指向 `D:\anaconda\python.exe`。
当前自动验收环境的第二条命令应显示 `2.12.1+cu130`、`True` 和
`NVIDIA GeForce RTX 5060 Laptop GPU`。

随后逐行运行下列三条独立命令。统一使用环境内的 `python -m he3sim`，
不使用可能仍指向 base 环境的全局 `he3sim.exe`，也不使用容易误粘连命令的 PowerShell 反引号：

```powershell
conda run -n signal_create python -m he3sim train-event-model -c configs/ml_event.yaml
conda run -n signal_create python -m he3sim compare-event-model -c configs/ml_event_eval.yaml -o outputs/phase05_comparison
conda run -n signal_create python -m pytest -q tests/ml/test_event_model_smoke.py
```

若仍提示 `Phase 5 requires the optional 'ml' dependencies`，先确认第一条预检输出的 Python 路径包含
`envs\signal_create`。本项目当前环境已经安装 ML 依赖，无需为了本次审核重新下载；只有新建环境时才需要
在内层项目根目录执行 `conda run -n signal_create python -m pip install -e ".[ml]"`。

要强制 CPU 或 CUDA，可把对应 YAML 中 `device` 改为 `cpu` 或 `cuda`。显式请求不可用 CUDA
必须报错，不能静默切换 CPU；`auto` 才会自动选择可用设备。

### 9.3 训练产物

```text
outputs/phase05_training/
├── checkpoint_epoch_0005.pt
├── checkpoint_epoch_0010.pt
├── checkpoint_epoch_0015.pt
├── checkpoint_epoch_0020.pt
├── checkpoint_latest.pt
├── MODEL_CARD.md
├── training_config.json
└── training_summary.json
```

checkpoint 包含网络权重、优化器状态、epoch、训练历史、架构、配置编码、基础/训练配置哈希和
`experimental` 状态。当前模型为 15705 个参数，CUDA 训练 20 epoch；训练配置哈希为
`ecaf407acc861a26e38833112a130637320d8181877a42ad6f13de4ebb51dedc`。

### 9.4 统计和速度比较

```text
outputs/phase05_comparison/
├── phase05_comparison.md
├── phase05_comparison.json
└── phase05_rate_metrics.csv
```

当前比较对 13 个标准计数率和 12 个几何中点分别运行 256 个独立窗口。结果为 25/25 工况通过
研究级统计门槛、0 个非法事件。最坏指标为：计数率相对偏差约 2.43%、Fano 误差约 0.224、
间隔 KS 约 0.0204、间隔一阶自相关绝对值约 0.0235、类型 TV 约 0.0266、能量分位误差约
0.0147、幅值分位误差约 0.0383、时间常数相对分位误差约 0.0560、能量-幅值相关误差约 0.0385。

本次人工审核命令复验中，CUDA 比较的精确基线约为 53268 events/s，网络约为 3787 events/s，
网络/基线速度比约 0.071。
训练峰值 CUDA 分配约 68.13 MiB，比较峰值约 32.34 MiB，远低于 8 GB，但网络没有速度优势，
所以即使统计匹配仍保持 `experimental`。评价配置哈希为
`8494c11ca183cb1485558eb86a884ec973794c97829a03f107c764332ed7755d`。

### 9.5 人工审核清单

- [ ] `train-event-model` 输出 checkpoint、模型卡和训练摘要；
- [ ] 模型卡明确写有 `experimental` 和 exact physical default；
- [ ] 相同 checkpoint、条件和 seed 生成完全相同的事件表；
- [ ] 事件数可变，时间严格递增且全部位于窗口内；
- [ ] 能量非负、幅值为正、类型合法，且 `tau_d > tau_r > 0`；
- [ ] 训练代码对 count、interval、type、energy、amplitude 和 tau 全部使用似然；
- [ ] checkpoint 可恢复到下一 epoch，且基础配置哈希不一致时拒绝恢复；
- [ ] CPU smoke test 和 RTX 5060 CUDA 训练/推理均可运行；
- [ ] 比较覆盖 13 个标准率和 12 个插值率，报告非法输出、统计、速度、内存和显存；
- [ ] 报告显示网络没有速度优势，并保持 `promotion_recommended=false`；
- [ ] 现有 `simulate-events`、Web 和数据集路径仍使用精确物理生成器；
- [ ] 未实现 Phase 6 波形残差网络。

### 9.6 已知限制

- 训练数据全部来自单个 `synthetic_demo` 配置，不是实测探测器总体；
- Poisson 计数和指数间隔本来就有精确采样器，网络在当前任务上更慢；
- GPU 比较按单窗口推理，尚未为大批量吞吐做专门优化；
- 未经 Phase 4 标定，不能评价真实能谱、增益或时间常数的外推；
- 统计门槛通过仅表示复现当前合成分布，不代表网络优于物理模型。

### 9.7 审核记录

| 项目 | 填写内容 |
|---|---|
| 审核人 | 待用户填写 |
| 审核时间（含时区） | 待填写 |
| checkpoint | `outputs/phase05_training/checkpoint_latest.pt` |
| 比较报告 | `outputs/phase05_comparison/phase05_comparison.md` |
| 模型状态 | `experimental` |
| 默认生成器 | `exact_poisson_parametric_spectrum` |
| 结论 | 通过 |
| 问题与备注 | 用户确认命令修复后的 Phase 5 审核通过；网络仍为 experimental，不自动替代精确物理基线 |

## 10. 如何提交人工审核结论

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

## 11. 后续 Phase 的手册更新要求

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

## 12. 文档变更记录

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
