import pytest
from pydantic import ValidationError

from api.config import Settings


def test_jwt_secret_required_non_dev(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("AUTH_DEV_PIN", raising=False)
    with pytest.raises(ValidationError):
        Settings(service_env="prod", _env_file=None)


def test_auth_fallback_user_disabled_in_prod(monkeypatch):
    monkeypatch.delenv("AUTH_DEV_PIN", raising=False)
    settings = Settings(service_env="prod", jwt_secret="s3cr3t", _env_file=None)
    assert settings.auth_fallback_user is None


def test_auth_dev_pin_required_in_dev(monkeypatch):
    monkeypatch.delenv("AUTH_DEV_PIN", raising=False)
    with pytest.raises(ValidationError):
        Settings(service_env="dev", _env_file=None)
    settings = Settings(service_env="dev", auth_dev_pin="123456", _env_file=None)
    assert settings.auth_dev_pin == "123456"


def test_auth_dev_pin_disallowed_in_prod(monkeypatch):
    monkeypatch.delenv("AUTH_DEV_PIN", raising=False)
    with pytest.raises(ValidationError):
        Settings(service_env="prod", jwt_secret="s3cr3t", auth_dev_pin="123456", _env_file=None)
