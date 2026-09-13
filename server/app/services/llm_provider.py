from abc import ABC, abstractmethod
from enum import Enum

from app.fixtures.data import FIXTURES


class Role(str, Enum):
    PROSECUTION = "prosecution"
    DEFENSE = "defense"
    JUDGMENT = "judgment"
    REJUDGMENT = "rejudgment"


class LLMProvider(ABC):
    """역할과 이미 조립된 요청을 받아 JSON 응답(dict)을 반환하는 얇은 어댑터.

    요청 조립, 스키마 검증, 재시도, 토큰/prompt_version 기록은 이 어댑터 밖(워커)의 책임이다.
    """

    @abstractmethod
    async def generate(self, role: Role, request: dict) -> dict: ...


class FixtureNotFoundError(Exception):
    """fixture 모드에서 등록되지 않은 code_hash로 호출했을 때 발생한다."""


class FixtureLLMProvider(LLMProvider):
    def __init__(self, fixtures: dict[str, dict[str, dict]] | None = None):
        self._fixtures = fixtures if fixtures is not None else FIXTURES

    async def generate(self, role: Role, request: dict) -> dict:
        code_hash = request.get("code_hash")
        case_fixtures = self._fixtures.get(code_hash)
        if case_fixtures is None:
            raise FixtureNotFoundError(
                f"등록된 fixture가 없는 code_hash입니다: {code_hash}. "
                "fixture 모드는 app/fixtures/data.py에 등록된 샘플 코드만 지원합니다."
            )
        return case_fixtures[role.value]


class RealLLMProvider(LLMProvider):
    async def generate(self, role: Role, request: dict) -> dict:
        raise NotImplementedError("실제 LLM provider는 아직 구현되지 않았습니다.")


def get_llm_provider(provider_name: str) -> LLMProvider:
    if provider_name == "fixture":
        return FixtureLLMProvider()
    if provider_name == "real":
        return RealLLMProvider()
    raise ValueError(f"알 수 없는 LLM_PROVIDER 값: {provider_name!r}")
