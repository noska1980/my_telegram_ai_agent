# tests/test_plan_handlers.py
import pytest
from unittest.mock import AsyncMock

from aiogram import types
from aiogram.types import ReplyKeyboardRemove

from plan_handlers import (
    handle_add_plan_button, add_plan_date_received, add_plan_topic_received,
    add_plan_content_received, add_plan_reminder_time_received, AddPlanStates,
    handle_delete_plan_button, delete_plans_ids_received, DeletePlanStates,
    handle_complete_plan_button, complete_plans_ids_received, CompletePlanStates,
    handle_today_plans_button
)
from db import get_all_user_plans, get_plan_by_id
from keyboards import get_date_keyboard # <--- ИМПОРТИРУЕМ НОВУЮ КЛАВИАТУРУ

pytestmark = pytest.mark.asyncio

# --- Тест на добавление (ИСПРАВЛЕН) ---
async def test_add_plan_full_cycle(user, state, db_conn):
    """Тестирует полный цикл добавления плана через FSM."""
    message = AsyncMock(spec=types.Message, from_user=user)
    message.answer = AsyncMock()

    await handle_add_plan_button(message, state)
    # ИСПРАВЛЕНИЕ: Проверяем новый текст и новую клавиатуру
    message.answer.assert_called_with(
        "На какую дату вы хотите добавить план? Введите в формате ДД.ММ.ГГГГ или нажмите кнопку 'Сегодня':",
        reply_markup=get_date_keyboard()
    )
    assert await state.get_state() == AddPlanStates.awaiting_date

    message.text = "25.12.2025"
    await add_plan_date_received(message, state)
    assert await state.get_state() == AddPlanStates.awaiting_topic
    # Проверяем, что после ввода даты клавиатура убирается
    message.answer.assert_called_with(
        "Дата 25.12.2025 г.. Теперь введите тему плана:",
        reply_markup=ReplyKeyboardRemove()
    )


    message.text = "Тестовая тема"
    await add_plan_topic_received(message, state)
    assert await state.get_state() == AddPlanStates.awaiting_plan_content

    message.text = "Описание тестового плана."
    await add_plan_content_received(message, state)
    assert await state.get_state() == AddPlanStates.awaiting_reminder_time

    message.text = "нет"
    await add_plan_reminder_time_received(message, state)
    args, kwargs = message.answer.call_args
    assert "План «Тестовая тема» на 25.12.2025 г. успешно добавлен" in args[0]

    current_state = await state.get_state()
    assert current_state is None

    all_plans = await get_all_user_plans(user.id)
    assert len(all_plans) == 1
    assert all_plans[0]['plan_topic'] == "Тестовая тема"

# --- Тест на удаление (исправлен) ---
async def test_delete_plan(user, state, plan_in_db):
    """Тестирует удаление существующего плана."""
    plan_id_to_delete = plan_in_db['id']

    message = AsyncMock(spec=types.Message, from_user=user)
    message.answer = AsyncMock()

    await handle_delete_plan_button(message, state)
    message.answer.assert_called_with("Введите ID плана (или нескольких ID через запятую/пробел) для удаления:", reply_markup=ReplyKeyboardRemove())
    assert await state.get_state() == DeletePlanStates.awaiting_ids

    message.text = str(plan_id_to_delete)
    await delete_plans_ids_received(message, state)

    final_call = message.answer.call_args_list[-1]
    args, _ = final_call
    assert "Удалено планов: 1" in args[0]

    assert await state.get_state() is None

    plan = await get_plan_by_id(user.id, plan_id_to_delete)
    assert plan is None

# --- Тест на отметку о выполнении (проходит успешно) ---
async def test_complete_plan(user, state, plan_in_db):
    """Тестирует отметку плана как выполненного и снятие отметки."""
    plan_id_to_complete = plan_in_db['id']

    message = AsyncMock(spec=types.Message, from_user=user)
    message.answer = AsyncMock()

    # Шаг 1: Отмечаем план как выполненный
    await state.set_state(CompletePlanStates.awaiting_ids)
    message.text = str(plan_id_to_complete)
    await complete_plans_ids_received(message, state)

    plan = await get_plan_by_id(user.id, plan_id_to_complete)
    assert plan['is_completed'] == 1

    # Шаг 2: Снимаем отметку (повторный вызов)
    await state.set_state(CompletePlanStates.awaiting_ids)
    message.text = str(plan_id_to_complete)
    await complete_plans_ids_received(message, state)

    plan = await get_plan_by_id(user.id, plan_id_to_complete)
    assert plan['is_completed'] == 0

# --- Тест на просмотр планов на сегодня (исправлен) ---
async def test_view_today_plans(user, state, plan_in_db):
    """Тестирует отображение планов на сегодня."""
    message = AsyncMock(spec=types.Message, from_user=user)
    message.answer = AsyncMock()

    # Сначала проверяем случай, когда планы есть
    await handle_today_plans_button(message)

    first_call_args, _ = message.answer.call_args_list[0]
    assert plan_in_db['topic'] in first_call_args[0]

    # Теперь удалим план и проверим случай, когда планов нет
    await state.set_state(DeletePlanStates.awaiting_ids)
    message.text = str(plan_in_db['id'])
    await delete_plans_ids_received(message, state)

    message.answer.reset_mock() # Сбрасываем мок перед новым вызовом
    await handle_today_plans_button(message)
    args, _ = message.answer.call_args
    assert "На сегодня" in args[0]
    assert "планов нет" in args[0]