# main.py
import asyncio
import nltk
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ContentType, ParseMode
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hbold

from config import BOT_TOKEN, logger
from db import init_db
from keyboards import get_main_keyboard, get_plans_keyboard, get_docs_keyboard, get_remove_keyboard, get_finance_keyboard

# --- Импорты ---
from plan_handlers import (
    handle_add_plan_button, add_plan_date_received, add_plan_topic_received, add_plan_content_received,
    add_plan_reminder_time_received, handle_today_plans_button, handle_all_plans_button, handle_edit_plan_button,
    edit_plan_id_received, choose_edit_field, update_plan_text, update_plan_date, update_plan_topic,
    handle_delete_plan_button, delete_plans_ids_received, handle_complete_plan_button, complete_plans_ids_received,
    handle_set_reminder_button, set_reminder_id_received, set_reminder_time_received,
    AddPlanStates, EditPlanStates, DeletePlanStates, CompletePlanStates, SetReminderStates
)
from file_handlers import (
    handle_list_files_button, handle_get_file_button, get_file_id_received,
    handle_search_files_by_name, search_query_received, choose_file_from_search,
    show_files_in_category,
    handle_edit_file_button, edit_file_choose_category, edit_file_choose_file,
    edit_file_choose_field, edit_file_new_name_received, edit_file_new_category_received,
    handle_done_categorizing, batch_category_received, process_category_action_choice, process_existing_category_selection,
    handle_delete_document_button, process_delete_type_choice,
    process_category_to_delete, process_file_ids_to_delete,
    DeleteFileStates,
    GetFileStates, SearchFileStates, EditFileStates, BatchCategorizeStates
)
from finance_handlers import (
    handle_create_book_button, process_book_name_to_create, process_book_currency_selection,
    handle_my_books_button, process_book_selection, process_book_selection_cancel,
    handle_delete_book_button, process_book_to_delete, process_delete_book_cancel,
    handle_edit_book_button, process_book_to_edit_selected, process_edit_book_cancel_selection,
    choose_edit_book_field, process_editing_book_name, process_editing_book_currency,
    handle_add_income_to_book_button, process_income_amount, process_income_description, process_income_category, process_income_date,
    handle_add_expense_to_book_button, process_expense_amount, process_expense_description, process_expense_category, process_expense_date,
    handle_book_balance_button, handle_book_report_button, choose_report_format_for_book,
    handle_edit_transaction_button, process_transaction_to_edit_id, choose_edit_transaction_field,
    process_editing_transaction_type, process_editing_transaction_amount, process_editing_transaction_description,
    process_editing_transaction_category, process_editing_transaction_date,
    handle_finance_main_menu_button, handle_back_to_books_button, 
    handle_scan_qr_button, process_qr_photo, process_qr_category,
    FinanceStates
)
from scheduler_jobs import scheduler, auto_archive_old_plans, load_reminders_on_startup, set_bot_instance_for_scheduler
from telegram_handlers import handle_document_upload
from filters import IsAuthorizedUser

# --- Инициализация ---
bot_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
bot = Bot(token=BOT_TOKEN, default=bot_properties)
dp = Dispatcher()

# --- Основные обработчики, живущие в main.py ---
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(f"Привет, {hbold(message.from_user.full_name)}!", reply_markup=get_main_keyboard())

async def handle_my_plans_button_main(message: types.Message):
    await message.answer("Действия с планами:", reply_markup=get_plans_keyboard())

async def handle_my_documents_button_main(message: types.Message):
    await message.answer("Действия с документами:", reply_markup=get_docs_keyboard())

async def handle_my_finance_button_main(message: types.Message):
    await message.answer("Добро пожаловать в раздел финансов! Выберите действие:", reply_markup=get_finance_keyboard())

async def handle_unknown_text(message: types.Message):
    await message.answer("Неизвестная команда. Пожалуйста, используйте кнопки меню.")

async def handle_hide_menu(message: types.Message):
    await message.answer("Меню скрыто.", reply_markup=get_remove_keyboard())

# --- РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ---

# 1. Главные команды
dp.message.register(send_welcome, CommandStart(), IsAuthorizedUser())
dp.message.register(handle_my_plans_button_main, F.text == "Мои планы 🗓️", IsAuthorizedUser())
dp.message.register(handle_my_documents_button_main, F.text == "Мои документы 📁", IsAuthorizedUser())
dp.message.register(handle_my_finance_button_main, F.text == "Мои финансы 💰", IsAuthorizedUser())
dp.message.register(send_welcome, F.text == "Главное меню 🏠", IsAuthorizedUser())
dp.message.register(handle_hide_menu, F.text == "Скрыть меню ❌", IsAuthorizedUser())

# 2. Обработчики планов
dp.message.register(handle_add_plan_button, F.text == "Добавить план ➕", IsAuthorizedUser())
# ... (остальные обработчики планов без изменений)
dp.message.register(handle_today_plans_button, F.text == "Планы на сегодня ☀️", IsAuthorizedUser())
dp.message.register(handle_all_plans_button, F.text == "Все планы 📝", IsAuthorizedUser())
dp.message.register(handle_edit_plan_button, F.text == "Редактировать план ✏️", IsAuthorizedUser())
dp.message.register(handle_delete_plan_button, F.text == "Удалить план 🗑️", IsAuthorizedUser())
dp.message.register(handle_complete_plan_button, F.text == "Выполнить план ✅", IsAuthorizedUser())
dp.message.register(handle_set_reminder_button, F.text == "Установить напоминание ⏰", IsAuthorizedUser())
dp.message.register(add_plan_date_received, AddPlanStates.awaiting_date, IsAuthorizedUser())
dp.message.register(add_plan_topic_received, AddPlanStates.awaiting_topic, IsAuthorizedUser())
dp.message.register(add_plan_content_received, AddPlanStates.awaiting_plan_content, F.text | F.photo | F.voice, IsAuthorizedUser())
dp.message.register(add_plan_reminder_time_received, AddPlanStates.awaiting_reminder_time, IsAuthorizedUser())
dp.message.register(edit_plan_id_received, EditPlanStates.awaiting_id, IsAuthorizedUser())
dp.callback_query.register(choose_edit_field, EditPlanStates.choosing_edit_field, F.data.startswith("edit:"), IsAuthorizedUser())
dp.message.register(update_plan_text, EditPlanStates.editing_text, IsAuthorizedUser())
dp.message.register(update_plan_date, EditPlanStates.editing_date, IsAuthorizedUser())
dp.message.register(update_plan_topic, EditPlanStates.editing_topic, IsAuthorizedUser())
dp.message.register(delete_plans_ids_received, DeletePlanStates.awaiting_ids, IsAuthorizedUser())
dp.message.register(complete_plans_ids_received, CompletePlanStates.awaiting_ids, IsAuthorizedUser())
dp.message.register(set_reminder_id_received, SetReminderStates.awaiting_id, IsAuthorizedUser())
dp.message.register(set_reminder_time_received, SetReminderStates.awaiting_time, IsAuthorizedUser())

# 3. Обработчики файлов
dp.message.register(handle_list_files_button, F.text == "Список файлов 📄", IsAuthorizedUser())
# ... (остальные обработчики файлов без изменений, кроме логики категоризации)
dp.message.register(handle_get_file_button, F.text == "Получить файл 📥", IsAuthorizedUser())
dp.message.register(handle_search_files_by_name, F.text == "Поиск в док.", IsAuthorizedUser())
dp.message.register(handle_edit_file_button, F.text == "Редактировать файл ✏️", IsAuthorizedUser())
dp.message.register(handle_delete_document_button, F.text == "Удалить док. 🗑️", IsAuthorizedUser())
dp.message.register(get_file_id_received, GetFileStates.awaiting_id, IsAuthorizedUser())
dp.message.register(search_query_received, SearchFileStates.awaiting_query, IsAuthorizedUser())
dp.callback_query.register(choose_file_from_search, SearchFileStates.choosing_file, F.data.startswith("get_file_search:"), IsAuthorizedUser())
dp.callback_query.register(show_files_in_category, F.data.startswith("list_files_cat:"), IsAuthorizedUser())
dp.callback_query.register(edit_file_choose_category, EditFileStates.choosing_category, F.data.startswith("edit_file_cat:"), IsAuthorizedUser())
dp.message.register(edit_file_choose_file, EditFileStates.choosing_file, IsAuthorizedUser())
dp.callback_query.register(edit_file_choose_field, EditFileStates.choosing_field, F.data.startswith("edit_file:"), IsAuthorizedUser())
dp.message.register(edit_file_new_name_received, EditFileStates.editing_name, IsAuthorizedUser())
dp.message.register(edit_file_new_category_received, EditFileStates.editing_category, IsAuthorizedUser())
# Новая логика категоризации
dp.message.register(handle_done_categorizing, BatchCategorizeStates.awaiting_files, F.text == "Готово ✅", IsAuthorizedUser())
dp.callback_query.register(process_category_action_choice, BatchCategorizeStates.choosing_category_action, F.data.startswith("cat_choice:"), IsAuthorizedUser())
dp.callback_query.register(process_existing_category_selection, BatchCategorizeStates.selecting_existing_category, F.data.startswith("select_cat:"), IsAuthorizedUser())
dp.message.register(batch_category_received, BatchCategorizeStates.awaiting_category_for_batch, IsAuthorizedUser())
# Логика удаления
dp.callback_query.register(process_delete_type_choice, DeleteFileStates.choosing_delete_type, F.data.startswith("delete_doc_type:"), IsAuthorizedUser())
dp.callback_query.register(process_category_to_delete, DeleteFileStates.awaiting_category_to_delete, F.data.startswith("delete_doc_cat:"), IsAuthorizedUser())
dp.message.register(process_file_ids_to_delete, DeleteFileStates.awaiting_file_ids_to_delete, IsAuthorizedUser())

# 4. Обработчики финансов
dp.message.register(handle_create_book_button, F.text == "Создать книгу 📖", IsAuthorizedUser())
# ... (остальные обработчики финансов без изменений, кроме QR и регистрации)
dp.message.register(handle_my_books_button, F.text == "Мои книги 📚", IsAuthorizedUser())
dp.message.register(handle_delete_book_button, F.text == "Удалить книгу 🗑️", IsAuthorizedUser())
dp.message.register(handle_edit_book_button, F.text == "Редактировать книгу ✏️", IsAuthorizedUser())
dp.message.register(handle_back_to_books_button, F.text == "Назад к книгам 🔙", IsAuthorizedUser())
dp.message.register(process_book_name_to_create, FinanceStates.awaiting_book_name_to_create, IsAuthorizedUser())
dp.callback_query.register(process_book_currency_selection, FinanceStates.awaiting_book_currency, F.data.startswith("currency:"), IsAuthorizedUser())
dp.callback_query.register(process_book_selection, FinanceStates.choosing_book, F.data.startswith("select_book:"), IsAuthorizedUser())
dp.callback_query.register(process_book_selection_cancel, FinanceStates.choosing_book, F.data == "books:cancel", IsAuthorizedUser())
dp.callback_query.register(process_book_to_delete, FinanceStates.awaiting_book_to_delete, F.data.startswith("delete_book:"), IsAuthorizedUser())
dp.callback_query.register(process_delete_book_cancel, FinanceStates.awaiting_book_to_delete, F.data == "books:cancel", IsAuthorizedUser())
dp.callback_query.register(process_book_to_edit_selected, FinanceStates.awaiting_book_to_edit, F.data.startswith("edit_book:"), IsAuthorizedUser())
dp.callback_query.register(process_edit_book_cancel_selection, FinanceStates.awaiting_book_to_edit, F.data == "books:cancel", IsAuthorizedUser())
dp.callback_query.register(choose_edit_book_field, FinanceStates.choosing_edit_book_field, F.data.startswith("edit_book_field:"), IsAuthorizedUser())
dp.message.register(process_editing_book_name, FinanceStates.editing_book_name, IsAuthorizedUser())
dp.callback_query.register(process_editing_book_currency, FinanceStates.editing_book_currency, F.data.startswith("currency:"), IsAuthorizedUser())
# Ручной ввод транзакций
dp.message.register(handle_add_income_to_book_button, F.text.startswith("Добавить доход в "), IsAuthorizedUser())
dp.message.register(handle_add_expense_to_book_button, F.text.startswith("Добавить расход в "), IsAuthorizedUser())
# QR-сканирование
dp.message.register(handle_scan_qr_button, F.text == "💸 Сканировать QR расхода", IsAuthorizedUser())
dp.message.register(process_qr_photo, FinanceStates.awaiting_qr_photo, F.content_type == ContentType.PHOTO, IsAuthorizedUser())
dp.message.register(process_qr_category, FinanceStates.awaiting_qr_category, IsAuthorizedUser())
# Отчеты и баланс
dp.message.register(handle_book_balance_button, F.text.startswith("Баланс "), IsAuthorizedUser())
dp.message.register(handle_book_report_button, F.text.startswith("Отчет "), IsAuthorizedUser())
dp.message.register(handle_edit_transaction_button, F.text == "Редактировать транзакцию 📝", IsAuthorizedUser())
# Состояния для ручного ввода
dp.message.register(process_income_amount, FinanceStates.awaiting_income_amount, IsAuthorizedUser())
dp.message.register(process_income_description, FinanceStates.awaiting_income_description, IsAuthorizedUser())
dp.message.register(process_income_category, FinanceStates.awaiting_income_category, IsAuthorizedUser())
dp.message.register(process_income_date, FinanceStates.awaiting_income_date, IsAuthorizedUser())
dp.message.register(process_expense_amount, FinanceStates.awaiting_expense_amount, IsAuthorizedUser())
dp.message.register(process_expense_description, FinanceStates.awaiting_expense_description, IsAuthorizedUser())
dp.message.register(process_expense_category, FinanceStates.awaiting_expense_category, IsAuthorizedUser())
dp.message.register(process_expense_date, FinanceStates.awaiting_expense_date, IsAuthorizedUser())
# Состояния для редактирования транзакций
dp.message.register(process_transaction_to_edit_id, FinanceStates.awaiting_transaction_to_edit, IsAuthorizedUser())
dp.callback_query.register(choose_edit_transaction_field, FinanceStates.choosing_edit_transaction_field, F.data.startswith("edit_transaction_field:"), IsAuthorizedUser())
dp.message.register(process_editing_transaction_type, FinanceStates.editing_transaction_type, IsAuthorizedUser())
dp.message.register(process_editing_transaction_amount, FinanceStates.editing_transaction_amount, IsAuthorizedUser())
dp.message.register(process_editing_transaction_description, FinanceStates.editing_transaction_description, IsAuthorizedUser())
dp.message.register(process_editing_transaction_category, FinanceStates.editing_transaction_category, IsAuthorizedUser())
dp.message.register(process_editing_transaction_date, FinanceStates.editing_transaction_date, IsAuthorizedUser())
dp.callback_query.register(choose_report_format_for_book, FinanceStates.choosing_report_format_for_book, F.data.startswith("report_format:"), IsAuthorizedUser())

# 5. Обработчики контента
dp.message.register(handle_document_upload, F.content_type == ContentType.DOCUMENT, IsAuthorizedUser())

# 6. Обработчик неизвестных команд (в самом конце)
dp.message.register(handle_unknown_text, F.text, IsAuthorizedUser())

# --- Точка входа ---
async def main():
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        logger.info("Загрузка NLTK 'punkt'...")
        nltk.download("punkt", quiet=True)
    
    await init_db()
    
    set_bot_instance_for_scheduler(bot)
    
    scheduler.add_job(auto_archive_old_plans, trigger="interval", days=1, id="auto_archive_job")
    scheduler.start()
    await load_reminders_on_startup()
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())