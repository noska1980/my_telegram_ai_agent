# tests/conftest.py
import pytest
import pytest_asyncio
import os
from unittest.mock import MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import User, Chat
# --- ВАЖНЫЙ ИМПОРТ ---
from aiogram.fsm.storage.base import StorageKey

# Импортируем ключевую функцию для инициализации БД
from db import init_db

@pytest_asyncio.fixture(scope="function")
async def db_conn(monkeypatch):
    """
    Фикстура, которая создает чистую тестовую БД для каждого теста
    и подменяет константу DB_NAME, чтобы все импортированные функции
    работали с тестовой базой.
    """
    TEST_DB_NAME = f"test_db_{os.urandom(4).hex()}.db"
    
    monkeypatch.setattr("db.DB_NAME", TEST_DB_NAME)
    # Важно: также подменяем имя БД для других модулей, если они его импортируют напрямую
    monkeypatch.setattr("plan_handlers.DB_NAME", TEST_DB_NAME)
    monkeypatch.setattr("telegram_handlers.DB_NAME", TEST_DB_NAME)
    monkeypatch.setattr("scheduler_jobs.DB_NAME", TEST_DB_NAME)
    # Добавим для finance_handlers на всякий случай
    monkeypatch.setattr("finance_handlers.DB_NAME", TEST_DB_NAME, raising=False)


    await init_db()
    yield TEST_DB_NAME
    os.remove(TEST_DB_NAME)

@pytest.fixture
def mock_bot():
    """Фикстура для создания мока бота."""
    bot = MagicMock()
    bot.id = 7276695864  # Устанавливаем ID для ключа FSM
    return bot

@pytest.fixture
def memory_storage():
    """Фикстура для создания хранилища FSM в памяти."""
    return MemoryStorage()

@pytest.fixture
def user():
    """Фикстура для создания тестового пользователя."""
    return User(id=12345, is_bot=False, first_name="Тестер", last_name="Тестеров", full_name="Тестер Тестеров")

@pytest.fixture
def chat():
    """Фикстура для создания тестового чата."""
    return Chat(id=54321, type="private")

@pytest_asyncio.fixture
async def state(memory_storage, mock_bot, user, chat):
    """
    Фикстура для создания и очистки контекста состояния (FSM).
    Теперь называется 'state' для краткости.
    """
    # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
    # Ключ для хранилища должен быть хешируемым объектом StorageKey, а не словарем.
    storage_key = StorageKey(
        bot_id=mock_bot.id,
        chat_id=chat.id,
        user_id=user.id,
    )

    fsm_context = FSMContext(
        storage=memory_storage,
        key=storage_key
    )
    # Убедимся, что начинаем с чистого состояния
    await fsm_context.clear()
    return fsm_context

# tests/conftest.py

# ... (существующий код фикстур user, state, db_conn и т.д.) ...

import datetime
from db import add_plan_to_db

@pytest_asyncio.fixture
async def plan_in_db(db_conn, user):
    """
    Фикстура, которая заранее создает один план в БД
    и возвращает его данные для использования в тесте.
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    plan_id = await add_plan_to_db(
        user_id=user.id,
        plan_date_str=today_str,
        plan_topic="Изначальный план",
        plan_text="Текст для теста"
    )
    return {
        "id": plan_id,
        "topic": "Изначальный план",
        "text": "Текст для теста",
        "date_db": today_str,
        "date_display": datetime.date.today().strftime("%d.%m.%Y г.")
    }
# tests/conftest.py

# ... (существующий код фикстур) ...

import aiosqlite

@pytest_asyncio.fixture
async def file_in_db(db_conn, user):
    """
    Фикстура, которая заранее создает один файл в БД
    для тестов редактирования и удаления.
    """
    async with aiosqlite.connect(db_conn) as db:
        cursor = await db.execute(
            """
            INSERT INTO user_files (user_id, telegram_file_id, original_file_name, file_type, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user.id, "FILE_ID_12345", "report.docx", "docx", "Отчеты")
        )
        await db.commit()
        file_id = cursor.lastrowid
    
    return {
        "id": file_id,
        "name": "report.docx",
        "category": "Отчеты",
        "tg_id": "FILE_ID_12345"
    }
# tests/conftest.py

# ... (существующий код фикстур) ...

from aiogram import types
from unittest.mock import AsyncMock

@pytest.fixture
def message(user):
    """
    Фикстура, которая создает готовый мок объекта Message
    со всеми необходимыми асинхронными методами.
    """
    # Создаем мок для самого сообщения
    msg = AsyncMock(spec=types.Message)
    msg.from_user = user
    msg.chat = user # Для личных сообщений чат и пользователь могут быть одним объектом
    
    # Сразу делаем его методы асинхронными, чтобы не повторяться в тестах
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.answer_document = AsyncMock()
    
    return msg