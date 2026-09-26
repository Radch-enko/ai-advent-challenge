from pydantic import BaseModel


class McpToolResult(BaseModel):
    call_id: str
    name: str
    content: str
    is_error: bool = False
