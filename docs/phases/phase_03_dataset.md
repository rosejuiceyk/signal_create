# Phase 3：触发、死时间、多尺度数据集与性能

- 阶段编号：3
- 初始状态：`not_started`
- 前置阶段：Phase 2 已通过
- 执行原则：本阶段通过验收后停止，未经用户确认不得进入下一阶段。

## 开始前必须阅读

- `AGENTS.md`
- `docs/PROJECT_SPEC.md`
- `docs/STATUS.md`
- 本文件

## 本阶段目标

建立“真实事件—连续波形—观测事件”完整链路，加入触发和死时间，生成可用于统计研究与神经网络的数据集，并保证高计数率下内存有界。

## 必须实现

1. 正/负脉冲阈值触发、滞回和最小保持时间。
2. 死时间模式：`none`、`nonparalyzable`、`paralyzable`。
3. 分离实现：
   - 理想事件级死时间；
   - 基于连续波形触发的采集死时间。
4. 多对多 `trigger_event_links`，支持一个触发关联多个真实事件。
5. 数据层：
   - `true_events`；
   - `continuous_blocks`；
   - `adc`；
   - `observed_events`；
   - `event_windows`；
   - 配置、标定和统计元数据。
6. 两种时长模式：`fixed_duration` 与 `target_event_count`，并支持最短/最长时长。
7. 区分事件生成 horizon 与实际连续波形渲染区，避免低计数率时生成不必要的超长满采样波形。
8. `max_samples_per_block`、HDF5 分块压缩和流式写盘。
9. 固定验证工况：`10, 30, 100, 300, 1e3, 3e3, 1e4, 3e4, 1e5, 3e5, 1e6, 3e6, 1e7 cps`。
10. 输出计数率、堆积、死时间损失、触发、误触发、饱和和性能报告。

## 物理约束

- 死时间内被拒绝的事件仍保留在 `true_events` 且仍参与连续波形；
- 观测计数率是输出统计，不是反向强制目标；
- 高计数率强堆积时允许无法逐事件识别，但真值关联必须可追溯。

## 测试与验收

- 非延长型与延长型理想死时间结果在统计误差内符合解析关系；
- 关闭死时间时不丢失符合触发条件的事件；
- 被死时间拒绝的事件仍出现在真值和连续波形中；
- 一个触发可关联多个堆积事件；
- 从 10 到 1e7 cps 的标准点均可运行；
- 高计数率分块流式处理，峰值内存不随总时长无限线性增长；
- HDF5 关联和索引可回读、可追踪；
- 分块边界连续。

建议命令：

```bash
pytest -q tests/test_trigger.py tests/test_deadtime.py tests/test_dataset_io.py
pytest -q tests/integration/test_phase3.py
he3sim generate-dataset -c configs/demo_minimal.yaml -o outputs/phase03_dataset
he3sim validate-physics -c configs/demo_minimal.yaml -o outputs/phase03_validation
he3sim inspect outputs/phase03_dataset/dataset.h5
```

实现说明：Phase 3 高计数率路径按连续时间块执行精确的 Poisson-count+sorted-uniform 抽样，真值
marks 生成后立即追加到可扩展 HDF5 表。连续区使用固定时间常数递推后端并保持跨块状态；事件视界
可以长于连续区。连续区外真值保留，但 `block_id/sample_index=-1`，不得解释为已生成连续波形。

## 可直接发送给 Codex 的执行提示词

```text
执行 Phase 3：实现触发、延长型/非延长型死时间、完整 HDF5 数据集、多尺度时长和高计数率流式生成。

阅读 @AGENTS.md、@docs/PROJECT_SPEC.md、@docs/phases/phase_03_dataset.md 和 @docs/STATUS.md。必须保证死时间只影响观测层，真实事件仍参与连续波形。完成标准计数率扫描、统计验证和内存分析，更新 STATUS 后停止，不得进入 Phase 4。
```
