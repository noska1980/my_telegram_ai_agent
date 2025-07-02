# tests/test_db.py
import pytest
import pytest_asyncio
import aiosqlite
import os

# Импортируем функции, которые мы хотим протестировать
from db import init_db, add_book, get_user_books, get_book_by_id

pytestmark = pytest.mark.asyncio

@pytest_asyncio.fixture(scope="function")
async def db_conn(monkeypatch):
    """
    Фикстура, которая создает чистую тестовую БД для каждого теста
    и подменяет константу DB_NAME, чтобы все импортированные функции
    работали с тестовой базой.
    """
    TEST_DB_NAME = "test_db_isolated.db"
    
    # 1. Подменяем имя БД в модуле db
    monkeypatch.setattr("db.DB_NAME", TEST_DB_NAME)

    # 2. Создаем таблицы, используя настоящую функцию из проекта
    await init_db()

    # 3. Отдаем имя тестовой БД в тест
    yield TEST_DB_NAME

    # 4. Очистка после каждого теста
    os.remove(TEST_DB_NAME)


async def test_add_and_get_book(db_conn):
    """
    Тест: проверяем добавление и получение книги через функции нашего приложения.
    """
    user_id = 12345
    book_name = "Моя тестовая книга"
    book_currency = "USD"

    # 1. Добавляем книгу, вызывая нашу функцию add_book
    new_book_id = await add_book(user_id=user_id, name=book_name, currency=book_currency)
    assert new_book_id is not None, "Функция add_book должна вернуть ID новой книги"

    # 2. Получаем книгу по ID, вызывая нашу функцию get_book_by_id
    book_from_db = await get_book_by_id(user_id=user_id, book_id=new_book_id)
    
    # 3. Проверяем результат
    assert book_from_db is not None
    assert book_from_db['name'] == book_name
    assert book_from_db['currency'] == book_currency

    # 4. Получаем список всех книг пользователя
    all_books = await get_user_books(user_id=user_id)
    assert len(all_books) == 1
    assert all_books[0]['name'] == book_name