from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel


class ToolContext(BaseModel):
    """运行时上下文，传递给每个 Tool 执行"""
    session_id: str
    user_id: Optional[str] = None
    profile_id: Optional[str] = None
    timeout_sec: Optional[int] = None


class ToolResult(BaseModel):
    """Tool 执行结果的统一格式"""
    status: str  # success / timeout / error / skipped
    data: Any = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = {}


class BaseTool(ABC):
    """所有 Tool 的基类，子类必须实现 run 方法"""
    name: str
    tool_type: str  # search / fetch / extract / verify / rank

    @abstractmethod
    async def run(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        pass
