# tests/test_finance_handlers.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from aiogram import types
from aiogram.types import ReplyKeyboardRemove, BufferedInputFile

from finance_handlers import (
    handle_add_income_to_book_button, process_income_amount, process_income_description,
    process_income_category, process_income_date, handle_book_balance_button,
    handle_add_expense_to_book_button, process_expense_amount, process_expense_description,
    process_expense_category, process_expense_date,
    handle_edit_transaction_button, process_transaction_to_edit_id, choose_edit_transaction_field,
    process_editing_transaction_amount,
    handle_book_report_button, choose_report_format_for_book,
    FinanceStates
)
from db import add_book, get_book_balance_summary, get_transactions_by_book

pytestmark = pytest.mark.asyncio

@pytest_asyncio.fixture(scope="function")
async def book_with_income(db_conn, user):
    """
    Фикстура для создания 'книги' и добавления в нее одной транзакции дохода.
    Возвращает данные книги и транзакции.
    """
    from db import add_transaction
    import datetime

    book_id = await add_book(user_id=user.id, name="ТестоваяКнига", currency="USD")

    transaction_id = await add_transaction(
        user_id=user.id,
        book_id=book_id,
        type='income',
        amount=1000.0,
        description='Начальный капитал',
        category='Старт',
        transaction_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    return {
        "book": {"id": book_id, "name": "ТестоваяКнига", "currency": "USD"},
        "transaction": {"id": transaction_id, "amount": 1000.0}
    }


# --- Тест на добавление дохода (проходит успешно) ---
async def test_add_income_and_check_balance(user, state, db_conn):
    """Тестирует добавление дохода и последующую проверку баланса."""
    book_id = await add_book(user_id=user.id, name="КнигаДоходов", currency="USD")
    book = {"id": book_id, "name": "КнигаДоходов", "currency": "USD"}
    await state.update_data(current_book_id=book['id'], current_book_name=book['name'], current_book_currency=book['currency'])

    message = AsyncMock(spec=types.Message, from_user=user)
    message.answer = AsyncMock()

    await handle_add_income_to_book_button(message, state)
    assert await state.get_state() == FinanceStates.awaiting_income_amount

    message.text = "150.50"
    await process_income_amount(message, state)
    assert await state.get_state() == FinanceStates.awaiting_income_description

    message.text = "Зарплата"
    await process_income_description(message, state)
    assert await state.get_state() == FinanceStates.awaiting_income_category

    message.text = "Работа"
    await process_income_category(message, state)
    assert await state.get_state() == FinanceStates.awaiting_income_date

    message.text = "сегодня"
    await process_income_date(message, state)
    assert await state.get_state() is None

    total_income, total_expense = await get_book_balance_summary(user.id, book['id'])
    assert total_income == 150.50

# --- Тест на добавление расхода (проходит успешно) ---
async def test_add_expense_full_cycle(user, state, book_with_income):
    """Тестирует полный цикл добавления расхода."""
    book = book_with_income['book']
    await state.update_data(current_book_id=book['id'], current_book_name=book['name'], current_book_currency=book['currency'])

    message = AsyncMock(spec=types.Message, from_user=user)
    message.answer = AsyncMock()

    await handle_add_expense_to_book_button(message, state)
    assert await state.get_state() == FinanceStates.awaiting_expense_amount

    message.text = "75.20"
    await process_expense_amount(message, state)
    assert await state.get_state() == FinanceStates.awaiting_expense_description

    message.text = "Кофе"
    await process_expense_description(message, state)
    assert await state.get_state() == FinanceStates.awaiting_expense_category

    message.text = "Еда"
    await process_expense_category(message, state)
    assert await state.get_state() == FinanceStates.awaiting_expense_date

    message.text = "сегодня"
    await process_expense_date(message, state)
    assert await state.get_state() is None

    total_income, total_expense = await get_book_balance_summary(user.id, book['id'])
    assert total_income == 1000.0
    assert total_expense == 75.20
    assert round(total_income - total_expense, 2) == 924.80

# --- Тест на редактирование транзакции (исправлен) ---
async def test_edit_transaction(user, state, book_with_income):
    """Тестирует FSM редактирования суммы транзакции."""
    book = book_with_income['book']
    transaction = book_with_income['transaction']

    callback = AsyncMock(spec=types.CallbackQuery, from_user=user)
    # ИСПРАВЛЕНИЕ №1: Явно делаем метод .answer() асинхронным
    callback.answer = AsyncMock()
    callback.message = AsyncMock(spec=types.Message)
    callback.message.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()

    message = AsyncMock(spec=types.Message, from_user=user)
    message.answer = AsyncMock()

    await state.set_state(FinanceStates.awaiting_transaction_to_edit)
    message.text = str(transaction['id'])
    await process_transaction_to_edit_id(message, state)
    assert await state.get_state() == FinanceStates.choosing_edit_transaction_field

    callback.data = "edit_transaction_field:amount"
    await choose_edit_transaction_field(callback, state)
    callback.message.answer.assert_called_with("Введите новую сумму:", reply_markup=ReplyKeyboardRemove())
    assert await state.get_state() == FinanceStates.editing_transaction_amount

    message.text = "555.55"
    await process_editing_transaction_amount(message, state)
    assert await state.get_state() is None

    transactions = await get_transactions_by_book(user.id, book['id'])
    assert transactions[0]['amount'] == 555.55

# --- Тест на генерацию отчета (исправлен) ---
async def test_generate_pdf_report(user, state, book_with_income):
    """Тестирует генерацию PDF отчета."""
    book = book_with_income['book']
    await state.update_data(current_book_id=book['id'], current_book_name=book['name'], current_book_currency=book['currency'])

    callback = AsyncMock(spec=types.CallbackQuery, from_user=user)
    callback.message = AsyncMock(spec=types.Message)
    # ИСПРАВЛЕНИЕ №2: Явно делаем метод .answer() для сообщения тоже асинхронным
    callback.message.answer = AsyncMock()
    callback.message.answer_document = AsyncMock()
    callback.message.edit_text = AsyncMock()

    await handle_book_report_button(callback.message, state)
    assert await state.get_state() == FinanceStates.choosing_report_format_for_book

    callback.data = "report_format:pdf"
    await choose_report_format_for_book(callback, state)

    callback.message.answer_document.assert_called_once()
    args, kwargs = callback.message.answer_document.call_args

    assert isinstance(args[0], BufferedInputFile)
    assert kwargs['caption'] == "Ваш PDF отчет."
    assert ".pdf" in args[0].filename
    
    assert await state.get_state() is None