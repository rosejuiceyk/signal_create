# OpenCode 项目交接稿：He-3 相关中子噪声数字孪生

> 快照日期：2026-07-20（Asia/Shanghai）  
> 交接对象：OpenCode 或其他后续编码代理  
> 实际仓库根目录：`C:\Users\rosejuice\Desktop\he-3-signal\he3_codex_context`  
> GitHub：`rosejuiceyk/signal_create`

## 一、交接结论

项目已完成并人工审核通过 Phase A；Phase B 的代码、测试、静态报告和文档已在本地完成自动验收，
但**尚未取得用户的 Phase B 人工审核结论，也尚未提交或推送**。当前必须停在
`awaiting_human_review`，不得自动进入 Phase HIL、Phase C 或其他后续阶段。

请把当前未提交工作树视为需要保护的有效成果，不要 reset、checkout、清理或覆盖。下一动作取决于
用户的人工审核结论：通过则更新审核记录并在获得明确授权后提交/推送；不通过则只修复用户指出的
Phase B 问题并重新验收。

## 二、仓库与远端状态

| 项目 | 当前值 |
|---|---|
| 本地分支 | `agent/prune-for-correlated-noise` |
| 本地 HEAD | `03a0165 Add Phase A static validation report` |
| 上游分支 | `origin/agent/prune-for-correlated-noise` |
| 远端主分支 | `origin/main`，当前已知 HEAD `cfa6a3d` |
| 草稿 PR | `#1 Prune Web/ML routes and complete Phase A correlated validation` |
| PR 状态 | `OPEN`、`DRAFT`，head 为当前分支，base 为 `main` |
| PR 地址 | `https://github.com/rosejuiceyk/signal_create/pull/1` |
| PR 当前内容 | 只到 Phase A，共 4 个提交；不含本地 Phase B 增量 |
| GitHub checks | 查询时 `statusCheckRollup` 为空，没有已报告的远端检查 |

当前本地工作树包含 Phase B 的已修改和新增文件，尚未 commit。执行任何 Git 操作前先运行：

```powershell
git status --short --branch
git diff --check
```

不要运行 `git reset --hard`、`git checkout -- .`、`git clean` 或其他会丢失当前改动的命令。

## 三、必须遵守的权威文档与门禁

开始工作前按以下顺序完整阅读：

1. `AGENTS.md`
2. `docs/PROJECT_SPEC.md` 中当前任务相关章节
3. `docs/STATUS.md`
4. `docs/ROADMAP_v2.md`
5. 当前阶段文件，例如 `docs/phases/phase_B_noise_analysis.md`
6. `docs/USER_MANUAL.md` 对应阶段审核章节
7. `docs/SOFTWARE_USER_MANUAL.md` 对应软件功能章节

优先级为：用户当前明确指令 > 当前阶段文档 > `AGENTS.md` > `PROJECT_SPEC.md`。

固定阶段纪律：

- 一次只实施一个阶段；先计划、经用户确认后再写代码。
- 自动验收与人工审核是两个独立状态。
- 自动验收通过后只能标记为 `awaiting_human_review` 并停止。
- 只有用户明确确认当前阶段人工审核通过，并另行明确要求进入下一阶段，才允许开始下一阶段。
- 所有临时物理量或设备量必须保持 `synthetic_demo` 或 `provisional`，不得伪装成实测标定。
- 原 Web/ML 路线已归档，活动代码不得重新导入 `archive/` 中的模块或依赖。
- 用户新增的长期制图约定：图片中的非专业名词尽量使用中文；Rossi-α、Feynman-α、PSD、
  VTM、Y∞、`k_eff` 等专业名词可以保留。

## 四、已完成阶段

| 阶段 | 状态 | 说明 |
|---|---|---|
| Phase 0–3 | `human_review_passed` | 工程骨架、事件/能谱、连续波形、触发/死时间/数据集 |
| M0 代码精简 | `human_review_passed` | Web/ML 只归档不删除；`competition/` 保留 |
| Phase A | `human_review_passed` | 纯瞬发相关事件生成器、lineage 旁表、6 图静态报告 |
| Phase 4Q | `awaiting_human_review` | 只读数据资格工具保留；科学出口仍 blocked |
| Phase 4 | `deferred` | 等待合格实测数据和明确授权 |
| Phase 3.5、5、6/6S | `archived` | 不再属于活动实现路线 |
| Phase B | `awaiting_human_review` | 本地自动验收通过，未提交、未推送、未人工确认 |

Phase A 已确认的科学约定：

- 使用纯瞬发、一速、源驱动分支过程；源仅在观测窗口内开启，不补造预热历史。
- 泊松过程仍是默认非相关基线。
- `TRUE_EVENT_DTYPE` 不变；相关谱系写入独立 `events/lineage` 旁表。
- `pileup_group_id` 仍只表示脉冲重叠，不能复用为裂变链编号。

## 五、Phase B 本地实现内容

### 5.1 核心代码

- `src/he3sim/analysis/noise.py`
  - Rossi-α：拟合 `B + A exp(-alpha |tau|)`。
  - Feynman-α：拟合纯瞬发单指数 `Y(T)`。
  - PSD/Cohn-α：Welch PSD 与洛伦兹拟合，拐点为 `alpha/(2*pi)`。
  - 固定拟合边界 `100–5000 s^-1`，不读取设定真值作为初值。
  - 时间块 bootstrap 保留曲线 bin 间共同波动；报告误差取 bootstrap 与朴素拟合误差的
    保守上界，并同时保留二者。
  - 非延长型死时间的一阶 Hazama/Mueller VTM lift：
    `Y_corr = Y_obs + 2 * R_obs * d`。
- `src/he3sim/analysis/phase_b_validation.py`
  - 三组 `(alpha, detection_efficiency, true_rate)` 闭环恢复。
  - 两组 alpha × 四组真率的死时间偏置网格。
  - 7 张 PNG、离线 HTML、JSON 报告的统一生成。
- `src/he3sim/analysis/figures.py`
  - 新增 7 个 Phase B 纯 Matplotlib 图函数；图函数只消费预计算数据/拟合结果。
  - 普通标题、说明和坐标尽量使用中文；专业名词保留。
- `src/he3sim/cli.py`
  - `he3sim analyze-noise`
  - `he3sim validate-alpha-recovery`
- `pyproject.toml`
  - 新增运行依赖 `scipy>=1.11,<2`。

### 5.2 测试

- `tests/unit/test_noise_estimators.py`
  - 数据级 α 恢复、泊松退化、Hazama lift、中文图函数等。
- `tests/integration/test_alpha_recovery.py`
  - CLI 报告、三种拟合结果、PNG/HTML/JSON 和保守不确定度。

### 5.3 文档

Phase B 已同步更新：

- `README.md`
- `docs/model_spec.md`
- `docs/phases/README.md`
- `docs/phases/phase_B_noise_analysis.md`
- `docs/STATUS.md`
- `docs/USER_MANUAL.md`
- `docs/SOFTWARE_USER_MANUAL.md`

本交接文件本身也属于当前未提交改动。

## 六、Phase B 自动验收证据

指定环境：Conda `signal_create`，Python 3.11。已执行：

```powershell
conda run -n signal_create python -m pip install -e ".[dev]"
conda run -n signal_create python -m ruff format --check .
conda run -n signal_create python -m ruff check .
conda run -n signal_create python -m mypy src
conda run -n signal_create python -m pytest -q
git diff --check
conda run -n signal_create python -m he3sim validate-alpha-recovery `
  -c configs/demo_minimal.yaml `
  -o outputs/phaseB_recovery
```

最后一次正式结果：

| 指标 | 结果 | 门限/解释 |
|---|---:|---|
| 全量 pytest | `167 passed` | 无失败、无跳过记录 |
| Ruff | 通过 | format check 与 lint 均通过 |
| mypy | 通过 | `52 source files` 无问题 |
| 最大 α 相对恢复误差 | `3.94%` | 默认门限 `< 5%` |
| 三方法最大差异 | `2.37%` | 默认门限 `< 5%` |
| 死时间修正改善比例 | `75%` | 8 个网格点中至少 6 个改善 |
| 共同连续可用上限 | 约 `10000 cps` | synthetic_demo `4 us` 非延长型死时间，5% 判据 |
| 正式报告 | `passed` | 7 PNG + HTML + JSON |

正式人工审核入口：

```text
outputs/phaseB_recovery/phase_b_validation.html
```

`outputs/` 被 `.gitignore` 忽略，因此报告只存在本地，不会随普通提交推送。七张图已逐图目检，
Rossi、PSD 与 bootstrap 图例遮挡已修复。

## 七、科学解释边界与已知风险

1. Phase B 结果是 synthetic_demo 内部闭环，不是反应堆测量、真实探测器标定或核数据验证。
2. `4 us` 死时间是本阶段的软件演示值；真实死时间类型和量值必须留到 Phase HIL 标定。
3. Hazama 实现是非延长型、弱损失的一阶 VTM lift；超过报告连续可用边界后不得声称无偏。
4. `10000 cps` 是当前 synthetic_demo 网格与 5% 判据下的对照基线，不是设备规格。
5. 当前未实现连续信号 ACF/VTM、去卷积、双探测器 CCF、缓发平台、DT5800 HIL、反应堆数据
   或交互仪表盘。
6. 不要为了让测试通过而读取真值 α 作为拟合初值、硬编码报告结果或改变物理逻辑。
7. `outputs/` 不受 Git 跟踪；如果重新生成报告，要保留 JSON 与图像供用户本地复核。

## 八、OpenCode 的立即工作顺序

### 情形 A：用户尚未给出 Phase B 人工审核结论

只做只读核对和回答问题，不进入后续阶段，不提交/推送。引导用户打开：

```text
outputs/phaseB_recovery/phase_b_validation.html
```

人工审核重点已记录在 `docs/USER_MANUAL.md` 的 Phase B 章节。

### 情形 B：用户明确说“Phase B 人工审核通过”

1. 更新 `docs/STATUS.md`：Phase B 改为 `human_review_passed`，记录用户确认日期和结论。
2. 更新 `docs/phases/phase_B_noise_analysis.md` 的阶段状态和人工审核记录。
3. 更新 `docs/USER_MANUAL.md` 的 Phase B 审核表：审核人、时间、结论。
4. 如软件功能没有新增，不必重写无关手册内容。
5. 运行全量 Ruff、mypy、pytest 和 `git diff --check`。
6. 只有用户同时明确授权提交/推送时，才把当前全部 Phase B 改动有意地 commit，push 到
   `agent/prune-for-correlated-noise`，并更新现有草稿 PR #1；不要另开重复 PR。
7. 提交后核对远端 commit、PR head 和工作树清洁状态。
8. 停止。即使 Phase B 人工通过，也不能自动进入 Phase HIL 或 Phase C。

### 情形 C：用户认为 Phase B 不通过

只修复用户列出的 Phase B 问题，保留阶段边界；重新运行正式报告和全量 QA，更新审核材料后再次
停在 `awaiting_human_review`。

### 情形 D：用户随后另行授权下一阶段

路线顺序为 Phase HIL，再到 Phase C。每个阶段都必须先完整阅读对应阶段文件、仅产出计划并停止，
等待用户确认计划后才能实施。不得把“Phase B 审核通过”自动解释为“开始下一阶段”。

## 九、提交与 PR 注意事项

历史上用户曾明确授权把同一阶段的现有改动一起提交并更新草稿 PR，但该授权不能自动扩张到新的
阶段或新的时点。OpenCode 应以用户当前指令为准。

如果本轮获得明确提交授权，建议提交信息概括为：

```text
Implement Phase B neutron-noise alpha recovery
```

提交前应至少检查：

```powershell
git status --short
git diff --stat
git diff --check
conda run -n signal_create python -m pytest -q
```

不要提交 `outputs/`，不要删除 `docs/competition/`，不要恢复已归档 Web/ML 依赖。

## 十、可直接复制给 OpenCode 的启动提示词

```text
你将接手仓库 C:\Users\rosejuice\Desktop\he-3-signal\he3_codex_context。

先完整阅读 AGENTS.md、docs/OPENCODE_HANDOFF.md、docs/STATUS.md、docs/ROADMAP_v2.md、
docs/phases/phase_B_noise_analysis.md、docs/USER_MANUAL.md 的 Phase B 章节。

保护当前未提交工作树：Phase B 已完成自动验收但尚未提交/推送，当前状态是
awaiting_human_review。不得 reset、clean、覆盖现有改动，不得自动进入 Phase HIL 或 Phase C。

先运行 git status --short --branch 并核对本地 HEAD 03a0165、分支
agent/prune-for-correlated-noise，以及 Phase B 未提交文件。正式报告位于
outputs/phaseB_recovery/phase_b_validation.html，outputs 被 Git 忽略。

如果用户尚未确认 Phase B 人工审核，只做只读核对并等待；如果用户明确确认人工审核通过，
更新 STATUS、阶段文档和 USER_MANUAL 审核表，运行全量 Ruff/mypy/pytest/diff check。只有得到
明确提交和推送授权时，才提交全部 Phase B 改动、推送当前分支并更新现有草稿 PR #1。

后续新增图片的普通说明尽量使用中文，专业名词保留。不要实现交互仪表盘，除非用户另行明确授权。
```

## 十一、仍需用户决定的问题

- Phase B 人工审核是通过还是不通过。
- Phase B 通过后，是否授权把全部当前改动（包括本交接稿）提交并推送到现有草稿 PR。
- 下一阶段是否按路线进入 Phase HIL；这需要独立明确授权和先行计划确认。

