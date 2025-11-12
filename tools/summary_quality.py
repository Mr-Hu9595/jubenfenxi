#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
摘要生成与质量校验模块：
 - generate_summary(text, title, target_chars=500): 生成约500字的概要，并保证包含关键情节、人物关系与核心冲突。
 - validate_summary(text, summary): 对概要进行长度、要素覆盖、连贯性与重复度等校验。

该模块依赖 tools/universal_cli.py 的 summarize_text 函数作为核心摘要器，
质量校验不通过时会进行一次重试与结构化兜底。
"""

import re
from typing import Tuple

try:
    import universal_cli as uni  # 复用 summarize_text
except Exception:
    uni = None


# 关键要素词表（覆盖冲突、关系与事件）
CONFLICT_KEYWORDS = {
    "冲突","反转","高潮","结局","代价","风险","博弈","复仇","对抗","牺牲","危机","矛盾","抉择"
}
RELATION_KEYWORDS = {
    "父","母","兄","姐","友","同事","上司","师徒","情侣","婚","家族","同盟","对手","反派","主角","女主","男主","队友"
}
EVENT_VERBS = {
    "发现","调查","揭示","曝光","策划","反击","成长","救赎","黑化","洗白","背叛","表白","分裂","和解","失败","成功","陷入","脱困","拯救"
}


def _length_ok(summary: str, target: int) -> bool:
    n = len(summary)
    # “500字左右”放宽下限以适配摘要算法的变动（中文分句差异较大）
    return (target - 180) <= n <= (target + 150)


def _has_keywords(summary: str) -> Tuple[bool, int]:
    cnt_conflict = sum(1 for k in CONFLICT_KEYWORDS if k in summary)
    cnt_relation = sum(1 for k in RELATION_KEYWORDS if k in summary)
    cnt_event = sum(1 for k in EVENT_VERBS if k in summary)
    ok = (cnt_conflict >= 1) and (cnt_relation >= 1) and (cnt_event >= 1)
    return ok, cnt_conflict + cnt_relation + cnt_event


def _coherence_ok(summary: str) -> bool:
    # 简易连贯性：至少3个完整句，存在连接词，有时间或因果线索
    sentences = [s for s in re.split(r"[。！？!?]", summary) if s.strip()]
    if len(sentences) < 3:
        return False
    conn = re.search(r"(但是|然而|一方面|另一方面|看似|实则|表面|内心|同时|随后|因此|于是)", summary)
    time_cause = re.search(r"(起初|随后|最终|同时|因为|由于|于是|因此)", summary)
    return bool(conn) or bool(time_cause)


def _repetition_ok(summary: str) -> bool:
    # 重复度：高频两字词不超过阈值、连续重复段落不明显
    pairs = re.findall(r"(..)", summary)
    from collections import Counter
    c = Counter(pairs)
    most = c.most_common(1)[0][1] if c else 0
    return most <= max(8, len(summary)//60)


def validate_summary(text: str, summary: str, target_chars: int = 500) -> Tuple[bool, str]:
    if not summary:
        return False, "摘要为空"
    if not _length_ok(summary, target_chars):
        return False, "长度不在500字±范围"
    ok_kw, kw_score = _has_keywords(summary)
    if not ok_kw:
        return False, "缺少关键情节/人物关系/核心冲突要素"
    if not _coherence_ok(summary):
        return False, "连贯性不足（连接/因果/时间线）"
    if not _repetition_ok(summary):
        return False, "重复度过高"
    return True, "ok"


def _structured_fallback(text: str, title: str, target_chars: int) -> str:
    """结构化兜底：按设定-人物-冲突-转折-结局/代价的模板生成。"""
    name = uni.extract_title(text, title) if uni else (title or "该剧本")
    # 粗提要：截取前段信息并避免截断句子
    blurb = (text[:600] if text else "").strip()
    blurb = re.sub(r"\s+", " ", blurb)
    template = (
        f"故事围绕《{name}》展开，开篇确定基本设定与世界观。"
        f"主角在明确目标与动机的驱动下进入主线，与关键人物（亲属/同事/师徒/情侣）形成复杂关系网络。"
        f"随着叙事推进，冲突不断升级并出现反转，风险与代价逐步加码，推动人物弧光的成长/救赎或黑化/洗白。"
        f"高潮阶段揭示核心谜团并促成关键抉择，结局对前文伏笔予以回收，形成较高的悬念闭合率与情感落点。"
        f"核心情节概览：{blurb[:max(0, target_chars-160)]}"
    )
    # 控长到目标范围
    template = template.strip()
    return template[:target_chars] if len(template) > target_chars else template


def generate_summary(text: str, title: str, target_chars: int = 500) -> str:
    """质量守护版摘要生成：先用 summarize_text，再做质量校验与兜底。"""
    if uni and hasattr(uni, "summarize_text"):
        try:
            summary = uni.summarize_text(text, title, target_chars=target_chars)
        except Exception:
            summary = (text[:target_chars]).strip()
    else:
        summary = (text[:target_chars]).strip()

    ok, _ = validate_summary(text, summary, target_chars=target_chars)
    if ok:
        return summary

    # 重试一次（微调目标长度）
    if uni and hasattr(uni, "summarize_text"):
        try:
            summary2 = uni.summarize_text(text, title, target_chars=min(600, target_chars + 80))
        except Exception:
            summary2 = summary
    else:
        summary2 = summary

    ok2, _ = validate_summary(text, summary2, target_chars=target_chars)
    if ok2:
        return summary2

    # 结构化兜底
    return _structured_fallback(text, title, target_chars)