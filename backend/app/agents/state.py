from __future__ import annotations

from typing import Annotated, Any, TypedDict
import operator
from datetime import datetime


class AgentState(TypedDict, total=False):
    msisdn: str
    features: dict[str, float]
    ml_outputs: dict[str, Any]
    db: Any
    client: dict[str, Any] | Any
    client_found: bool
    enable_llm: bool
    raw_client: Any
    persisted: bool

    profile: dict[str, Any]
    explanations: dict[str, Any]
    decision: dict[str, Any]
    message: dict[str, Any] | None

    action_id: int | None
    agent_run_id: int | None
    report_id: int | None

    run_id: str
    started_at: datetime
    errors: Annotated[list[str], operator.add]
