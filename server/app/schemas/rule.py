from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Effort(str, Enum):
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


class Rule(BaseModel):
    rule_id: str
    category: str
    title: str
    description: str
    default_severity: Severity
    typical_effort: Effort
    languages: list[str] = Field(default_factory=list)
    active: bool
