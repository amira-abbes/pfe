from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BadDebtsHealthResponse(BaseModel):
    status: str
    module: str
    storage: str
    schema_: str = Field(alias="schema")


class BadDebtClientItem(BaseModel):
    msisdn: str
    state: str | None = None
    cluster_id: int | None = None
    cluster_name: str | None = None
    risk_level: int | None = None
    risk_label: str | None = None
    risk_tier: str | None = None
    final_risk_score: float | None = None
    risk_score_raw: float | None = None
    is_anomaly: bool | None = None
    anomaly_score: float | None = None
    top_drivers: Any = None
    avg_credit_amount: float | None = None
    avg_reimburse_ratio: float | None = None
    avg_days_since_credit: float | None = None
    total_outstanding_amount: float | None = None
    nb_sos: int | None = None
    debt_to_credit: float | None = None
    credit_intensity: float | None = None
    tenure_days: float | None = None
    has_debt: int | None = None
    uses_sos: int | None = None
    never_repaid: int | None = None
    full_repayer: int | None = None
    is_dormant_like: int | None = None
    imported_at: datetime | None = None


class BadDebtClientDetail(BadDebtClientItem):
    actions: list[dict[str, Any]] = Field(default_factory=list)


class BadDebtClientsPage(BaseModel):
    items: list[BadDebtClientItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class ImportRunItem(BaseModel):
    id: int
    file_name: str
    rows_imported: int | None = None
    status: str
    error_message: str | None = None
    imported_at: datetime | None = None


class BadDebtsSummary(BaseModel):
    date: str
    total_clients: int
    at_risk_count: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    anomaly_count: int
    avg_final_risk_score: float | None = None
    max_final_risk_score: float | None = None
    latest_import_at: datetime | None = None
    by_tier: dict[str, int]
    by_cluster_name: dict[str, int]
    latest_import: ImportRunItem | None = None


class N8nSummary(BaseModel):
    date: str
    at_risk_count: int
    messages_sent: int
    anomaly_count: int
    total_clients_scored: int
    by_tier: dict[str, int]
    by_cluster_name: dict[str, int]


class N8nAtRiskClientItem(BaseModel):
    msisdn: str
    risk_tier: str | None = None
    final_risk_score: float | None = None
    risk_label: str | None = None
    cluster_name: str | None = None
    is_anomaly: bool | None = None


class N8nAtRiskClientsPage(BaseModel):
    items: list[N8nAtRiskClientItem]
    total: int
    page: int
    page_size: int


class BadDebtsAgentResponse(BaseModel):
    run_id: str
    msisdn: str
    profile: dict[str, Any]
    explanations: dict[str, Any]
    decision: dict[str, Any]
    message: dict[str, Any]
    errors: list[str] = Field(default_factory=list)


class AgentActionItem(BaseModel):
    id: int
    msisdn: str
    action_type: str
    priority: int
    recommendation: str | None = None
    status: str
    created_at: datetime | None = None
