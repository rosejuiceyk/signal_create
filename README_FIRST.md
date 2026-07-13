# Codex 投喂说明

本目录已经把总方案拆成可逐阶段执行的文件。

## 第一次使用

将整个目录放进代码仓库根目录。首先让 Codex 进入计划模式，只读取：

- `@AGENTS.md`
- `@docs/PROJECT_SPEC.md`
- `@docs/phases/phase_00_foundation.md`
- `@docs/STATUS.md`

不要让 Codex 一次完成全部阶段。

## 每个阶段的固定流程

1. 计划：让 Codex 阅读当前阶段文件，不修改代码；
2. 审核：你确认计划；
3. 实施：只执行当前阶段；
4. 验收：运行阶段文件内的测试和检查；
5. 自审：对照阶段验收标准修复问题；
6. 更新：写入 `docs/STATUS.md`；
7. 提交：确认后再进入下一阶段。

## 最简首次提示词

```text
请进入计划模式，本轮不要修改文件。

阅读：
- @AGENTS.md
- @docs/PROJECT_SPEC.md
- @docs/phases/phase_00_foundation.md
- @docs/STATUS.md

只为阶段 0 制订实施计划：列出目录、模块、配置对象、依赖、测试、验收命令、风险和不属于本阶段的内容。发现歧义要明确指出，不得虚构设备参数。等待我确认后再实施。
```

## 计划确认后的提示词

```text
阶段 0 计划已确认。现在只实施 @docs/phases/phase_00_foundation.md，并遵守 @AGENTS.md。完成后运行全部阶段 0 验收命令，更新 @docs/STATUS.md，然后停止。不得进入阶段 1。
```
