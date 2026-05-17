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
    recommended_action: str | None = None
    recommended_action_label: str | None = None
    priority: int | None = None
    priority_label: str | None = None
    next_best_action: str | None = None
    raw_risk_tier: str | None = None
    effective_tier: str | None = None
    anomaly_escalated: bool | None = None


class BadDebtClientDetail(BadDebtClientItem):
    actions: list[dict[str, Any]] = Field(default_factory=list)


class BadDebtFilterOption(BaseModel):
    value: str
    label: str
    count: int


class BadDebtFilterOptions(BaseModel):
    recommended_actions: list[BadDebtFilterOption] = Field(default_factory=list)


class BadDebtClientsSummary(BaseModel):
    total_clients: int = 0
    high_risk_count: int = 0
    average_score: float | None = None
    average_reimburse_ratio: float | None = None
    priority_actions_count: int = 0


class BadDebtClientsPage(BaseModel):
    items: list[BadDebtClientItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    filter_options: BadDebtFilterOptions = Field(default_factory=BadDebtFilterOptions)
    summary: BadDebtClientsSummary = Field(default_factory=BadDebtClientsSummary)


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


class BadDebtsAgentResponse(BaseModel):
    run_id: str
    action_id: int | None = None
    agent_run_id: int | None = None
    msisdn: str
    profile: dict[str, Any]
    explanations: dict[str, Any]
    decision: dict[str, Any]
    message: dict[str, Any]
    ai_analysis: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    reused_existing_analysis: bool = False


class BadDebtsClientLocalReport(BaseModel):
    title: str
    case_reading: str
    signals_interpretation: str
    operational_risk: str
    verification_points: list[str] = Field(default_factory=list)
    argued_recommendation: str
    sms_proposal: str | None = None
    manager_summary: str
    confidence: str


class BadDebtsClientReportResponse(BaseModel):
    msisdn: str
    report: BadDebtsClientLocalReport
    report_source: str
    decision_locked: bool = True


class GlobalReportFilters(BaseModel):
    risk_tier: str | None = None
    cluster_name: str | None = None
    is_anomaly: bool | None = None
    recommended_action: str | None = None
    search: str | None = None


class GlobalReportKpiItem(BaseModel):
    label: str
    value: str
    comment: str = ""


class DecisionSupportItem(BaseModel):
    priority: str
    target: str
    business_goal: str
    recommended_focus: str


class BusinessRecommendationItem(BaseModel):
    title: str
    why: str
    example: str
    expected_impact: str


class GlobalReportContent(BaseModel):
    report_title: str
    executive_summary: str
    risk_reading: str
    key_kpis: list[GlobalReportKpiItem] = Field(default_factory=list)
    business_rationale: list[str] = Field(default_factory=list)
    decision_support: list[DecisionSupportItem] = Field(default_factory=list)
    main_findings: list[str] = Field(default_factory=list)
    business_recommendations: list[str | BusinessRecommendationItem] = Field(default_factory=list)
    decision_limits: str = ""
    internal_note: str = ""


class GlobalReportKpis(BaseModel):
    total_clients: int = 0
    clients_high: int = 0
    clients_medium: int = 0
    clients_low: int = 0
    clients_with_anomaly: int = 0
    average_risk_score: float | None = None
    average_debt: float | None = None
    average_reimbursement_ratio: float | None = None
    dominant_segment: str | None = None
    dominant_recommended_action: str | None = None
    distribution_by_segment: dict[str, int] = Field(default_factory=dict)
    distribution_by_risk: dict[str, int] = Field(default_factory=dict)
    distribution_by_action: dict[str, int] = Field(default_factory=dict)
    filter_summary: str = ""


class BadDebtsGlobalReportResponse(BaseModel):
    scope: str
    filters: dict[str, Any]
    kpis: GlobalReportKpis
    report: GlobalReportContent
    report_source: str
    decision_locked: bool = True
    generated_at: str
