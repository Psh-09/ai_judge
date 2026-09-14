import pytest

from app.config import Settings


def test_postgresql_url_is_normalized_to_asyncpg_driver():
    settings = Settings(database_url="postgresql://user:pw@host:5432/db")
    assert settings.database_url == "postgresql+asyncpg://user:pw@host:5432/db"


def test_already_asyncpg_url_is_left_unchanged():
    settings = Settings(database_url="postgresql+asyncpg://user:pw@host:5432/db")
    assert settings.database_url == "postgresql+asyncpg://user:pw@host:5432/db"


def test_empty_database_url_is_left_unchanged():
    settings = Settings(database_url="")
    assert settings.database_url == ""


def test_production_with_default_jwt_secret_raises():
    settings = Settings(environment="production", jwt_secret="changeme")
    with pytest.raises(RuntimeError):
        settings.validate_for_production()


def test_production_with_example_jwt_secret_raises():
    settings = Settings(environment="production", jwt_secret="change-me-in-production")
    with pytest.raises(RuntimeError):
        settings.validate_for_production()


def test_production_with_real_secret_does_not_raise():
    settings = Settings(environment="production", jwt_secret="a-real-random-secret")
    settings.validate_for_production()  # 예외가 없어야 함


def test_development_with_default_secret_does_not_raise():
    settings = Settings(environment="development", jwt_secret="changeme")
    settings.validate_for_production()  # 예외가 없어야 함


def test_cors_allowed_origin_list_parses_comma_separated_values():
    settings = Settings(cors_allowed_origins="https://a.example.com, https://b.example.com")
    assert settings.cors_allowed_origin_list == ["https://a.example.com", "https://b.example.com"]


def test_cors_allowed_origin_list_empty_by_default():
    settings = Settings(cors_allowed_origins="")
    assert settings.cors_allowed_origin_list == []
