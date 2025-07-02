# db.py
import logging
import aiosqlite
from config import DB_NAME

logger = logging.getLogger(__name__)

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_date TEXT NOT NULL,
                plan_topic TEXT NOT NULL,
                plan_text TEXT NOT NULL,
                is_completed INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                reminder_datetime TEXT,
                is_reminder_sent INTEGER DEFAULT 0,
                is_archived INTEGER DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                telegram_file_id TEXT NOT NULL,
                original_file_name TEXT,
                file_type TEXT,
                category TEXT DEFAULT 'Без категории',
                upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_processed_for_chunks INTEGER DEFAULT 0,
                plan_id INTEGER,
                FOREIGN KEY (plan_id) REFERENCES plans (id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS file_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_file_id INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                chunk_order INTEGER NOT NULL,
                FOREIGN KEY (user_file_id) REFERENCES user_files (id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL UNIQUE,
                currency TEXT NOT NULL DEFAULT 'UZS',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                category TEXT,
                transaction_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                check_url TEXT UNIQUE,
                FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
            )
            """
        )
        await db.commit()
    logger.info(f"База данных '{DB_NAME}' инициализирована со всеми таблицами.")

async def check_if_url_exists(check_url: str) -> bool:
    """Проверяет, существует ли транзакция с таким URL чека."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT 1 FROM transactions WHERE check_url = ?", (check_url,))
        return await cursor.fetchone() is not None

async def add_transaction(user_id: int, book_id: int, type: str, amount: float, description: str = None, category: str = None, transaction_date: str = None, check_url: str = None) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO transactions (user_id, book_id, type, amount, description, category, transaction_date, check_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
            (user_id, book_id, type, amount, description, category, transaction_date, check_url)
        )
        await db.commit()
        return cursor.lastrowid

# ... (остальной код файла без изменений)
async def update_file_category(file_id: int, user_id: int, category: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("UPDATE user_files SET category = ? WHERE id = ? AND user_id = ?", (category, file_id, user_id))
        await db.commit()
        return cursor.rowcount > 0

async def update_file_name(file_id: int, user_id: int, new_name: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("UPDATE user_files SET original_file_name = ? WHERE id = ? AND user_id = ?", (new_name, file_id, user_id))
        await db.commit()
        return cursor.rowcount > 0

async def get_file_categories(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT DISTINCT category FROM user_files WHERE user_id = ? ORDER BY category", (user_id,))
        return await cursor.fetchall()

async def get_files_by_category(user_id: int, category: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, original_file_name, file_type, upload_date FROM user_files WHERE user_id = ? AND category = ? ORDER BY upload_date DESC", (user_id, category))
        return await cursor.fetchall()

async def get_user_file_by_id(user_id: int, file_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM user_files WHERE id = ? AND user_id = ?", (file_id, user_id))
        return await cursor.fetchone()

async def get_files_by_search_query(user_id: int, query: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, original_file_name, category FROM user_files WHERE user_id = ? AND original_file_name LIKE ? ORDER BY upload_date DESC", (user_id, f"%{query}%"))
        return await cursor.fetchall()

async def delete_files_by_ids(user_id: int, file_ids: list[int]) -> int:
    """Удаляет файлы и связанные с ними чанки по списку ID."""
    deleted_count = 0
    async with aiosqlite.connect(DB_NAME) as db:
        for file_id in file_ids:
            # Сначала удаляем связанные чанки
            await db.execute("DELETE FROM file_chunks WHERE user_file_id = ?", (file_id,))
            # Затем удаляем сам файл
            cursor = await db.execute("DELETE FROM user_files WHERE id = ? AND user_id = ?", (file_id, user_id))
            if cursor.rowcount > 0:
                deleted_count += 1
        await db.commit()
    return deleted_count

async def delete_category_by_name(user_id: int, category: str) -> int:
    """Удаляет все файлы в указанной категории."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # Находим все файлы в этой категории
        cursor_files = await db.execute("SELECT id FROM user_files WHERE user_id = ? AND category = ?", (user_id, category))
        file_ids = [row['id'] for row in await cursor_files.fetchall()]
        
        if not file_ids:
            return 0
        
        # Создаем строку с плейсхолдерами '?' для SQL-запроса
        placeholders = ','.join('?' for _ in file_ids)
        
        # Удаляем все чанки для этих файлов
        await db.execute(f"DELETE FROM file_chunks WHERE user_file_id IN ({placeholders})", file_ids)
        
        # Удаляем сами файлы
        cursor_delete = await db.execute(f"DELETE FROM user_files WHERE id IN ({placeholders}) AND user_id = ?", (*file_ids, user_id))
        
        await db.commit()
        return cursor_delete.rowcount

async def add_plan_to_db(user_id: int, plan_date_str: str, plan_topic: str, plan_text: str, reminder_datetime: str = None) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("INSERT INTO plans (user_id, plan_date, plan_topic, plan_text, reminder_datetime) VALUES (?, ?, ?, ?, ?)", (user_id, plan_date_str, plan_topic, plan_text, reminder_datetime))
        await db.commit(); return cursor.lastrowid

async def get_plans_for_date(user_id: int, date_str: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; cursor = await db.execute("SELECT * FROM plans WHERE user_id = ? AND plan_date = ? ORDER BY id", (user_id, date_str)); return await cursor.fetchall()

async def get_all_user_plans(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; cursor = await db.execute("SELECT * FROM plans WHERE user_id = ? ORDER BY plan_date ASC, id ASC", (user_id,)); return await cursor.fetchall()

async def get_plan_by_id(user_id: int, plan_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; cursor = await db.execute("SELECT * FROM plans WHERE id = ? AND user_id = ?", (plan_id, user_id)); return await cursor.fetchone()

async def get_attachments_for_plan(plan_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; cursor = await db.execute("SELECT telegram_file_id, file_type FROM user_files WHERE plan_id = ?", (plan_id,)); return await cursor.fetchall()

async def get_transactions_by_book(user_id: int, book_id: int, transaction_type: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; query = "SELECT * FROM transactions WHERE user_id = ? AND book_id = ?"; params = (user_id, book_id)
        if transaction_type: query += " AND type = ?"; params += (transaction_type,)
        query += " ORDER BY transaction_date DESC"; cursor = await db.execute(query, params); return await cursor.fetchall()

async def get_book_balance_summary(user_id: int, book_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        inc_cursor = await db.execute("SELECT SUM(amount) AS total FROM transactions WHERE user_id = ? AND book_id = ? AND type = 'income'", (user_id, book_id)); total_income = (await inc_cursor.fetchone())['total'] or 0.0
        exp_cursor = await db.execute("SELECT SUM(amount) AS total FROM transactions WHERE user_id = ? AND book_id = ? AND type = 'expense'", (user_id, book_id)); total_expense = (await exp_cursor.fetchone())['total'] or 0.0
        return total_income, total_expense

async def add_book(user_id: int, name: str, currency: str = 'UZS') -> int:
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("INSERT INTO books (user_id, name, currency) VALUES (?, ?, ?)", (user_id, name, currency)); await db.commit(); return cursor.lastrowid
    except aiosqlite.IntegrityError: return None

async def get_user_books(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; cursor = await db.execute("SELECT * FROM books WHERE user_id = ? ORDER BY name ASC", (user_id,)); return await cursor.fetchall()

async def get_book_by_id(user_id: int, book_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; cursor = await db.execute("SELECT * FROM books WHERE id = ? AND user_id = ?", (book_id, user_id)); return await cursor.fetchone()

async def delete_book(user_id: int, book_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM books WHERE id = ? AND user_id = ?", (book_id, user_id)); await db.commit(); return cursor.rowcount > 0

async def update_book_currency(user_id: int, book_id: int, new_currency: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("UPDATE books SET currency = ? WHERE id = ? AND user_id = ?", (new_currency, book_id, user_id)); await db.commit(); return cursor.rowcount > 0

async def update_book_name(user_id: int, book_id: int, new_name: str) -> bool:
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("UPDATE books SET name = ? WHERE id = ? AND user_id = ?", (new_name, book_id, user_id)); await db.commit(); return cursor.rowcount > 0
    except aiosqlite.IntegrityError: return False

async def get_transaction_by_id(user_id: int, transaction_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; cursor = await db.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, user_id)); return await cursor.fetchone()

async def update_transaction(user_id: int, transaction_id: int, field: str, value):
    async with aiosqlite.connect(DB_NAME) as db:
        if field not in ['type', 'amount', 'description', 'category', 'transaction_date']: return False
        cursor = await db.execute(f"UPDATE transactions SET {field} = ? WHERE id = ? AND user_id = ?", (value, transaction_id, user_id)); await db.commit(); return cursor.rowcount > 0

async def delete_transaction(user_id: int, transaction_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, user_id)); await db.commit(); return cursor.rowcount > 0