# OfferGraph — Claude Code 入口

本文件是 Claude Code 的项目入口。进入本仓库后，先阅读本文件，再按指引阅读相关文档。

---

## 1. 统一规范

**请先阅读 [`AGENTS.md`](AGENTS.md)**。

`AGENTS.md` 是本项目所有 AI 工具（Codex、Claude Code、Cursor）共享的统一开发规范，包含：

- 总原则（PRD 优先、验证优先、可回退优先）
- **强制需求处理流程**（理解上下文 → 主动澄清 → 复述需求 → 更新 PRD → 获取许可 → 实现验证 → 交付说明）
- 编码规则
- 前端功能与视觉设计规则
- 测试与验证规则
- 二次审查规则（must-fix / should-fix / note）
- 最终回复格式

---

## 需求处理流程

Claude Code 处理任何新需求或需求变更时，必须先执行 `AGENTS.md` 中的「强制需求处理流程」。

默认顺序：

1. 理解上下文
2. 主动澄清
3. 复述需求
4. 更新 `PRD.md`
5. 获取开发许可
6. 实现与验证
7. 交付说明

不得直接从用户一句需求跳到编码。

如果用户明确授权自主执行，可以继续，但必须把关键假设写入 `PRD.md` 和最终交付说明。

所有流程图必须使用 Mermaid。所有需求变更必须先更新 `PRD.md` 或对应设计文档，再改代码。

---

## 2. 产品事实来源

**`PRD.md`** 是产品需求的权威来源。

功能新增、接口变更、数据模型调整、行为变化都必须先更新 PRD，再编码。

---

## 3. 项目架构概要

```
offergraph-v2/
├── AGENTS.md                 # 统一 AI 开发规范
├── CLAUDE.md                 # 本文件（Claude Code 入口）
├── PRD.md                    # 产品需求文档
├── package.json              # Electron 桌面应用入口
├── backend/                  # FastAPI 后端
│   └── app/
│       ├── api/              # API 路由层
│       ├── runtime/          # Agent Runtime 核心
│       ├── adapters/         # 平台适配器
│       ├── tools/            # 工具层
│       ├── llm/              # LLM 集成
│       ├── models/           # SQLAlchemy ORM
│       ├── schemas/          # Pydantic API 模型
│       ├── services/         # 业务逻辑层
│       └── utils/            # 工具函数
├── frontend/                 # Next.js 15 + React 19 + Tailwind CSS 4
└── electron/                 # Electron 主进程
```

### 调用链

```
API Route → Service → AgentRuntime → QueryPlanner → SourceAdapters → HookEngine → Ranker → TraceLogger
```

### 技术栈

- 后端：FastAPI + Python 3.11+ + SQLAlchemy (async) + httpx + OpenAI SDK
- 前端：Next.js 15 + React 19 + Tailwind CSS 4 + lucide-react
- 桌面端：Electron
- 数据库：SQLite（开发）/ PostgreSQL（生产）
- 缓存：Redis

---

## 4. Claude Code 专属配置

### settings.json

`.claude/settings.json` 配置自动流程与门禁：

- `UserPromptSubmit` hook：根据用户 prompt 自动注入流程上下文
- `Stop` hook：结束前检查是否完成所有交付要求

### Skills

`.claude/skills/` 提供专项流程指引：

| Skill | 用途 |
|-------|------|
| `frontend-design` | Anthropic 官方前端设计 skill，避免 generic AI aesthetics |
| `offergraph-visual-style` | 项目专属视觉风格规范 |
| `frontend-safe-implementation` | 前端页面/组件/交互的安全实现流程 |
| `ui-ux-pro-max` | UI/UX 设计知识库（第三方，复杂 UI 参考） |
| `requirement-lifecycle` | 需求生命周期管理（需求变更时强制使用） |
| `test-regression-review` | 代码改动后的测试与二次审查收尾流程 |
| `shadcn-component-discovery` | shadcn 组件发现（需 shadcn/ui 安装后使用） |
| `shadcn-component-review` | shadcn 组件审查（需 shadcn/ui 安装后使用） |

### Agents

`.claude/agents/` 提供专项审查角色：

| Agent | 用途 |
|-------|------|
| `code-reviewer` | 通用代码审查（规范、PRD、安全、测试） |
| `frontend-reviewer` | 前端状态完整性审查 |
| `visual-reviewer` | 前端视觉质量审查（防止 AI 模板感） |

---

## 前端设计与视觉质量

涉及前端页面、组件、布局、样式、交互时，必须先使用以下 skills：

- `.claude/skills/frontend-design`
- `.claude/skills/offergraph-visual-style`
- `.claude/skills/frontend-safe-implementation`

如果项目使用 Tailwind/shadcn，也应使用 shadcn 相关 skills。

如果已安装 `.claude/skills/ui-ux-pro-max`，需要在复杂 UI、dashboard、数据产品页面中参考它。

实现完成后必须调用：

- `.claude/agents/frontend-reviewer.md`
- `.claude/agents/visual-reviewer.md`

视觉审查发现 must-fix 时，必须自动修复并重新验证。

---

## 5. 工作流程

### 涉及前端时

1. 阅读 `AGENTS.md` 第 4-5 节
2. 使用 `frontend-design` skill 选择视觉方向
3. 参考 `offergraph-visual-style` skill 确认产品气质
4. 使用 `frontend-safe-implementation` skill 确保状态完整性
5. 完成后调用 `frontend-reviewer` 审查状态
6. 调用 `visual-reviewer` 审查视觉质量
7. 修复 must-fix 问题

### 涉及后端时

1. 阅读 `AGENTS.md` 第 2-3 节
2. 检查 schema、路由、服务边界、PRD
3. 实现后运行测试
4. 调用 `code-reviewer` 审查

### 完成代码改动后

1. 使用 `test-regression-review` skill 完成测试与二次审查
2. 确保最终回复符合 `AGENTS.md` 第 10 节格式
3. Stop hook 阻止结束时，必须继续修复或明确未验证原因

---

## 6. 密钥与安全规范（血泪教训）

### ⚠️ 2026-06-08 踩坑记录

**事故**：将 LLM API Key 硬编码在 `config.py` 中，推送到公共 GitHub 仓库，导致密钥泄露。

**根因**：
1. 在 `config.py` 中写了 `llm_api_key: str = "真实密钥"` 作为默认值
2. 推送前没有扫描代码中的硬编码密钥
3. 没有在推送前运行安全审查

### 强制规则

**规则 1：绝对禁止硬编码密钥**

```python
# ❌ 错误 - 绝对不允许
llm_api_key: str = "sk-xxxx"
api_secret = "real-secret-here"

# ✅ 正确 - 必须从环境变量读取
llm_api_key: str = ""  # 通过 .env 配置
api_secret: str = ""   # 通过 .env 配置
```

**规则 2：敏感配置必须有 .env.example 模板**

每个使用 `.env` 的目录必须有对应的 `.env.example`：
- `backend/.env.example` — 后端配置模板
- `frontend/.env.local.example` — 前端配置模板

`.env.example` 中只包含占位符，不包含真实值。

**规则 3：推送前必须检查**

在 `git push` 之前，必须执行：

```bash
# 检查是否有硬编码密钥
grep -rn --include="*.py" --include="*.ts" --include="*.tsx" \
  -E "(api_key|secret|token|password|cookie)\s*[:=]\s*[\"'][^\"']{10,}" .

# 确认 .env 未被追踪
git ls-files | grep -E "\.env$|\.env\."
```

**规则 4：.gitignore 必须包含**

```gitignore
# Environment files
.env
.env.local
.env.*.local
!.env.example
!.env.local.example

# Database
*.db
*.sqlite3
```

**规则 5：CORS 不允许 `allow_origins=["*"]`**

```python
# ❌ 错误
allow_origins=["*"]

# ✅ 正确 - 明确列出允许的源
allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"]
```

**规则 6：禁止将敏感信息打印到日志/控制台**

```python
# ❌ 错误
print(f"Cookie: {cookie_string}")
logger.info(f"API Key: {api_key}")

# ✅ 正确 - 只打印状态
print(f"Cookie configured: {bool(cookie)}")
logger.info(f"API Key configured: {bool(api_key)}")
```

### 涉及密钥的代码审查清单

提交前必须确认：
- [ ] 代码中无硬编码密钥、Token、Cookie
- [ ] `.env` 文件未被 `git ls-files` 追踪
- [ ] `.env.example` 已创建且只含占位符
- [ ] 日志/打印中无敏感信息输出
- [ ] CORS 配置不使用 `*` 通配符

---

## 7. 禁止清单

详见 `AGENTS.md` 第 12 节。

核心禁止项：

- 禁止猜测性修复
- 禁止空 catch
- **禁止硬编码密钥（详见第 6 节）**
- 禁止静默删除功能
- 禁止默认 AI SaaS 风格前端
- 禁止不更新 PRD 就提交功能代码
- 禁止新增功能不带测试就交付

---

## 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-06-08 | 2.4.0 | 新增「密钥与安全规范」章节（第 6 节），记录密钥泄露踩坑教训，制定 6 条强制规则和提交前审查清单 |
| 2026-06-08 | 2.3.0 | 前端全量优化 — Radar Intelligence 视觉方向：首页重写、Feed 卡片改为列表项风格、ActivityLog 改为 console 风格、全局色彩 emerald→cyan、新增 radar-grid/sweep/scan 动画；后端新增 phase_start/fetch_started 事件，每个搜索阶段都有流式反馈 |
| 2026-06-08 | 2.2.0 | AgentRuntime 的 _safe_batch_extract 和 _batch_extract 从串行改为 asyncio.gather 并行，每篇独立 db session；同步更新 PRD.md 9.3/10.1 节 |
| 2026-06-08 | 2.1.0 | 新增「需求处理流程」章节，引用 AGENTS.md 强制需求处理流程。新增 requirement-lifecycle skill 索引 |
| 2026-06-08 | 2.0.0 | 改造为 Claude Code 入口文件，核心规范迁移到 AGENTS.md，新增 skills/agents/hooks 索引 |
| 2026-06-08 | 0.5.0 | Ranker 新增 relevance 维度；QueryPlanner 搜索词加入身份标签；LLM 抽取改并行 |
| 2026-06-07 | 0.4.0 | 新增 CI 测试要求 |
| 2026-06-07 | 0.3.0 | 强化自验证要求 |
| 2026-06-07 | 0.2.0 | 新增自验证要求；更新 TrustScore 权重 |
| 2026-06-06 | 0.1.0 | 初始版本 |
