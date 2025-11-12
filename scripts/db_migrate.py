import os
import sys
import sqlite3
import argparse
from werkzeug.security import generate_password_hash


def db_path() -> str:
    base = os.environ.get('DATA_DIR') or os.getcwd()
    d = os.path.join(base, 'system')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'nebula.db')


def ensure_is_admin_column(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(users)")
    cols = [r[1] for r in cur.fetchall()]
    if 'is_admin' not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
        conn.commit()


def set_admin_by_id(conn: sqlite3.Connection, uid: int):
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_admin=1 WHERE id=?", (uid,))
    conn.commit()


def set_admin_by_username(conn: sqlite3.Connection, username: str):
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_admin=1 WHERE username=?", (username,))
    conn.commit()


def set_password_by_id(conn: sqlite3.Connection, uid: int, new_password: str):
    cur = conn.cursor()
    pwd_hash = generate_password_hash(new_password)
    cur.execute("UPDATE users SET password_hash=? WHERE id=?", (pwd_hash, uid))
    conn.commit()


def set_password_by_username(conn: sqlite3.Connection, username: str, new_password: str):
    cur = conn.cursor()
    pwd_hash = generate_password_hash(new_password)
    cur.execute("UPDATE users SET password_hash=? WHERE username=?", (pwd_hash, username))
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Nebula DB Migration')
    parser.add_argument('--user-id', type=int, help='将指定用户ID设为管理员/更新密码')
    parser.add_argument('--username', type=str, help='将指定用户名设为管理员/更新密码')
    parser.add_argument('--set-password', type=str, help='为指定用户设置新密码')
    args = parser.parse_args()

    path = db_path()
    print(f"Using DB at: {path}")
    conn = sqlite3.connect(path)
    try:
        ensure_is_admin_column(conn)
        if args.user_id:
            set_admin_by_id(conn, int(args.user_id))
            print(f"Admin set by id: {args.user_id}")
            if args.set_password:
                set_password_by_id(conn, int(args.user_id), args.set_password)
                print("Password updated by id.")
        elif args.username:
            set_admin_by_username(conn, args.username)
            print(f"Admin set by username: {args.username}")
            if args.set_password:
                set_password_by_username(conn, args.username, args.set_password)
                print("Password updated by username.")
        else:
            print("No user specified; ensured is_admin column only.")
    finally:
        conn.close()
    print("Migration complete.")


if __name__ == '__main__':
    main()