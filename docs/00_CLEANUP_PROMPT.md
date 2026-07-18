# 00 · 代码库精简提示词（单独运行，先于 START_HERE）

> 用途：把当前仓库精简到"后续相关中子噪声数字孪生"真正会用到的部分，移除已判定为死胡同的 Web(3.5) 与 ML(网络A/网络C) 路线，同时**不破坏保留模块的可导入性与测试**。
> 使用方式：把**本文件全部内容**发给 Codex 作为一次独立任务。它完成后你再进行 `START_HERE_codex.md` 的前向开发。

---

## 给 Codex 的指令（逐字生效）

你是本仓库的执行代理。本任务只做一件事：**安全地精简代码库**。全程遵守 `@AGENTS.md`。

### 0. 安全前提

1. 先创建独立分支（如 `chore/prune-for-correlated-noise`），所有改动在分支上进行。
2. **优先"归档"而非"硬删除"**：新建 `archive/` 目录，把要移除的内容 `git mv` 进去；只有在确认无任何保留模块引用、且用户已确认后，才可考虑真正删除。本轮默认只归档。
3. 每一步之后运行 `pytest -q`、`ruff check`、`mypy src`，确保保留部分始终绿灯。任何一步导致失败，先修复或回退，不得带着红灯继续。
4. 不要改动任何保留模块的物理逻辑，本任务不是重构，是"移除 + 修补引用"。

### 1. 先做依赖体检（不改代码，只读）

进入计划模式，先产出一份"依赖体检报告"并停止等待确认，内容包括：

1. 用 `grep -rn` 列出 `src/he3sim/ml/` 与 `src/he3sim/app/` 被哪些文件 `import`（预期主要是 `cli.py`、`__main__.py`、`tests/`、`configs/`）。
2. 列出 `cli.py` 中属于 Web / ML 的子命令（预期：`web`、`train-event-model`、`compare-event-model`；请以实际代码为准）。
3. 列出 `pyproject.toml` 中的可选依赖组（预期 `[ml]`、`streamlit`/`rich` 相关）与 `environment.yml` 中对应项。
4. 列出 `configs/` 中属于 ML 的文件（预期 `ml_event.yaml`、`ml_event_eval.yaml`）。
5. 列出 `docs/phases/` 中应归档的阶段文档（预期 `phase_03_5_local_web.md`、`phase_05_network_a.md`、`phase_06_network_c.md`）。
6. 明确指出任何"保留模块反向依赖了将被移除模块"的情况——如有，这类耦合要在移除前先解开，报告里列出解耦方案。

**先停在这里，等我确认这份报告，再进入第 2 节实施。**

### 2. 精简执行（确认报告后）

#### 2.1 保留（forward work 会用到，禁止移除）

- `src/he3sim/physics/`（全部：arrivals、spectra、pulse_models、amplitude、events、event_stream、rate_profiles、pulse_parameters、protocols 等）——**这是新工作的物理核心**。
- `src/he3sim/synthesis/`（baseline、noise、digitizer、renderers、streaming、dataset）——波形合成全栈，Phase A 之后直接复用。
- `src/he3sim/acquisition/`（trigger、dead_time、event_matching）——触发/死时间，Phase B/HIL 需要。
- `src/he3sim/analysis/`（counting_stats、pulse_features、reports、waveform_plot；`phase3_validation` 保留）——Phase B 的噪声分析将新增到这里。
- `src/he3sim/io/`（dataset、hdf5、mcnp、oscilloscope、dt5800_stub、dt5790 相关）——数据 IO；**保留 `dt5800_stub` 与示波器/CSV 导入**，Phase HIL 与未来数据接入会用；`mcnp.py` 保留（Phase D 后续用）。
- `src/he3sim/config.py`、`types.py`、`random.py`、`logging.py`、`cli.py`、`__main__.py`、`__init__.py`——核心骨架（`cli.py` 需按 2.2 删掉 Web/ML 子命令）。
- `configs/demo_minimal.yaml`、`configs/provisional_he3.yaml`、`configs/schemas/`——基础配置与 schema。
- `docs/`：`PROJECT_SPEC.md`、`STATUS.md`、`USER_MANUAL.md`、`SOFTWARE_USER_MANUAL.md`、`model_spec.md` 保留；`docs/phases/phase_00..phase_03`、`phase_04_calibration.md` 保留（04 维持 `deferred`）。
- 全部保留模块对应的 `tests/`。
- `AGENTS.md`、`README.md`、`pyproject.toml`、`environment.yml`、`scripts/`。

#### 2.2 归档（`git mv` 到 `archive/`）

- `src/he3sim/ml/` 整个包 → `archive/src_ml/`。
- `src/he3sim/app/` 整个包（Streamlit/web_backend/launcher）→ `archive/src_app/`。
- `tests/ml/`、`tests/test_web_backend.py`（及其它仅测试 ML/Web 的用例）→ `archive/tests/`。
- `configs/ml_event.yaml`、`configs/ml_event_eval.yaml` → `archive/configs/`。
- `docs/phases/phase_03_5_local_web.md`、`phase_05_network_a.md`、`phase_06_network_c.md` → `archive/docs_phases/`。
- `docs/competition/` 如与后续无关可整体 → `archive/competition/`（**先询问用户**：竞赛材料可能仍要用，不要擅自归档，报告里单列此项让用户决定）。

#### 2.3 修补引用（关键，避免留下断链）

- 从 `cli.py` 移除 Web/ML 子命令及其 import；保证 `he3sim --help` 正常、其余子命令可用。
- 从 `pyproject.toml` 移除 `[ml]` 可选依赖组与仅 Web 用到的依赖（如 `streamlit`）；保留物理核心依赖。同步更新 `environment.yml`。
- 全仓库 `grep` 残留的 `he3sim.ml` / `he3sim.app` 引用并清理或改为存档说明。
- 更新 `README.md`：删除 Phase 3.5 / Phase 5 / Phase 6 的使用说明段落，加入一行"这些路线已归档至 `archive/`，项目主线转向相关中子噪声数字孪生（见 `docs/ROADMAP_v2.md`）"。

#### 2.4 状态与验收

- 在 `docs/STATUS.md` 追加一条"代码库精简"记录：说明归档了哪些内容、保留了哪些、`pytest` 通过数、以及主线已切换到相关中子噪声方向。将 Phase 3.5/5/6 标记为 `archived`，Phase 4 保持 `deferred`。
- 运行并附上结果：`pytest -q`、`ruff format --check .`、`ruff check .`、`mypy src`、`pip check`、`git diff --check`。
- 全部绿灯后停止，输出改动摘要（归档清单 + 修补点 + 测试结果），等待用户审核。**不要在本任务里实现任何新功能。**

### 3. 明确不做

- 不删除物理核心、合成、采集、分析、IO、配置 schema。
- 不重构保留模块的内部逻辑。
- 不硬删除任何东西（本轮只归档）；未经用户确认不动 `docs/competition/`。
- 不开始 Phase A 或任何新阶段（那是 `START_HERE_codex.md` 的事）。
