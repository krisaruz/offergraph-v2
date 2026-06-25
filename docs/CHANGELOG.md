# Changelog

## 2026-06-17 - 五源端到端面经结论验收

**问题现象**：用户在 Feed 中看到 Kimi 产品介绍、官网动态和科普内容后，继续追问“LLM 怎么过滤的”。后续真实 SSE 验收还发现 Kimi 查询虽然不再混入产品页，但牛客兜底会返回阿里、字节、百度、腾讯等非目标公司面经，仍然干扰用户判断。

**根因**：已有测试主要覆盖局部过滤、Adapter 兜底和异常状态，缺少“像用户一样”从流式搜索、排序、抓正文、结构化抽取、证据落库到 Feed 摘要的完整断言。此前的确定性过滤只判断“是不是面经”，没有强制判断“是不是目标公司”。

**修改文件**：
- `PRD.md` - 新增五源端到端推理验收要求和 Mermaid 流程。
- `backend/app/services/interview_filter.py` - 新增目标公司别名匹配与候选门禁。
- `backend/app/runtime/ranker.py` - 排序前过滤非目标公司候选。
- `backend/app/runtime/streaming_coordinator.py` - SSE `source_results` 前过滤非目标公司候选，并记录过滤计数。
- `backend/app/runtime/agent_runtime.py` - 非流式搜索同步应用目标公司过滤并输出质量计数。
- `backend/tests/test_source_reasoning_e2e.py` - 新增 5 个端到端样本，覆盖牛客、脉脉、小红书、通用搜索引擎和官网 JD。
- `backend/tests/test_ranker.py` - 增加非目标公司面经过滤回归测试。

**验证结果**：`cd backend && python -m pytest tests/test_source_reasoning_e2e.py tests/test_ranker.py -q` 通过，29 passed。

**风险与回退**：目标公司过滤依赖 title/url/company 强字段中的公司名或别名；极少数真实面经如果只在摘要正文提到公司、标题和元数据完全不提公司，可能被过滤，需要来源适配器补齐 company 元数据。回退方式为移除 `candidate_matches_target_company` 在 Ranker/Runtime 的接入，并恢复 PRD 的 0.3/2.9 条目。

---

## 2026-06-17 - 搜索策略稳定性优化（MCP 并发 + 超时治理 + Cookie 自动复验）

**问题现象**：用户反馈实时搜索"有时候超时，有时候 cookie 过期"。单条小红书笔记详情最坏路径接近 70s（`_connect` 15s + `call_tool` 30s × 2 + fallback），`agent_runtime` 用 `asyncio.gather` 并行调 5 条 `adapter.fetch(url)`，但 `xhs_mcp_client._call_lock` 把所有 MCP 调用串行化，实际 5 条详情串行执行需 5×20s=100s。Cookie 过期只能靠搜索阶段的 302 被动检测，详情阶段 `get_note_content` 遇到"请先登录"静默落错误，不触发 UNAUTHORIZED 标记。前端只能手动点击校验，看不到"上次验证时间"。

**根因**：
1. `XhsMcpClient._call_lock` 用 `asyncio.Lock` 把所有 `call_tool` 串行化，与运行时 `asyncio.gather` 并行 fetch 的意图相悖。
2. `call_tool` 默认 30s 超时晚于运行时 `webfetch_timeout=20s`，导致运行时先超时但 MCP 内部还在重试，浪费资源。
3. 单次超时就 `self._connected = False`，导致后续每次都重启 Playwright 浏览器（15s 成本）。
4. `get_note_content` 没有"请先登录"检测，详情失败无法识别 cookie 过期。
5. `SourceAuthManager` 没有 `lastValidatedAt` 元数据，前端无法展示和判断是否需要复验。
6. PRD 6.2.5 写的"平台 API 5s、搜索引擎 8s、WebFetch 10s"与代码实际值（30s/12s/20s）严重脱节。

**修改文件**：
- `backend/app/adapters/xhs_mcp_client.py` - `_call_lock` 改为 `_call_semaphore = asyncio.Semaphore(3)` 允许 3 路并发；`call_tool` 默认超时 30s→20s；单次超时不再立即断连，改为 `_health_failures += 1`，连续 3 次才标记 `_healthy = False` 触发重连；`get_note_content` 加"请先登录"检测，命中则 `raise ValueError("auth_required")`；心跳探活升级为同时检查 `_session` 存活。
- `backend/app/adapters/xiaohongshu.py` - `fetch` 重试从 2 次降为 1 次（单次尝试）；在 `except Exception` 分支识别 `auth_required`，命中则调 `GLOBAL_SOURCE_HEALTH.record_status("xiaohongshu", SourceStatus.UNAUTHORIZED, "Login required in fetch")` 主动上报，然后 return None。
- `backend/app/runtime/source_auth.py` - `SourceAuthManager` 新增 `_last_validated: dict[str, float]` 内存字典，新增 `mark_validated(source)` / `last_validated_at(source)` 方法；`import_maimai_cookie` / `import_xhs_cookie` 校验通过后调用 `mark_validated`。
- `backend/app/api/routes_source_auth.py` - 改用模块级单例 `_MANAGER = GLOBAL_SOURCE_AUTH` 共享状态；`GET /api/source-auth/{maimai,xhs}/status` 返回新增字段 `lastValidatedAt` 和 `revalidateIntervalHours`；`POST /api/source-auth/{maimai,xhs}/cookie` 校验通过后调用 `manager.mark_validated(source)`；新增 `POST /api/source-auth/validate-all` 端点（仅 localhost），对每个 source 执行轻量校验。
- `backend/app/config.py` - 新增 `source_auth_revalidate_interval_hours: int = 24`。
- `frontend/src/lib/types.ts` - `MaimaiAuthStatus` / `XhsAuthStatus` 新增 `lastValidatedAt` 和 `revalidateIntervalHours`；Cookie 导入响应新增 `lastValidatedAt`；新增 `ValidateAllResult` 和 `ValidateAllResponse` 类型。
- `frontend/src/lib/api.ts` - 新增 `validateAllSources(sources?: string[])` 函数，调用 `/api/source-auth/validate-all`，timeout 60s。
- `frontend/src/components/source-auth-panel.tsx` - 新增 `formatLastValidated` 展示"刚刚/X 分钟前/X 小时前/X 天前"；新增 `shouldRevalidate` 判断是否超过 24h；新增 `runAutoRevalidation` 在 15s 轮询中自动触发复验，用 `revalidationInFlight` ref 防重；新增"立即复验全部数据源"按钮；展示"上次验证：X 分钟前"或"正在自动复验..."。
- `PRD.md` - 升级到 2.8：6.2.2 小红书行补充 MCP 并发上限 3 与单条详情 18s 超时；6.2.5 修正超时数值（30s/12s/20s）并加 Semaphore(3) 与超时不断连策略说明；6.9.2/6.9.3/6.9.4/6.9.5 补充 lastValidatedAt、自动复验、UNAUTHORIZED 识别、手动复验按钮等验收标准；变更记录追加 2.8 条目。
- `backend/tests/test_xhs_mcp_client.py`（新建） - 4 个测试：Semaphore(3) 并发上限、单次超时不断连、连续 3 次超时才标记 unhealthy、`get_note_content` 检测 auth_required。
- `backend/tests/test_xiaohongshu_adapter.py` - 新增 2 个测试：`fetch` 捕获 auth_required 后上报 UNAUTHORIZED、auth_required 不触发 `_reset_client`。
- `backend/tests/test_source_auth.py` - 新增 2 个测试：`mark_validated` 记录时间戳、`last_validated_at` 对未知 source 返回 None。
- `backend/tests/test_source_auth_routes.py` - 新增 `isolated_manager` fixture 替换 `_MANAGER`；新增 4 个测试：status 返回 lastValidatedAt、validate-all 端点、validate-all 拒绝非 localhost、xhs cookie 导入成功后标记 validated。

**验证结果**：`cd backend && python -m pytest tests/ -q` 全部通过（136 passed）；`cd frontend && npm run build` 构建成功，无 TypeScript 错误。二次审查后追加修复：`maimai.py` / `xiaohongshu.py` 的 search 成功路径补调 `mark_validated`（兑现 PRD 6.9.2 "搜索成功即视为 cookie 有效"契约）；`source-auth-panel.tsx` 15s 定时器改用 ref + 空依赖数组，避免每次状态刷新重置计时。详见本轮交付说明。

**风险与回退**：
1. `Semaphore(3)` 可能压垮 Playwright 单浏览器，若 XHS 风控频繁可降回 `Semaphore(2)` 或 `Lock()`。
2. `fetch` 不重试可能导致偶发网络抖动失败，若抖动频繁可恢复为 2 次但缩短单次超时。
3. `last_validated_at` 不持久化，服务重启后丢失，但搜索成功即重新标记，正常运行下 15s 内会恢复。
4. 24h 自动复验会拉起 MCP 浏览器，若担心成本可加配置开关 `source_auth_auto_revalidate_enabled`。
5. 回退方式：`git revert` 单个 commit；或手动把 `_call_semaphore` 改回 `_call_lock`，`for attempt in range(1):` 改回 `range(2):`，删除前端 `validateAllSources` 调用。PRD 6.2.5 数值修正建议保留（事实修正）。

## 2026-06-17 - Kimi 产品页误入面经 Feed 修复

**问题现象**：实时搜索 Kimi + 自动化测试时，Feed 中出现“Kimi AI with K2.6”“Kimi 官网”“三分钟读懂 Kimi”等产品介绍、官网动态、知乎科普内容，这些不是面经。
**根因**：LLM 结构化抽取发生在搜索结果展示之后，只负责从已抓取正文中抽取问题；通用搜索引擎候选在 `ranking_completed/search_completed` 前只做了时间和相关度排序，没有强制要求 title/snippet 具备“面经/面试/面试题/interview”等面经意图信号。
**修改文件**：
- `backend/app/services/interview_filter.py` - 新增确定性面经意图过滤规则。
- `backend/app/runtime/ranker.py` - 通用搜索引擎候选缺少面经信号时，不进入 Feed 排序。
- `backend/app/runtime/streaming_coordinator.py` - SSE `source_results` 和最终排序都复用面经意图过滤，前端不会先看到垃圾候选。
- `backend/app/runtime/agent_runtime.py` - 非流式搜索同步过滤非面经候选，并输出过滤计数。
- `backend/app/llm/structured_extract.py` - LLM 抽取前增加正文面经信号检查，非面经正文直接 `skipped/non_interview_content`。
- `backend/tests/test_ranker.py`、`backend/tests/test_streaming_coordinator.py`、`backend/tests/test_structured_extract.py` - 增加 Kimi 产品页过滤和非面经正文跳过 LLM 的回归测试。
**验证结果**：`cd backend && python -m pytest tests/ -q` 通过，124 passed；本地页面验收见本轮交付说明。
**风险与回退**：该规则只对通用搜索引擎候选做硬过滤，不影响牛客/脉脉/小红书/官网 JD 的来源特化结果。回退方式为移除 `interview_filter.py` 接入并恢复原 ranker/streaming_coordinator 逻辑。

## 2026-06-17 - 牛客免费兜底与授权状态纠偏

**问题现象**：Feed 状态栏显示牛客“无结果”、脉脉“登录失效”，但授权面板可能仍把脉脉显示为“已保存”，用户会感觉来源又没有生效。
**根因**：牛客 Adapter 只在配置了 SearXNG 时才会做 `site:nowcoder.com` 兜底，当前免费环境未配置 SearXNG 时，Nowcoder API 空结果会直接结束；脉脉授权状态接口只读取本地 Cookie 文件存在性，没有返回最近运行时记录的 `unauthorized` 状态。
**修改文件**：
- `backend/app/adapters/nowcoder.py` - 牛客 API 空结果且缺少 SearXNG 时，改用免费 Bing RSS 做 `site:nowcoder.com` URL/snippet 兜底。
- `backend/app/runtime/source_health.py` - 新增最近运行状态读取能力。
- `backend/app/api/routes_source_auth.py` - 授权状态接口透传最近运行时的登录失效状态。
- `frontend/src/components/source-auth-panel.tsx`、`frontend/src/lib/types.ts` - 授权面板把过期 Cookie 显示为“已过期”，不再显示绿色正常态。
- `backend/tests/test_nowcoder_adapter.py`、`backend/tests/test_source_auth_routes.py` - 增加回归测试。
**验证结果**：见本轮交付说明。
**风险与回退**：Bing RSS 兜底只作为低置信 URL/snippet 候选，不作为真实正文证据。回退方式为移除牛客 Bing RSS 分支和授权状态运行态透传。

## 2026-06-17 - SSE 搜索数据库会话生命周期修复

**问题现象**：Feed 页面发起实时搜索后，前端出现红色错误框：`sqlite3.OperationalError: no active connection`，错误发生在更新 `search_sessions.query_plan_json` 时。
**根因**：`/api/feed/search/stream` 把 FastAPI 请求依赖注入的 `AsyncSession` 传给 `StreamingCoordinator`。SSE 响应返回后，请求级依赖可能先结束并关闭连接，而流式搜索仍在后台继续写入 `SearchSession`，导致 SQLite 连接失效。
**修改文件**：
- `backend/app/api/routes_feed.py` - 将 SSE 搜索的数据库会话移动到 `event_generator` 内部，用 `async_session_factory()` 覆盖整个流式生成生命周期。
- `backend/tests/test_api_routes.py` - 新增回归测试，验证流式搜索期间数据库会话保持可用，流结束后才关闭。
**验证结果**：已运行针对性后端测试与本地页面验收，结果见本轮交付说明。
**风险与回退**：改动只影响 SSE 搜索路由的会话生命周期，不改数据库结构。回退方式为恢复 `/api/feed/search/stream` 使用请求级 `db` 的旧实现，但会重新暴露本问题。

## 2026-06-16 - 脉脉授权恢复、结构化分析终态与浅色 Research Console

**问题现象**：脉脉 Cookie 过期后只能人工改环境变量或文件，前端没有恢复入口；部分帖子已抓到正文但结构化抽取失败/超时后，卡片会一直显示“等待结构化分析”；首页和 Feed 大面积黑底、霓虹风格，阅读密度和专业感不足。

**根因**：已有 `SourceAuthManager` 只支持读取/续期项目授权状态，缺少本地安全导入与校验 API；`streaming_coordinator` 异常分支缺少 `status/extraction_status` 终态，前端也没有在增强完成时收敛未完成状态；核心页面视觉令牌和组件仍沿用暗色 Radar Console。

**修改文件**：
- `PRD.md` - 升级到 3.8，定义脉脉用户授权导入、成功响应续期、硬过期显式恢复、结构化抽取终态和浅色 Research Console 方向。
- `backend/app/api/routes_source_auth.py`、`backend/app/main.py` - 新增 localhost-only 脉脉 Cookie 状态/导入接口，校验未授权时不保存，不回显 Cookie。
- `backend/app/adapters/maimai.py` - 暴露只读 `current_cookie`，用于保存校验过程中被 `Set-Cookie` 续期后的项目 Cookie。
- `backend/app/runtime/streaming_coordinator.py` - 抽取文档缺失、失败和超时都返回明确 `extraction_status`，并把失败/超时写回文档状态。
- `frontend/src/lib/api.ts`、`frontend/src/lib/types.ts` - 新增脉脉授权状态和 Cookie 导入客户端类型/方法。
- `frontend/src/components/source-auth-panel.tsx` - 新增本地脉脉授权恢复面板。
- `frontend/src/app/page.tsx`、`frontend/src/app/feed/page.tsx`、`frontend/src/components/streaming-feed.tsx`、`frontend/src/components/feed-card.tsx`、`frontend/src/components/activity-log.tsx`、`frontend/src/components/agent-activity.tsx`、`frontend/src/components/source-status.tsx`、`frontend/src/components/profile-form.tsx`、`frontend/src/components/app-header.tsx`、`frontend/src/app/globals.css` 等 - 将首页、Feed、详情和状态组件改为浅色研究工作台风格，并修正结构化分析终态展示。
- `backend/tests/test_source_auth_routes.py`、`backend/tests/test_streaming_coordinator.py` - 增加脉脉 Cookie 导入保存/拒绝、抽取失败终态事件测试。

**验证结果**：新增后端测试通过；前端 `npx tsc --noEmit` 通过。真实 localhost 浏览器链路和完整后端/前端构建结果见本轮最终交付说明。

**风险与回退**：脉脉长期有效策略仍受平台会话硬过期限制，系统只做用户授权导入与响应续期，不绕过登录；Cookie 仅保存到项目授权目录。回退方式为移除 `routes_source_auth.py`、`SourceAuthPanel` 和本轮前端浅色改造文件变更，并恢复 `streaming_coordinator` 事件结构。

## 2026-06-16 - 免费搜索兜底与小红书 URL 发现增强

**问题现象**：本地未配置 `SEARXNG_BASE_URL` 时，实时搜索页中 `search_engine` 和 `official_job` 显示红色 `config_error`；小红书主链路不稳定时，URL 发现能力也依赖 SearXNG，导致重要来源容易直接消失。
**根因**：搜索引擎改造成免费方案后只保留了自托管 SearXNG 路径，但本机环境尚未配置 SearXNG；小红书 fallback 也只接入了 SearXNG，没有无 Key 的免费 URL 发现兜底。
**修改文件**：
- `PRD.md` - 升级到 3.7，明确 SearXNG 是首选免费方案，缺失时可使用无 Key Bing RSS fallback。
- `backend/app/adapters/free_web_search.py` - 新增无 Key Bing RSS 搜索工具，只返回 URL/title/snippet/date。
- `backend/app/adapters/search_engine.py` - `SEARXNG_BASE_URL` 缺失时改用 Bing RSS fallback，不再直接 `config_error`。
- `backend/app/adapters/official_job.py` - 官网 JD 搜索缺 SearXNG 时改用 Bing RSS fallback，并继续执行官方域名过滤。
- `backend/app/adapters/xiaohongshu.py` - MCP 不可用且缺 SearXNG 时，使用 Bing RSS 发现公开小红书笔记 URL，标记为低置信 URL/snippet 候选。
- `backend/app/main.py` - `/api/debug/sources` 对缺 SearXNG 的免费 fallback 返回 `ok` 和 `fallbackProvider=bing_rss`。
- `backend/tests/test_free_web_search.py`、`backend/tests/test_search_engine_adapter.py`、`backend/tests/test_official_job_adapter.py`、`backend/tests/test_xiaohongshu_free_fallback.py`、`backend/tests/test_api_routes.py` - 更新和补充 fallback 测试。
**验证结果**：`python -m pytest tests/ -v` 通过（115 passed）；本地 `/api/debug/sources` 返回 `search_engine` 与 `official_job` 为 `ok` 且 `fallbackProvider=bing_rss`；真实 Feed 搜索返回 15 条结果，除脉脉 Cookie 过期外其他来源可用；真实小红书 MCP 搜索返回 2 条并成功抓取 1 条笔记正文。
**风险与回退**：Bing RSS 是免费公开端点，稳定性弱于自托管 SearXNG，可能超时或限流；fallback 只作为 URL/snippet 发现，不作为高置信正文证据。回退方式为移除 `free_web_search.py` 接入并恢复缺 SearXNG 时的 `config_error` 逻辑。


本文记录 OfferGraph 项目的工程变更事实。

格式：改动时间、问题现象、根因、修改文件、验证结果、风险与回退。

---

## 2026-06-16 — 岗位画像前端工作台

**问题现象**：后端已有 `/api/role-profile/search`，但前端没有直接输入自然语言关键词并查看岗位画像、来源状态和证据链的入口，用户仍无法在 localhost 上完整验收岗位画像能力。

**根因**：现有前端只覆盖画像向导、流式 Feed、详情页和公司画像页，缺少 RoleProfile API 的类型、客户端方法和页面状态管理。

**修改文件**：
- `PRD.md` — 升级到 3.6，新增 `/role-profile` 页面目标、用户流程、信息层级、状态和交互规则。
- `frontend/src/lib/types.ts` — 新增岗位画像请求、响应、证据、技能权重和准备计划类型。
- `frontend/src/lib/api.ts` — 新增 `searchRoleProfile()` 调用 `POST /api/role-profile/search`。
- `frontend/src/lib/format.ts` — 新增 `local_job_radar_cache` 来源展示名。
- `frontend/src/app/role-profile/page.tsx` — 新增岗位画像工作台，覆盖 empty/loading/error/success、重复提交防护、中文输入法回车处理、来源状态、质量统计、证据链和限制项。
- `frontend/src/components/app-header.tsx`、`frontend/src/app/page.tsx` — 增加岗位画像入口。

**验证结果**：
- `cd frontend && npx tsc --noEmit`：通过。
- `cd frontend && npm run build`：通过；`/role-profile` 生成静态页面。
- `git diff --check`：通过，仅有 Windows CRLF 提示。
- `http://127.0.0.1:3001/role-profile`：HTTP 200。
- Edge headless 截图：桌面与 390px 移动视口均可渲染；移动端已修复样例标签横向溢出。

**风险与回退**：该页面复用即时 API，不新增前端状态持久化；真实搜索耗时和质量仍取决于后端来源配置、Cookie 授权状态、SearXNG 和 LLM Key。回退方式为移除 `/role-profile` 页面、API 客户端方法和导航入口，并恢复 PRD/文档条目。

---

## 2026-06-16 — 本地 JobRadar JD 缓存兜底

**问题现象**：岗位画像依赖实时官网 JD 和 SearXNG 发现入口；当本地没有配置 SearXNG、官网搜索未命中或官方站点短时不可用时，画像容易缺少 JD 证据，只能基于面经低置信推断岗位职责。

**根因**：`ai-job-radar` 项目已沉淀公司官网岗位快照，但 OfferGraph 没有读取这类本地官方 JD 缓存的入口，也没有把缓存证据与实时官网 JD 在置信度和限制项上区分开。

**修改文件**：
- `PRD.md` — 升级到 3.5，定义本地 JobRadar 官方岗位快照为在线 JD 不足时的兜底来源，要求标记 `local_snapshot` 和 `not_live_verified`。
- `backend/app/services/local_job_radar_cache.py` — 新增本地 `ai-job-radar` 缓存读取与匹配逻辑，读取 `data/jobs.json` 和最新 `data/daily/*.json`，按公司与方向筛选 JD 证据；多公司查询先保证目标公司覆盖，再按相关度补足。
- `backend/app/services/role_profile_service.py` — 在实时 JD 数不足目标公司数时补充本地缓存 JD，并输出 `local_job_radar_cache` 状态、质量统计和画像限制项。
- `backend/app/config.py`、`backend/.env.example` — 新增 `JOB_RADAR_CACHE_DIR` 和 `JOB_RADAR_CACHE_AUTO_DETECT`，默认不自动探测本机路径，避免测试和生产被隐式本地状态污染。
- `backend/tests/test_role_profile_service.py`、`backend/tests/conftest.py` — 增加阿里+字节、Kimi Eval 两个本地 JD 缓存兜底测试，并在测试配置中关闭自动探测。
- `docs/CHANGELOG.md`、`docs/RELEASE_NOTES.md` — 记录本次用户可感知与工程变更。

**验证结果**：
- `cd backend && python -m py_compile app\services\local_job_radar_cache.py app\services\role_profile_service.py app\config.py`：通过。
- `cd backend && python -m pytest tests\test_role_profile_service.py -v`：6 passed。

**风险与回退**：本地 JobRadar 证据是快照，不保证岗位仍在招；接口会标记 `local_snapshot` / `not_live_verified`，且置信度低于实时官网 JD。回退方式为清空 `JOB_RADAR_CACHE_DIR` 或关闭 `JOB_RADAR_CACHE_AUTO_DETECT`，也可移除 `LocalJobRadarCache` 接入并恢复上述文件。

---

## 2026-06-16 — 岗位画像即时生成 API

**问题现象**：项目已有 Feed 搜索和公司画像，但还没有从自然语言关键词直接生成“官网 JD + 面经证据”的岗位画像链路，无法验证“阿里+字节自动化测试工程师”或“Kimi 大模型 Eval 评测方向”的端到端输出。

**根因**：现有 API 只返回搜索结果列表或基于历史归档的公司画像，缺少关键词解析、JD/面经证据分流、低质面经过滤、技能权重和准备计划生成模块。

**修改文件**：
- `PRD.md` — 升级到 3.4，明确 `POST /api/role-profile/search` 为即时生成 MVP，持久化查询放到下一阶段。
- `backend/app/schemas/role_profile.py` — 新增岗位画像请求/响应结构。
- `backend/app/services/role_profile_service.py` — 新增关键词解析、Runtime 编排、JD/面经证据收集、质量门禁、启发式画像和可选 LLM 画像生成。
- `backend/app/api/routes_role_profile.py`、`backend/app/main.py` — 新增并注册 `/api/role-profile/search`。
- `backend/tests/test_role_profile_service.py` — 覆盖阿里+字节自动化测试、Kimi Eval 关键词解析，以及低价值帖子过滤和画像输出。

**验证结果**：
- `cd backend && python -m pytest tests/test_role_profile_service.py -q`：3 passed。

**风险与回退**：MVP 阶段不新增数据库表，不支持 `GET /api/role-profile/{session_id}` 历史回看；没有 LLM Key 时会返回启发式画像，质量低于真实 LLM 总结。回退方式为移除新路由、服务、schema 和对应测试，并恢复 `PRD.md` 3.4 条目。

---

## 2026-06-16 — 来源稳定性、Cookie 续期与小红书/牛客兜底

**问题现象**：平台 Cookie 过期、小红书 MCP/浏览器上下文关闭、牛客 API 空结果或抖动时，搜索容易出现单源失败且缺少明确恢复动作；牛客和小红书作为核心信息源缺少免费搜索兜底。

**根因**：Runtime 只记录简单 `status/reason`，没有统一的来源健康、冷却和下一步动作；脉脉 Cookie 只读 `.env` 静态值；牛客和小红书 Adapter 过度依赖各自主链路，没有把 SearXNG 作为 URL 发现兜底。

**修改文件**：
- `backend/app/runtime/source_health.py` — 新增 `SourceHealthRegistry`，统一 `nextAction`、`recoverable`、`failureCount`、`cooldownSeconds` 状态字段，并对超时/限流/普通错误做短冷却。
- `backend/app/runtime/source_auth.py` — 新增 `SourceAuthManager`，只从项目授权状态目录读取/更新 Cookie 或 Playwright `storage_state.json`，不读取用户浏览器资料。
- `backend/app/runtime/agent_runtime.py`、`backend/app/runtime/streaming_coordinator.py` — 接入来源健康状态，普通搜索和 SSE 搜索都输出结构化来源状态。
- `backend/app/main.py` — `/api/debug/sources` 使用同一套状态描述，配置错误显示可恢复动作。
- `backend/app/adapters/maimai.py` — Cookie 缺失或过期时从项目授权状态刷新并重试一次；成功响应中的 `Set-Cookie` 会合并并更新本地项目状态。
- `backend/app/adapters/nowcoder.py` — 牛客 API 空结果/异常时，通过免费 SearXNG `site:nowcoder.com` 做 URL 发现兜底，兜底项标记为 `snippet_only`。
- `backend/app/adapters/xiaohongshu.py` — MCP 缺失、连接失败、空结果或异常时，通过免费 SearXNG 发现公开笔记 URL；详情抓取失败会重置 MCP/浏览器连接并重试一次，兜底项标记为低置信 URL 摘要。
- `backend/app/config.py`、`backend/.env.example` — 新增 `MAIMAI_COOKIE_FILE`、`XHS_COOKIE_FILE`、`SOURCE_AUTH_STATE_DIR`、`SOURCE_AUTH_AUTO_REFRESH_ENABLED`。
- `backend/tests/test_source_health.py`、`backend/tests/test_source_auth.py`、`backend/tests/test_maimai_adapter.py`、`backend/tests/test_nowcoder_adapter.py`、`backend/tests/test_xiaohongshu_adapter.py`、`backend/tests/test_agent_runtime.py` — 增加来源健康、授权 Cookie 刷新、牛客兜底、小红书兜底和 Runtime 状态测试。

**验证结果**：
- `cd backend && python -m pytest tests/test_source_health.py tests/test_source_auth.py tests/test_maimai_adapter.py tests/test_nowcoder_adapter.py tests/test_xiaohongshu_adapter.py tests/test_agent_runtime.py tests/test_api_routes.py::test_debug_sources_reports_searxng_configuration -q`：13 passed。
- `cd backend && python -m pytest tests/ -v`：107 passed。

**风险与回退**：Cookie 自动刷新依赖用户先通过项目授权流程或手动文件提供有效会话状态；若状态文件不存在，仍返回 `config_error`/`unauthorized` 并给出 `login` 动作。小红书和牛客的 SearXNG 兜底只提供 URL/snippet，不能作为高置信真实问题证据。回退方式为移除 `SourceHealthRegistry`/`SourceAuthManager` 接入并恢复上述 Adapter 文件。

---

## 2026-06-15 — 新增公司官网 JD 来源

**问题现象**：搜索能力已能触达面经，但还不能稳定把公司官网 JD 作为一等来源，岗位画像缺少官方职责、任职要求和业务方向证据。

**根因**：现有 Adapter 仅覆盖牛客、脉脉、小红书和通用搜索引擎，未注册官方招聘站来源，也没有对官方域名和第三方搬运 JD 做区分。

**修改文件**：
- `backend/app/adapters/official_job.py` — 新增 `official_job` 适配器，通过 SearXNG 发现字节、阿里/千问/夸克、Kimi/月之暗面官方招聘页，并过滤非官方域名结果。
- `backend/app/adapters/__init__.py` — 注册 `OfficialJobAdapter`。
- `backend/app/config.py`、`backend/.env.example` — 新增 `OFFICIAL_JOB_ENABLED`。
- `backend/app/main.py` — `/api/debug/sources` 新增 `official_job` 诊断。
- `backend/app/runtime/ranker.py` — 增加 `official_job` 来源可信度和 JD 关键词内容丰富度。
- `backend/tests/test_official_job_adapter.py`、`backend/tests/test_config.py`、`backend/tests/test_api_routes.py`、`backend/tests/test_ranker.py` — 增加官方 JD 来源、诊断和排序测试。
- `frontend/src/lib/format.ts`、`frontend/src/components/source-status.tsx`、`frontend/src/components/feed-card.tsx` — 将 `official_job` 展示为"官网 JD"，使用已有 Briefcase 图标。

**验证结果**：
- `cd backend && python -m pytest tests/ -v`：96 passed。
- `cd frontend && npx tsc --noEmit`：通过。

**风险与回退**：依赖 SearXNG 可用性和官方站点搜索可发现性；若官方招聘站改版或 SearXNG 未启用 JSON，该来源会返回结构化 `config_error`/`empty`，不影响其他来源。回退方式为移除 `official_job` 注册并恢复上述文件。

---

## 2026-06-15 — 搜索引擎切换为免费 SearXNG

**问题现象**：搜索引擎来源依赖 SerpAPI，缺少 `SEARCH_API_KEY` 时 `/api/debug/sources` 报 `config_error`，不满足只使用免费搜索能力的要求。

**根因**：`SearchEngineAdapter` 直接请求 `https://serpapi.com/search`，配置和诊断接口都围绕付费 API Key 设计。

**修改文件**：
- `backend/app/adapters/search_engine.py` — 改为请求自托管 SearXNG `/search?format=json`，移除 SerpAPI 调用和 `api_key` 参数，补充 403 JSON 未启用、超时、限流、空结果等结构化状态。
- `backend/app/config.py` — 默认搜索 provider 改为 `searxng`，新增 `searxng_base_url`、`searxng_language`、`searxng_safe_search`。
- `backend/app/main.py` — `/api/debug/sources` 改为诊断 SearXNG provider/baseUrl 配置。
- `backend/.env.example` — 搜索引擎示例改为 SearXNG JSON API 配置。
- `backend/tests/test_search_engine_adapter.py` — 新增 SearXNG 成功、缺配置、拒绝非免费 provider、JSON 未启用、超时测试。
- `backend/tests/test_config.py`、`backend/tests/test_api_routes.py`、`backend/tests/conftest.py` — 同步配置和诊断断言。

**验证结果**：
- `python -m pytest backend/tests/test_config.py backend/tests/test_search_engine_adapter.py backend/tests/test_api_routes.py::test_debug_sources_reports_searxng_configuration -q`：9 passed。
- `cd backend && python -m pytest tests/ -v`：90 passed。

**风险与回退**：需要本地或部署环境提供 SearXNG 并启用 `search.formats=json`。如需回退，恢复上述文件即可重新使用旧 SerpAPI 适配器；但该回退不符合当前"只用免费搜索"产品要求。

---

## 2026-06-15 — 岗位画像雷达 PRD 规划

**问题现象**：现有产品规划主要围绕面经搜索，搜索引擎仍写成 SerpAPI，无法满足"只用免费搜索能力"、"搜索触达 JD"、"Cookie 过期可恢复"、"小红书和牛客稳定作为重要来源"的目标。

**根因**：PRD 中没有把官网 JD 作为一等证据源，也没有定义岗位画像的数据结构、双轨查询流程、授权会话刷新边界和 SearXNG 免费搜索方案。

**修改文件**：
- `PRD.md` — 升级到 3.3，新增 JD + 面经岗位画像模块、免费 SearXNG 搜索方案、SourceAuth/SourceHealth 规划、RoleProfile API 规划、验收样例和风险对策。

**验证结果**：文档变更，无代码改动；已通过文本检查确认 PRD 中不再把 SerpAPI 作为目标搜索引擎配置，新增岗位画像、SearXNG、授权会话、小红书稳定策略和牛客核心源描述。

**风险与回退**：低风险，仅影响产品与工程规划。回退方式为恢复 `PRD.md` 和本 Changelog 条目到变更前版本。

---

## 2026-06-12 — 文档体系重构

**改动内容**：整理 AI 开发规范文档体系，明确职责边界、减少重复、新增工程流程文档。

**修改文件**：
- `PRD.md` — 移出 AI 工具协作规则（11.1 节），修正 SSE 事件顺序，统一 API camelCase，修正 Cookie 边界
- `AGENTS.md` — 增加任务分级、开发许可规则、批量修改保护、重复检测、Adapter 容错、依赖变更声明、数据库备份、LLM 测试、CHANGELOG 规则、影响范围声明、代码删除规则、函数注释规则
- `CLAUDE.md` — 瘦身为 Claude Code 入口索引，删除重复规则
- `docs/engineering/ai-agent-workflow.md` — 新增，从 PRD 11.1 迁出
- `docs/engineering/release-checklist.md` — 新增
- `docs/engineering/security-checklist.md` — 新增
- `docs/engineering/validation-matrix.md` — 新增
- `docs/METHODOLOGY.md` — 新增
- `docs/CHANGELOG.md` — 新增（本文件）
- `docs/RELEASE_NOTES.md` — 新增
- `docs/adr/ADR-0001-remove-local-ai-hooks.md` — 新增
- `.cursor/rules/001-core.mdc` — 新增，替换 000-project.mdc
- `.cursor/rules/002-frontend.mdc` — 新增，替换 100-frontend.mdc
- `.cursor/rules/003-security.mdc` — 新增

**验证结果**：文档变更，无代码改动，无需运行测试。

**风险与回退**：低风险。如需回退，`git checkout` 恢复原文件即可。

---

## 历史变更

历史变更记录在各文件的变更记录表格中：
- `PRD.md` 变更记录（2026-06-06 至 2026-06-12）
- `AGENTS.md` 变更记录（2026-06-08 至 2026-06-12）
- `CLAUDE.md` 变更记录（2026-06-06 至 2026-06-12）
