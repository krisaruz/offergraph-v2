# OfferGraph v2 — 面经雷达

> 实时搜索全网面经，AI 结构化提取面试问题，帮你知道真实会问什么。

## 快速启动（开发模式）

### 前置依赖

- Python 3.11+
- Node.js 20+
- npm

### 1. 安装后端依赖

```bash
cd backend
pip install -e ".[dev]"
```

### 2. 生成演示数据

```bash
cd backend
python -m scripts.seed_demo_data
```

### 3. 安装前端依赖

```bash
cd frontend
npm install
```

### 4. 启动应用

**方式 A：分别启动（推荐开发）**

```bash
# 终端 1：启动后端
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 终端 2：启动前端
cd frontend
npx next dev -p 3000
```

**方式 B：一键启动（Electron 桌面模式）**

```bash
# 在根目录
npm install
npm run dev
```

### 5. 访问

| 服务 | 地址 |
|------|------|
| 前端 UI | http://localhost:3000 |
| 后端 API | http://127.0.0.1:8000 |
| API 文档 | http://127.0.0.1:8000/docs |

## 运行测试

```bash
cd backend
pytest tests/ -v
```

**结果：65 tests passed**

## 项目结构

```
offergraph-v2/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── main.py             # FastAPI 入口
│   │   ├── config.py           # 配置（.env 驱动）
│   │   ├── database.py         # SQLAlchemy async
│   │   ├── api/                # 路由 (feed, company-profile)
│   │   ├── adapters/           # 多源适配器 (nowcoder, maimai, xhs, search_engine)
│   │   ├── llm/                # LLM 客户端 + 结构化抽取
│   │   ├── models/             # 8 张数据表 ORM
│   │   ├── runtime/            # Agent Runtime 核心
│   │   │   ├── agent_runtime.py   # 主编排引擎
│   │   │   ├── query_planner.py   # 查询规划
│   │   │   ├── ranker.py          # TrustScore 排序
│   │   │   ├── hook_engine.py     # 质量门禁
│   │   │   └── ...
│   │   ├── services/           # 公司画像服务
│   │   ├── schemas/            # Pydantic 模型
│   │   ├── tools/              # 工具抽象
│   │   └── utils/              # 文本清洗等
│   ├── tests/                  # 单元测试 (65 tests)
│   ├── scripts/                # 演示数据生成
│   ├── pyproject.toml
│   └── .env                    # LLM 配置
├── frontend/                   # Next.js 前端
│   ├── src/app/                # 页面 (首页/Feed/详情/公司画像)
│   ├── src/components/         # 10+ 自定义组件
│   └── src/lib/                # API 客户端 + 类型
├── electron/                   # Electron 桌面壳
│   └── main.cjs
├── package.json                # 根 package（Electron + 并发启动）
└── PRD.md                      # 产品需求文档 (v2.1)
```

## 核心功能

| 功能 | 状态 |
|------|------|
| 多源并行搜索（牛客/脉脉/小红书/搜索引擎） | ✅ |
| Agent Runtime 编排引擎 | ✅ |
| LLM 结构化提取（面试问题/证据链） | ✅ |
| TrustScore 可信度排序 | ✅ |
| 质量门禁（Hook Engine） | ✅ |
| 搜索会话审计（tool_runs） | ✅ |
| 公司面试画像 | ✅ |
| 前端 UI（深色主题） | ✅ |
| Electron 桌面打包 | ✅ |
| 单元测试覆盖 | ✅ (65 tests) |

## LLM 配置

使用公司 AI Gateway（WPS）：

```env
LLM_API_BASE=http://ai-gateway.wps.cn/api/v3
LLM_MODEL=deepseek/deepseek-v4-flash
```

支持模型：deepseek-v4-flash, deepseek-v4-pro, claude-opus-4-6, gpt-5.5, gemini-3.5-flash 等。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /api/feed/search | 实时搜索面经 |
| GET | /api/feed/cached | 从数据库返回已有数据 |
| GET | /api/feed/detail/{id} | 面经详情 + 证据链 |
| GET | /api/feed/search-sessions/{id} | 搜索会话审计 |
| GET | /api/company-profile/{company} | 公司面试画像 |
