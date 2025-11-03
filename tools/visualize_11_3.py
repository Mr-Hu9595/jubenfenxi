#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import matplotlib.pyplot as plt

BASE = "/Users/mr.hu/Desktop/爆款排名"
SRC = os.path.join(BASE, 'analysis_results_11.3.json')
OUT_DIR = os.path.join(BASE, '可视化', '11.3')


def ensure_dir(d):
    os.makedirs(d, exist_ok=True)


def setup_font():
    import matplotlib
    plt.rcParams['axes.unicode_minus'] = False
    for candidate in ['PingFang SC', 'Arial Unicode MS', 'Songti SC', 'Noto Sans CJK SC']:
        try:
            matplotlib.font_manager.findfont(candidate, fallback_to_default=False)
            plt.rcParams['font.family'] = candidate
            return
        except Exception:
            continue


def load_records():
    with open(SRC, 'r', encoding='utf-8') as f:
        return json.load(f)


def top15_bar(records):
    ensure_dir(OUT_DIR)
    setup_font()
    # 已按综合优先级排序（现代优先）
    recs = records[:15]
    names = [r['剧本名称'][:12] for r in recs]
    scores = [r['综合优先级分'] for r in recs]
    plt.figure(figsize=(12, 6))
    bars = plt.barh(names, scores, color='#00A59D')
    plt.gca().invert_yaxis()
    plt.xlabel('综合优先级分')
    plt.title('11.3 综合优先级 Top15')
    for b, s in zip(bars, scores):
        plt.text(b.get_width()+1, b.get_y()+b.get_height()/2, str(s), va='center')
    out = os.path.join(OUT_DIR, '综合优先级_Top15.png')
    plt.tight_layout()
    plt.savefig(out, dpi=160)
    plt.close()
    print(f"Saved {out}")


def metrics_hist(records):
    ensure_dir(OUT_DIR)
    setup_font()
    diff = [r['拍摄难度指数'] for r in records]
    pot = [r['爆款潜力指数'] for r in records]
    nov = [r['题材新颖度'] for r in records]
    plt.figure(figsize=(12, 4))
    for i, data in enumerate([diff, pot, nov]):
        plt.subplot(1, 3, i+1)
        plt.hist(data, bins=8, color='#00A59D', edgecolor='white')
        plt.title(['拍摄难度','爆款潜力','题材新颖度'][i])
    out = os.path.join(OUT_DIR, '核心指标分布.png')
    plt.tight_layout()
    plt.savefig(out, dpi=160)
    plt.close()
    print(f"Saved {out}")


def main():
    records = load_records()
    # 维持排序一致（现代优先）
    records.sort(key=lambda r: (
        0 if r['题材时代']=='现代' else (1 if r['题材时代'].startswith('古代') else 2),
        -r['综合优先级分'],
        -r['爆款潜力指数']
    ))
    top15_bar(records)
    metrics_hist(records)


if __name__ == '__main__':
    main()