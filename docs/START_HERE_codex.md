# START HERE —— 交给 Codex 的主控提示词（相关中子噪声数字孪生）


## 给 Codex 的总指令（逐字生效）

你是本仓库的执行代理。请严格遵守本仓库既有的工作纪律与本提示词。

### 0. 全局规则（必须遵守）

1. **先计划，后实施**。每个阶段先进入计划模式，产出实施计划并停止，等待用户确认后再写代码。
2. **一次只做一个阶段**。禁止跨阶段实施。每个阶段自动验收通过后，更新 `docs/STATUS.md`，然后停止，等待用户人工审核确认，未获确认不得进入下一阶段。
3. **不得虚构任何核数据、探测器参数、设备参数或标定结论**。所有新引入的物理/设备参数一律先标 `synthetic_demo`；只有在有实测或权威来源支撑并经用户确认后才可升级为 `provisional`/`validated`。
4. **保护物理核心的纯净**：`src/he3sim/physics/` 内不得引入 PyTorch 或任何重型可选依赖；新代码遵循既有 Protocol 抽象与 `TRUE_EVENT_DTYPE` 契约。
5. 每阶段结束必须通过：`ruff format --check`、`ruff check`、`mypy src`、`pytest -q` 全量绿灯。
6. 若发现歧义或与既有代码冲突，明确指出并暂停，不要自行猜测填充。

### 1. 开始前必读（按顺序）

- `@AGENTS.md`（仓库既有执行规范）
- `@docs/PROJECT_SPEC.md`（仓库既有总规格）
- `@docs/STATUS.md`（当前状态）
- `@docs/ROADMAP_v2.md`（**本包核心：优化后的技术方案与三级验证阶梯，取代此前任何路线文档**）
- `@docs/EXPERIMENT_DATA_COLLECTION.md`（零功率装置实测数据采集规范——供数据接入阶段对齐 schema，本轮不采集数据）
- `@docs/DT5800_HIL_integration.md`（CAEN DT5800 硬件在环方案）

### 2. 阶段执行清单（严格顺序，逐阶段停）

> 每个阶段的完整规格、必做项、禁止项、验收标准、以及"可直接执行的阶段提示词"，都在对应的 `docs/phases/*.md` 文件里。进入某阶段时，先读该文件，再进入计划模式。

| 顺序 | 阶段 | 规格文件 | 一句话目标 |
|---|---|---|---|
| ① | **Phase A（纯瞬发）** | `@docs/phases/phase_A_prompt_generator.md` | 相关中子事件生成器：点模型/分支过程 MC，仅瞬发中子，实现 `EventArrivalGenerator`，产出带裂变链关联的探测时间戳，无缝复用现有波形/ADC/触发/死时间/数据集全栈。 |
| ② | **Phase B** | `@docs/phases/phase_B_noise_analysis.md` | 噪声分析与自洽验证：实现 Rossi-α / Feynman-α / PSD 估计器，闭合"设定已知 α → 复原 α"回路。 |
| ③ | **Phase HIL（DT5800）** | `@docs/phases/phase_DT5800_hil.md` | 硬件在环：厂商无关的 DT5800 导出/导入与比对工具，用已知真值在真实电子学链上验证脉冲模型、死时间、双探测器互协方差。 |
| ④ | **Phase C** | `@docs/phases/phase_C_continuous_signal.md` | 连续信号噪声分析（He-3 前沿）：连续 ACF/VTM（含脉冲衰减项 α_e）、脉冲去卷积、双探测器互协方差；给出脉冲计数 vs 连续信号的可用边界。 |

**本包范围之外（不要在本轮做，留待后续单独授权）**：延迟中子（Phase A2）、全输运交叉验证 Phase D（MCNP-PoliMi/OpenMC/Serpent）、逆问题 ML Phase E、真实反应堆数据接入与标定、任何硬件实际控制。

### 3. 每阶段的固定动作

1. 读该阶段 `docs/phases/*.md`；
2. 进入计划模式，产出：新增/修改模块、公共接口、配置字段与校验、派生量计算、测试清单、验收命令、风险、以及"本阶段明确不做"的边界；停止等待确认；
3. 确认后实施；
4. 运行该阶段全部验收命令 + 全量 `ruff/mypy/pytest`；
5. 自审修复；
6. 更新 `docs/STATUS.md`（记录本阶段自动验收结果、命令哈希、遗留项）；
7. 停止，等待用户人工审核后再进入下一阶段。

### 4. 首个动作

请只做一件事：进入计划模式，阅读第 1 节所列文件与 `@docs/phases/phase_A_prompt_generator.md`，为 **Phase A（纯瞬发）** 制订实施计划并停止。不要修改任何文件。
