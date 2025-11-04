#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import shutil
import json
import sqlite3
from typing import List, Optional, Dict

from flask import Flask, request, render_template, redirect, url_for, send_file, session
from werkzeug.utils import secure_filename
from openpyxl import load_workbook
from uuid import uuid4
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash


BASE_DIR = os.getcwd()
DEFAULT_EXCEL = os.environ.get('EXCEL_PATH') or os.path.join(BASE_DIR, '剧本评估表.xlsx')
DEFAULT_SHEET = os.environ.get('SHEET_NAME') or '工作表1'
UPLOAD_DIR = os.environ.get('UPLOAD_DIR') or os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXT = {'.txt', '.docx', '.pdf'}
DB_PATH = os.path.join(BASE_DIR, 'nebula.db')
DATA_DIR = os.environ.get('DATA_DIR') or BASE_DIR
MAX_FILES = int(os.environ.get('MAX_FILES', '100'))

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
# 会话隔离所需的密钥（生产环境建议通过环境变量 SECRET_KEY 设置）
app.secret_key = os.environ.get('SECRET_KEY', 'nebula-secret-key-change-me')
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # 如启用 HTTPS 可改为 True


# -------------------- 账号与操作留存（SQLite） --------------------

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                detail TEXT,
                ts INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_user_by_username(username: str) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, password_hash FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "email": row[2], "password_hash": row[3]}


def get_user_by_id(uid: int) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, username, email FROM users WHERE id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "email": row[2]}


def create_user(username: str, password: str, email: str = "") -> int:
    pwd_hash = generate_password_hash(password)
    ts = int(time.time())
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (username, email, pwd_hash, ts),
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def log_action(action: str, detail: dict = None):
    uid = session.get('user_id')
    if not uid:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO operations (user_id, action, detail, ts) VALUES (?, ?, ?, ?)",
        (uid, action, json.dumps(detail or {}), int(time.time())),
    )
    conn.commit()
    conn.close()


def current_user() -> Optional[Dict]:
    uid = session.get('user_id')
    if not uid:
        return None
    return get_user_by_id(int(uid))


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            nxt = request.path
            return redirect(url_for('login', next=nxt))
        return fn(*args, **kwargs)
    return wrapper


def allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXT


def ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_session_id() -> str:
    sid = session.get('sid')
    if not sid:
        sid = uuid4().hex
        session['sid'] = sid
    return sid


def get_session_dir() -> str:
    # 优先使用账号ID实现账号级隔离；未登录则退回会话ID
    uid = session.get('user_id')
    base_id = str(uid) if uid else get_session_id()
    # 将会话数据持久化到可挂载的数据目录（容器中默认 /data）
    d = os.path.join(DATA_DIR, 'user_data', base_id)
    os.makedirs(d, exist_ok=True)
    return d


def ensure_user_upload_dir() -> str:
    uid = session.get('user_id')
    base_id = str(uid) if uid else get_session_id()
    d = os.path.join(UPLOAD_DIR, base_id)
    os.makedirs(d, exist_ok=True)
    return d


def session_excel_path() -> str:
    """为当前会话/账号提供独立的 Excel 文件路径并确保存在。"""
    user_dir = get_session_dir()
    path = os.path.join(user_dir, '剧本评估表.xlsx')
    ensure_excel_file(path)
    session['excel_path'] = path
    return path


def process_files(files: List[str], excel_path: str, sheet_name: str) -> int:
    wb = load_workbook(excel_path)
    ws = uni.ensure_sheet(wb, sheet_name)
    start_row = ws.max_row + 1 if ws.max_row >= 2 else 2
    cur_row = start_row
    count = 0

    # 单次最多处理 MAX_FILES 个，超出部分提示并忽略
    if len(files) > MAX_FILES:
        print(f"[提示] 本次仅处理前 {MAX_FILES} 个文件，其余 {len(files) - MAX_FILES} 个请分批上传。")
    files_to_process = files[:MAX_FILES]

    for path in files_to_process:
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
    excel_path = session.get('excel_path') or session_excel_path()
    sheet_name = request.args.get('sheet', DEFAULT_SHEET)
    ensure_excel_file(excel_path)
    return render_template('nebula.html', excel_path=excel_path, sheet_name=sheet_name, user=current_user())


@app.route('/nebula', methods=['GET'])
def nebula_home():
    """品牌首页：星河无限。提供引导与跳转。"""
    excel_path = session.get('excel_path') or session_excel_path()
    sheet_name = request.args.get('sheet', DEFAULT_SHEET)
    ensure_excel_file(excel_path)
    return render_template('nebula.html', excel_path=excel_path, sheet_name=sheet_name, user=current_user())


@app.route('/app', methods=['GET'])
@login_required
def app_upload_form():
    """上传入口（原首页上传页）。"""
    excel_path = session.get('excel_path') or session_excel_path()
    sheet_name = request.args.get('sheet', DEFAULT_SHEET)
    ensure_excel_file(excel_path)
    return render_template('index.html', excel_path=excel_path, sheet_name=sheet_name, user=current_user())


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    # 强制使用当前会话的独立 Excel，避免跨用户干扰
    excel_path = session.get('excel_path') or session_excel_path()
    sheet_name = request.form.get('sheet_name', DEFAULT_SHEET)
    # 使用会话独立上传目录
    user_upload_dir = ensure_user_upload_dir()
    ensure_excel_file(excel_path)

    saved_paths = []
    files = request.files.getlist('files')
    for f in files:
        filename = secure_filename(f.filename)
        if not filename or not allowed_file(filename):
            continue
        ts = int(time.time()*1000)
        out_path = os.path.join(user_upload_dir, f"{ts}_{filename}")
        f.save(out_path)
        saved_paths.append(out_path)

    if not saved_paths:
        return "未选择有效文件（仅支持 .txt/.docx/.pdf）", 400

    count = process_files(saved_paths, excel_path, sheet_name)
    log_action('upload', {'files': saved_paths, 'count': count, 'sheet': sheet_name})
    # 预览与下载均读取当前会话的 Excel，不再依赖外部传入路径
    return redirect(url_for('preview', sheet=sheet_name, added=count))


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
@login_required
def preview():
    excel_path = session.get('excel_path') or session_excel_path()
    sheet_name = request.args.get('sheet', DEFAULT_SHEET)
    added = int(request.args.get('added', '0'))
    ensure_excel_file(excel_path)
    header, data = sheet_to_rows(excel_path, sheet_name)
    log_action('preview', {'sheet': sheet_name, 'rows': len(data)})
    return render_template('preview.html', excel_path=excel_path, sheet_name=sheet_name, added=added, header=header, data=data, user=current_user())


@app.route('/download', methods=['GET'])
@login_required
def download():
    excel_path = session.get('excel_path') or session_excel_path()
    ensure_excel_file(excel_path)
    fname = os.path.basename(excel_path)
    log_action('download', {'file': fname})
    return send_file(excel_path, as_attachment=True, download_name=fname)


# -------------------- 认证路由 --------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    init_db()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        nxt = request.args.get('next') or url_for('app_upload_form')
        user = get_user_by_username(username)
        if not user or not check_password_hash(user['password_hash'], password):
            return render_template('login.html', error='用户名或密码错误', user=current_user(), next=request.args.get('next', ''))
        session.clear()
        session['user_id'] = int(user['id'])
        session_excel_path()
        log_action('login', {'username': username})
        return redirect(nxt)
    return render_template('login.html', user=current_user(), next=request.args.get('next', ''))


@app.route('/register', methods=['GET', 'POST'])
def register():
    init_db()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        email = request.form.get('email', '').strip()
        if not username or not password:
            return render_template('register.html', error='用户名与密码必填', user=current_user())
        if get_user_by_username(username):
            return render_template('register.html', error='用户名已存在', user=current_user())
        uid = create_user(username, password, email)
        session.clear()
        session['user_id'] = int(uid)
        session_excel_path()
        log_action('register', {'username': username, 'email': email})
        return redirect(url_for('app_upload_form'))
    return render_template('register.html', user=current_user())


@app.route('/logout', methods=['GET'])
def logout():
    # 先记录操作再清理会话
    log_action('logout')
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=5000, debug=False)