#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
批量解析 /Users/mr.hu/Desktop/爆款排名/10.31剧本_txt 下的 txt 文件，
抽取关键信息并计算评分与综合排序。

输出：analysis_results.json（每部剧本的指标与评分）
"""

import os
import re
import json
from collections import Counter
try:
    # 统一从 analyze_docx 导入时代、倾向与题材识别，消除重复实现
    from analyze_docx import detect_era, detect_gender_channel, detect_genre
except Exception:
    detect_genre = None

TXT_DIR = "/Users/mr.hu/Desktop/爆款排名/10.31剧本_txt"
OUT_JSON = "/Users/mr.hu/Desktop/爆款排名/analysis_results.json"


def read_text(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        with open(path, 'r', encoding='gb18030', errors='ignore') as f:
            return f.read()


# 删除本地重复实现，统一使用 analyze_docx 的实现


def detect_original(text):
    return '改编' if ('改编' in text or '版权' in text and '改' in text) else '原创'


def count_core_roles(text):
    # 统计关键词出现次数，粗略估算核心角色数量
    keys = ['男主','女主','反派','配角','重要角色','主要角色']
    c = sum(text.count(k) for k in keys)
    # 容错：若读不到明确人物表，根据文本长度估计核心角色数量
    length = len(text)
    if c == 0:
        if length < 8000:
            return 4
        elif length < 15000:
            return 6
        elif length < 30000:
            return 8
        else:
            return 10
    # 每个关键词未必代表不同人，给一个合理上界
    return max(4, min(12, c))


def count_scenes(text):
    # 搜索场景提示词与编号模式
    patterns = [
        r'场景[一二三四五六七八九十百]+', r'第[一二三四五六七八九十百]+场', r'内景', r'外景', r'昼', r'夜'
    ]
    hits = 0
    for p in patterns:
        hits += len(re.findall(p, text))
    # 若未找到，按地点关键词估算
    if hits == 0:
        loc_words = ['家','公司','医院','学校','村','街道','王府','皇宫','科举考场','牢房','郊外','码头','船']
        loc_hits = sum(text.count(k) for k in loc_words)
        hits = max(6, min(20, loc_hits))
    # 将命中数压缩到合理场景数量范围
    if hits < 6:
        return 6
    if hits > 30:
        return 30
    return hits


def budget_bracket(era, text):
    high_words = ['皇帝','王府','朝臣','宫','航拍','大型群演','打戏','水戏','海','船','特效','绿幕']
    medium_words = ['夜戏','外景','车戏','办公室群戏','学校群戏']
    if era.startswith('古代'):
        if any(w in text for w in high_words):
            return '高'
        return '中'
    if '玄幻' in era:
        return '高' if any(w in text for w in high_words) else '中'
    # 现代
    if any(w in text for w in high_words):
        return '中/高'
    if any(w in text for w in medium_words):
        return '中'
    return '低'


def tech_complexity_score(text):
    tech_words = ['航拍','斯坦尼康','轨道','绿幕','特效','打戏','水下','船','海','爆破','枪战']
    hits = sum(text.count(w) for w in tech_words)
    # 0-100
    return max(0, min(100, hits * 12))


def novelty_score(title, text):
    # 1-10 分，转 0-100
    novel_words = ['分身','摆烂系统','拼夕夕','海蛇','饥荒年','育儿师','女帝逼婚','视频号','直播逼我整活','捞船装备','黄毛','民国','政务']
    common_words = ['系统','重生','科举','皇帝','状元','逆袭','打脸','豪门','保镖','外卖']
    n = sum((title+text).count(w) for w in novel_words)
    c = sum((title+text).count(w) for w in common_words)
    base = 6
    if n >= 3:
        base = 8
    elif n == 2:
        base = 7
    elif n == 1:
        base = 6.5
    else:
        base = 5.5
    # 常见套路越多，新颖度稍降
    base -= min(2.5, c * 0.15)
    base = max(3.5, min(9.5, base))
    return round(base * 10)  # 0-100


def market_potential_score(era, gender, title, text):
    # 0-100：根据近年短剧市场经验的启发式（后续由联网摘要校正）
    boosts = 0
    if era == '现代':
        boosts += 10
    if gender == '男' and any(k in (title+text) for k in ['系统','重生','逆袭','打脸','直播']):
        boosts += 15
    if gender == '女' and any(k in (title+text) for k in ['甜宠','虐恋','霸总','婚恋','男友']):
        boosts += 15
    if '乡村' in text or '书记' in text or '清北' in text:
        boosts += 8
    if '科举' in text or '皇帝' in text:
        boosts += 5
    # 基础 60，上下浮动
    base = 60 + boosts
    base = max(35, min(95, base))
    return base


def difficulty_index(core_roles, scenes, budget, tech_score):
    # 核心：演员数量25%、场景数量25%、预算成本25%、技术复杂度（含外景/夜戏）15%、地理分散性10%
    # 这里用场景数量近似地理分散性（再乘一个折算）
    # 将各项映射到 0-100
    role_s = max(10, min(100, int(core_roles / 12 * 100)))
    scene_s = max(10, min(100, int(scenes / 30 * 100)))
    budget_s_map = {'低': 30, '中': 60, '中/高': 75, '高': 90}
    budget_s = budget_s_map.get(budget, 60)
    tech_s = tech_score
    geo_s = int(scene_s * 0.8)
    idx = role_s*0.25 + scene_s*0.25 + budget_s*0.25 + tech_s*0.15 + geo_s*0.10
    return round(idx)


def difficulty_star(idx):
    # 0-100 -> ★☆☆☆☆ .. ★★★★★
    if idx < 35:
        return '★☆'
    if idx < 50:
        return '★★'
    if idx < 65:
        return '★★★'
    if idx < 80:
        return '★★★★'
    return '★★★★★'


def budget_control_score(budget):
    return {'低': 90, '中': 65, '中/高': 55, '高': 40}.get(budget, 60)


def overall_priority(potential, difficulty, budget_control, novelty, era):
    # 综合优先级分：爆款潜力35%、拍摄难度（倒扣）25%、预算可控性20%、题材新颖度15%、现代剧加权5%
    # 难度倒扣：100 - difficulty
    score = potential*0.35 + (100 - difficulty)*0.25 + budget_control*0.20 + novelty*0.15 + (5 if era == '现代' else 0)
    return round(score)


def analyze_one(path):
    title = os.path.basename(path).replace('.txt','')
    text = read_text(path)
    era = detect_era(text, title)
    gender = detect_gender_channel(text, title)
    original = detect_original(text)
    core_roles = count_core_roles(text)
    scenes = count_scenes(text)
    budget = budget_bracket(era, text)
    tech_s = tech_complexity_score(text)
    diff_idx = difficulty_index(core_roles, scenes, budget, tech_s)
    diff_star = difficulty_star(diff_idx)
    novelty = novelty_score(title, text)
    potential = market_potential_score(era, gender, title, text)
    budget_ctrl = budget_control_score(budget)
    overall = overall_priority(potential, diff_idx, budget_ctrl, novelty, era)

    return {
        '剧本名称': title,
        '男女频': gender,
        '是否原创': original,
        '题材时代': era,
        '核心演员数': core_roles,
        '群演估算': max(0, int(core_roles*0.6)),
        '场景数量': scenes,
        '预算档位': budget,
        '技术复杂度': tech_s,
        '拍摄难度指数': diff_idx,
        '拍摄难易度': diff_star,
        '题材新颖度': novelty,
        '爆款潜力指数': potential,
        '预算可控性': budget_ctrl,
        '综合优先级分': overall,
    }


def main():
    records = []
    for name in sorted(os.listdir(TXT_DIR)):
        if not name.endswith('.txt'):
            continue
        path = os.path.join(TXT_DIR, name)
        rec = analyze_one(path)
        records.append(rec)
    # 排序：现代剧优先，同分时爆款潜力更高者优先
    records.sort(key=lambda r: (
        0 if r['题材时代']=='现代' else (1 if r['题材时代'].startswith('古代') else 2),
        -r['综合优先级分'],
        -r['爆款潜力指数']
    ))
    # 加上排名
    for i, r in enumerate(records, 1):
        r['排名'] = i
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(records)} records to {OUT_JSON}")


if __name__ == '__main__':
    main()