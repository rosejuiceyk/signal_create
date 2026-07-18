# 分阶段文件索引

按顺序执行，每次只处理一个阶段。每个阶段自动验收通过后必须更新
[`docs/USER_MANUAL.md`](../USER_MANUAL.md)，停止并等待用户人工审核；人工审核通过且用户明确要求后，
才能进入下一阶段。

活动基线保留 Phase 0–3。Phase 4/4Q 文档保留用于实测数据资格与标定，但 Phase 4 仍为
`deferred`。原 Phase 3.5 Web、Phase 5 网络 A、Phase 6 网络 C 和 Phase 6S 资料已移入
[`archive/docs_phases/`](../../archive/docs_phases/)，不再是可执行阶段。

- [`phase_00_foundation.md`](phase_00_foundation.md)：Phase 0：工程骨架、配置系统与数学规范
- [`phase_01_event_generator.md`](phase_01_event_generator.md)：Phase 1：真实事件到达、He-3 能谱与幅值
- [`phase_02_waveform.md`](phase_02_waveform.md)：Phase 2：归一化双指数脉冲与连续波形
- [`phase_03_dataset.md`](phase_03_dataset.md)：Phase 3：触发、死时间、多尺度数据集与性能
- [`phase_04q_data_qualification.md`](phase_04q_data_qualification.md)：Phase 4Q：数据资格与采样轴确认
- [`phase_04_calibration.md`](phase_04_calibration.md)：Phase 4：示波器数据标定与实测模板（deferred）

后续相关中子噪声阶段只以 [`docs/ROADMAP_v2.md`](../ROADMAP_v2.md) 为路线参考；本次精简不实现
其中任何新阶段。
