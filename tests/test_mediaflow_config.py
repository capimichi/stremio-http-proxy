import os
from unittest.mock import patch
from stremio_http_proxy.container.default_container import DefaultContainer


def test_default_container_initializes_mediaflow_env():
    env = {
        "APP_SECRET": "testsecret123",
        "MEDIAFLOW_BASE_URL": "https://mediaflow.example.com",
        "MEDIAFLOW_API_PASSWORD": "mypassword123",
        "MEDIAFLOW_ENABLED": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        DefaultContainer.instance = None
        container = DefaultContainer()
        assert container.get_var("mediaflow_base_url") == "https://mediaflow.example.com"
        assert container.get_var("mediaflow_api_password") == "mypassword123"
        assert container.get_var("mediaflow_enabled") is True
