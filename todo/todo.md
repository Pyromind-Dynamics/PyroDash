# PyroDash Evaluate TODO

> **评测实现与基线对比**  
> Math：Minerva / GSM8K / Olympiad / AIME-2024 / AIME-2025  
> Coding + Agentic：SWE-Bench / Terminal-Bench v2

## Milestone 1：Math 场景评测闭环

> 目标：5 个数学基准上，PyroDash 协同质量 ≈ 大模型直调，并统计 Token / 成本

*Step 1 — Baseline 性能评估*

- [x] 大模型直调（GLM-5.2）质量上界：Minerva / GSM8K / Olympiad-Bench（pass@1，greedy）+ AIME-2024 / AIME-2025（avg@32）
- [x] 小模型（Qwen3.5-4B）独立推理质量下界：同上 5 个 benchmark
- [x] Token 消耗基线统计（大模型全量 vs 小模型全量，按 benchmark 分项 avg tokens/sample）

*Step 2 — 推理与 Relay*

- [x] 本地小模型 vLLM serve + `math_eval.sh` 一键评测
- [x] GLM / 商业 API relay（检测到 `<|llm_offload|>` 后 one-shot 接力）
- [x] per-dataset JSON 落盘（回答、offload 轨迹、基础 token 统计）
- [x] Token / 费用汇总脚本：分 benchmark 输出 SLM/LLM In·Out、Call Ratio、Cost

*Step 3 — 基线对比与结论*

- [x] 大模型直调（全量 Token，质量上界）
- [x] 小模型独立（零云端消耗，质量下界）
- [x] PyroDash 协同：Token 级动态 offload
- [x] Query Router：Query 级难度判断后整题路由（RouteLLM）
- [x] Token Router：基于token的熵进行路由（GlimpRouter）
- [x] 汇总：5 数学基准结果表 + Token 消耗对比 + 成本–准确率帕累托曲线

*Step 4 — λ 扫描与消融*

- [x] $\lambda$ 扫描（λ=0.05 / 0.1 / 0.2 / 0.3 / 0.6），自动出表找帕累托点
- [x] 消融对比入口： Avg.Acc.(%)、LLM Token Ratio(%)、Avg.LLM Calls、Cost($)

*Step 5 — 一键复现 & Collaborate Engine*

- [ ] PyroMind Console 一键复现（端到端评测）
- [ ] Collaborate Engine

---

## Milestone 2：Coding + Agentic 全场景评测

> 目标：SWE-Bench / Terminal-Bench v2 上协同 ≈ 大模型，并完善评估体系与全场景汇总

*Step 1 — 数据与 Harness*

- [ ] SWE-Bench（Verified / Lite）数据与评测 harness 接入
- [ ] Terminal-Bench v2 数据与评测 harness 接入
- [ ] Sandbox / 安全执行（仓库 patch、终端命令隔离）+ 判分流程跑通
- [ ] Offload 轨迹落盘与 Call Ratio / Token 统计模块

*Step 2 — 基线与分析*

- [ ] Qwen3.5-4B / GLM-5.2 / PyroDash 三方对比
- [ ] SWE-Bench + Terminal-Bench v2 结果表 + Token / 成本汇总

*Step 3 — 全场景汇总*

- [ ] Math + SWE-Bench + Terminal-Bench v2 统一结果表
- [ ] 完整基线对比：Query Router / Token Route
- [ ] 消融实验：$\lambda$ 值
- [ ] 端到端集成测试：`math_eval` + swe + terminal-bench 一键脚本 + 全场景汇总表

---

## Milestone 3：发布 Coding Plan

> 目标：基于协同推理能力，发布面向编程场景的完整产品方案

- [ ] Coding Plan 产品定义与方案设计
- [ ] 集成协同推理引擎（本地小模型 + 云端大模型协作）
- [ ] 编程场景专项优化（代码补全 / 重构 / Debug 等）
- [ ] 发布与推广
