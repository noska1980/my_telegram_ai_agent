# tests/test_negative_scenarios.py
import pytest
from unittest.mock import AsyncMock # <--- ДОБАВЛЕН ЭТОТ ИМПОРТ

# Импортируем обработчики и состояния из разных модулей
from plan_handlers import add_plan_date_received, add_plan_topic_received, delete_plans_ids_received, AddPlanStates, DeletePlanStates
from finance_handlers import process_income_amount, process_book_name_to_create, FinanceStates
from db import add_book, get_book_by_id # Импортируем функции БД для теста дубликатов

pytestmark = pytest.mark.asyncio


async def test_invalid_date_input(message, state):
    """
    Тест на ввод некорректной даты при добавлении плана.
    Ожидаем: Бот должен ответить сообщением об ошибке и не менять состояние.
    """
    await state.set_state(AddPlanStates.awaiting_date)
    message.text = "это не дата"
    
    await add_plan_date_received(message, state)
    
    message.answer.assert_called_once()
    args, kwargs = message.answer.call_args
    assert "Неверный формат даты" in args[0]
    
    current_state = await state.get_state()
    assert current_state == AddPlanStates.awaiting_date


async def test_invalid_amount_input(message, state):
    """
    Тест на ввод текста вместо суммы при добавлении дохода.
    Ожидаем: Бот должен ответить сообщением об ошибке и не менять состояние.
    """
    await state.set_state(FinanceStates.awaiting_income_amount)
    message.text = "стопицот"
    
    await process_income_amount(message, state)
    
    message.answer.assert_called_once_with("Неверная сумма.")
    
    current_state = await state.get_state()
    assert current_state == FinanceStates.awaiting_income_amount

# --- НОВЫЕ ТЕСТЫ ---

async def test_delete_non_existent_plan(message, state, db_conn):
    """
    Тест на попытку удаления плана с ID, которого не существует.
    Ожидаем: Бот должен сообщить, что удалено 0 планов, и не должно быть ошибок.
    """
    await state.set_state(DeletePlanStates.awaiting_ids)
    message.text = "9999" # Явно несуществующий ID
    
    await delete_plans_ids_received(message, state)

    # Проверяем, что бот корректно сообщил о том, что ничего не удалил
    final_call = message.answer.call_args_list[-1]
    args, _ = final_call
    assert "Удалено планов: 0" in args[0]
    
    # Проверяем, что состояние сбросилось
    assert await state.get_state() is None

async def test_create_duplicate_book(user, message, state, db_conn):
    """
    Тест на попытку создания финансовой книги с уже существующим именем.
    Ожидаем: Вторая попытка создания должна быть заблокирована.
    """
    # Устанавливаем состояние ожидания имени книги
    await state.set_state(FinanceStates.awaiting_book_name_to_create)
    
    # Первая, успешная попытка
    book_name = "ЕдинственнаяКнига"
    message.text = book_name
    
    # Мокаем необходимый метод для CallbackQuery, который будет в следующем шаге
    message.answer.return_value.edit_reply_markup = AsyncMock()
    
    # Вызываем обработчик имени, он должен перейти к выбору валюты
    await process_book_name_to_create(message, state)
    assert await state.get_state() == FinanceStates.awaiting_book_currency
    
    # Напрямую добавляем книгу в БД, чтобы симулировать завершение первого FSM
    first_id = await add_book(user.id, book_name, "UZS")
    assert first_id is not None
    
    # Вторая, неуспешная попытка с тем же именем
    # Сбрасываем мок и состояние для чистоты эксперимента
    message.answer.reset_mock()
    await state.set_state(FinanceStates.awaiting_book_name_to_create)
    message.text = book_name # То же самое имя
    
    # Пытаемся создать дубликат
    second_id = await add_book(user.id, book_name, "UZS")
    
    # Проверяем, что функция добавления в БД вернула None, как и должна
    assert second_id is None


async def test_add_plan_with_empty_topic(message, state):
    """
    Тест на ввод пустой строки в качестве темы плана.
    Ожидаем: Сообщение об ошибке, состояние не меняется.
    """
    await state.set_state(AddPlanStates.awaiting_topic)
    message.text = "   " # Пустая строка с пробелами
    
    await add_plan_topic_received(message, state)
    
    message.answer.assert_called_once()
    args, _ = message.answer.call_args
    assert "Тема плана не может быть пустой" in args[0]
    
    assert await state.get_state() == AddPlanStates.awaiting_topic