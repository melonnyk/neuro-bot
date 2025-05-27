# db.py
import sqlite3

conn = sqlite3.connect('data.db', check_same_thread=False)
cur = conn.cursor()

# Таблица пунктов меню с категорией
cur.execute("""
CREATE TABLE IF NOT EXISTS menu_items (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  category TEXT    NOT NULL,   -- категория пункта
  name     TEXT    NOT NULL,
  kind     TEXT    NOT NULL,   -- 'file' или 'url'
  value    TEXT    NOT NULL    -- file_id или ссылка
)
""")
conn.commit()

def add_item(category, name, kind, value):
    cur.execute(
        "INSERT OR IGNORE INTO menu_items(category,name,kind,value) VALUES (?,?,?,?)",
        (category, name, kind, value)
    )
    conn.commit()

def list_categories():
    cur.execute("SELECT DISTINCT category FROM menu_items ORDER BY category")
    return [row[0] for row in cur.fetchall()]

def list_items(category):
    cur.execute(
        "SELECT id,name,kind,value FROM menu_items WHERE category=? ORDER BY id",
        (category,)
    )
    return cur.fetchall()

def get_item(item_id):
    cur.execute("SELECT name,kind,value FROM menu_items WHERE id=?", (item_id,))
    return cur.fetchone()

def delete_item(item_id):
    cur.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
    conn.commit()

def update_item(item_id, name=None, kind=None, value=None, category=None):
    # Собираем части запроса
    parts = []
    params = []
    if category is not None:
        parts.append("category=?"); params.append(category)
    if name is not None:
        parts.append("name=?");     params.append(name)
    if kind is not None:
        parts.append("kind=?");     params.append(kind)
    if value is not None:
        parts.append("value=?");    params.append(value)
    if not parts:
        return
    params.append(item_id)
    sql = f"UPDATE menu_items SET {', '.join(parts)} WHERE id=?"
    cur.execute(sql, params)
    conn.commit()

def list_all_items():
    # возвращаем id, категорию, имя и тип каждого пункта
    cur.execute("SELECT id, category, name, kind FROM menu_items ORDER BY category, id")
    return cur.fetchall()

