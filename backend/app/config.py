from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    # 搜索引擎
    search_api_provider: str = "serpapi"
    search_api_key: str = ""
    search_results_per_query: int = 10

    # 平台开关
    nowcoder_enabled: bool = True
    maimai_enabled: bool = True
    xhs_enabled: bool = True

    # 平台 Cookie
    xhs_cookie: str = ""
    maimai_cookie: str = ""

    # 小红书 MCP Server 可执行路径（空字符串时使用默认路径）
    xhs_mcp_command: str = ""

    # 超时（秒）
    search_timeout_platform: int = 60
    search_timeout_search_engine: int = 12
    webfetch_timeout: int = 30
    webfetch_max_urls: int = 10

    # 排序与筛选
    ranking_top_n: int = 15
    max_content_age_days: int = 180  # 超过此天数的内容直接过滤（默认 6 个月）

    # 缓存
    feed_cache_ttl_hours: int = 24
    feed_cache_max_age_days: int = 30

    # LLM
    llm_api_base: str = "http://ai-gateway.wps.cn/api/v3"
    llm_api_key: str = ""
    llm_model: str = "deepseek/deepseek-v4-flash"
    llm_gateway_uid: str = ""
    llm_gateway_product: str = ""
    llm_gateway_intention: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./offergraph.db"

    # 服务器
    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()
