from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# server/app/config.py -> server/ -> repo root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# .env.example에 적힌 값과 코드 기본값 둘 다 "미설정"으로 취급한다.
_INSECURE_JWT_SECRETS = {"changeme", "change-me-in-production"}


class Settings(BaseSettings):
    database_url: str = ""
    jwt_secret: str = "changeme"
    llm_provider: str = "fixture"
    rules_path: Path = BASE_DIR / "rules.yaml"

    # 배포 관련 설정 (기본값은 전부 로컬 개발 기준)
    environment: str = "development"
    run_worker_in_app: bool = False
    cors_allowed_origins: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        # 대부분의 PaaS가 발급하는 연결 문자열은 드라이버 지정이 없는 postgresql:// 형태다.
        prefix = "postgresql://"
        if value.startswith(prefix):
            return "postgresql+asyncpg://" + value[len(prefix) :]
        return value

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    def validate_for_production(self) -> None:
        if self.environment == "production" and self.jwt_secret in _INSECURE_JWT_SECRETS:
            raise RuntimeError(
                "JWT_SECRET이 기본값입니다. ENVIRONMENT=production에서는 실제 비밀값을 설정해야 합니다."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
