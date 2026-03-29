from typing import Any, Optional

from pydantic import BaseModel


class ApiResponse(BaseModel):
    success: bool = True
    message: str = "ok"
    data: Optional[Any] = None

