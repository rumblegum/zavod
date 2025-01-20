# database.py
import sqlite3
import datetime
from config import DEPARTMENTS, ROLE_ADMIN, ROLE_LEADER, ROLE_WORKER, OLD_DATA_RETENTION_DAYS

# Инициализация / создание таблиц
def init_db(db_path="factory.db"):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()

    # Создаём таблицы (если не существуют)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        full_name TEXT,
        role TEXT,        -- 'worker' | 'leader' | 'admin'
        department TEXT,  -- 'Пекарня' | 'Кондитерка' | ...
        approved INTEGER DEFAULT 0   -- 0: не подтверждён, 1: подтверждён
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dishes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        category TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER,
        from_department TEXT,
        to_department TEXT,
        dish_id INTEGER,
        quantity REAL,
        label_date TEXT,           -- Дата на этикетке (если нужно)
        created_at TEXT,
        accepted_at TEXT,
        status TEXT DEFAULT 'pending',  -- 'pending' | 'accepted' | 'rejected' | 'auto_done'
        FOREIGN KEY (from_user_id) REFERENCES users (id),
        FOREIGN KEY (dish_id) REFERENCES dishes (id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        timestamp TEXT
    )
    """)

    conn.commit()
    return conn


# Функции для работы с БД

def log_action(conn, user_id: int, action: str):
    """Логирует действие пользователя (user_id, action, timestamp)."""
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.execute("INSERT INTO logs (user_id, action, timestamp) VALUES (?, ?, ?)",
                   (user_id, action, now))
    conn.commit()

def get_user_by_telegram_id(conn, telegram_id: int):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    return cursor.fetchone()  # (id, telegram_id, full_name, role, department, approved)

def create_user(conn, telegram_id, full_name, role, department, approved=0):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (telegram_id, full_name, role, department, approved)
        VALUES (?, ?, ?, ?, ?)
    """, (telegram_id, full_name, role, department, approved))
    conn.commit()

def approve_user(conn, user_id: int):
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET approved=1 WHERE id=?", (user_id,))
    conn.commit()

def set_user_role(conn, user_id: int, role: str):
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    conn.commit()

def get_all_pending_users(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, role, department FROM users WHERE approved=0")
    return cursor.fetchall()

def get_user(conn, user_id: int):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
    return cursor.fetchone()

def is_approved(conn, user_id: int):
    cursor = conn.cursor()
    cursor.execute("SELECT approved FROM users WHERE id=?", (user_id,))
    row = cursor.fetchone()
    if row and row[0] == 1:
        return True
    return False

def get_role(conn, user_id: int):
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE id=?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else None

def add_dish(conn, name: str, category: str):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO dishes (name, category) VALUES (?, ?)", (name, category))
    conn.commit()

def get_all_dishes(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category FROM dishes")
    return cursor.fetchall()

def create_transaction(conn, from_user_id, from_dep, to_dep, dish_id, qty, label_date, status):
    cursor = conn.cursor()
    now_str = datetime.datetime.now().isoformat()
    accepted_at = None
    if status in ["auto_done", "accepted"]:  # Если авто-завершение
        accepted_at = now_str

    cursor.execute("""
        INSERT INTO transactions 
        (from_user_id, from_department, to_department, dish_id, quantity, label_date, created_at, accepted_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (from_user_id, from_dep, to_dep, dish_id, qty, label_date, now_str, accepted_at, status))
    conn.commit()
    return cursor.lastrowid

def get_pending_transactions_for_department(conn, department):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, d.name, t.quantity, t.from_department, t.label_date
        FROM transactions t
        JOIN dishes d ON t.dish_id = d.id
        WHERE t.to_department=? AND t.status='pending'
    """, (department,))
    return cursor.fetchall()

def accept_transaction(conn, trans_id: int):
    cursor = conn.cursor()
    now_str = datetime.datetime.now().isoformat()
    cursor.execute("""
        UPDATE transactions 
        SET status='accepted', accepted_at=? 
        WHERE id=?
    """, (now_str, trans_id))
    conn.commit()

def reject_transaction(conn, trans_id: int):
    cursor = conn.cursor()
    cursor.execute("UPDATE transactions SET status='rejected' WHERE id=?", (trans_id,))
    conn.commit()

def get_transactions_by_date(conn, date_str=None):
    """Пример для получения транзакций за конкретную дату (YYYY-MM-DD).
       Если date_str не задана, возвращает все.
    """
    cursor = conn.cursor()
    if date_str:
        cursor.execute("""
            SELECT t.id, t.from_department, t.to_department, d.name, t.quantity, 
                   t.label_date, t.created_at, t.accepted_at, t.status
            FROM transactions t
            JOIN dishes d ON t.dish_id = d.id
            WHERE substr(t.created_at, 1, 10)=?
            ORDER BY t.id DESC
        """, (date_str,))
    else:
        cursor.execute("""
            SELECT t.id, t.from_department, t.to_department, d.name, t.quantity, 
                   t.label_date, t.created_at, t.accepted_at, t.status
            FROM transactions t
            JOIN dishes d ON t.dish_id = d.id
            ORDER BY t.id DESC
        """)
    return cursor.fetchall()

def cleanup_old_data(conn):
    """Пример очистки старых транзакций, если нужно.
       Удаляем записи старше N дней (OLD_DATA_RETENTION_DAYS) из transactions и logs.
    """
    cursor = conn.cursor()
    now = datetime.datetime.now()
    delta = datetime.timedelta(days=OLD_DATA_RETENTION_DAYS)
    cutoff_date = now - delta

    # Превратим cutoff_date в строку YYYY-MM-DD
    cutoff_str = cutoff_date.isoformat()  # 2025-01-19T14:40:00....
    # Обрежем до даты, если хотим сравнивать только по дате
    cutoff_date_str = cutoff_str.split("T")[0]  # "2025-01-19"

    # Удаляем транзакции, у которых created_at < cutoff_date
    cursor.execute("""
        DELETE FROM transactions
        WHERE substr(created_at, 1, 10) < ?
    """, (cutoff_date_str,))

    # Удаляем логи старые
    cursor.execute("""
        DELETE FROM logs
        WHERE substr(timestamp, 1, 10) < ?
    """, (cutoff_date_str,))

    conn.commit()
