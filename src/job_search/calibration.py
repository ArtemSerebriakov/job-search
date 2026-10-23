"""Turns fit scores into reply probabilities, and measures itself from logged outcomes.

Until enough applications have resolved, probabilities are an assumed reply rate scaled by score
and are labelled "uncalibrated". Applications still waiting for an answer are censored (left out of
the fit) rather than counted as rejections; after `no_reply_after_days` silence they count as 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from job_search.config import Calibration

POSITIVE = {"reply", "interview"}
NEGATIVE = {"rejected"}
_REFERENCE_SCORE = 70.0


def resolve(outcomes: list[dict], today: date, cfg: Calibration) -> tuple[list[tuple[float, int]], int]:
    """(score, label) pairs for resolved applications, and the number still censored."""
    resolved, censored = [], 0
    for o in outcomes:
        if o["status"] in POSITIVE:
            resolved.append((o["final_score"], 1))
        elif o["status"] in NEGATIVE:
            resolved.append((o["final_score"], 0))
        elif o["status"] == "sent":
            waited = (today - date.fromisoformat(o["sent_on"])).days
            if waited > cfg.no_reply_after_days:
                resolved.append((o["final_score"], 0))
            else:
                censored += 1
    return resolved, censored


def fit_logistic(xs: np.ndarray, ys: np.ndarray, l2: float = 1e-3, iterations: int = 50) -> tuple[float, float]:
    """Newton/IRLS fit of P(y=1) = sigmoid(a + b * x) with x = score/100 and a small ridge penalty."""
    X = np.column_stack([np.ones_like(xs), xs])
    w = np.zeros(2)
    for _ in range(iterations):
        p = 1 / (1 + np.exp(-X @ w))
        grad = X.T @ (p - ys) + l2 * w
        hess = X.T @ (X * (p * (1 - p))[:, None]) + l2 * np.eye(2)
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return float(w[0]), float(w[1])


@dataclass
class Calibrator:
    calibrated: bool
    resolved: int
    censored: int
    min_resolved: int
    default_rate: float
    a: float = 0.0
    b: float = 0.0

    @classmethod
    def from_outcomes(cls, outcomes: list[dict], today: date, cfg: Calibration) -> Calibrator:
        pairs, censored = resolve(outcomes, today, cfg)
        base = dict(resolved=len(pairs), censored=censored, min_resolved=cfg.min_resolved,
                    default_rate=cfg.default_reply_rate)
        labels = {y for _, y in pairs}
        if len(pairs) < cfg.min_resolved or labels != {0, 1}:
            return cls(calibrated=False, **base)
        xs = np.array([s for s, _ in pairs]) / 100
        a, b = fit_logistic(xs, np.array([y for _, y in pairs], dtype=float))
        return cls(calibrated=True, a=a, b=b, **base)

    def probability(self, score: float) -> float:
        if self.calibrated:
            return float(1 / (1 + np.exp(-(self.a + self.b * score / 100))))
        return float(np.clip(self.default_rate * score / _REFERENCE_SCORE, 0.005, 0.5))

    def chance(self, scores: list[float]) -> float:
        """P(at least one reply) when applying to all of `scores` (the day's top 3)."""
        return 1 - float(np.prod([1 - self.probability(s) for s in scores]))

    def note(self) -> str:
        if self.calibrated:
            return f"Calibrated on {self.resolved} resolved applications ({self.censored} still pending)."
        need = max(0, self.min_resolved - self.resolved)
        return (f"Uncalibrated: this is a fit estimate, not a measured probability. "
                f"{self.resolved} resolved outcomes logged, {need} more needed ({self.censored} pending, not counted as rejections).")
