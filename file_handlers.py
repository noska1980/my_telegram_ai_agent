# file_handlers.py
import asyncio
import datetime
import re
from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.markdown import hbold

from config import logger
from filters import IsAuthorizedUser
from keyboards import (
    get_docs_keyboard, get_edit_file_keyboard,
    get_delete_document_choice_keyboard, get_categories_for_delete_keyboard,
    get_category_choice_keyboard
)
from db import (
    update_file_category, get_file_categories, get_files_by_category,
    get_user_file_by_id, update_file_name, get_files_by_search_query,
    delete_files_by_ids, delete_category_by_name
)

class GetFileStates(StatesGroup):
    awaiting_id = State()

class SearchFileStates(StatesGroup):
    awaiting_query = State()
    choosing_file = State()

class EditFileStates(StatesGroup):
    choosing_category = State()
    choosing_file = State()
    choosing_field = State()
    editing_name = State()
    editing_category = State()

class BatchCategorizeStates(StatesGroup):
    awaiting_files = State()
    choosing_category_action = State()
    selecting_existing_category = State()
    awaiting_category_for_batch = State()

class DeleteFileStates(StatesGroup):
    choosing_delete_type = State()
    awaiting_category_to_delete = State()
    awaiting_file_ids_to_delete = State()


async def handle_done_categorizing(message: types.Message, state: FSMContext):
    await message.answer(
        "Файлы готовы к категоризации. Вы хотите добавить их в существующую категорию или создать новую?",
        reply_markup=get_category_choice_keyboard()
    )
    await state.set_state(BatchCategorizeStates.choosing_category_action)

async def process_category_action_choice(callback_query: types.CallbackQuery, state: FSMContext):
    action = callback_query.data.split(':')[1]
    await callback_query.message.delete()

    if action == 'create_new':
        await callback_query.message.answer("Введите одну общую категорию для всех загруженных файлов:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(BatchCategorizeStates.awaiting_category_for_batch)

    elif action == 'select_existing':
        categories = await get_file_categories(callback_query.from_user.id)
        if not categories:
            await callback_query.message.answer("У вас еще нет ни одной категории. Пожалуйста, создайте первую, введя ее название:", reply_markup=ReplyKeyboardRemove())
            await state.set_state(BatchCategorizeStates.awaiting_category_for_batch)
            return

        buttons = [[InlineKeyboardButton(text=c['category'], callback_data=f"select_cat:{c['category']}")] for c in categories]
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="select_cat:cancel")])
        await callback_query.message.answer("Выберите существующую категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await state.set_state(BatchCategorizeStates.selecting_existing_category)

    elif action == 'cancel':
        await callback_query.message.answer("Категоризация отменена.", reply_markup=get_docs_keyboard())
        await state.clear()
    
    await callback_query.answer()


async def process_existing_category_selection(callback_query: types.CallbackQuery, state: FSMContext):
    category_name = callback_query.data.split(':', 1)[1]
    await callback_query.message.delete()

    if category_name == 'cancel':
        await callback_query.message.answer("Категоризация отменена.", reply_markup=get_docs_keyboard())
        await state.clear()
        return

    user_data = await state.get_data()
    file_ids = user_data.get('files_to_categorize', [])
    if not file_ids:
        await callback_query.message.answer("Ошибка: не найдено файлов для категоризации.", reply_markup=get_docs_keyboard())
        await state.clear()
        return
    
    updated_count = 0
    for file_id in file_ids:
        if await update_file_category(file_id, callback_query.from_user.id, category_name):
            updated_count += 1

    await callback_query.message.answer(f"✅ Категория «{hbold(category_name)}» присвоена {updated_count} файлам.", parse_mode="HTML", reply_markup=get_docs_keyboard())
    await state.clear()
    await callback_query.answer()


async def batch_category_received(message: types.Message, state: FSMContext):
    category_name = message.text.strip()
    if not category_name:
        await message.reply("Название категории не может быть пустым.")
        return
    user_data = await state.get_data()
    file_ids = user_data.get('files_to_categorize', [])
    if not file_ids:
        await message.reply("Ошибка: не найдено файлов для категоризации.", reply_markup=get_docs_keyboard())
        await state.clear()
        return
    updated_count = 0
    for file_id in file_ids:
        if await update_file_category(file_id, message.from_user.id, category_name):
            updated_count += 1
    await message.answer(f"✅ Категория «{hbold(category_name)}» присвоена {updated_count} файлам.", parse_mode="HTML", reply_markup=get_docs_keyboard())
    await state.clear()

# ... (остальной код файла без изменений)
async def show_files_in_category(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    category = callback_query.data.split(':', 1)[1]
    if category == 'cancel':
        await callback_query.message.edit_text("Отменено.")
        return

    await callback_query.message.edit_text(f"Файлы в категории «{hbold(category)}»:", parse_mode="HTML")
    files = await get_files_by_category(callback_query.from_user.id, category)
    if not files:
        await callback_query.message.answer("В этой категории файлов нет.", reply_markup=get_docs_keyboard())
        return

    response_parts = [
        f"ID: {hbold(str(f['id']))} | {f['original_file_name']} ({f['file_type']}) - {datetime.datetime.fromisoformat(f['upload_date']).strftime('%d.%m.%Y')}"
        for f in files
    ]

    current_message_chunk = ""
    for line in response_parts:
        if len(current_message_chunk) + len(line) + 1 > 4096:
            await callback_query.message.answer(current_message_chunk, parse_mode="HTML")
            await asyncio.sleep(0.5)
            current_message_chunk = line
        else:
            if current_message_chunk:
                current_message_chunk += "\n" + line
            else:
                current_message_chunk = line

    if current_message_chunk.strip():
        await callback_query.message.answer(current_message_chunk, parse_mode="HTML")


async def handle_edit_file_button(message: types.Message, state: FSMContext):
    categories = await get_file_categories(message.from_user.id)
    if not categories:
        await message.answer("У вас еще нет категорий для редактирования файлов.", reply_markup=get_docs_keyboard())
        return
    buttons = [[InlineKeyboardButton(text=c['category'], callback_data=f"edit_file_cat:{c['category']}")] for c in categories]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="edit_file_cat:cancel")])
    await message.answer("Выберите категорию файла для редактирования:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(EditFileStates.choosing_category)

async def edit_file_choose_category(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    category = callback_query.data.split(':', 1)[1]
    if category == 'cancel':
        await callback_query.message.edit_text("Редактирование отменено.")
        await state.clear()
        return
    files = await get_files_by_category(callback_query.from_user.id, category)
    if not files:
        await callback_query.message.edit_text(f"В категории «{hbold(category)}» нет файлов.", parse_mode="HTML")
        await state.clear()
        return
    response = [f"Файлы в категории «{hbold(category)}»:", ""] + [f"ID: {hbold(str(f['id']))} | {f['original_file_name']}" for f in files]
    await callback_query.message.edit_text("\n".join(response), parse_mode="HTML")
    await callback_query.message.answer("Введите ID файла для редактирования:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditFileStates.choosing_file)

async def edit_file_choose_file(message: types.Message, state: FSMContext):
    try:
        file_id = int(message.text.strip())
        file_data = await get_user_file_by_id(message.from_user.id, file_id)
        if not file_data:
            await message.reply("Файл с таким ID не найден.", reply_markup=get_docs_keyboard())
            await state.clear()
            return
        await state.update_data(file_to_edit_id=file_id, file_to_edit_name=file_data['original_file_name'])
        await message.answer(f"Выбран файл: {hbold(file_data['original_file_name'])} (ID: {file_id}).\nЧто изменить?", parse_mode="HTML", reply_markup=get_edit_file_keyboard())
        await state.set_state(EditFileStates.choosing_field)
    except ValueError:
        await message.reply("ID должен быть числом.", reply_markup=get_docs_keyboard())
        await state.clear()

async def edit_file_choose_field(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    action = callback_query.data.split(':', 1)[1]
    await callback_query.message.delete_reply_markup()
    if action == 'name':
        await callback_query.message.answer("Введите новое название файла:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(EditFileStates.editing_name)
    elif action == 'category':
        await callback_query.message.answer("Введите новую категорию для файла:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(EditFileStates.editing_category)
    else:  # cancel
        await callback_query.message.edit_text("Редактирование отменено.")
        await state.clear()

async def edit_file_new_name_received(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    if not new_name:
        await message.reply("Имя не может быть пустым.")
        return
    user_data = await state.get_data()
    file_id = user_data.get('file_to_edit_id')
    await update_file_name(file_id, message.from_user.id, new_name)
    await message.answer(f"✅ Имя файла изменено на: {hbold(new_name)}", parse_mode="HTML", reply_markup=get_docs_keyboard())
    await state.clear()

async def edit_file_new_category_received(message: types.Message, state: FSMContext):
    new_category = message.text.strip()
    if not new_category:
        await message.reply("Категория не может быть пустой.")
        return
    user_data = await state.get_data()
    file_id = user_data.get('file_to_edit_id')
    await update_file_category(file_id, message.from_user.id, new_category)
    await message.answer(f"✅ Категория файла изменена на: {hbold(new_category)}", parse_mode="HTML", reply_markup=get_docs_keyboard())
    await state.clear()

async def handle_list_files_button(message: types.Message):
    categories = await get_file_categories(message.from_user.id)
    if not categories:
        await message.answer("У вас еще нет категорий.", reply_markup=get_docs_keyboard())
        return
    buttons = [[InlineKeyboardButton(text=c['category'], callback_data=f"list_files_cat:{c['category']}")] for c in categories]
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="list_files_cat:cancel")])
    await message.answer("Выберите категорию для просмотра:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

async def handle_get_file_button(message: types.Message, state: FSMContext):
    await message.answer("Введите ID файла:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(GetFileStates.awaiting_id)

async def get_file_id_received(message: types.Message, state: FSMContext):
    try:
        file_id_db = int(message.text.strip())
        file_data = await get_user_file_by_id(message.from_user.id, file_id_db)
        if not file_data:
            await message.reply(f"Файл с ID {file_id_db} не найден.", reply_markup=get_docs_keyboard())
            await state.clear()
            return
        await message.answer(f"Отправляю файл: «{file_data['original_file_name']}»...", reply_markup=get_docs_keyboard())
        await message.bot.send_document(chat_id=message.chat.id, document=file_data['telegram_file_id'])
    except ValueError:
        await message.reply("ID должен быть числом.", reply_markup=get_docs_keyboard())
    except Exception as e:
        logger.error(f"Ошибка при отправке файла: {e}", exc_info=True)
        await message.reply("Не удалось отправить файл.", reply_markup=get_docs_keyboard())
    finally:
        await state.clear()

async def handle_search_files_by_name(message: types.Message, state: FSMContext):
    await message.answer("Введите текст для поиска в названии файла:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(SearchFileStates.awaiting_query)

async def search_query_received(message: types.Message, state: FSMContext):
    query = message.text.strip()
    if not query:
        await message.answer("Поисковый запрос не может быть пустым.", reply_markup=get_docs_keyboard())
        await state.clear()
        return
    found_files = await get_files_by_search_query(message.from_user.id, query)
    if not found_files:
        await message.answer(f"Файлы, содержащие '{query}' в названии, не найдены.", reply_markup=get_docs_keyboard())
        await state.clear()
        return
    keyboard_buttons = []
    response_text = f"Найденные файлы по запросу '{hbold(query)}':\n"
    for file_info in found_files:
        response_text += f"\nID: {hbold(str(file_info['id']))} | {file_info['original_file_name']} (Категория: {file_info['category']})"
        keyboard_buttons.append([InlineKeyboardButton(text=f"{file_info['original_file_name']} (ID: {file_info['id']})", callback_data=f"get_file_search:{file_info['id']}")])
    await message.answer(response_text, parse_mode="HTML")
    keyboard_buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="get_file_search:cancel")])
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer("Выберите файл для получения:", reply_markup=reply_markup)
    await state.set_state(SearchFileStates.choosing_file)

async def choose_file_from_search(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    action = callback_query.data.split(':', 1)[1]
    await callback_query.message.delete_reply_markup()
    if action == 'cancel':
        await callback_query.message.answer("Поиск отменен.", reply_markup=get_docs_keyboard())
        await state.clear()
        return
    try:
        file_id_db = int(action)
        file_data = await get_user_file_by_id(callback_query.from_user.id, file_id_db)
        if not file_data:
            await callback_query.message.answer("Этот файл больше не найден.", reply_markup=get_docs_keyboard())
            await state.clear()
            return
        await callback_query.message.answer(f"Отправляю файл: «{file_data['original_file_name']}»...", reply_markup=get_docs_keyboard())
        await callback_query.bot.send_document(chat_id=callback_query.message.chat.id, document=file_data['telegram_file_id'])
    except (ValueError, TypeError):
        logger.error(f"Некорректные данные в callback: {callback_query.data}")
    except Exception as e:
        logger.error(f"Ошибка при отправке файла из поиска: {e}", exc_info=True)
        await callback_query.message.answer("Не удалось отправить файл.", reply_markup=get_docs_keyboard())
    finally:
        await state.clear()

async def handle_delete_document_button(message: types.Message, state: FSMContext):
    logger.info(f"Получено нажатие 'Удалить док. 🗑️' от пользователя {message.from_user.id}")
    await message.answer(
        "Что вы хотите удалить?",
        reply_markup=get_delete_document_choice_keyboard()
    )
    await state.set_state(DeleteFileStates.choosing_delete_type)

async def process_delete_type_choice(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    action = callback_query.data.split(':', 1)[1]
    await callback_query.message.delete()

    if action == 'category':
        categories = await get_file_categories(callback_query.from_user.id)
        if not categories:
            await callback_query.message.answer("У вас нет ни одной категории для удаления.", reply_markup=get_docs_keyboard())
            await state.clear()
            return
        await callback_query.message.answer(
            "Выберите категорию для полного удаления (все файлы в ней будут удалены):",
            reply_markup=get_categories_for_delete_keyboard(categories)
        )
        await state.set_state(DeleteFileStates.awaiting_category_to_delete)

    elif action == 'file':
        await callback_query.message.answer(
            "Введите ID файла (или нескольких ID через запятую/пробел) для удаления:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(DeleteFileStates.awaiting_file_ids_to_delete)

    elif action == 'cancel':
        await callback_query.message.answer("Удаление отменено.", reply_markup=get_docs_keyboard())
        await state.clear()

async def process_category_to_delete(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    category_to_delete = callback_query.data.split(':', 1)[1]
    await callback_query.message.delete()

    if category_to_delete == 'cancel':
        await callback_query.message.answer("Удаление отменено.", reply_markup=get_docs_keyboard())
        await state.clear()
        return

    deleted_count = await delete_category_by_name(callback_query.from_user.id, category_to_delete)

    if deleted_count > 0:
        await callback_query.message.answer(
            f"✅ Категория «{hbold(category_to_delete)}» и {deleted_count} файл(ов) в ней были удалены.",
            parse_mode="HTML",
            reply_markup=get_docs_keyboard()
        )
    else:
        await callback_query.message.answer(
            f"Не удалось удалить категорию «{hbold(category_to_delete)}». Возможно, она уже была удалена.",
            parse_mode="HTML",
            reply_markup=get_docs_keyboard()
        )
    await state.clear()

async def process_file_ids_to_delete(message: types.Message, state: FSMContext):
    logger.info(f"Получены ID для удаления файлов от пользователя {message.from_user.id}: {message.text}")
    ids_str = re.split(r'[,\s]+', message.text.strip())
    ids = [int(pid) for pid in ids_str if pid.isdigit()]

    if not ids:
        await message.answer("ID не найдены или введены некорректно. Введите один или несколько ID.", reply_markup=get_docs_keyboard())
        await state.clear()
        return

    deleted_count = await delete_files_by_ids(message.from_user.id, ids)

    await message.answer(
        f"✅ Удалено файлов: {deleted_count}.",
        reply_markup=get_docs_keyboard()
    )
    await state.clear()