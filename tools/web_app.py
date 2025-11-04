#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import shutil
from typing import List

from flask import Flask, request, render_template, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from openpyxl import load_workbook


BASE_DIR = os.getcwd()
DEFAULT_EXCEL = os.environ.get('EXCEL_PATH') or os.path.join(BASE_DIR, '剧本评估表.xlsx')
DEFAULT_SHEET = os.environ.get('SHEET_NAME') or '通用导入'
UPLOAD_DIR = os.environ.get('UPLOAD_DIR') or os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXT = {'.txt', '.docx', '.pdf'}

# 允许直接导入 tools 目录下的脚本
TOOLS_DIR = os.path.join(BASE_DIR, 'tools')
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import universal_cli as uni  # 复用读取与公式函数
from auto_score_from_text import fill_row  # 复用评分填充逻辑


def resource_path(*parts):
    """PyInstaller 兼容的数据路径解析。"""
    base = getattr(sys, '_MEIPASS', None)
    if base:
        return os.path.join(base, *parts)
    return os.path.join(BASE_DIR, *parts)

def ensure_excel_file(excel_path: str):
    """如果指定 Excel 文件不存在，尝试从资源目录复制一份模板。"""
    try:
        if not os.path.exists(excel_path):
            src = resource_path('剧本评估表.xlsx')
            if os.path.exists(src):
                os.makedirs(os.path.dirname(excel_path), exist_ok=True)
                shutil.copyfile(src, excel_path)
    except Exception as e:
        print(f"[警告] 默认 Excel 初始化失败: {e}")


# 指定模板目录，兼容打包后的目录结构
TEMPLATES_DIR = resource_path('tools', 'templates')
app = Flask(__name__, template_folder=TEMPLATES_DIR)


def allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXT


def ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def process_files(files: List[str], excel_path: str, sheet_name: str) -> int:
    wb = load_workbook(excel_path)
    ws = uni.ensure_sheet(wb, sheet_name)
    start_row = ws.max_row + 1 if ws.max_row >= 2 else 2
    cur_row = start_row
    count = 0

    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        ext = os.path.splitext(path)[1].lower()
        text = ''
        tip = ''
        if ext == '.txt':
            text = uni.read_txt(path)
        elif ext == '.docx':
            text = uni.read_docx(path)
        elif ext == '.pdf':
            text, tip = uni.read_pdf(path)
        if not text and ext == '.pdf':
            # PDF 解析失败则跳过并在界面提示
            print(f"[提示] PDF 解析失败：{path}，请提供 txt/docx 版本")
            continue

        # 基础字段
        ws.cell(row=cur_row, column=1, value=cur_row - 1)  # 序号
        ws.cell(row=cur_row, column=2, value=name)         # 剧本名
        ws.cell(row=cur_row, column=3, value=path)         # 文本/URL
        ws.cell(row=cur_row, column=4, value=text)         # 文本粘贴

        try:
            fill_row(ws, cur_row, name, text)
        except Exception as e:
            print(f"[警告] 行 {cur_row} 填充失败：{e}，文本长度={len(text)}")

        # 只为当前行写入联动公式
        uni.apply_formulas(ws, cur_row, cur_row)

        cur_row += 1
        count += 1

    wb.save(excel_path)
    return count


@app.route('/', methods=['GET'])
def index():
    # 默认首页切换为品牌页“星河无限”
    excel_path = request.args.get('excel', DEFAULT_EXCEL)
    sheet_name = request.args.get('sheet', DEFAULT_SHEET)
    ensure_excel_file(excel_path)
    return render_template('nebula.html', excel_path=excel_path, sheet_name=sheet_name)


@app.route('/nebula', methods=['GET'])
def nebula_home():
    """品牌首页：星河无限。提供引导与跳转。"""
    excel_path = request.args.get('excel', DEFAULT_EXCEL)
    sheet_name = request.args.get('sheet', DEFAULT_SHEET)
    ensure_excel_file(excel_path)
    return render_template('nebula.html', excel_path=excel_path, sheet_name=sheet_name)


@app.route('/app', methods=['GET'])
def app_upload_form():
    """上传入口（原首页上传页）。"""
    excel_path = request.args.get('excel', DEFAULT_EXCEL)
    sheet_name = request.args.get('sheet', DEFAULT_SHEET)
    ensure_excel_file(excel_path)
    return render_template('index.html', excel_path=excel_path, sheet_name=sheet_name)


@app.route('/upload', methods=['POST'])
def upload():
    excel_path = request.form.get('excel_path', DEFAULT_EXCEL)
    sheet_name = request.form.get('sheet_name', DEFAULT_SHEET)
    ensure_upload_dir()
    ensure_excel_file(excel_path)

    saved_paths = []
    files = request.files.getlist('files')
    for f in files:
        filename = secure_filename(f.filename)
        if not filename or not allowed_file(filename):
            continue
        ts = int(time.time()*1000)
        out_path = os.path.join(UPLOAD_DIR, f"{ts}_{filename}")
        f.save(out_path)
        saved_paths.append(out_path)

    if not saved_paths:
        return "未选择有效文件（仅支持 .txt/.docx/.pdf）", 400

    count = process_files(saved_paths, excel_path, sheet_name)
    return redirect(url_for('preview', excel=excel_path, sheet=sheet_name, added=count))


def sheet_to_rows(excel_path: str, sheet_name: str, max_rows: int = 50, max_cols: int = 30):
    # 注意：openpyxl 不计算公式，预览将显示已有值或公式文本
    wb = load_workbook(excel_path, data_only=False)
    if sheet_name not in wb.sheetnames:
        return ["工作表不存在"], []
    ws = wb[sheet_name]
    n_rows = min(ws.max_row, max_rows)
    n_cols = min(ws.max_column, max_cols)
    header = [ws.cell(row=1, column=c).value for c in range(1, n_cols + 1)]
    data = []
    for r in range(2, n_rows + 1):
        row = []
        for c in range(1, n_cols + 1):
            cell = ws.cell(row=r, column=c)
            # 如果是公式，展示公式文本
            v = cell.value
            row.append(v)
        data.append(row)
    return header, data


@app.route('/preview', methods=['GET'])
def preview():
    excel_path = request.args.get('excel', DEFAULT_EXCEL)
    sheet_name = request.args.get('sheet', DEFAULT_SHEET)
    added = int(request.args.get('added', '0'))
    ensure_excel_file(excel_path)
    header, data = sheet_to_rows(excel_path, sheet_name)
    return render_template('preview.html', excel_path=excel_path, sheet_name=sheet_name, added=added, header=header, data=data)


@app.route('/download', methods=['GET'])
def download():
    excel_path = request.args.get('excel', DEFAULT_EXCEL)
    ensure_excel_file(excel_path)
    fname = os.path.basename(excel_path)
    return send_file(excel_path, as_attachment=True, download_name=fname)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)