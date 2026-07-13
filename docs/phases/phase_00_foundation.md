# Phase 0：工程骨架、配置系统与数学规范

- 阶段编号：0
- 初始状态：`not_started`
- 前置阶段：无
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

## 开始前必须阅读

- `AGENTS.md`
- `docs/PROJECT_SPEC.md`
- `docs/STATUS.md`
- 本文件

## 本阶段目标

建立可安装、可测试、可扩展的 Python 科研工程骨架，并冻结单位、参数状态、配置和数据类型约定。本阶段不实现完整事件模拟或连续波形生成。

## 必须实现

1. 创建 `pyproject.toml`、`src/he3sim/`、`tests/`、`configs/`、`docs/`、`notebooks/`、`scripts/`。
2. 使用 Pydantic 建立配置模型，至少覆盖：
   - 仿真元数据与随机种子；
   - 计数率、采样率、固定时长/目标事件数；
   - 参数状态 `synthetic_demo/provisional/validated`；
   - 能谱、幅值标定、双指数时间常数；
   - 噪声、基线、ADC、触发与死时间的占位配置。
3. 定义事件、波形块、观测事件、标定元数据的数据类型或结构化 dtype。
4. 提供 `numpy.random.Generator` 随机上下文和可复现配置哈希。
5. 创建 CLI 骨架，至少实现 `he3sim validate-config -c <yaml>`。
6. 创建：
   - `configs/demo_minimal.yaml`，所有参数为 `synthetic_demo`；
   - `configs/provisional_he3.yaml`，明确显示待标定字段。
7. 创建 `docs/model_spec.md`，写清：
   - 齐次泊松过程；
   - He-3 能谱 provider 接口；
   - 峰值归一化双指数公式；
   - 真实事件/连续波形/观测事件三层模型；
   - SI 单位和字段命名规则。
8. 为 MCNP、示波器数据和 DT5800 只定义 Protocol/stub；不得实现设备控制。
9. 建立 pytest、格式检查和类型检查配置。

## 明确不做

- 不生成真实事件；
- 不实现 He-3 能谱采样；
- 不生成连续波形；
- 不实现触发、死时间、神经网络或 GUI；
- 不读取 DT5790 文件作为核心逻辑。

## 交付物

- 可安装 Python 包；
- 配置、数据类型、日志和 CLI 骨架；
- 数学规范文档；
- 两份示例配置；
- 基础测试与安装说明；
- 更新后的 `docs/STATUS.md`。

## 测试与验收

至少执行：

```bash
python -m pip install -e .
pytest -q
he3sim validate-config -c configs/demo_minimal.yaml
he3sim validate-config -c configs/provisional_he3.yaml
```

建议同时执行项目实际配置的格式和类型检查命令。

通过条件：

- 可编辑安装成功；
- 全部测试通过；
- 两份配置可校验；
- 参数状态、单位和 seed 能序列化；
- Windows 路径与多进程入口无明显问题；
- 没有提前实现阶段 1 业务。

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase 0：只搭建 he3-pulse-sim 工程骨架、配置系统和数学基线。

阅读并遵守 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/phases/phase_00_foundation.md 和 @docs/STATUS.md。

先给出实施计划；计划获确认后再修改文件。只完成本阶段“必须实现”的内容，运行全部验收命令，更新 docs/STATUS.md，然后报告变更、命令、测试、限制和是否通过验收。不得进入 Phase 1，不得虚构任何真实设备参数。
```
