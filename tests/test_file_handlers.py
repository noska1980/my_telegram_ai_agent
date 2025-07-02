# tests/test_file_handlers.py
import pytest
from unittest.mock import AsyncMock

from aiogram import types
from aiogram.types import ReplyKeyboardRemove

from file_handlers import (
    handle_edit_file_button, edit_file_choose_category, edit_file_choose_file,
    edit_file_choose_field, edit_file_new_name_received,
    handle_delete_document_button, process_delete_type_choice,
    process_category_to_delete, process_file_ids_to_delete,
    EditFileStates, DeleteFileStates
)
from db import get_user_file_by_id, get_files_by_category
# Добавляем импорт клавиатуры для ассерта
from keyboards import get_docs_keyboard

pytestmark = pytest.mark.asyncio


async def test_edit_file_name(user, state, file_in_db):
    """Тестирует полный FSM-цикл редактирования имени файла."""

    message = AsyncMock(spec=types.Message, from_user=user)
    message.answer = AsyncMock()

    callback = AsyncMock(spec=types.CallbackQuery, from_user=user)
    # ИСПРАВЛЕНО: Явно делаем метод .answer() асинхронным
    callback.answer = AsyncMock()
    callback.message = AsyncMock(spec=types.Message)
    callback.message.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.message.delete_reply_markup = AsyncMock()

    # --- Шаг 1: Нажимаем кнопку "Редактировать файл" ---
    await handle_edit_file_button(message, state)
    message.answer.assert_called_once()
    args, kwargs = message.answer.call_args
    assert "Выберите категорию файла" in args[0]
    assert await state.get_state() == EditFileStates.choosing_category

    # --- Шаг 2: Выбираем категорию ---
    callback.data = f"edit_file_cat:{file_in_db['category']}"
    await edit_file_choose_category(callback, state)
    callback.message.answer.assert_called_with("Введите ID файла для редактирования:", reply_markup=ReplyKeyboardRemove())
    assert await state.get_state() == EditFileStates.choosing_file

    # --- Шаг 3: Вводим ID файла ---
    message.text = str(file_in_db['id'])
    await edit_file_choose_file(message, state)
    assert await state.get_state() == EditFileStates.choosing_field

    # --- Шаг 4: Выбираем "Название файла" ---
    callback.data = "edit_file:name"
    await edit_file_choose_field(callback, state)
    callback.message.answer.assert_called_with("Введите новое название файла:", reply_markup=ReplyKeyboardRemove())
    assert await state.get_state() == EditFileStates.editing_name

    # --- Шаг 5: Вводим новое имя и завершаем ---
    message.text = "new_report_final.docx"
    await edit_file_new_name_received(message, state)
    args, _ = message.answer.call_args
    assert "Имя файла изменено на: <b>new_report_final.docx</b>" in args[0]
    assert await state.get_state() is None

    # --- Финальная проверка в БД ---
    updated_file = await get_user_file_by_id(user.id, file_in_db['id'])
    assert updated_file['original_file_name'] == "new_report_final.docx"


async def test_delete_file_by_id(user, state, file_in_db):
    """Тестирует удаление одного файла по его ID."""

    message = AsyncMock(spec=types.Message, from_user=user)
    message.answer = AsyncMock()

    callback = AsyncMock(spec=types.CallbackQuery, from_user=user)
    # ИСПРАВЛЕНО: Явно делаем метод .answer() асинхронным
    callback.answer = AsyncMock()
    callback.message = AsyncMock(spec=types.Message)
    callback.message.answer = AsyncMock()
    callback.message.delete = AsyncMock()

    # --- Шаг 1: Нажимаем "Удалить док." ---
    await handle_delete_document_button(message, state)
    assert await state.get_state() == DeleteFileStates.choosing_delete_type

    # --- Шаг 2: Выбираем "Один или несколько файлов" ---
    callback.data = "delete_doc_type:file"
    await process_delete_type_choice(callback, state)
    callback.message.answer.assert_called_with("Введите ID файла (или нескольких ID через запятую/пробел) для удаления:", reply_markup=ReplyKeyboardRemove())
    assert await state.get_state() == DeleteFileStates.awaiting_file_ids_to_delete

    # --- Шаг 3: Вводим ID и удаляем ---
    message.text = str(file_in_db['id'])
    await process_file_ids_to_delete(message, state)
    # ИСПРАВЛЕНО: Проверяем правильную клавиатуру
    message.answer.assert_called_with("✅ Удалено файлов: 1.", reply_markup=get_docs_keyboard())
    assert await state.get_state() is None

    # --- Проверка в БД ---
    deleted_file = await get_user_file_by_id(user.id, file_in_db['id'])
    assert deleted_file is None


async def test_delete_category(user, state, file_in_db):
    """Тестирует удаление целой категории файлов."""

    callback = AsyncMock(spec=types.CallbackQuery, from_user=user)
    # ИСПРАВЛЕНО: Явно делаем метод .answer() асинхронным
    callback.answer = AsyncMock()
    callback.message = AsyncMock(spec=types.Message)
    callback.message.answer = AsyncMock()
    callback.message.delete = AsyncMock()

    # --- Шаг 1: Устанавливаем состояние выбора типа удаления ---
    await state.set_state(DeleteFileStates.choosing_delete_type)

    # --- Шаг 2: Выбираем "Категорию целиком" ---
    callback.data = "delete_doc_type:category"
    await process_delete_type_choice(callback, state)
    assert await state.get_state() == DeleteFileStates.awaiting_category_to_delete

    # --- Шаг 3: Выбираем категорию для удаления ---
    callback.data = f"delete_doc_cat:{file_in_db['category']}"
    await process_category_to_delete(callback, state)
    args, _ = callback.message.answer.call_args
    assert f"Категория «<b>{file_in_db['category']}</b>» и 1 файл(ов) в ней были удалены." in args[0]
    assert await state.get_state() is None

    # --- Проверка в БД ---
    files_in_category = await get_files_by_category(user.id, file_in_db['category'])
    assert not files_in_category