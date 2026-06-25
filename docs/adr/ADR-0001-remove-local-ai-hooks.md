# ADR-0001: 移除本地 AI 工具硬门禁

- 日期：2026-06-12
- 状态：已采纳
- 决策者：OfferGraph Team

---

## 背景

Claude Code / Codex 的项目级 `UserPromptSubmit`、`Stop` hooks 曾直接执行 `scripts/ai_guards/*`，在工作目录不一致时会阻断用户输入或结束流程。

这些规则本质是 AI 协作规范，不是 OfferGraph 业务运行时逻辑；不应以本地 hook 硬门禁形式影响对话可用性。

## 决策

1. Claude Code / Codex 项目级配置不再注册 `UserPromptSubmit` / `Stop` 硬门禁。
2. 需求流程、测试验证、二次审查和交付格式沉到 `AGENTS.md`、`CLAUDE.md`、`.cursor/rules/*` 等规范文档中，由 Agent 读取后执行。
3. `scripts/ai_guards/*` 保留为可选诊断脚本或 CI 候选能力，不作为本地对话阻断条件。

## 理由

硬门禁容易造成：

- 本地路径不一致导致工具无法启动
- 多工具行为不一致
- 用户输入被误拦截
- 对话结束被脚本阻断
- 维护成本高

## 后果

- Agent 依赖文档自觉执行流程
- 通过入口文档强化规范和最终交付格式降低风险
- 如确需恢复本地自动提醒，可重新添加非阻断 hook 或在 CI 中调用 `scripts/ai_guards/*`
