# -*- coding: utf-8 -*-

import os
import sys

# 确保可以导入 tools 模块
BASE = os.path.dirname(os.path.dirname(__file__))
TOOLS_DIR = os.path.join(BASE, 'tools')
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from summary_quality import generate_summary, validate_summary


SAMPLE_TEXT = (
    "现代都市背景下，男主林舟起初性格温和但内心坚韧，因公司风波被迫卷入权力博弈。"
    "女主苏芷是调研部门的骨干，与林舟从同事关系逐步发展为并肩作战的伙伴。"
    "反派表面正义实则自利，通过操控舆论与资本合谋，制造危机与冲突。"
    "林舟在导师的点拨下逐步成长，团队关系网从松散到紧密，并且经历多次反转。"
    "项目推进中，信息密度高，线索交错但能闭合，高潮阶段曝光关键证据并承担代价。"
    "最终在风险与代价权衡后选择揭示真相，完成个人救赎与团队和解。"
)


def test_generate_summary_length_and_quality():
    summary = generate_summary(SAMPLE_TEXT, title="权力博弈")
    assert isinstance(summary, str)
    assert 340 <= len(summary) <= 650, f"摘要长度不在预期范围: {len(summary)}"
    ok, msg = validate_summary(SAMPLE_TEXT, summary, target_chars=500)
    assert ok, f"质量校验失败: {msg}"


def test_validate_summary_requires_keywords():
    bad_summary = (
        ("这是一个普通的故事，人物行走与对话，结尾开放，侧重景物描写与日常细节，" 
         "不涉及核心冲突、人物关系与关键事件，仅表现氛围与节奏。") * 10
    )  # 有长度但缺少关系/冲突/事件要素
    ok, msg = validate_summary(SAMPLE_TEXT, bad_summary, target_chars=500)
    assert not ok and ("要素" in msg or "连贯性" in msg)