import numpy as np

from job_search.rank import rank
from tests.conftest import make_posting

VOCAB = ["llm", "agent", "graduate", "bank", "sales"]


def bag_embed(texts, **_):
    """Toy embedder: word counts over a tiny vocabulary (plus a bias so no vector is zero)."""
    return np.array([[t.lower().count(w) for w in VOCAB] + [0.1] for t in texts], dtype=float)


def test_relevant_role_buried_under_boilerplate_still_ranks_first():
    # Live run 2026-10-23: Revolut's graduate AI role ranked #48 because its description opens with
    # company boilerplate; the role details come later.
    boilerplate = "We are a bank. " * 120
    buried = make_posting(title="Graduate LLM agent engineer", url="https://x.io/jobs/1001",
                          description=boilerplate + " You will build LLM agent systems.")
    salesy = make_posting(title="Sales bank associate", url="https://x.io/jobs/1002",
                          description="sales sales bank llm")
    ranked = rank("graduate LLM agent", [salesy, buried], top_k=2, embed=bag_embed)
    assert ranked[0][0].title == "Graduate LLM agent engineer"


def test_top_k_and_empty():
    postings = [make_posting(url=f"https://x.io/jobs/{i}", title=f"LLM role {i}") for i in range(5)]
    assert len(rank("llm", postings, top_k=3, embed=bag_embed)) == 3
    assert rank("llm", [], top_k=3, embed=bag_embed) == []
