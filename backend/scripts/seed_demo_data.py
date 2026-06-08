"""
演示数据生成脚本 - 生成真实面经数据用于验证流程。

使用公司 LLM API 生成结构化面经内容，写入数据库。
运行: cd backend && python -m scripts.seed_demo_data
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta
import random
import sys

sys.path.insert(0, ".")

from app.config import settings
from app.database import engine, async_session, Base
from app.models.source_document import SourceDocumentModel
from app.models.interview_event import InterviewEvent
from app.models.question import InterviewQuestion
from app.models.evidence import QuestionEvidence
from app.models.search_session import SearchSession
from app.models.tool_run import ToolRun
import app.models  # noqa: ensure all tables registered


DEMO_INTERVIEWS = [
    {
        "source": "nowcoder",
        "title": "字节跳动后端开发二面面经（2026春招）",
        "source_url": "https://www.nowcoder.com/discuss/12345",
        "full_text": """字节跳动后端开发二面面经分享

面试时间：2026年5月15日
岗位：后端开发工程师
轮次：二面（技术面）
面试官：组内 TL

一上来先自我介绍，然后直接问项目。

1. 说一下你做的分布式缓存系统的架构？为什么选择 Redis Cluster 而不是 Codis？
追问：如果某个节点挂了，你的系统怎么处理？自动故障转移的延迟是多少？

2. Redis 和 MySQL 数据一致性怎么保证？用的什么方案？
追问：延迟双删的时间窗口怎么设置的？为什么是 500ms？如果删除失败了呢？

3. 讲一下你理解的分布式锁，有哪些实现方式？Redlock 算法了解吗？
追问：Redlock 有什么争议？Martin Kleppmann 的批评点是什么？

4. 设计题：设计一个支持百万 QPS 的短链服务。要考虑存储、缓存、高可用。
追问：如何防止恶意刷短链？限流方案？

5. 算法题：给你一个无序数组，找出最长连续序列的长度。要求 O(n) 时间复杂度。

整体感觉面试官很专业，问题由浅入深，对项目细节追问很多。建议准备好项目中每个技术决策的原因。
难度 4/5，时长约 60 分钟。""",
        "company": "字节跳动",
        "position": "后端开发",
        "candidate_type": "social",
        "round": "二面",
        "region": "北京",
        "difficulty": 4,
        "questions": [
            {
                "text": "说一下你做的分布式缓存系统的架构？为什么选择 Redis Cluster 而不是 Codis？",
                "category": "project",
                "difficulty": 3,
                "tags": ["Redis", "分布式", "架构"],
                "source_type": "real_interview",
                "evidence_quote": "说一下你做的分布式缓存系统的架构？为什么选择 Redis Cluster 而不是 Codis？",
                "followups": ["如果某个节点挂了，你的系统怎么处理？", "自动故障转移的延迟是多少？"],
            },
            {
                "text": "Redis 和 MySQL 数据一致性怎么保证？",
                "category": "fundamentals",
                "difficulty": 4,
                "tags": ["Redis", "MySQL", "一致性"],
                "source_type": "real_interview",
                "evidence_quote": "Redis 和 MySQL 数据一致性怎么保证？用的什么方案？",
                "followups": ["延迟双删的时间窗口怎么设置的？", "如果删除失败了呢？"],
            },
            {
                "text": "讲一下你理解的分布式锁，有哪些实现方式？Redlock 算法了解吗？",
                "category": "fundamentals",
                "difficulty": 4,
                "tags": ["分布式锁", "Redlock", "Redis"],
                "source_type": "real_interview",
                "evidence_quote": "讲一下你理解的分布式锁，有哪些实现方式？Redlock 算法了解吗？",
                "followups": ["Redlock 有什么争议？", "Martin Kleppmann 的批评点是什么？"],
            },
            {
                "text": "设计一个支持百万 QPS 的短链服务",
                "category": "system_design",
                "difficulty": 5,
                "tags": ["系统设计", "高并发", "短链"],
                "source_type": "real_interview",
                "evidence_quote": "设计一个支持百万 QPS 的短链服务。要考虑存储、缓存、高可用。",
                "followups": ["如何防止恶意刷短链？", "限流方案？"],
            },
            {
                "text": "给你一个无序数组，找出最长连续序列的长度",
                "category": "algorithm",
                "difficulty": 3,
                "tags": ["算法", "哈希表", "数组"],
                "source_type": "real_interview",
                "evidence_quote": "给你一个无序数组，找出最长连续序列的长度。要求 O(n) 时间复杂度。",
                "followups": [],
            },
        ],
    },
    {
        "source": "nowcoder",
        "title": "美团后端一面面经（Go方向）",
        "source_url": "https://www.nowcoder.com/discuss/23456",
        "full_text": """美团后端一面面经 - Go 方向

面试时间：2026年5月20日
岗位：后端开发（Go）
轮次：一面
地点：线上

1. Go 的 GMP 调度模型讲一下？G、M、P 分别是什么？
追问：当一个 Goroutine 阻塞在 syscall 上时，调度器怎么处理？

2. Go 的 Channel 底层是怎么实现的？有缓冲和无缓冲的区别？
追问：向一个已关闭的 channel 发送数据会怎样？

3. MySQL 的 MVCC 机制讲一下？Read View 是什么时候创建的？
追问：RR 和 RC 隔离级别下 Read View 创建时机有什么不同？

4. 微服务之间的通信方式有哪些？gRPC 和 HTTP 的区别？
追问：gRPC 的流式通信在什么场景下用？美团的 Thrift 了解吗？

5. 场景题：设计一个订单超时取消系统。要求高可用、精准触发。
追问：如果用延迟队列，消息积压了怎么办？

总结：一面偏基础，Go 语言和数据库考得多。建议把 GMP、Channel、GC 这些高频题准备好。
难度 3/5。""",
        "company": "美团",
        "position": "后端开发(Go)",
        "candidate_type": "social",
        "round": "一面",
        "region": "北京",
        "difficulty": 3,
        "questions": [
            {
                "text": "Go 的 GMP 调度模型讲一下？G、M、P 分别是什么？",
                "category": "fundamentals",
                "difficulty": 3,
                "tags": ["Go", "GMP", "调度"],
                "source_type": "real_interview",
                "evidence_quote": "Go 的 GMP 调度模型讲一下？G、M、P 分别是什么？",
                "followups": ["当一个 Goroutine 阻塞在 syscall 上时，调度器怎么处理？"],
            },
            {
                "text": "Go 的 Channel 底层是怎么实现的？",
                "category": "fundamentals",
                "difficulty": 3,
                "tags": ["Go", "Channel", "并发"],
                "source_type": "real_interview",
                "evidence_quote": "Go 的 Channel 底层是怎么实现的？有缓冲和无缓冲的区别？",
                "followups": ["向一个已关闭的 channel 发送数据会怎样？"],
            },
            {
                "text": "MySQL 的 MVCC 机制讲一下？",
                "category": "fundamentals",
                "difficulty": 4,
                "tags": ["MySQL", "MVCC", "事务"],
                "source_type": "real_interview",
                "evidence_quote": "MySQL 的 MVCC 机制讲一下？Read View 是什么时候创建的？",
                "followups": ["RR 和 RC 隔离级别下 Read View 创建时机有什么不同？"],
            },
            {
                "text": "设计一个订单超时取消系统",
                "category": "system_design",
                "difficulty": 4,
                "tags": ["系统设计", "延迟队列", "订单"],
                "source_type": "real_interview",
                "evidence_quote": "设计一个订单超时取消系统。要求高可用、精准触发。",
                "followups": ["如果用延迟队列，消息积压了怎么办？"],
            },
        ],
    },
    {
        "source": "maimai",
        "title": "阿里云后端三面（交叉面）分享",
        "source_url": "https://maimai.cn/article/detail?fid=34567",
        "full_text": """阿里云后端开发三面面经

这是交叉面，面试官是另一个部门的 P8。

面试时间：2026年4月28日
岗位：后端开发 P6
轮次：三面（交叉面）

1. 介绍一个你做过的最有技术挑战的项目？遇到了什么困难？怎么解决的？
追问：如果让你重新做这个项目，你会怎么改进架构？

2. 分布式事务了解哪些方案？TCC、Saga、本地消息表、事务消息各有什么优缺点？
追问：在你的项目中用了哪个？为什么？有没有遇到过分布式事务失败的情况？

3. 高并发场景下，如何设计一个秒杀系统？从前端到后端到数据库各层怎么做？
追问：库存扣减用乐观锁还是悲观锁？为什么？Redis 预扣减怎么和数据库最终一致？

4. 你怎么看待微服务拆分的粒度？什么时候应该拆？什么时候不应该拆？
追问：你们现在的服务是不是太细了？有没有考虑合并？

5. 对阿里云有什么了解？想做什么方向？有什么职业规划？

总体感觉交叉面更侧重架构思维和技术判断力，不太抠细节。
难度 4/5，时长约 45 分钟。""",
        "company": "阿里云",
        "position": "后端开发",
        "candidate_type": "social",
        "round": "三面",
        "region": "杭州",
        "difficulty": 4,
        "questions": [
            {
                "text": "介绍一个你做过的最有技术挑战的项目",
                "category": "project",
                "difficulty": 3,
                "tags": ["项目", "架构"],
                "source_type": "real_interview",
                "evidence_quote": "介绍一个你做过的最有技术挑战的项目？遇到了什么困难？怎么解决的？",
                "followups": ["如果让你重新做这个项目，你会怎么改进架构？"],
            },
            {
                "text": "分布式事务了解哪些方案？TCC、Saga、本地消息表各有什么优缺点？",
                "category": "fundamentals",
                "difficulty": 4,
                "tags": ["分布式事务", "TCC", "Saga"],
                "source_type": "real_interview",
                "evidence_quote": "分布式事务了解哪些方案？TCC、Saga、本地消息表、事务消息各有什么优缺点？",
                "followups": ["在你的项目中用了哪个？为什么？"],
            },
            {
                "text": "高并发场景下，如何设计一个秒杀系统？",
                "category": "system_design",
                "difficulty": 5,
                "tags": ["秒杀", "高并发", "系统设计"],
                "source_type": "real_interview",
                "evidence_quote": "高并发场景下，如何设计一个秒杀系统？从前端到后端到数据库各层怎么做？",
                "followups": ["库存扣减用乐观锁还是悲观锁？", "Redis 预扣减怎么和数据库最终一致？"],
            },
            {
                "text": "你怎么看待微服务拆分的粒度？",
                "category": "system_design",
                "difficulty": 4,
                "tags": ["微服务", "架构设计"],
                "source_type": "real_interview",
                "evidence_quote": "你怎么看待微服务拆分的粒度？什么时候应该拆？什么时候不应该拆？",
                "followups": ["你们现在的服务是不是太细了？有没有考虑合并？"],
            },
        ],
    },
    {
        "source": "search_engine",
        "title": "腾讯 WXG 后端面试经历总结",
        "source_url": "https://www.cnblogs.com/dev/wxg-interview-2026.html",
        "full_text": """腾讯微信事业群后端面试经历

时间线：2026年3月投递，4月一面，4月二面
岗位：后端开发
部门：微信支付

一面（基础+项目）：
1. TCP 三次握手为什么不能是两次？四次挥手中的 TIME_WAIT 状态的作用？
2. HTTP/2 对比 HTTP/1.1 有什么改进？多路复用是怎么实现的？
3. 进程和线程的区别？协程呢？Go 的 goroutine 和 Java 的虚拟线程有什么不同？
4. 数据库索引的底层数据结构？为什么用 B+ 树而不是 B 树或跳表？
5. 项目里的消息队列用的什么？Kafka 的消息怎么保证不丢失？

二面（设计+深度）：
1. 设计一个分布式 ID 生成系统，要求全局唯一、趋势递增、高可用。
2. 微信红包的随机算法你怎么设计？要保证公平性。
3. 如何设计一个支持亿级用户的推送系统？长连接怎么维护？

总结：WXG 面试风格偏向底层原理和系统设计，对网络和操作系统基础要求较高。
一面难度 3/5，二面难度 4/5。""",
        "company": "腾讯",
        "position": "后端开发",
        "candidate_type": "social",
        "round": "一面+二面",
        "region": "深圳",
        "difficulty": 4,
        "questions": [
            {
                "text": "TCP 三次握手为什么不能是两次？",
                "category": "fundamentals",
                "difficulty": 2,
                "tags": ["网络", "TCP"],
                "source_type": "real_interview",
                "evidence_quote": "TCP 三次握手为什么不能是两次？四次挥手中的 TIME_WAIT 状态的作用？",
                "followups": [],
            },
            {
                "text": "数据库索引的底层数据结构？为什么用 B+ 树而不是 B 树或跳表？",
                "category": "fundamentals",
                "difficulty": 3,
                "tags": ["数据库", "索引", "B+树"],
                "source_type": "real_interview",
                "evidence_quote": "数据库索引的底层数据结构？为什么用 B+ 树而不是 B 树或跳表？",
                "followups": [],
            },
            {
                "text": "设计一个分布式 ID 生成系统",
                "category": "system_design",
                "difficulty": 4,
                "tags": ["分布式ID", "系统设计"],
                "source_type": "real_interview",
                "evidence_quote": "设计一个分布式 ID 生成系统，要求全局唯一、趋势递增、高可用。",
                "followups": [],
            },
            {
                "text": "如何设计一个支持亿级用户的推送系统？",
                "category": "system_design",
                "difficulty": 5,
                "tags": ["推送系统", "长连接", "高并发"],
                "source_type": "real_interview",
                "evidence_quote": "如何设计一个支持亿级用户的推送系统？长连接怎么维护？",
                "followups": [],
            },
        ],
    },
    {
        "source": "nowcoder",
        "title": "字节跳动前端面经（React方向）",
        "source_url": "https://www.nowcoder.com/discuss/45678",
        "full_text": """字节跳动前端开发面经

岗位：前端开发工程师
时间：2026年5月底
轮次：一面+二面

一面：
1. React 的 Fiber 架构是什么？为什么要从 Stack 架构改为 Fiber？
追问：时间切片是怎么实现的？requestIdleCallback 了解吗？

2. useEffect 和 useLayoutEffect 的区别？什么时候用 useLayoutEffect？
追问：useEffect 的清理函数是在什么时机执行的？

3. Webpack 的 Tree Shaking 原理是什么？为什么只能用于 ES Module？
追问：如何判断一个模块有没有副作用？sideEffects 配置怎么用？

4. 跨域问题怎么解决？CORS 的预检请求是什么？
5. 手写一个 Promise.all 的实现。

二面：
1. 设计一个前端监控系统，包括错误监控、性能监控、用户行为监控。
2. 大文件上传方案？断点续传怎么实现？

总结：字节前端考察 React 底层原理比较多，建议深入研究 Fiber 和 Hooks 实现。""",
        "company": "字节跳动",
        "position": "前端开发",
        "candidate_type": "social",
        "round": "一面+二面",
        "region": "北京",
        "difficulty": 4,
        "questions": [
            {
                "text": "React 的 Fiber 架构是什么？",
                "category": "fundamentals",
                "difficulty": 4,
                "tags": ["React", "Fiber", "前端"],
                "source_type": "real_interview",
                "evidence_quote": "React 的 Fiber 架构是什么？为什么要从 Stack 架构改为 Fiber？",
                "followups": ["时间切片是怎么实现的？"],
            },
            {
                "text": "设计一个前端监控系统",
                "category": "system_design",
                "difficulty": 4,
                "tags": ["监控", "系统设计", "前端"],
                "source_type": "real_interview",
                "evidence_quote": "设计一个前端监控系统，包括错误监控、性能监控、用户行为监控。",
                "followups": [],
            },
        ],
    },
]


async def seed_data():
    """生成演示数据"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print(f"正在生成 {len(DEMO_INTERVIEWS)} 条演示面经数据...")

    async with async_session() as db:
        for idx, interview in enumerate(DEMO_INTERVIEWS):
            doc_id = str(uuid.uuid4())
            now = datetime.utcnow()

            # 创建 source_document
            source_doc = SourceDocumentModel(
                id=doc_id,
                source=interview["source"],
                source_url=interview["source_url"],
                title=interview["title"],
                snippet=interview["full_text"][:200],
                full_text=interview["full_text"],
                content_hash=str(uuid.uuid4())[:16],
                fetched_at=now - timedelta(days=random.randint(1, 30)),
                fetch_policy="public_fetch_allowed",
                extraction_status="extracted",
                extraction_confidence=0.9,
            )
            db.add(source_doc)

            # 创建 interview_event
            event_id = str(uuid.uuid4())
            event = InterviewEvent(
                id=event_id,
                source_document_id=doc_id,
                company=interview["company"],
                position=interview["position"],
                candidate_type=interview["candidate_type"],
                round=interview["round"],
                region=interview["region"],
                summary=interview["title"],
                difficulty=interview["difficulty"],
                tags_json=json.dumps(
                    [q["tags"][0] for q in interview["questions"] if q.get("tags")],
                    ensure_ascii=False,
                ),
                evidence_coverage=0.85,
            )
            db.add(event)

            # 创建 questions + evidence
            for q_data in interview["questions"]:
                q_id = str(uuid.uuid4())
                question = InterviewQuestion(
                    id=q_id,
                    interview_event_id=event_id,
                    question_text=q_data["text"],
                    normalized_question=q_data["text"],
                    category=q_data["category"],
                    difficulty=q_data["difficulty"],
                    tags_json=json.dumps(q_data.get("tags", []), ensure_ascii=False),
                    followups_json=json.dumps(q_data.get("followups", []), ensure_ascii=False),
                    source_type=q_data["source_type"],
                    confidence=0.9,
                )
                db.add(question)

                # 证据
                if q_data.get("evidence_quote"):
                    start_offset = interview["full_text"].find(q_data["evidence_quote"])
                    evidence = QuestionEvidence(
                        id=str(uuid.uuid4()),
                        question_id=q_id,
                        source_document_id=doc_id,
                        quote=q_data["evidence_quote"],
                        start_offset=start_offset if start_offset >= 0 else None,
                        end_offset=(start_offset + len(q_data["evidence_quote"])) if start_offset >= 0 else None,
                        confidence=0.9,
                    )
                    db.add(evidence)

            print(f"  [{idx+1}/{len(DEMO_INTERVIEWS)}] {interview['title']}")

        # 创建一个示例 SearchSession
        session_id = str(uuid.uuid4())
        session = SearchSession(
            id=session_id,
            user_id="demo_user",
            profile_snapshot_json=json.dumps({
                "identity": "working_switch",
                "directions": ["后端开发"],
                "targetCompanies": ["字节跳动", "美团", "阿里云", "腾讯"],
                "regions": ["北京", "杭州", "深圳"],
            }, ensure_ascii=False),
            status="success",
            query_plan_json=json.dumps({"queries": [{"query": "字节跳动 后端 面经"}]}, ensure_ascii=False),
            source_status_json=json.dumps({"nowcoder": "ok", "search_engine": "ok", "maimai": "ok"}, ensure_ascii=False),
            total_count=len(DEMO_INTERVIEWS),
            fresh_count=len(DEMO_INTERVIEWS),
            search_duration_ms=3200,
            quality_report_json=json.dumps({"fetchedCount": 5, "evidenceCoverageAvg": 0.85}, ensure_ascii=False),
        )
        db.add(session)

        await db.commit()
        print(f"\n演示数据生成完毕！共 {len(DEMO_INTERVIEWS)} 条面经、"
              f"{sum(len(i['questions']) for i in DEMO_INTERVIEWS)} 个问题。")
        print(f"数据库文件: {settings.database_url}")


if __name__ == "__main__":
    asyncio.run(seed_data())
