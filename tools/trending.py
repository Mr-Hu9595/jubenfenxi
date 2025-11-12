#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
舆情配置与评分辅助模块：
- 从 tools/data/trending_config.json 读取红果/抖音的近月舆情快照与权重；
- 提供热度、传播因子与营销方向的趋势化计算；
- 若配置不存在，返回合理默认值，不影响现有管线。
"""

import os
import json
from typing import Dict, Tuple


BASE_DIR = os.getcwd()
CONFIG_PATH = os.path.join(BASE_DIR, "tools", "data", "trending_config.json")


def load_trending_config() -> Dict:
    """读取舆情配置，若不存在则返回默认配置。"""
    default = {
        "last_updated": "",
        "sources": [],
        "platforms": {
            "douyin": {
                "strong_tags": ["反转", "逆袭", "甜宠", "虐恋", "成长", "救赎"],
                "moderate_tags": ["悬疑", "家国", "群像", "知识", "专业"],
                "topic_words": ["爆点", "争议", "话题", "热搜"]
            },
            "hongguo": {
                "strong_tags": ["甜虐", "成年人爱情", "反差", "家国叙事"],
                "moderate_tags": ["现实题材", "家庭伦理", "群像"],
                "topic_words": ["热度值", "榜单", "新剧榜", "热播榜"]
            }
        },
        "weights": {
            "strong": 1.0,
            "moderate": 0.6,
            "topic": 0.5
        }
    }
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg or default
    except Exception:
        return default


def trend_hotness(title: str, text: str, cfg: Dict) -> float:
    """根据舆情配置计算题材热度（0~2）。"""
    ft = (title or "") + (text or "")
    w = cfg.get("weights", {})
    strong_w = float(w.get("strong", 1.0))
    moderate_w = float(w.get("moderate", 0.6))
    strong = 0.0
    moderate = 0.0
    for p in cfg.get("platforms", {}).values():
        strong += sum(ft.count(k) for k in p.get("strong_tags", [])) * strong_w
        moderate += sum(ft.count(k) for k in p.get("moderate_tags", [])) * moderate_w
    # 映射到 0~2 区间，基础 1.0，强标签显著提升
    raw = 1.0 + min(1.0, strong * 0.15 + moderate * 0.08)
    return max(0.5, min(2.0, raw))


def trend_spread(title: str, text: str, cfg: Dict) -> float:
    """根据舆情配置计算传播因子（0.5~1.5）。"""
    ft = (title or "") + (text or "")
    w = cfg.get("weights", {})
    topic_w = float(w.get("topic", 0.5))
    rev = sum(ft.count(k) for k in ["反转", "高潮", "意外", "出乎意料"]) * 0.15
    emo = sum(ft.count(k) for k in ["虐", "甜", "哭", "燃"]) * 0.1
    topic = 0.0
    for p in cfg.get("platforms", {}).values():
        topic += sum(ft.count(k) for k in p.get("topic_words", [])) * topic_w * 0.1
    raw = rev + emo + topic
    return max(0.5, min(1.5, raw if raw > 0.5 else 0.5 + raw))


def trend_marketing_direction(text: str, cfg: Dict) -> str:
    """基于舆情标签选择营销方向（五选一）。"""
    t = text or ""
    # 优先级：反转爽点 > 成长救赎 > 甜虐情绪 > 知识信息量 > 家国叙事
    if any(k in t for k in ["反转", "逆袭", "打脸"]):
        return "反转爽点"
    if any(k in t for k in ["成长", "救赎", "弧光"]):
        return "成长救赎"
    if any(k in t for k in ["甜宠", "虐恋", "霸总", "甜虐"]):
        return "甜虐情绪"
    if any(k in t for k in ["知识", "信息量", "专业", "术语"]):
        return "知识信息量"
    if any(k in t for k in ["家国", "群像", "权谋"]):
        return "家国叙事"
    # 若无明显标签，默认反转爽点（平台偏好）
    return "反转爽点"