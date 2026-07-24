"""Adaptive SSE / process-log timeouts for long-running skills (e.g. AI4Drug)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from config import settings


@dataclass(frozen=True)
class StreamBudget:
    max_wait_after_content_sec: float
    idle_long_rounds: int
    max_rounds: int
    poll_interval_sec: float = 0.2
    molecule_count: int | None = None
    post_tool_idle_sec: float = 5.0

    @property
    def frontend_timeout_ms(self) -> int:
        # 主流结束后仍可能 tail 过程日志，预留 2 分钟余量
        return int((self.max_wait_after_content_sec + 120) * 1000)

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "max_wait_after_content_sec": self.max_wait_after_content_sec,
            "idle_long_rounds": self.idle_long_rounds,
            "max_rounds": self.max_rounds,
            "molecule_count": self.molecule_count,
            "post_tool_idle_sec": self.post_tool_idle_sec,
        }


def _parse_molecule_count(message: str) -> int | None:
    text = (message or "").strip()
    if not text:
        return None
    patterns = (
        r"设计\s*(\d+)\s*个",
        r"生成\s*(\d+)\s*个",
        r"(\d+)\s*个候选",
        r"(\d+)\s*个分子",
        r"num_to_generate\s*[=:]\s*(\d+)",
        r"(\d+)\s*(?:个|种)?\s*(?:小分子|分子|候选)",
    )
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        n = int(m.group(1))
        if 1 <= n <= 100:
            return n
    if any(token in text for token in ("一批", "多个", "若干")):
        return 8
    return None


def estimate_stream_budget(
    message: str,
    skill_name: str | None = None,
) -> StreamBudget:
    """Estimate how long to keep SSE / process-log tail open after main text ends."""
    poll = settings.stream_poll_interval_sec
    short_idle = max(1, int(settings.stream_short_idle_sec / poll))
    skill = (skill_name or "").strip()
    msg = (message or "").strip()
    molecule_count: int | None = None
    post_tool_idle = 5.0

    if skill == "分子设计":
        molecule_count = _parse_molecule_count(msg) or 5
        total = settings.stream_molecule_base_sec + molecule_count * settings.stream_per_molecule_sec
        post_tool_idle = 5.0
    elif skill in {
        "口袋预测",
        "分子对接",
        "ADMET评估",
        "受体准备",
        "配体准备",
        "对接盒配置",
        "逆合成分析",
    }:
        total = settings.stream_ai4drug_step_sec
        post_tool_idle = 1.0
    elif skill in {
        "靶点发现",
        "蛋白质获取",
        "3D构象生成",
    }:
        total = settings.stream_ai4drug_fast_sec
        post_tool_idle = 1.0
    elif skill:
        total = settings.stream_skill_default_sec
        post_tool_idle = 5.0
    else:
        total = settings.stream_general_sec
        post_tool_idle = 5.0

    total = min(max(total, settings.stream_short_idle_sec + 30), settings.stream_max_sec)
    long_rounds = max(short_idle, int(total / poll))
    return StreamBudget(
        max_wait_after_content_sec=total,
        idle_long_rounds=long_rounds,
        max_rounds=long_rounds,
        poll_interval_sec=poll,
        molecule_count=molecule_count,
        post_tool_idle_sec=post_tool_idle,
    )


def budget_from_process_log(rows: list[dict]) -> StreamBudget | None:
    for row in rows:
        if row.get("type") != "session":
            continue
        sec = row.get("stream_budget_sec")
        if sec is None:
            continue
        poll = settings.stream_poll_interval_sec
        long_rounds = max(1, int(float(sec) / poll))
        post_idle = float(row.get("post_tool_idle_sec") or 5.0)
        return StreamBudget(
            max_wait_after_content_sec=float(sec),
            idle_long_rounds=long_rounds,
            max_rounds=long_rounds,
            poll_interval_sec=poll,
            molecule_count=row.get("molecule_count"),
            post_tool_idle_sec=post_idle,
        )
    return None
