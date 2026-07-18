# he3_correlated_noise_pkg —— 交给 Codex 的完整开发包

本包把"相关中子零功率反应堆噪声数字孪生"的完整后续开发，打包成 Codex 可直接执行的形态。你**不需要逐条复制提示词**：解压到仓库根目录，按下面两步把对应文件整体发给 Codex 即可。

## 使用流程（两步）

1. **解压到仓库根目录**：把本包内容解压到 `signal_create` 仓库根目录，使 `docs/` 与仓库既有 `docs/` 合并（新增文件不覆盖既有 `AGENTS.md`/`PROJECT_SPEC.md`/`STATUS.md`）。
   - 若担心覆盖，可先解压到 `docs/correlated_noise/` 子目录，再把 `START_HERE_codex.md` 里的 `@docs/...` 路径相应调整。

2. **先精简，再前向开发**：
   - 第一步：把 `00_CLEANUP_PROMPT.md` 的**全部内容**发给 Codex（独立任务，精简代码库、归档 Web/ML 死胡同）。审核通过。
   - 第二步：把 `START_HERE_codex.md` 的**全部内容**发给 Codex。它会据此读取本包各文件，按 Phase A → B → HIL → C 逐阶段推进（每阶段停下等你人工审核）。

## 目录内容

```
he3_correlated_noise_pkg/
├── PACKAGE_README.md                     ← 本文件
├── START_HERE_codex.md                   ← 【任务2】前向开发主控提示词（发给 Codex）
├── 00_CLEANUP_PROMPT.md                  ← 【任务3】代码库精简提示词（先单独发给 Codex）
└── docs/
    ├── ROADMAP_v2.md                     ← 【任务1】优化后的技术方案（三级验证阶梯，权威规格）
    ├── EXPERIMENT_DATA_COLLECTION.md     ← 创新点1：零功率装置实测数据采集规范 + 强制元数据 schema
    ├── DT5800_HIL_integration.md         ← 创新点2：CAEN DT5800 硬件在环方案（按能力分档）
    └── phases/
        ├── phase_A_prompt_generator.md   ← Phase A：相关中子生成器（纯瞬发）
        ├── phase_B_noise_analysis.md     ← Phase B：Rossi/Feynman/PSD + α 复原闭环
        ├── phase_DT5800_hil.md           ← Phase HIL：DT5800 导出/导入/比对工具
        └── phase_C_continuous_signal.md  ← Phase C：连续信号噪声分析（He-3 前沿）
```

## 三个任务与文件的对应

| 你的任务 | 对应产物 |
|---|---|
| 1. 优化技术方案 | `docs/ROADMAP_v2.md`（+ 两份创新点专文 + 四个阶段文件） |
| 2. 可直接交给 Codex、不用逐条复制的前向开发提示词 | `START_HERE_codex.md`（发这一份即可，它自会引用其余文件） |
| 3. 单独的代码库精简提示词 | `00_CLEANUP_PROMPT.md` |

## 本包实现范围

Phase A（纯瞬发）+ Phase B + Phase HIL + Phase C。
**范围之外（后续单独授权）**：延迟中子（Phase A2）、全输运交叉验证（Phase D，已按你要求推迟）、逆问题 ML（Phase E）、反应堆真实数据接入与标定、硬件实时控制。

## 关键设计原则（Codex 全程遵守）

- 先计划后实施、一次一阶段、每阶段人工审核门禁。
- 不虚构核数据/设备参数/标定结论；新参数一律 `synthetic_demo`。
- 物理核心不引入 PyTorch；遵守既有 Protocol 与 `TRUE_EVENT_DTYPE` 契约。
- DT5800 与数据接入工具厂商无关、profile 驱动、可用合成 fixture 通过 CI（不接实体设备也全绿）。
- 每阶段 ruff/mypy/pytest 全绿方可停。
