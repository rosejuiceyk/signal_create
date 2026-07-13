# 项目状态

## 当前阶段

- 当前阶段：Phase 0（已通过验收，等待用户确认下一阶段）
- 当前状态：`passed`
- 最后更新：2026-07-13

## 已确认的范围

- 软件输入：死时间前真实计数率 `10~1e7 cps`
- 首版事件过程：恒定计数率齐次泊松过程
- 首版粒子：热中子
- 首版能谱：参数化 He-3 能谱
- 首版脉冲：峰值归一化双指数前放脉冲
- 采样率：`100~250 MS/s`
- 当前硬件范围：不实现 DT5800；DT5790 非核心依赖
- 后续实测：孤立脉冲和多个已知计数率下的连续示波器波形
- 神经网络：路线 A 与路线 C，均在物理模拟通过后实施

## 阶段记录

| 阶段 | 状态 | 通过日期 | 说明 |
|---|---|---|---|
| 0 工程骨架 | passed | 2026-07-11 | 安装、配置校验、格式、类型和测试均通过 |
| 1 事件与能谱 | blocked |  | Phase 0 已通过；等待用户明确确认进入 Phase 1 |
| 2 连续波形 | blocked |  | 等待阶段 1 |
| 3 触发与数据集 | blocked |  | 等待阶段 2 |
| 4 示波器标定 | blocked |  | 等待阶段 3 及真实数据 |
| 5 网络 A | blocked |  | 等待物理基线 |
| 6 网络 C | blocked |  | 等待真实连续波形及阶段 4 |

## 最近一次执行结果

- 新增/修改：Python 包骨架、Pydantic 配置、数据类型、随机上下文、结构化日志、CLI、外部接口 stub、两份示例配置、JSON Schema、数学规范、`signal_create` Conda 环境声明、安装说明和 Phase 0 测试。
- 运行命令：
  - `conda install -n signal_create python=3.11 pip -y`
  - `conda run -n signal_create python -m pip install -e ".[dev]"`
  - `conda run -n signal_create python -m pip install -e .`
  - `conda run -n signal_create python -m ruff format --check .`
  - `conda run -n signal_create python -m ruff check .`
  - `conda run -n signal_create python -m mypy src`
  - `conda run -n signal_create python -m pytest -q`
  - `conda run -n signal_create he3sim validate-config -c configs/demo_minimal.yaml`
  - `conda run -n signal_create he3sim validate-config -c configs/provisional_he3.yaml`
  - `conda run -n signal_create python -m he3sim validate-config -c configs/demo_minimal.yaml`
- 测试结果：在 `signal_create` 的 Python 3.11.15 中，Ruff 格式检查和 lint 通过；mypy 检查 13 个源文件无问题；pytest 29 项全部通过；两份配置和模块入口校验通过。
- 安装说明：`signal_create` 已升级到 Python 3.11.15，并完成项目及开发依赖的可编辑安装。项目后续命令统一在此环境运行。
- 已知问题：
  - 真实探测器、前放、ADC、触发和示波器参数尚未标定；`provisional_he3.yaml` 因此明确保留空值，不能用于物理模拟。
  - 当前目录未检测到 Git 元数据，未来输出的代码版本需要允许 `0+unknown`，直到项目纳入版本控制。
  - 共享 Anaconda base 环境中的依赖冲突已通过专用 `signal_create` 环境隔离；不要再把本项目依赖安装到 base。
- 本次审查修复：Markdown 展示公式改用 `$$`；新增 UTF-8/公式分隔符回归检查；拒绝非有限配置；`validated` 强制记录人工复核信息；标定元数据增加 JSON 兼容序列化；补齐 `RecoveryModel` Protocol。
- 阶段结论：Phase 0 通过验收；未实现 Phase 1 业务，未经用户确认保持阻塞。

## 决策日志

Codex 每次作出影响公共 API、数据结构、单位、随机性或物理模型的决定时，在此追加：

```text
YYYY-MM-DD | 决策 | 原因 | 影响范围 | 是否需用户确认
```

```text
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
```
