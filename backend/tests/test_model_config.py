import pytest

from app.schemas.model_config import ModelConfig
from app.services.llm_service import validate_model_config


def test_model_config_rejects_non_https_urls():
    config = ModelConfig(api_key="test-api-key-123", base_url="http://example.com/v1", model="test-model")
    with pytest.raises(ValueError):
        validate_model_config(config)


def test_model_config_rejects_localhost():
    config = ModelConfig(api_key="test-api-key-123", base_url="https://localhost/v1", model="test-model")
    with pytest.raises(ValueError):
        validate_model_config(config)


def test_model_config_rejects_credentials_in_url():
    config = ModelConfig(api_key="test-api-key-123", base_url="https://user:pass@example.com/v1", model="test-model")
    with pytest.raises(ValueError):
        validate_model_config(config)
