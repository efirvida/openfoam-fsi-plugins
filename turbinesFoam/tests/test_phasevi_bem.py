"""Regression and sanity tests for the reference BEM (bemPhaseVI.py)."""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "validation" / "phaseVI" / "scripts"))

import bemPhaseVI  # noqa: E402


def _args(**kw):
    base = dict(speed=7.0, rpm=71.8667, rho=1.25249, pitch=3.0, blades=2,
                tip="on", nstations=120, cd_scale=1.0, drag="total")
    base.update(kw)
    return Namespace(**base)


def test_baseline_power_is_reproducible():
    _, thrust, _, power, _ = bemPhaseVI.run(_args())
    assert 5.9e3 < power < 6.1e3
    assert 1.2e3 < thrust < 1.4e3


def test_less_drag_gives_more_power():
    p_total = bemPhaseVI.run(_args())[3]
    p_half = bemPhaseVI.run(_args(cd_scale=0.5))[3]
    p_pressure = bemPhaseVI.run(_args(drag="pressure"))[3]
    assert p_half > p_total
    assert p_pressure > p_total


def test_tip_loss_off_raises_loading():
    thrust_on = bemPhaseVI.run(_args())[1]
    thrust_off = bemPhaseVI.run(_args(tip="off"))[1]
    assert thrust_off > thrust_on
