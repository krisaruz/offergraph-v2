# Validation Matrix

不同改动类型对应的最低验证要求。

---

| 改动类型 | 必须验证 |
|---|---|
| 纯函数 | 单元测试 |
| API | 请求参数、正常响应、错误响应、边界输入 |
| 数据模型 | 字段、默认值、序列化、兼容性、迁移回退 |
| Runtime | 主链路、异常分支、单源失败容错 |
| Adapter | 正常返回、空结果、超时、解析异常、认证失效 |
| LLM 抽取 | 正常抽取、空文档、格式错误、不确定信息、Schema 校验 |
| 前端页面 | loading、empty、error、success、failed request、重复提交 |
| 前端输入框 | IME `isComposing`、Enter、Shift+Enter |
| 视觉改动 | 浏览器观察、截图、visual-reviewer |
| 依赖变更 | install、typecheck、lint、build |
| 数据库变更 | 备份、迁移、回退验证 |
| 发布 | diff 检查、Release Notes 对齐、回退方案 |

---

## 变更记录

| 日期 | 变更内容 |
|------|---------|
| 2026-06-12 | 初始版本 |
