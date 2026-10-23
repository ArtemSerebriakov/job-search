from datetime import date

import numpy as np

from job_search.calibration import Calibrator, fit_logistic, resolve
from job_search.config import Calibration

CFG = Calibration(min_resolved=30, no_reply_after_days=45, default_reply_rate=0.08)
TODAY = date(2026, 12, 1)


def outcome(status, score=70, sent_on="2026-11-20"):
    return {"status": status, "final_score": score, "sent_on": sent_on}


def test_pending_applications_are_censored_not_rejections():
    pairs, censored = resolve([outcome("sent"), outcome("reply"), outcome("rejected")], TODAY, CFG)
    assert sorted(y for _, y in pairs) == [0, 1] and censored == 1


def test_silence_beyond_cutoff_counts_as_no_reply():
    pairs, censored = resolve([outcome("sent", sent_on="2026-10-01")], TODAY, CFG)
    assert pairs == [(70, 0)] and censored == 0


def test_uncalibrated_until_enough_outcomes():
    calib = Calibrator.from_outcomes([outcome("reply"), outcome("rejected")], TODAY, CFG)
    assert not calib.calibrated
    assert "28 more needed" in calib.note()
    assert calib.probability(80) > calib.probability(60)


def test_fit_recovers_known_slope():
    rng = np.random.default_rng(0)
    xs = rng.uniform(0.3, 1.0, 4000)
    ys = (rng.uniform(size=xs.size) < 1 / (1 + np.exp(-(-6 + 8 * xs)))).astype(float)
    a, b = fit_logistic(xs, ys)
    assert abs(a + 6) < 0.6 and abs(b - 8) < 0.8


def test_calibrated_after_enough_outcomes():
    outcomes = [outcome("reply", 90)] * 10 + [outcome("rejected", 50)] * 25
    calib = Calibrator.from_outcomes(outcomes, TODAY, CFG)
    assert calib.calibrated
    assert calib.probability(90) > 0.5 > calib.probability(50)


def test_chance_of_at_least_one_reply():
    calib = Calibrator.from_outcomes([], TODAY, CFG)
    p = calib.probability(70)
    assert abs(calib.chance([70, 70, 70]) - (1 - (1 - p) ** 3)) < 1e-9
