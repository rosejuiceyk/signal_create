# Phase 6S：物理残差网络合成工程预演

- 阶段编号：6S（比赛进度插入的工程预演，不是正式 Phase 6）
- 当前状态：`awaiting_human_review`
- 参数状态：`synthetic_demo`
- 用户授权：2026-07-15 明确允许在真实标定前使用人工干扰开展工程预演

## 目标与边界

复用已经审核的精确泊松事件和连续物理波形，人工加入可审计的基线游移、有色/白噪声、振铃和非线性
尾部干扰，训练轻量事件保护 TCN 恢复已知人工残差。该阶段只验证数据流、网络、约束、GPU和报告流程，
不得解释为真实 He-3 探测器标定或正式 Phase 6 科学验证。

精确泊松物理链仍是唯一真值事件生成器和默认波形路径。网络：

- 不生成、删除或移动真值事件；
- 不修改能谱、到达间隔、死时间前计数率或真值账本；
- 只输出有明确幅值上限的残差；
- 在真值事件保护区内强制输出零残差；
- 形状、有限值、幅值或事件保护检查失败时回退纯物理波形；
- 不接入本地 Web 默认生成链。

每个检查点和评估报告必须显式保留 `model_status: synthetic_scaffold`、
`real_data_calibrated: false` 和 `scientific_promotion_allowed: false`，防止合成预演结果
被误用为真实标定结论。

## 实现内容

1. 严格 YAML：`configs/ml_residual_synthetic.yaml`，所有人工干扰均为 `synthetic_demo`。
2. 每个 patch 通过现有 `prepare_waveform_simulation` 和 `iter_waveform_blocks` 生成，不复制物理逻辑。
3. train/validation/test 使用不同合成 run 和 seed；patch 不跨 split 复用。
4. 三通道输入：物理波形、事件保护掩码、归一化位置；计数率和采样率通过 FiLM 注入。
5. 轻量 dilated TCN，输出经 `tanh` 限幅并乘以事件保护反掩码。
6. 损失包括 Huber、多分辨率频谱、非事件区基线、事件保护和残差能量项。
7. 输出 checkpoint、合成 run 清单、逐 run 指标、训练摘要、评价、模型卡、比较报告和 PNG。

## 正式运行

```powershell
conda run -n signal_create python -m he3sim rehearse-residual-model -c configs/ml_residual_synthetic.yaml -o outputs/phase06s_rehearsal
```

本次 CUDA 运行使用3个合成计数率，每个计数率12/4/4个独立训练/验证/测试 run，共60个run。测试集
包含445个物理真值事件，事件保护违规和安全回退均为0。人工目标 RMSE 从约4.06 mV降至约0.943 mV，
相对改善约76.8%。这些数字只说明已知人工干扰可恢复，不是实测准确度。

## 验收命令

```powershell
conda run -n signal_create python -m pytest -q tests/ml/test_residual_scaffold_smoke.py
conda run -n signal_create python -m he3sim rehearse-residual-model -c configs/ml_residual_synthetic.yaml -o outputs/phase06s_rehearsal
conda run -n signal_create python -m ruff format --check src tests
conda run -n signal_create python -m ruff check src tests
conda run -n signal_create python -m mypy src
conda run -n signal_create python -m pytest -q
conda run -n signal_create python -m pip check
git diff --check
```

根目录三份用户比赛绘图脚本不属于 Phase 6S 源码验收范围，保持原样且另行审核。

## 不会实现

- 不读取 DT5790 数据训练网络；
- 不构造 `real - calibrated_physical` 伪配对；
- 不生成 B1～B4 正式对比；
- 不声称跨真实 run、计数率或采集会话泛化；
- 不证明真实硬件或 DT5800 就绪；
- 不解除 Phase 4Q、4C、4V 和正式 Phase 6 的科学门禁。
