#!/usr/bin/env python3
"""Tests for process poll step collapsing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from tool_summarize import collapse_process_poll_steps, polish_ai4drug_exec_steps


def test_collapse_repeated_polls():
    steps = [
        {"kind": "tool", "name": "靶点发现", "title": "靶点发现", "status": "running", "result": "命令仍在后台运行", "input": "lung cancer"},
        {"kind": "tool", "name": "后台进程", "title": "后台进程", "status": "running", "result": "后台任务仍在运行", "input": "poll", "record_id": "r1"},
        {"kind": "tool", "name": "后台进程", "title": "后台进程", "status": "done", "result": "工具执行完成", "input": "poll", "record_id": "r2"},
        {"kind": "tool", "name": "后台进程", "title": "后台进程", "status": "done", "result": "工具执行完成", "input": "poll", "record_id": "r3"},
        {
            "kind": "tool",
            "name": "靶点发现",
            "title": "靶点发现",
            "status": "done",
            "result": "发现 3 个靶点",
            "detail": "EGFR · 关联分 0.812",
            "input": "lung cancer",
        },
    ]
    out = collapse_process_poll_steps(steps)
    poll_done = [s for s in out if s.get("name") == "后台进程" and s.get("status") == "done"]
    assert len(poll_done) == 0, poll_done
    target_steps = [s for s in out if s.get("name") == "靶点发现"]
    assert len(target_steps) == 1, target_steps
    assert target_steps[0]["status"] == "done"
    assert "发现" in str(target_steps[0].get("result") or "")


def test_polish_includes_collapse():
    steps = [
        {"kind": "tool", "name": "后台进程", "status": "done", "result": "工具执行完成", "input": "poll", "record_id": "a"},
        {"kind": "tool", "name": "后台进程", "status": "done", "result": "后台任务仍在运行", "input": "poll", "record_id": "b"},
    ]
    out = polish_ai4drug_exec_steps(steps)
    assert len(out) <= 1


def test_backfill_target_discovery_from_reply():
    from tool_summarize import backfill_generic_tool_steps

    reply = (
        "共发现 **143 个关联靶点**（10 个独特基因）\n"
        "| 1 | **EGFR** | 0.888 | 1 | ✅ | 3 |"
    )
    steps = [
        {
            "kind": "tool",
            "name": "靶点发现",
            "title": "靶点发现",
            "status": "done",
            "result": "工具执行完成",
            "detail": "",
        }
    ]
    out = backfill_generic_tool_steps(steps, reply=reply)
    assert "发现 143 个靶点" in out[0]["result"]
    assert "EGFR" in out[0]["detail"]


def test_dedupe_identical_done_tools():
    from tool_summarize import polish_ai4drug_exec_steps

    steps = [
        {"kind": "tool", "name": "逆合成分析", "status": "done", "result": "逆合成路线已生成", "detail": ""},
        {"kind": "tool", "name": "逆合成分析", "status": "done", "result": "逆合成路线已生成", "detail": ""},
    ]
    out = polish_ai4drug_exec_steps(steps)
    assert len([s for s in out if s.get("name") == "逆合成分析"]) == 1


def test_drop_superseded_failed_tools():
    from tool_summarize import polish_ai4drug_exec_steps

    steps = [
        {"kind": "tool", "name": "分子设计", "status": "done", "result": "口袋预测失败", "detail": ""},
        {"kind": "tool", "name": "蛋白质获取", "status": "done", "result": "EGFR · PDB 3W2S", "detail": ""},
        {"kind": "tool", "name": "分子设计", "status": "done", "result": "已生成 3 个候选分子", "detail": ""},
    ]
    out = polish_ai4drug_exec_steps(steps)
    names = [s.get("name") for s in out if s.get("kind") == "tool" and s.get("name") == "分子设计"]
    assert names == ["分子设计"]
    assert "失败" not in str(out[0].get("result") or "")


def test_prune_target_discovery_debug_steps():
    from tool_summarize import polish_ai4drug_exec_steps

    reply = (
        "共找到 **124 个靶点关联**，去重后 **50 个独立靶点基因**，Top 靶点为 KCNJ11（关联分数 0.9250）\n"
        "| 1 | **KCNJ11** | 0.9250 |"
    )
    steps = [
        {"kind": "thinking", "name": "深度思考", "status": "done", "result": "准备开始执行调用。", "detail": "准备开始执行调用。"},
        {
            "kind": "tool",
            "name": "靶点发现",
            "status": "done",
            "result": '/chembl_37/chembl_37.db", "chembl_release_id": 37',
            "detail": '"opentargets": { "provider": "Open Targets", "targets": [{"gene_symbol": "KCNJ11"}]',
        },
        {"kind": "thinking", "name": "深度思考", "status": "done", "result": "JSON 文件中的目标结构不一致。", "detail": "JSON 文件中的目标结构不一致。"},
        {"kind": "tool", "name": "exec", "status": "done", "result": "Top-level keys: ['report_id', 'targets_all']", "detail": "full exec output here"},
        {"kind": "tool", "name": "读取报告", "status": "done", "result": "总靶点数: 0", "detail": ""},
    ]
    out = polish_ai4drug_exec_steps(steps, reply=reply)
    think = [s for s in out if s.get("kind") == "thinking"]
    assert len(think) == 2, think
    target = [s for s in out if s.get("name") == "靶点发现"][0]
    assert "124" in target["result"]
    assert "KCNJ11" in target["result"]
    assert len(target.get("detail") or "") >= 10
    assert [s for s in out if s.get("name") == "exec"] == []


def test_runtime_noise_not_in_final_display_block():
    from skill_display import format_step_display_block
    from tool_summarize import polish_ai4drug_exec_step, polish_ai4drug_exec_steps

    noise = (
        "Command still running (session kind-sable, pid 1911313). "
        "Use process (list/poll/log/write/send-keys/submit/paste/kill/clear/remove) for follow-up."
    )
    step = {
        "kind": "tool",
        "name": "靶点发现",
        "title": "靶点发现",
        "status": "done",
        "result": "发现 1039 个靶点",
        "detail": noise,
        "input": "non-small cell lung cancer",
    }
    polished = polish_ai4drug_exec_step(step)
    block = format_step_display_block(polished) or ""
    assert "Command still running" not in block, block
    assert "Use process" not in block, block
    assert "1039" in block or "靶点" in block, block

    noisy_live = [
        {"kind": "thinking", "title": "深度思考", "status": "done", "name": "深度思考", "result": "命令仍在后台运行", "detail": "命令仍在后台运行"},
        {"kind": "tool", "name": "后台进程", "title": "后台进程", "status": "running", "result": noise, "input": "poll", "record_id": "p1"},
        step,
    ]
    pruned = polish_ai4drug_exec_steps(noisy_live)
    assert len(pruned) == 2, pruned
    assert any(s.get("kind") == "thinking" for s in pruned), pruned
    target = [s for s in pruned if s.get("name") == "靶点发现"][0]
    assert "Command still running" not in str(target.get("detail") or ""), pruned


def test_exec_vina_config_not_in_final_display():
    from skill_display import format_step_display_block, synthesize_final_from_steps
    from tool_summarize import polish_ai4drug_exec_steps

    vina = (
        "AutoDock Vina config # Auto-generated by data_pre_processing.py "
        "center_x = 6.795 center_y = -0.339 center_z = 13.901 "
        "size_x = 29.0 size_y = 23.1 size_z = 30.0 exhaustiveness = 8"
    )
    steps = polish_ai4drug_exec_steps(
        [
            {
                "kind": "tool",
                "name": "对接盒配置",
                "title": "对接盒配置",
                "status": "done",
                "result": "已配置 1 个对接盒",
                "detail": "EGFR_3W2S_pocket1 · 中心 (6.8, -0.3, 13.9) · 尺寸 29.0×23.1×30.0 Å",
            },
            {
                "kind": "tool",
                "name": "exec",
                "title": "执行命令",
                "status": "done",
                "result": vina,
                "detail": vina,
            },
        ]
    )
    final = synthesize_final_from_steps(steps)
    assert "执行命令" not in final, final
    assert "AutoDock Vina" not in final, final
    assert "center_x" not in final, final
    assert "对接盒" in final or "6.8" in final, final
    block = format_step_display_block(steps[0]) or ""
    assert "对接盒" in block or "6.8" in block, block


def test_drop_running_when_done_exists():
    from tool_summarize import _drop_running_when_done_exists

    steps = [
        {"kind": "tool", "name": "口袋预测", "status": "running", "result": "命令仍在后台运行"},
        {"kind": "tool", "name": "口袋预测", "status": "done", "result": "识别 3 个结合口袋", "detail": "EGFR_3W2S_pocket1"},
    ]
    out = _drop_running_when_done_exists(steps)
    assert len(out) == 1, out
    assert out[0]["status"] == "done"


def test_chinese_runtime_noise_filtered():
    from tool_summarize import is_process_runtime_noise, prune_live_display_steps

    assert is_process_runtime_noise("命令仍在运行，需要轮询以确认完成。")
    assert is_process_runtime_noise("进程仍在运行，让我再等一会儿。")
    steps = prune_live_display_steps(
        [
            {
                "kind": "thinking",
                "name": "深度思考",
                "status": "done",
                "detail": "进程仍在运行，让我再等一会儿。",
            },
            {
                "kind": "tool",
                "name": "分子设计",
                "status": "done",
                "result": "已生成 5 个候选分子",
            },
        ]
    )
    assert any(s.get("kind") == "thinking" for s in steps), steps


def test_should_emit_early_final_retrosynthesis():
    from skill_display import should_emit_early_final

    merged = [
        {"kind": "tool", "name": "3D构象生成", "status": "done", "result": "已生成 1 个分子构象"},
        {"kind": "tool", "name": "逆合成分析", "status": "running", "result": "命令仍在后台运行"},
    ]
    assert not should_emit_early_final(merged, "逆合成分析")
    merged[1]["status"] = "done"
    merged[1]["result"] = "逆合成路线已生成"
    assert should_emit_early_final(merged, "逆合成分析")


def test_should_emit_early_final_molecular_docking():
    from skill_display import should_emit_early_final, synthesize_final_from_steps

    merged = [
        {"kind": "tool", "name": "蛋白质获取", "status": "done", "result": "EGFR · PDB 3W2S"},
        {"kind": "tool", "name": "配体准备", "status": "done", "result": "已制备 1 个配体"},
    ]
    assert not should_emit_early_final(merged, "分子对接")
    assert not synthesize_final_from_steps(merged, "分子对接")
    merged.append(
        {
            "kind": "tool",
            "name": "分子对接",
            "status": "done",
            "result": "分子对接完成，最佳 -8.2 kcal/mol",
        }
    )
    assert should_emit_early_final(merged, "分子对接")
    final = synthesize_final_from_steps(merged, "分子对接")
    assert "kcal" in final


def test_should_emit_early_final_empty_skill():
    from skill_display import should_emit_early_final

    merged = [{"kind": "tool", "name": "配体准备", "status": "done", "result": "已制备 1 个配体"}]
    assert not should_emit_early_final(merged, None)
    assert not should_emit_early_final(merged, "")


def test_extract_final_answer_picks_longest():
    from reply_rebuild import extract_final_answer

    raw = (
        "## 最终回答\n\n**3D构象生成**\n\n- mol0\n\n"
        "## 分析过程\n- 工具数: 2\n\n"
        "## 最终回答\n\n### 吉非替尼逆合成\n\n路线 1 · 6 步\n\n**关键中间体：**\n"
        "- 中间体 A\n"
    )
    final = extract_final_answer(raw)
    assert "关键中间体" in final
    assert "中间体 A" in final
    assert "3D构象生成" not in final


if __name__ == "__main__":
    test_collapse_repeated_polls()
    test_polish_includes_collapse()
    test_backfill_target_discovery_from_reply()
    test_dedupe_identical_done_tools()
    test_drop_superseded_failed_tools()
    test_prune_target_discovery_debug_steps()
    test_runtime_noise_not_in_final_display_block()
    test_exec_vina_config_not_in_final_display()
    test_drop_running_when_done_exists()
    test_chinese_runtime_noise_filtered()
    test_should_emit_early_final_retrosynthesis()
    test_should_emit_early_final_molecular_docking()
    test_should_emit_early_final_empty_skill()
    test_extract_final_answer_picks_longest()
    print("poll_collapse OK")
