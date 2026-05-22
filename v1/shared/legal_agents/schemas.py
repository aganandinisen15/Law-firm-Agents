from typing import Any, Optional, List, Dict
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    agent: str


class GenericAgentRequest(BaseModel):
    correlation_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GenericAgentResponse(BaseModel):
    agent: str
    status: str
    summary: str
    data: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
