# 项目状态

## 当前阶段

- 当前任务：代码库精简（M0）
- 当前状态：`awaiting_human_review`
- 活动物理基线：Phase 0–3；Phase 4Q 只读数据资格工具保留
- Phase 4：`deferred`
- Phase 3.5、Phase 5、Phase 6/6S：`archived`
- 后续主线：相关中子噪声信号级数字孪生，见 `docs/ROADMAP_v2.md`
- 本次边界：只归档和修补引用，不实现 Phase A 或任何新功能

## 已确认的范围

- 保留物理、合成、采集、分析、IO、配置 schema 与 Phase 4Q 校准资格代码；
- 保留精确齐次泊松生成器作为非相关中子基线；
- 原 Web/ML 源码、配置、测试和阶段文档只归档，不硬删除；
- `docs/competition/` 按用户确认保留原位；
- 原始采集目录保持只读，派生产物只写入 `outputs/`；
- 所有演示参数继续标记为 `synthetic_demo`。

## 阶段记录

| 阶段 | 状态 | 自动验收日期 | 说明 |
|---|---|---|---|
| 0 工程骨架 | human_review_passed | 2026-07-11 | 历史审核通过 |
| 1 事件与能谱 | human_review_passed | 2026-07-13 | 历史审核通过 |
| 2 连续波形 | human_review_passed | 2026-07-13 | 历史审核通过 |
| 3 触发与数据集 | human_review_passed | 2026-07-13 | 历史审核通过 |
| 3.5 本地 Web | archived | 2026-07-18 | 源码、测试与文档移入 `archive/` |
| 4 示波器标定 | deferred |  | 等待合格实测数据和用户授权 |
| 4Q 数据资格 | awaiting_human_review | 2026-07-15 | 保留只读资格审查；科学出口仍 blocked |
| 5 网络 A | archived | 2026-07-18 | 历史实现移入 `archive/` |
| 6/6S 网络 C | archived | 2026-07-18 | 正式路线与工程预演均移入 `archive/` |
| M0 代码库精简 | awaiting_human_review | 2026-07-18 | 自动验收完成后等待用户审核 |

## 最近一次执行结果

### 2026-07-18 代码库精简

- 归档：`src/he3sim/app/`、`src/he3sim/ml/`、对应 Web/ML 测试、三份 ML 配置、四份阶段文档、
  Web 专用绘图脚本，以及已被新路线图取代的旧总控/技术方案文档。
- 保留：physics、synthesis、acquisition、analysis、io、calibration、配置 schema、Phase 0–3 与
  Phase 4/4Q 文档；`docs/competition/` 保持原位。
- 修补：CLI 移除 Web/ML 子命令和导入；环境移除 Streamlit/PyTorch；活动 README、项目规范、
  两份用户手册和阶段索引切换到归档说明与相关中子噪声路线图。
- 新路线图：导入 `docs/ROADMAP_v2.md`，但本次未实施其中 Phase A 或后续功能。
- 自动验收：`pytest -q` 138 项通过；Ruff format 检查 70 个文件、lint、mypy（46 个源文件）、
  `pip check`、`he3sim --help` 与 `git diff --check` 全部通过。
- 当前结论：M0 完成后只能标记为 `awaiting_human_review`。

### 已归档历史记录

#### Phase 6S 合成残差网络工程预演

- 授权与边界：用户于2026-07-15为比赛进度明确授权在真实标定前使用人工干扰搭建网络；模型固定标记
  `synthetic_scaffold`、`real_data_calibrated=false`、`scientific_promotion_allowed=false`，没有接入
  默认物理/Web生成链，也没有恢复网络A。
- 数据：所有patch均复用现有精确泊松事件和连续物理波形API；3个计数率、60个独立合成run按
  36/12/12划分train/validation/test，不复用patch或seed。人工干扰包含配置化基线游移、白噪声、
  AR型有色噪声、衰减振铃和有界非线性尾部，全部为`synthetic_demo`。
- 模型与约束：10,833参数的轻量FiLM dilated TCN；输入物理波形、事件保护掩码、位置、计数率和
  采样率，只输出限幅残差。事件保护区输出硬置零，推理形状、有限值、幅值或保护检查失败时回退纯物理
  波形；网络没有可写真值事件账本。
- 正式CUDA运行：PyTorch 2.12.1+cu130、CUDA 13.0、RTX 5060 Laptop GPU；最终30 epoch墙钟约2.35秒，
  峰值CUDA分配79,770,624 bytes。测试集12个run保留445个物理真值事件。
- 合成结果：物理到人工目标平均RMSE约0.00406049 V，修正后约0.000942519 V，相对改善约76.788%；
  频谱误差约0.006893降至0.003483；事件保护违规0，安全回退0，真值事件账本未修改。该结果只证明
  已知人工干扰恢复，不是实测探测器误差或泛化证据。
- 产物：`outputs/phase06s_rehearsal/`包含checkpoint、合成run清单、逐run指标、训练摘要、评价JSON、
  模型卡、比较报告和三面板PNG。
- 专项自动验收：6项通过，覆盖独立且可复现的物理patch、可移植配置哈希、残差限幅/事件硬保护、
  违规回退、CPU产物/检查点和CUDA前向。正式CLI运行通过；Ruff格式与lint通过，mypy检查56个源文件
  无问题，全量pytest 150项通过、0失败、0跳过，`pip check`、CLI帮助和`git diff --check`均通过。
- 当前结论：工程预演已达到人工审核条件，但正式Phase 6继续`blocked`，不得用该checkpoint声明真实
  He-3精度、B1～B4优越性、跨run泛化或硬件就绪。

#### Phase 4Q 候选 DT5790 数据入口审查

- 审查范围：只读检查 `C:\Users\rosejuice\Desktop\7.9-data\4\DAQ` 下15个符合 `run3_数字` 命名的目录；未修改原始采集文件，未实现或训练网络 C。
- run 级识别：`run3_1`、`run3_9`、`run3_10`、`run3_11` 的 input/output counts 均为0且 CSV 只有表头，判定为空 run；`run3_2`～`run3_8`、`run3_12`～`run3_15` 同时具有非零事件元数据和脉冲样波形偏转，判定为含信号 run。
- 窗口分组：`run3_2`～`run3_3` 去重后约248点，`run3_4`～`run3_8` 约2500点，`run3_12`～`run3_15` 约16380点；短窗口组不能提供完整下降沿，长窗口组仍有明显事件间质量差异。
- 计数率覆盖：非空 run 的采集软件平均率从约 `0.243 cps` 到 `2375.6 cps`，包含多个项目范围内计数率，但当前每个计数率只有一个 run，不能形成同工况独立 train/validation/test 划分。
- 关键质量问题：检查记录均存在严格相邻点成对重复，XML 的 `sampleTime=4000` 与导出数组之间需要进一步确认；多条记录存在振铃、台阶、低幅值或下降沿截断；能量保存格式为 ADC channel，不能视为已验证 keV 标定。
- 审查产物：`outputs/data_audit/run3_pulse_inventory.csv`、`outputs/data_audit/run3_pulse_inventory.md` 和 `outputs/data_audit/run3_representative_waveforms.png`。
- 入口结论：目前只确认哪些 run 含脉冲样信号，不把采集软件粒子标签重新解释为已验证 He-3 分类。必须完成逐事件 QC 和采样轴确认后才能选择 Phase 4/Phase 6 数据；Phase 6 继续保持 `blocked`，没有进入网络实现。

#### Phase 5 条件标记事件网络 A

> 以下是2026-07-14人工审核时的历史快照。当前活动实现、配置、CLI和测试已删除，状态为
> `retired_by_user`，不得按本节历史命令恢复。

- 实施范围：用户明确授权推迟 Phase 4 后，只实现 Phase 5 合成研究对照；未导入或虚构实测标定参数，未进入 Phase 6，未改变默认事件、波形、数据集或 Web 生成链。
- 研究结论：exact Poisson + parametric spectrum 继续作为默认基线；网络 A 的模型卡、checkpoint 和比较报告均标记为 `experimental`，`promotion_recommended=false`。
- 核心交付：
  - 历史实现现保存在 `archive/src_ml/`，其中包含 `ConditionalMarkedEventGenerator` Protocol；
    归档前 PyTorch 也未进入物理核心。
  - 条件输入包含 `log10(rate)`、窗口时长/预期规模、配置编码和显式 seed 随机潜变量；输出沿用真值事件 dtype，事件数可变且时间严格递增。
  - 使用 Poisson 计数似然、正值指数混合间隔似然、categorical 类型似然、按类型有界 logistic-normal 能量似然，以及正值 log-normal 幅值/时间常数似然；不使用 MSE 代替密度训练。
  - 类型头屏蔽零权重成分，推理保证能量非负、幅值为正、类型合法和 `tau_d > tau_r > 0`；超过显式事件上限直接拒绝。
  - 新增严格 ML YAML、log-uniform 训练率、13 个标准验证率、12 个几何中点插值率、无跨 split 复用的独立窗口、checkpoint/恢复、模型卡、训练摘要和逐率比较报告。
  - 设备模式支持 `cpu`、`cuda` 和 `auto`；显式请求不可用 CUDA 会报错，不静默回退。
  - 新增 `he3sim train-event-model` 与 `he3sim compare-event-model`；物理 CLI 在未安装可选 ML 依赖时仍可导入。
- 依赖与设备：`signal_create` 已安装官方 `torch 2.12.1+cu130`；CUDA 13.0 成功识别 `NVIDIA GeForce RTX 5060 Laptop GPU`，矩阵计算、正式训练和完整比较均通过。
- 正式训练：`configs/ml_event.yaml`，768 个训练窗口、130 个固定率验证窗口、20 epoch、15705 个参数；最佳验证 NLL `-19.740675`，本次人工审核命令复验的 CUDA 墙钟约 `10.114 s`，峰值 CUDA 分配 `71439872 bytes`（约 68.13 MiB），训练配置哈希 `ecaf407acc861a26e38833112a130637320d8181877a42ad6f13de4ebb51dedc`。
- 严格比较：`configs/ml_event_eval.yaml` 在 13 个标准率和 12 个插值率各运行 256 个独立窗口，共比较约 20.5 万个 exact 与 20.5 万个 model 事件；25/25 工况通过研究阈值、非法事件为 0。
- 最坏统计指标：计数率相对偏差 `0.0243`、Fano 误差 `0.2241`、间隔 KS `0.0204`、间隔一阶自相关绝对值 `0.0235`、事件类型 TV `0.0266`、能量分位误差 `0.0147`、幅值分位误差 `0.0383`、时间常数相对分位误差 `0.0560`、能量-幅值相关误差 `0.0385`，均低于配置门槛。
- 速度与资源：本次人工审核命令复验的 exact 基线约 `53268 events/s`，CUDA 网络约 `3787 events/s`，网络/基线速度比 `0.0711`；比较峰值 Python 跟踪内存 `2735579 bytes`，峰值 CUDA 分配 `33911296 bytes`（约 32.34 MiB）。网络没有速度优势，因此保持 `experimental`。
- 人工审核命令修复：截图中的失败由外层工作目录、base 环境全局 `he3sim.exe` 和 PowerShell 反引号续行共同造成；手册现要求先进入 `he3_codex_context`，再以单行 `conda run -n signal_create python -m ...` 执行。即使提示符仍显示 `(base)`，也会强制使用统一环境；新增文档回归测试锁定该合同。
- 正式产物：`outputs/phase05_training/` 保存 checkpoint、模型卡与训练摘要；`outputs/phase05_comparison/` 保存 Markdown、JSON 和逐率 CSV；评价配置哈希 `8494c11ca183cb1485558eb86a884ec973794c97829a03f107c764332ed7755d`。
- 正式与回归命令：
  - `conda run -n signal_create python -m he3sim train-event-model -c configs/ml_event.yaml`
  - `conda run -n signal_create python -m he3sim compare-event-model -c configs/ml_event_eval.yaml -o outputs/phase05_comparison`
  - `conda run -n signal_create python -m pytest -q tests/ml/test_event_model_smoke.py`
  - `conda run -n signal_create python -m ruff format --check .`
  - `conda run -n signal_create python -m ruff check .`
  - `conda run -n signal_create python -m mypy src`
  - `conda run -n signal_create python -m pytest -q`
  - `conda run -n signal_create python -m pip check`
  - `git diff --check`
- 最终自动验收：Phase 5 专项 7 项通过，Phase 5 与文档命令联合回归 9 项通过；全量 pytest 145 项通过、0 失败、0 跳过；Ruff 格式检查 76 个文件通过，Ruff lint 通过，mypy 检查 51 个源文件无问题；修正后的环境预检、正式训练、完整比较、依赖一致性和 `git diff --check` 均通过。
- 人工审核：用户于 2026-07-14 明确确认 Phase 5 人工审核通过；`docs/USER_MANUAL.md` 已同步记录。
- 阶段结论：Phase 5 自动验收与人工审核均通过，但统计匹配不等于优于精确基线；网络继续保持 `experimental`。Phase 6 仅完成入口条件审查，尚未开始实现。

#### Phase 3.5 本地 Web

- 实施范围：只新增 Phase 3.5 本地 Web 集成；未进入 Phase 4 示波器导入、拟合或标定，也未实现神经网络或硬件功能。
- 核心交付：
  - 新增绑定 `127.0.0.1` 的 Streamlit 页面和 `he3sim web` 启动命令。
  - 页面允许填写真实计数率、采样率、观察时间和 seed；每个输入框附近均显示允许范围，并在生成前显示预期事件数、采样点数、采样间隔和 11 bytes/点的原始数组估算（两份 float32 电压、uint16 ADC 与 bool 饱和标记）。
  - 交互模式限制为 5000000 个采样点和 1000000 个预期事件；观察时间输入框根据计数率和采样率计算两类上限、显示较小值并直接限制输入，后端仍独立校验。
  - 后端复用 `prepare_waveform_simulation`、`write_waveform_hdf5` 和 `plot_waveform_hdf5`，未复制或修改物理生成器。
  - 每次运行输出独立的 `run_config.yaml`、`waveform.h5`、`waveform.csv`、`waveform.png` 和 `sampling_info.json`；CSV 严格为 `time_s,voltage_V` 两列并采用分块写出。
  - 按用户人工审核反馈移除页面顶部参数状态警告条和结果区“参数状态”卡片；参数状态仍保留在 HDF5、YAML 和 JSON 元数据中。
  - Phase 2/Web HDF5 同时保存软件裁剪前诊断电压和裁剪后 ADC 输入电压；PNG 优先绘制裁剪前数据并自适应纵轴，CSV 继续严格对应裁剪后电压。密集窗口最多绘制 80 条事件线和 500 个饱和点，并显示附近事件数、标记数和饱和比例。
  - 新建独立软件手册 `docs/SOFTWARE_USER_MANUAL.md`，包含完整数据流、泊松过程、He-3 参数化能谱、幅值映射、双指数脉冲、连续叠加、噪声/基线、裁剪/ADC、触发/死时间、数据格式和后端模块对应说明；`docs/USER_MANUAL.md` 只保留分阶段人工审核指南与记录。
  - 新增 Streamlit `1.59.2` 运行依赖，并在 `signal_create` 环境重新执行 editable 安装。
- Phase 3.5 专项回归：10 项通过，覆盖纵轴常量信号留白、密集事件标记限流、饱和比例、两类观察时间约束、五类产物一致性、CSV 与 HDF5 逐点对应、采样点预览、无浏览器页面生成和 CLI 帮助。
- 全量验收：Ruff 格式检查通过（67 个文件），Ruff lint 通过，mypy 检查 44 个源文件无问题，pytest 137 项通过、0 失败、0 跳过；`he3sim web --help` 和 `git diff --check` 通过。
- 人工复核样例：`outputs/manual_review/phase03_5/web-20260713T141226.728734Z-11eba945/`；输入 100000 cps、100 MS/s、0.1 ms、seed 20260711，生成 10001 个采样点、10 个真值事件和 334445 bytes CSV，渲染器为 `recursive_fixed_tau`，配置哈希为 `41136b5d4ccd94adf114a4d9113a3270eeca18fbf1c31e26df994536ddd49416`。
- 高计数率复核：`outputs/manual_review/phase03_5/preclip_high_rate/web-20260713T161050.699272Z-acbd6468/`；输入 1e7 cps、100 MS/s、15 ms、seed 20260303，生成 149843 个事件和 1500001 个采样点；裁剪前总览及细节图可见约 7～10 V 的堆积变化，裁剪后 ADC 输入仍按配置显示 100% 饱和，细节窗口 876 个事件限流为 80 条标记，配置哈希为 `1444759b4199b77f8ed43c1ee5b553214487db5d0a98a94aae9e6e9c75e415c0`。
- 参数真实性：用户输入的工况和所有基础模型参数仍记录为 `synthetic_demo`，但按人工审核反馈不再在页面顶部和结果指标区重复展示；状态保留在文件元数据中。
- 已知限制：界面只适合单机有界交互任务；旧版 HDF5 未保存裁剪前数据，无法仅靠重新绘图恢复被 1.0 V 软件上限压平的幅值，必须重新生成；暂不编辑能谱、增益、时间常数、噪声、ADC、触发或死时间；完整 HDF5 不整体加载进浏览器，超过 50 MiB 的 CSV 也只保存在本机；没有账号、队列、并发隔离、远程部署或硬件连接。
- 用户手册：阶段审核说明保留在 `docs/USER_MANUAL.md`；独立软件操作、数据格式、原理和模块说明已迁移到 `docs/SOFTWARE_USER_MANUAL.md`。
- 阶段结论：Phase 3.5 自动验收通过，状态仍为 `awaiting_human_review`；Phase 4 后于 2026-07-14 按用户明确指令改为推迟。

### Phase 3 历史自动验收与人工审核记录

- 实施范围：仅完成 Phase 3；未进入示波器标定、真实恢复模型、神经网络或硬件阶段。
- 核心交付：
  - 实现正/负电压阈值、滞回、最小保持时间和跨块触发状态。
  - 分离事件级理想死时间和波形触发死时间，支持 `none`、`nonparalyzable`、`paralyzable`；死时间只修改观测候选接受状态。
  - 实现精确的分块 Poisson-count+sorted-uniform 真值流，marks 生成后立即追加至 HDF5；递推波形、噪声和触发状态跨块连续。
  - 区分事件视界、有限连续区和事件窗口；连续区外真值保留并以 `block_id/sample_index=-1` 标明未渲染。
  - 完整 HDF5 新增 `events/observed`、多对多 `trigger_event_links`、固定 ADC 窗口、标定声明和统计组，并使用分块压缩。
  - 实现 `fixed_duration`、`target_event_count` 及可选最短/最长时长；事件、样本和窗口均有显式安全上限。
  - 新增 `generate-dataset` 和 `validate-physics` CLI；标准扫描覆盖 10–1e7 cps 的 13 个点，并记录本机墙钟时间和事件吞吐率但不设置跨机器固定门槛。
- 正式与回归命令：
  - `conda run -n signal_create python -m pytest -q tests/test_trigger.py tests/test_deadtime.py tests/test_dataset_io.py`
  - `conda run -n signal_create python -m pytest -q tests/integration/test_phase3.py`
  - `conda run -n signal_create he3sim generate-dataset -c configs/demo_minimal.yaml -o outputs/manual_review/phase03`
  - `conda run -n signal_create he3sim inspect outputs/manual_review/phase03/dataset.h5`
  - `conda run -n signal_create he3sim validate-physics -c configs/demo_minimal.yaml -o outputs/manual_review/phase03/validation`
  - `conda run -n signal_create python -m ruff format --check .`
  - `conda run -n signal_create python -m ruff check .`
  - `conda run -n signal_create python -m mypy src`
  - `conda run -n signal_create python -m pytest -q`
  - `git diff --check`
- 最终结果：Phase 3 指定单元测试 7 项通过，Phase 3 集成测试 2 项通过；全量 pytest 130 项通过、0 失败、0 跳过；Ruff 格式与 lint 通过；mypy 检查 40 个源文件无问题；三条 Phase 3 CLI 命令通过。
- 数据集复验：固定 seed 演示生成 14 个真值事件，8 个位于 5 ms 连续区并全部注入，8 个触发均接受；输出 1,250,001 个样本、20 个块和 8 个固定窗口，配置哈希为 `aef387ee946e33f4bd090a56d70c109e82f6a0371bbb737615ef3b13d3d0e58b`。
- 统计复验：13 个标准计数率的非延长型/延长型共 26 个点全部通过；1e7 cps 时模拟/理论分别为约 4.984e6/5.000e6 cps 和 3.664e6/3.679e6 cps。
- 内存分析：默认安全上限下保守工作集边界为 179,028,160 bytes；文件和 HDF5 行数随视界增长，但真值临时块和波形块不按全视界累积。连续区关联和触发索引仍受显式事件/样本上限约束。
- 参数真实性：触发阈值、滞回、保持时间、前后窗口、`1e-7 s` 死时间、连续区长度、压缩和窗口上限均为 `synthetic_demo` 软件参数，不是探测器、前放、ADC 或采集设备标定。`provisional_he3.yaml` 继续保留待标定空值并拒绝运行。
- 已知限制：流式连续波形当前只支持固定时间常数递推；触发关联按配置窗口定义而非因果反演；高堆积允许无法逐事件触发；不完整特征交点记录为 NaN 并计数；关联事件和候选索引虽有上限但仍占有限内存。
- 用户手册：`docs/USER_MANUAL.md` 已记录 Phase 2 阶段转换授权、Phase 3 命令、数据结构、统计/内存报告和限制；Phase 3 审核清单及审核记录已更新为通过。
- 阶段结论：Phase 3 自动验收和用户人工审核均已通过，状态为 `human_review_passed`；按用户要求停止，Phase 4 保持阻塞，必须等待另行明确指令。

## 决策日志

Codex 每次作出影响公共 API、数据结构、单位、随机性或物理模型的决定时，在此追加：

```text
YYYY-MM-DD | 决策 | 原因 | 影响范围 | 是否需用户确认
```

```text
2026-07-18 | Web/ML 路线只归档不删除，活动包不再安装或导入其依赖 | 保留历史可审计性并把主线切换到相关中子噪声 | archive、CLI、依赖与文档 | 是，用户已确认
2026-07-11 | 可调数值逐字段保存 value/status/source/notes | 防止演示值、待审核值和已确认值混淆 | YAML 配置与未来元数据 | 否，属于已确认 Phase 0 计划
2026-07-11 | 配置结构合法与可运行物理模拟分离 | 允许待标定值为 null，同时不伪造设备参数 | provisional 配置与后续运行门禁 | 否，属于已确认 Phase 0 计划
2026-07-11 | 时间、电压、频率使用 SI，沉积能量保留显式 keV | 遵循单位优先原则及事件表既定字段 | 公共字段命名和 dtype | 否，属于已确认 Phase 0 计划
2026-07-11 | 配置哈希使用规范化 JSON 的 SHA-256 | 消除 YAML 键顺序和路径差异并支持复现 | 配置元数据 | 否，属于已确认 Phase 0 计划
2026-07-11 | 随机上下文使用 Generator 与 SeedSequence 子流 | 禁止全局随机状态并为 Windows spawn 预留确定性并行 | 随机 API | 否，属于已确认 Phase 0 计划
2026-07-11 | MCNP、示波器和 DT5800 仅提供 Protocol 与显式失败 stub | 保留扩展点且避免提前实现硬件或导入业务 | 外部接口 | 否，属于 Phase 0 明确边界
2026-07-11 | 项目开发与验收统一使用 signal_create Conda 环境和 Python 3.11 | 隔离共享 Anaconda 环境的依赖冲突并固定可复现入口 | 安装、测试和后续阶段命令 | 否，用户已明确指定
2026-07-13 | Markdown 展示公式统一使用独占行的双美元分隔符并测试 UTF-8/分隔符 | 避免当前渲染器把 LaTeX 方括号分隔符显示为乱码文本 | 全部 Markdown 文档和文档回归测试 | 否，用户已明确要求
2026-07-13 | validated 参数强制记录来源、人工复核者和带时区复核时间 | 防止未经人工确认的参数被标记为 validated | 配置模型和 JSON Schema | 否，属于既有参数状态规则
2026-07-13 | 所有浮点配置拒绝 NaN 和无穷值 | 防止非法物理量绕过范围校验并污染配置哈希 | 全部 Pydantic 配置 | 否，属于 Phase 0 数据质量修复
2026-07-13 | 齐次泊松同时保留 Poisson-count+sorted-uniform 与累积指数间隔实现 | 提供精确主算法、交叉验证和未来流式入口 | Phase 1 到达生成 API | 否，属于 Phase 1 明确要求
2026-07-13 | 参数化谱使用全能峰正值截断高斯与三个有界 Beta 连续区 | 满足可配置混合、权重、定义域和峰位验收且不声称真实标定 | Phase 1 能谱 API 与配置 | 否，属于 Phase 1 明确要求
2026-07-13 | 幅值展宽使用正值重采样，极性独立存储 | 保证 A_peak 为正且不把符号混入幅值 | Phase 1 幅值 API 与事件表 | 否，属于 Phase 1 明确要求

2026-07-13 | Phase 1 HDF5 只写 events/true 与 metadata | 保持真值层边界，防止提前进入波形、触发和死时间 | Phase 1 IO | 否，属于阶段门禁
2026-07-13 | 到达统计使用固定 seed、经验 CDF 距离和随重复数缩放的 Fano 容限 | 避免单次脆弱 p-value，同时检验均值、方差和算法一致性 | Phase 1 统计验收 | 否，属于测试稳健性要求
2026-07-13 | 内存内事件生成默认限制预期事件数并允许显式调整 | 防止误配置直接分配超大真值表；流式输出留待 Phase 3 | Phase 1 CLI 与事件编排 | 否，属于安全边界
2026-07-13 | 公共恒定计数率接口与配置统一执行 10 到 1e7 cps 边界 | 防止绕过配置后进入未支持工况 | Phase 1 到达生成 API | 否，属于既有范围修复
2026-07-13 | 零权重 double_wall 不要求虚构未使用形状参数 | 保持可选成分语义并避免补造物理数值 | Phase 1 能谱配置与 provider | 否，属于既有范围修复
2026-07-13 | 固定时间常数经 PulseParameterProvider 条件接口写入事件表 | 保证数组对齐并为后续分布模型保留边界，不生成波形 | Phase 1 真值事件参数 | 否，属于既有接口要求
2026-07-13 | KS 容差随间隔样本量按 max(0.01, 4/sqrt(n)) 缩放 | 避免大样本仍使用过宽固定阈值，同时保留确定性回归稳定性 | Phase 1 统计验收 | 否，属于测试质量修复
2026-07-13 | 每个事件按其分数采样相位校正离散双指数峰值 | 保证孤立脉冲实际离散峰值等于 A_peak，而不只保证连续解析峰值 | Phase 2 脉冲数学与两种渲染器 | 否，属于 Phase 2 明确要求
2026-07-13 | direct_sparse 保留为逐事件参考，固定时间常数使用双指数递推状态 | 提供可读回归基线并使优化后端复杂度随样本数和事件数线性增长 | Phase 2 连续波形合成 | 否，属于 Phase 2 明确要求
2026-07-13 | 递推指数状态、AR(1) 状态和独立随机子流跨块连续 | 防止块边界截断脉冲尾部或重置低频基线，并保持固定 seed 可复现 | Phase 2 分块与噪声 | 否，属于 Phase 2 明确要求
2026-07-13 | 波形网格包含零时刻及事件视界终点，默认总样本上限为 10000000 | 使视界内最后事件至少拥有一个因果样本并防止误配置产生超大输出 | Phase 2 样本布局与 CLI | 否，属于内存安全边界
2026-07-13 | 模拟裁剪与 ADC 输入越界合并为饱和掩码，ADC 保存 uint16 | 明确模拟电压和数字化边界并支持 1 到 16 位统一码流 | Phase 2 数字化与 HDF5 | 否，属于 Phase 2 明确要求
2026-07-13 | Phase 2 HDF5 只新增 blocks/index、模拟电压、ADC 和饱和掩码，不新增观测层 | 保留真值可追溯与分块写入，同时防止提前实现 Phase 3 观测层；2026-07-14 模拟电压细分为裁剪前诊断值和裁剪后 ADC 输入值 | Phase 2 IO 与 inspect CLI | 否，属于阶段门禁
2026-07-13 | 每个 Phase 自动验收后必须更新用户手册并等待用户人工审核 | 将自动测试与用户功能确认分离，确保用户可操作、可核对并记录审核结论 | AGENTS、PROJECT_SPEC、USER_MANUAL、STATUS 和所有后续阶段 | 是，用户已明确要求
2026-07-13 | Phase 2 波形审核使用只读三面板 PNG 和流式最小/最大包络 | HDF5 结构清单不能直观展示脉冲，包络可避免总览降采样遗漏窄峰 | Phase 2 分析工具、CLI、测试和用户手册 | 是，用户随后明确要求进入 Phase 3
2026-07-13 | Phase 3 真值按连续时间块执行精确 Poisson-count+sorted-uniform 并立即追加 HDF5 | 避免高计数率长事件视界先构造整张真值表 | 真值生成、连续波形和 HDF5 IO | 否，属于 Phase 3 明确要求
2026-07-13 | 事件视界与连续渲染前缀分离，未渲染真值使用 -1 索引 | 避免低计数率长视界产生不必要的满采样波形，也不伪造样本 | 多尺度数据集和真值表语义 | 否，属于 Phase 3 明确要求
2026-07-13 | 死时间只标记观测候选接受状态，真值、波形和关联行不删除 | 保持真实事件层、模拟电子学层和观测层严格分离 | acquisition、HDF5 和统计 | 否，属于固定科学边界
2026-07-13 | 标准扫描使用暖机区和固定 seed 聚合计数容差 | 消除有限窗口初始存活偏差，并处理延长型理论率接近零的工况 | 13 点死时间统计验证 | 否，属于稳健统计验收
2026-07-13 | 内存报告使用事件、样本和块上限推导保守工作集，不设置跨机器秒数门槛 | 明确磁盘规模与 RAM 工作集的不同缩放规律 | 性能与内存报告 | 否，属于 Phase 3 验收要求
2026-07-13 | 在 Phase 3 与 Phase 4 之间新增 Phase 3.5 而不重编号 | 允许真实标定数据到位前先集成现有功能，并保持后续阶段引用稳定 | 阶段文档、状态和用户手册 | 是，用户明确要求新增阶段并先配置本地 Web
2026-07-13 | 本地 Web 后端只编排既有 Phase 1～2 API | 防止界面层产生第二套物理逻辑或改变已审核公共 API | 现存档于 archive/src_app 与连续波形产物 | 否，属于阶段边界
2026-07-13 | 交互单次限制 5000000 样本和 1000000 预期事件 | 避免页面请求造成大规模数组、HDF5 或绘图内存风险 | 资源预检、后端和用户手册 | 否，属于安全边界
2026-07-13 | Streamlit 服务固定监听 127.0.0.1，完整 HDF5 仅保存在本机 | 当前只需要个人离线操作界面，不扩张为远程服务或大型文件浏览器下载 | CLI、页面和安全边界 | 否，属于 Phase 3.5 明确范围
2026-07-13 | CSV 只包含 time_s 和 voltage_V，并从 HDF5 模拟电压分块写出 | 满足通用文本导出需求，同时避免第二套波形计算或一次性加载全部采样点 | Web 产物、页面和测试 | 是，用户人工审核反馈
2026-07-13 | 页面移除参数状态警告条和结果状态卡片，文件元数据继续保留状态 | 精简用户操作界面且不牺牲科研可追溯性 | Streamlit 页面与元数据边界 | 是，用户人工审核反馈
2026-07-13 | 波形图使用数据驱动纵轴，事件线最多 80 条、饱和点最多 500 个 | 防止高计数率密集标记遮住曲线，同时明确裁剪压平与绘图失败的区别 | waveform_plot、PNG 和回归测试 | 是，用户人工审核反馈
2026-07-13 | 观察时间最大值取采样点上限与预期事件上限对应时长的较小值 | 在输入位置提前阻止超限任务，后端继续保留独立安全校验 | Web 后端、Streamlit 和测试 | 是，用户人工审核反馈
2026-07-14 | Phase 2/Web HDF5 同时保存裁剪前诊断电压和裁剪后 ADC 输入电压 | 仅调整纵轴无法恢复已经被软件量程裁掉的高计数率堆积形态；两份数据可同时保留合成诊断与量程饱和事实 | WaveformBlock、流式合成、Phase 2 HDF5、Web 资源估算、PNG 和测试 | 是，用户人工审核反馈
2026-07-14 | 软件操作与原理手册独立为 docs/SOFTWARE_USER_MANUAL.md | 将软件使用说明和分阶段人工审核记录分离，便于持续维护与审阅 | AGENTS、PROJECT_SPEC、Phase 3.5 文档和两份手册 | 是，用户明确要求
2026-07-14 | 推迟 Phase 4 并以 synthetic_demo 数据先执行 Phase 5 | 用户当前没有实测示波器数据，但明确授权先研究网络 A；不得把合成训练解释为真实标定 | 阶段顺序、状态和 Phase 5 模型卡 | 是，用户明确授权
2026-07-14 | 网络 A 使用已知物理参数中心加有界神经残差的似然头 | 保留 exact Poisson 的可解释基准，同时允许检验条件密度网络是否能复现可变长事件与 marks | 现存档于 archive/src_ml 的模型、训练和推理 | 否，属于 Phase 5 研究假设
2026-07-14 | 机器学习依赖曾隔离为可选组，物理核心不导入 PyTorch | 遵守物理核心独立边界，并允许未安装 ML 依赖时继续使用精确物理 CLI | 历史依赖、归档 ML 与 CLI 延迟导入 | 否，属于固定工程边界
2026-07-14 | Phase 5 checkpoint 和报告固定标记 experimental，比较不自动提升默认级别 | 当前数据由 exact 基线自身生成，统计匹配不等于更准确；正式比较还显示网络显著更慢 | checkpoint、模型卡、比较报告和默认生成链 | 否，属于 Phase 5 明确门禁
2026-07-14 | 设备选择使用 cpu/cuda/auto，显式 CUDA 不可用时直接失败 | 防止用户以为 GPU 已启用而实际静默回退 CPU，并支持 RTX 5060 8 GB 的可审计运行 | ML 配置、训练、比较和测试 | 否，属于设备可复现要求
2026-07-15 | 插入Phase 6S合成工程预演但不改变正式阶段顺序 | 用户为比赛进度授权先搭建网络；无真实标定时只能验证工程流程，不能生成科学结论 | Phase文档、CLI、ML模块、手册和状态 | 是，用户明确授权
2026-07-15 | 人工干扰全部标记synthetic_demo且checkpoint禁止科学推广 | 防止已知人工目标恢复率被误写成真实探测器准确度 | 配置、数据、模型卡、评价和比赛表述 | 否，属于固定真实性边界
2026-07-15 | TCN只输出有界残差，事件保护区硬置零，违规回退纯物理波形 | 精确泊松物理链必须继续拥有唯一真值事件账本，网络不得新增、删除或移动事件 | residual模型、安全门和测试 | 否，属于固定科学约束
```
