#!/usr/bin/env python3
"""Smoke tests for adaptive stream timeouts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from stream_timeouts import estimate_stream_budget


def test_molecule_design_scales_with_count():
    b5 = estimate_stream_budget("针对 EGFR 设计 5 个候选小分子", skill_name="分子设计")
    b20 = estimate_stream_budget("设计 20 个分子", skill_name="分子设计")
    assert b5.molecule_count == 5
    assert b20.molecule_count == 20
    assert b20.max_wait_after_content_sec > b5.max_wait_after_content_sec
    assert b5.max_wait_after_content_sec == 1800 + 5 * 600
    assert b20.max_wait_after_content_sec == 7200  # capped at stream_max_sec


def test_default_molecule_count():
    b = estimate_stream_budget("帮我做分子设计", skill_name="分子设计")
    assert b.molecule_count == 5
    assert b.max_wait_after_content_sec == 1800 + 5 * 600


def test_general_chat_short():
    b = estimate_stream_budget("你好", skill_name=None)
    assert b.max_wait_after_content_sec == 600


def test_pocket_prediction_medium():
    b = estimate_stream_budget("预测口袋", skill_name="口袋预测")
    assert b.max_wait_after_content_sec == 600
    assert b.post_tool_idle_sec == 1.0


def test_molecular_docking_fast_tail():
    b = estimate_stream_budget("对接", skill_name="分子对接")
    assert b.post_tool_idle_sec == 1.0


def test_cap_at_max():
    b = estimate_stream_budget("设计 100 个分子", skill_name="分子设计")
    assert b.max_wait_after_content_sec == 7200


if __name__ == "__main__":
    test_molecule_design_scales_with_count()
    test_default_molecule_count()
    test_general_chat_short()
    test_pocket_prediction_medium()
    test_molecular_docking_fast_tail()
    test_cap_at_max()
    print("stream_timeouts OK")
