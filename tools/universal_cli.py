#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
通用 CLI：批量导入剧本文本（txt/docx/pdf），自动填充剧本评估 Excel。

功能概述：
- 递归扫描指定目录或处理单文件，支持 .txt/.docx/.pdf。
- 读取文本后调用现有评估逻辑（fill_row）写入指定工作表。
- 自动补齐关键联动公式（建议集数、分项汇总、人物饱满度、商业价值指数、总分、评分等级）。
- 若目标工作表不存在，将复制“评估输入”的表头创建新表。

使用示例：
python tools/universal_cli.py --input ./scripts --excel \
  "/Users/mr.hu/Desktop/爆款排名/剧本评估表.xlsx" --sheet "通用导入"

注意：
- PDF 解析优先使用 pdfminer.six；如不可用或解析失败，按规则提示提供可解析文本版本。
"""

import os
import sys
import argparse
from typing import List, Tuple

from openpyxl import load_workbook

# 确保可导入同目录下的 auto_score_from_text
HERE = os.path.dirname(__file__)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from auto_score_from_text import fill_row  # 复用已有评分逻辑
except Exception as e:
    print("[错误] 无法导入 auto_score_from_text.fill_row：", e)
    print("请确保在 tools/ 目录内存在 auto_score_from_text.py 并可被导入。")
    sys.exit(1)


def read_txt(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="gbk", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def read_docx(path: str) -> str:
    # 优先使用 python-docx；失败时尝试解压 xml
    try:
        import docx  # type: ignore
        doc = docx.Document(path)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception:
        # 退回使用 zip 解包 word/document.xml
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
            # 简单去标签
            return (
                xml.replace("<w:p>", "\n")
                .replace("</w:p>", "")
                .replace("<w:t>", "")
                .replace("</w:t>", "")
            )
        except Exception:
            return ""


def read_pdf(path: str) -> Tuple[str, str]:
    """
    返回 (文本, 提示)。若无法解析，文本为空并提供提示信息。
    """
    # 优先 pdfminer.six
    try:
        from pdfminer.high_level import extract_text  # type: ignore
        text = extract_text(path) or ""
        if text.strip():
            return text, ""
    except Exception:
        pass

    # 备选 PyMuPDF
    try:
        import fitz  # type: ignore
        doc = fitz.open(path)
        texts = []
        for page in doc:
            texts.append(page.get_text())
        text = "\n".join(texts)
        if text.strip():
            return text, ""
    except Exception:
        pass

    # 备选 pdfplumber
    try:
        import pdfplumber  # type: ignore
        texts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                texts.append(page.extract_text() or "")
        text = "\n".join(texts)
        if text.strip():
            return text, ""
    except Exception:
        pass

    return "", "PDF 解析失败：请提供可解析的 txt/docx 文本版本。"


def collect_files(input_path: str) -> List[str]:
    if os.path.isfile(input_path):
        ext = os.path.splitext(input_path)[1].lower()
        if ext in [".txt", ".docx", ".pdf"]:
            return [input_path]
        return []
    files = []
    for root, _, fnames in os.walk(input_path):
        for fn in fnames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in [".txt", ".docx", ".pdf"]:
                files.append(os.path.join(root, fn))
    files.sort()
    return files


def ensure_sheet(wb, sheet_name: str):
    if sheet_name in wb.sheetnames:
        return wb[sheet_name]
    # 若存在“评估输入”，复制其表头
    headers = None
    if "评估输入" in wb.sheetnames:
        ws_src = wb["评估输入"]
        headers = [ws_src.cell(row=1, column=c).value for c in range(1, ws_src.max_column + 1)]
    ws = wb.create_sheet(title=sheet_name)
    if headers:
        for idx, val in enumerate(headers, start=1):
            ws.cell(row=1, column=idx, value=val)
    else:
        # 兜底最小表头（与模板兼容的关键列）
        base_headers = [
            "序号","剧本名","文本/URL","文本粘贴","字数(千字)","页数","建议集数区间",
            # 中间列将由 fill_row 与公式自动填充
        ]
        for idx, val in enumerate(base_headers, start=1):
            ws.cell(row=1, column=idx, value=val)
    return ws


def apply_formulas(ws, start_row: int, end_row: int):
    for r in range(start_row, end_row + 1):
        # 建议集数区间（G列）：基于 E 列集数
        ws[f"G{r}"] = f'=IF(E{r}<=8,"15–20集",IF(E{r}<=20,"20–30集","30–40集"))'
        # 剧情结构总分（AC）：Y+Z+AA+AB
        ws[f"AC{r}"] = f'=Y{r}+Z{r}+AA{r}+AB{r}'
        # 角色塑造总分（AH）：AD+AE+AF+AG
        ws[f"AH{r}"] = f'=AD{r}+AE{r}+AF{r}+AG{r}'
        # 冲突设置总分（AI）：Q+R+S+T
        ws[f"AI{r}"] = f'=Q{r}+R{r}+S{r}+T{r}'
        # 台词质量总分（AL）：AJ+U+V+W+X
        ws[f"AL{r}"] = f'=AJ{r}+U{r}+V{r}+W{r}+X{r}'
        # 信息密度副本（AK）：与 U 列保持一致，供台词计算与视图使用
        ws[f"AK{r}"] = f'=U{r}'
        # 制作总分（AS）：场景数量与演员结构，封顶 15 分
        ws[f"AS{r}"] = f'=MIN(15,L{r}+M{r})'
        # 宣发总分（AW）：受众定位/上线时间/营销方向，封顶 10 分
        ws[f"AW{r}"] = f'=MIN(10,AT{r}+AU{r}+AV{r})'
        # 人物饱满度标签（AR）：按 AQ 分数映射 高/中/低
        ws[f"AR{r}"] = f'=IF(AQ{r}>=67,"高",IF(AQ{r}>=34,"中","低"))'
        # 人物饱满度（AQ）：按 AM/AN/AO/AP 权重 8/6/4/2，总计 20 分
        ws[f"AQ{r}"] = (
            f'=ROUND((MIN(AM{r},10)/10*8)+'
            f'(MIN(AN{r},10)/10*6)+'
            f'(MIN(AO{r},10)/10*4)+'
            f'(MIN(AP{r},10)/10*2),2)'
        )
        # 商业价值指数（BB）：AX/AY/AZ/BA 加权归一到 0–100
        ws[f"BB{r}"] = (
            f'=ROUND((AX{r}/2*0.4 + AY{r}/1.5*0.3 + AZ{r}/1*0.2 + BA{r}/0.5*0.1)*100,2)'
        )
        # 总分（BC）：内容四项 + 人物饱满度 + 制作 + 宣发 + 商业价值指数的 5%
        ws[f"BC{r}"] = (
            f'=ROUND(AC{r}+AH{r}+AI{r}+AL{r}+AQ{r}+AS{r}+AW{r}+(BB{r}/100*5),2)'
        )
        # 评分等级（BD）：区间映射
        ws[f"BD{r}"] = (
            f'=IF(BC{r}<=20,"极弱",IF(BC{r}<=40,"偏弱",IF(BC{r}<=60,"中等",IF(BC{r}<=80,"较强","卓越"))))'
        )


def main():
    parser = argparse.ArgumentParser(description="剧本评估通用导入 CLI")
    parser.add_argument("--input", required=True, help="输入路径（文件或目录），支持 .txt/.docx/.pdf")
    parser.add_argument(
        "--excel",
        default="/Users/mr.hu/Desktop/爆款排名/剧本评估表.xlsx",
        help="目标 Excel 文件路径",
    )
    parser.add_argument("--sheet", default="通用导入", help="目标工作表名，不存在则自动创建")
    args = parser.parse_args()

    files = collect_files(args.input)
    if not files:
        print("[提示] 未发现可处理的文件（支持 .txt/.docx/.pdf）。")
        sys.exit(0)

    print(f"[信息] 即将处理 {len(files)} 个文件，写入工作表：{args.sheet}")

    wb = load_workbook(args.excel)
    ws = ensure_sheet(wb, args.sheet)

    start_row = ws.max_row + 1 if ws.max_row >= 2 else 2
    cur_row = start_row
    pdf_failures = []

    for idx, path in enumerate(files, start=1):
        name = os.path.splitext(os.path.basename(path))[0]
        ext = os.path.splitext(path)[1].lower()
        text = ""
        tip = ""
        if ext == ".txt":
            text = read_txt(path)
        elif ext == ".docx":
            text = read_docx(path)
        elif ext == ".pdf":
            text, tip = read_pdf(path)
        else:
            continue

        # 写入基础信息
        ws.cell(row=cur_row, column=1, value=cur_row - 1)  # 序号
        ws.cell(row=cur_row, column=2, value=name)         # 剧本名
        ws.cell(row=cur_row, column=3, value=path)         # 文本/URL
        ws.cell(row=cur_row, column=4, value=text)         # 文本粘贴

        # 调用现有评分逻辑填充各项指标
        try:
            fill_row(ws, cur_row, name, text)
        except Exception as e:
            print(f"[警告] 行 {cur_row} 填充失败：{e}")

        if ext == ".pdf" and tip:
            pdf_failures.append((path, tip))

        cur_row += 1

    # 补齐公式联动：为稳健起见，统一对整张工作表(自第2行至当前最大行)回填一次，
    # 可避免已有数据在外部编辑后出现公式缺失的情况。
    end_row = ws.max_row
    apply_formulas(ws, 2, end_row)
    wb.save(args.excel)

    print(f"[完成] 已写入 {end_row - start_row + 1} 行到工作表：{args.sheet}")
    if pdf_failures:
        print("[提示] 以下 PDF 未能解析，请改用 txt/docx：")
        for p, t in pdf_failures:
            print(f" - {p}：{t}")


if __name__ == "__main__":
    main()