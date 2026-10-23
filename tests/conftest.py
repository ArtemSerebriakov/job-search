import pytest

from job_search.config import load_criteria
from job_search.models import Posting


@pytest.fixture(scope="session")
def criteria():
    return load_criteria()


def make_posting(**overrides) -> Posting:
    base = dict(
        source="test",
        url="https://boards.greenhouse.io/acme/jobs/1234567",
        title="Junior Machine Learning Engineer",
        company="Acme AI GmbH",
        location="Munich, Germany",
        country="DE",
        description="You will build LLM-based tools with Python and PyTorch.",
        source_is_origin=True,
    )
    base.update(overrides)
    return Posting(**base)


@pytest.fixture
def posting():
    return make_posting
