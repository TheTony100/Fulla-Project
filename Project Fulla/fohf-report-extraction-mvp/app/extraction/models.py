from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractedField:
    field_name: str
    extracted_value: str
    source_pdf_filename: str
    source_page: int
    snippet: str
    confidence: float
    review_status: str  # ok | needs_review
    source_table: str = ""
    source_section_name: str = ""
    matched_row_label: str = ""
    matched_column_label: str = ""


@dataclass
class ExtractionException:
    field_name: str
    exception_type: str
    message: str
    source_pdf_filename: str
    review_status: str = "needs_review"


@dataclass
class ExtractionPipelineResult:
    fields: list[ExtractedField] = field(default_factory=list)
    exceptions: list[ExtractionException] = field(default_factory=list)
    audit_records: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class PerformanceTimelinePoint:
    period_year: int
    period_month: int
    period_label: str
    return_value: str
    return_pct: float | None
    source_pdf_filename: str
    source_page: int
    snippet: str
    confidence: float
    review_status: str
    source_table: str = ""
    source_section_name: str = ""
    matched_row_label: str = ""
    matched_column_label: str = ""


@dataclass(frozen=True)
class ProjectDocument:
    id: int
    project_id: int
    filename: str
    path: str
    document_type: str
    upload_time: str
    status: str
    error_message: str | None
    report_period: str


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    manager_name: str
    created_at: str
    updated_at: str


@dataclass
class GroupedValue:
    label: str
    value: str
    report_period: str
    report_quarter: str
    source_pdf: str
    source_page: int
    snippet: str
    confidence: float
    review_status: str
    field_name: str
    category: str


@dataclass
class ProjectKpis:
    latest_aum: str
    latest_aum_period: str
    latest_monthly_return: str
    latest_monthly_period: str
    total_extracted_metrics: int
    review_issues: int


@dataclass
class ReviewQueueItem:
    issue_type: str
    metric: str
    value: str
    source_pdf: str
    details: str


@dataclass
class ProjectAnalysisView:
    project_id: int
    project_name: str
    performance: list[GroupedValue]
    exposure: list[GroupedValue]
    aum_history: list[GroupedValue]
    attribution: list[GroupedValue]
    metadata: list[GroupedValue]
    historical_performance: list[dict[str, object]]
    document_count: int
    kpis: ProjectKpis | None = None
    review_queue: list[ReviewQueueItem] | None = None

