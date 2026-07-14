# 分阶段文件索引

按顺序执行，每次只处理一个阶段。每个阶段自动验收通过后必须更新
[`docs/USER_MANUAL.md`](../USER_MANUAL.md)，停止并等待用户人工审核；人工审核通过且用户明确要求后，
才能进入下一阶段。

例外仅在用户明确授权时成立：Phase 4 可因实测数据尚未到位而标记为 `deferred_by_user`，先执行
只使用 `synthetic_demo` 目标的 Phase 5 研究对照；这不构成真实标定，网络必须保持 `experimental`。

- [`phase_00_foundation.md`](phase_00_foundation.md)：Phase 0：工程骨架、配置系统与数学规范
- [`phase_01_event_generator.md`](phase_01_event_generator.md)：Phase 1：真实事件到达、He-3 能谱与幅值
- [`phase_02_waveform.md`](phase_02_waveform.md)：Phase 2：归一化双指数脉冲与连续波形
- [`phase_03_dataset.md`](phase_03_dataset.md)：Phase 3：触发、死时间、多尺度数据集与性能
- [`phase_03_5_local_web.md`](phase_03_5_local_web.md)：Phase 3.5：本地 Web 波形生成界面
- [`phase_04_calibration.md`](phase_04_calibration.md)：Phase 4：示波器数据标定与实测模板
- [`phase_05_network_a.md`](phase_05_network_a.md)：Phase 5：神经网络 A——条件事件参数生成
- [`phase_06_network_c.md`](phase_06_network_c.md)：Phase 6：神经网络 C——物理残差与三链路比较
