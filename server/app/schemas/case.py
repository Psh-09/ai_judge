import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import CaseStatus, FailedStage, FailureReason, PleaValue, VerdictValue
from app.schemas.rule import Effort, Severity


class CreateCaseRequest(BaseModel):
    """붙여넣기 모드만 지원한다. GitHub 링크 모드는 다음 단계에서 추가된다."""

    code: str
    language: str
    force_retrial: bool = False


class CaseOrigin(BaseModel):
    type: str
    repo_url: str | None = None
    commit_sha: str | None = None
    file_path: str | None = None


class CaseSubmissionResult(BaseModel):
    case_id: uuid.UUID
    cached: bool
    in_progress: bool | None = None
    origin: CaseOrigin | None = None
    origin_label: str | None = None
    previous_case_id: uuid.UUID | None = None


class CaseProgress(BaseModel):
    status: CaseStatus
    revision: int
    appeal_used: bool


class Charge(BaseModel):
    charge_index: int
    rule_id: str
    rule_title: str
    evidence_start: int
    evidence_end: int
    charged_severity: Severity
    severity_adjusted: bool
    severity_reason: str | None
    description: str


class Plea(BaseModel):
    charge_index: int
    plea: PleaValue
    argument: str


class Verdict(BaseModel):
    charge_index: int
    verdict: VerdictValue
    final_severity: Severity | None
    reasoning: str


class Sentence(BaseModel):
    sentence_id: uuid.UUID
    charge_index: int
    task: str
    target_start: int
    target_end: int
    effort: Effort
    effort_adjusted: bool
    effort_reason: str | None
    effort_clamped: bool
    advisory: bool
    rationale: str
    completed_at: datetime | None


class Judgment(BaseModel):
    revision: int
    opinion: str
    rebuttal_accepted: bool | None
    precedent_verdict_ids: list[int]
    verdicts: list[Verdict]
    sentences: list[Sentence]


class Appeal(BaseModel):
    rebuttal: str
    created_at: datetime


class CaseDetail(BaseModel):
    case_id: uuid.UUID
    language: str
    status: CaseStatus
    revision: int
    appeal_used: bool
    charges_truncated: bool
    total_lines: int
    failed_stage: FailedStage | None
    failure_reason: FailureReason | None
    origin: CaseOrigin
    created_at: datetime
    updated_at: datetime
    charges: list[Charge]
    pleas: list[Plea]
    judgment: Judgment | None
    appeal: Appeal | None


class SentenceToggleRequest(BaseModel):
    completed: bool


class SentenceProgress(BaseModel):
    done: int
    total: int


class SentenceToggleResponse(BaseModel):
    sentence_id: uuid.UUID
    completed_at: datetime | None
    progress: SentenceProgress


class CaseSummary(BaseModel):
    case_id: uuid.UUID
    language: str
    status: CaseStatus
    origin_label: str
    charges_count: int
    sustained_count: int
    sentence_progress: SentenceProgress
    created_at: datetime


class CaseListResponse(BaseModel):
    items: list[CaseSummary]
    page: int
    per_page: int
    total: int


class RuleFrequencyItem(BaseModel):
    rule_id: str
    rule_title: str
    count: int


class RuleFrequencyResponse(BaseModel):
    items: list[RuleFrequencyItem]
