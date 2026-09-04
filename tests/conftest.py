import pytest

from elk_lead_agent.config import load_config


@pytest.fixture
def config():
    return load_config()
