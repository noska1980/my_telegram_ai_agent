# finance_handlers.py
import re
import datetime
import csv
import io
import os
import pytz
import aiohttp
import json
from bs4 import BeautifulSoup
from PIL import Image
from pyzbar.pyzbar import decode
import google.generativeai as genai

from reportlab.lib.pagesizes import A4
# ... (остальные импорты reportlab)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove, BufferedInputFile
from aiogram.utils.markdown import hbold

from config import logger, GEMINI_API_KEY
from filters import IsAuthorizedUser
from keyboards import (
    get_finance_keyboard, get_main_keyboard, get_report_format_keyboard,
    get_books_list_keyboard, get_book_menu_keyboard, get_currency_selection_keyboard,
    get_edit_book_field_keyboard, get_edit_transaction_field_keyboard,
    get_date_keyboard
)
from db import (
    add_transaction, get_book_balance_summary, get_transactions_by_book,
    add_book, get_user_books, delete_book, get_book_by_id, update_book_currency,
    update_book_name, get_transaction_by_id, update_transaction, delete_transaction,
    check_if_url_exists
)

# --- НАСТРОЙКА GEMINI AI ---
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')


# ... (код регистрации шрифтов без изменений)
FONT_NAME = "TimesNewRoman"
FONT_NAME_BOLD = "TimesNewRoman-Bold"
try:
    local_font_path = os.path.join(os.getcwd(), 'times.ttf')
    local_font_path_bold = os.path.join(os.getcwd(), 'timesbd.ttf') 
    if os.path.exists(local_font_path) and os.path.exists(local_font_path_bold):
        pdfmetrics.registerFont(TTFont(FONT_NAME, local_font_path))
        pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, local_font_path_bold))
    else:
        FONT_NAME = "Helvetica"
        FONT_NAME_BOLD = "Helvetica-Bold"
except Exception as e:
    logger.error(f"Ошибка при регистрации шрифта для ReportLab: {e}", exc_info=True)
    FONT_NAME = "Helvetica"
    FONT_NAME_BOLD = "Helvetica-Bold"


CURRENCY_SYMBOLS = {'USD': '$', 'UZS': 'сум', 'RUB': '₽', 'EUR': '€'}
def get_currency_symbol(currency_code: str) -> str:
    if not currency_code:
        return ""
    return CURRENCY_SYMBOLS.get(currency_code.upper(), currency_code.upper())

class FinanceStates(StatesGroup):
    # ... (все состояния без изменений)
    awaiting_book_name_to_create = State()
    awaiting_book_currency = State()
    awaiting_book_to_delete = State()
    choosing_book = State()
    awaiting_income_amount = State()
    awaiting_income_description = State()
    awaiting_income_category = State()
    awaiting_income_date = State()
    awaiting_expense_amount = State()
    awaiting_expense_description = State()
    awaiting_expense_category = State()
    awaiting_expense_date = State()
    awaiting_qr_photo = State()
    awaiting_qr_category = State()
    choosing_report_format_for_book = State()
    awaiting_book_to_edit = State()
    choosing_edit_book_field = State()
    editing_book_name = State()
    editing_book_currency = State()
    awaiting_transaction_to_edit = State()
    choosing_edit_transaction_field = State()
    editing_transaction_type = State()
    editing_transaction_amount = State()
    editing_transaction_description = State()
    editing_transaction_category = State()
    editing_transaction_date = State()

# ... (код до process_qr_photo без изменений)
async def handle_create_book_button(message: types.Message, state: FSMContext):
    await message.answer("Введите название новой книги учета:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(FinanceStates.awaiting_book_name_to_create)

async def handle_my_books_button(message: types.Message, state: FSMContext):
    books = await get_user_books(message.from_user.id)
    if not books:
        await message.answer("У вас пока нет книг учета.", reply_markup=get_finance_keyboard())
        return
    await message.answer("Выберите книгу для работы:", reply_markup=get_books_list_keyboard(books))
    await state.set_state(FinanceStates.choosing_book)

async def handle_delete_book_button(message: types.Message, state: FSMContext):
    books = await get_user_books(message.from_user.id)
    if not books:
        await message.answer("У вас пока нет книг для удаления.", reply_markup=get_finance_keyboard())
        return
    await message.answer("Выберите книгу для удаления:", reply_markup=get_books_list_keyboard(books, action_prefix="delete_book"))
    await state.set_state(FinanceStates.awaiting_book_to_delete)

async def handle_edit_book_button(message: types.Message, state: FSMContext):
    books = await get_user_books(message.from_user.id)
    if not books:
        await message.answer("У вас пока нет книг для редактирования.", reply_markup=get_finance_keyboard())
        return
    await message.answer("Выберите книгу для редактирования:", reply_markup=get_books_list_keyboard(books, action_prefix="edit_book"))
    await state.set_state(FinanceStates.awaiting_book_to_edit)

async def handle_finance_main_menu_button(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы вернулись в главное меню.", reply_markup=get_main_keyboard())

async def handle_back_to_books_button(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы вернулись к управлению книгами.", reply_markup=get_finance_keyboard())

async def process_book_name_to_create(message: types.Message, state: FSMContext):
    book_name = message.text.strip()
    if not book_name:
        await message.answer("Название не может быть пустым.", reply_markup=get_finance_keyboard())
        return
    await state.update_data(new_book_name=book_name)
    await message.answer("Выберите валюту:", reply_markup=get_currency_selection_keyboard())
    await state.set_state(FinanceStates.awaiting_book_currency)

async def process_book_currency_selection(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    user_data = await state.get_data()
    book_name = user_data.get('new_book_name')
    await callback.message.edit_reply_markup(reply_markup=None)
    if action == "cancel":
        await callback.message.answer("Создание книги отменено.", reply_markup=get_finance_keyboard())
    else:
        book_id = await add_book(callback.from_user.id, book_name, action.upper())
        if book_id:
            await callback.message.answer(f"✅ Книга «{hbold(book_name)}» ({hbold(action.upper())}) создана.", parse_mode="HTML", reply_markup=get_finance_keyboard())
        else:
            await callback.message.answer(f"❌ Книга «{hbold(book_name)}» уже существует.", parse_mode="HTML", reply_markup=get_finance_keyboard())
    await state.clear()

async def process_book_selection(callback: types.CallbackQuery, state: FSMContext):
    book_id = int(callback.data.split(":")[1])
    book = await get_book_by_id(callback.from_user.id, book_id)
    if book:
        await state.update_data(current_book_id=book['id'], current_book_name=book['name'], current_book_currency=book['currency'])
        await callback.message.edit_text(f"Выбрана книга «{hbold(book['name'])}» ({hbold(book['currency'])}).", parse_mode="HTML")
        await callback.message.answer("Выберите действие:", reply_markup=get_book_menu_keyboard(book['name']))
        await state.set_state(None)
    else:
        await callback.message.edit_text("Книга не найдена.")
    await callback.answer()

async def process_book_selection_cancel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Выбор отменен.")
    await state.clear()
    await callback.answer()

async def process_book_to_delete(callback: types.CallbackQuery, state: FSMContext):
    book_id = int(callback.data.split(":")[1])
    book = await get_book_by_id(callback.from_user.id, book_id)
    if book and await delete_book(callback.from_user.id, book_id):
        await callback.message.edit_text(f"✅ Книга «{hbold(book['name'])}» удалена.", parse_mode="HTML")
    else:
        await callback.message.edit_text("❌ Ошибка удаления.")
    await state.clear()
    await callback.answer()

async def process_delete_book_cancel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Удаление отменено.")
    await state.clear()
    await callback.answer()

async def process_book_to_edit_selected(callback: types.CallbackQuery, state: FSMContext):
    book_id = int(callback.data.split(":")[1])
    book = await get_book_by_id(callback.from_user.id, book_id)
    if book:
        await state.update_data(editing_book_id=book['id'], editing_book_name=book['name'])
        await callback.message.edit_text(f"Редактирование «{hbold(book['name'])}». Что изменить?", reply_markup=get_edit_book_field_keyboard(), parse_mode="HTML")
        await state.set_state(FinanceStates.choosing_edit_book_field)
    else:
        await callback.message.edit_text("Книга не найдена.")
    await callback.answer()

async def process_edit_book_cancel_selection(callback: types.CallbackQuery, state: FSMContext):
     await callback.message.edit_text("Редактирование отменено.")
     await state.clear()
     await callback.answer()

async def choose_edit_book_field(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    await callback.message.edit_reply_markup(reply_markup=None)
    if action == "name":
        await callback.message.answer("Введите новое название:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(FinanceStates.editing_book_name)
    elif action == "currency":
        await callback.message.answer("Выберите новую валюту:", reply_markup=get_currency_selection_keyboard())
        await state.set_state(FinanceStates.editing_book_currency)
    else:
        await callback.message.answer("Отменено.", reply_markup=get_finance_keyboard())
        await state.clear()
    await callback.answer()

async def process_editing_book_name(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    new_name = message.text.strip()
    if not new_name:
        await message.answer("Название не может быть пустым.", reply_markup=get_finance_keyboard()); await state.clear(); return
    if await update_book_name(message.from_user.id, user_data.get('editing_book_id'), new_name):
        await message.answer(f"✅ Название изменено на «{hbold(new_name)}».", parse_mode="HTML", reply_markup=get_finance_keyboard())
    else:
        await message.answer("❌ Ошибка смены имени.", reply_markup=get_finance_keyboard())
    await state.clear()

async def process_editing_book_currency(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    user_data = await state.get_data()
    await callback.message.edit_reply_markup(reply_markup=None)
    if action == "cancel":
        await callback.message.answer("Отменено.", reply_markup=get_finance_keyboard()); await state.clear(); return
    if await update_book_currency(callback.from_user.id, user_data.get('editing_book_id'), action.upper()):
        await callback.message.answer(f"✅ Валюта изменена на {hbold(action.upper())}.", parse_mode="HTML", reply_markup=get_finance_keyboard())
    else:
        await callback.message.answer("❌ Ошибка смены валюты.", reply_markup=get_finance_keyboard())
    await state.clear()

async def handle_add_income_to_book_button(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    if not user_data.get('current_book_id'):
        await message.answer("Сначала выберите книгу из меню 'Мои книги 📚'.", reply_markup=get_finance_keyboard())
        return
    await message.answer(f"Введите сумму дохода для «{hbold(user_data.get('current_book_name'))}»:", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await state.set_state(FinanceStates.awaiting_income_amount)

async def process_income_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        if amount <= 0: raise ValueError
        await state.update_data(income_amount=amount)
        await message.answer("Введите описание дохода:")
        await state.set_state(FinanceStates.awaiting_income_description)
    except ValueError:
        await message.answer("Неверная сумма.")

async def process_income_description(message: types.Message, state: FSMContext):
    await state.update_data(income_description=(message.text.strip() or "Без описания"))
    await message.answer("Введите категорию (или 'нет'):")
    await state.set_state(FinanceStates.awaiting_income_category)

async def process_income_category(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, введите название категории текстом.")
        return
    category = message.text.strip()
    await state.update_data(income_category=("Прочие" if category.lower() == 'нет' else category))
    await message.answer("Введите дату транзакции в формате 'ДД.ММ.ГГГГ' или нажмите кнопку 'Сегодня'.", reply_markup=get_date_keyboard())
    await state.set_state(FinanceStates.awaiting_income_date)

async def process_income_date(message: types.Message, state: FSMContext):
    try:
        date_str = message.text.strip().lower()
        if date_str == 'сегодня':
            transaction_dt = datetime.datetime.now()
        else:
            transaction_dt = datetime.datetime.strptime(date_str, "%d.%m.%Y")
        
        user_data = await state.get_data()
        if not user_data.get('current_book_id'):
            await message.answer("Сессия выбора книги истекла. Пожалуйста, выберите книгу заново.", reply_markup=get_finance_keyboard())
            await state.clear()
            return
        
        await add_transaction(
            user_id=message.from_user.id,
            book_id=user_data['current_book_id'],
            type='income',
            amount=user_data['income_amount'],
            description=user_data['income_description'],
            category=user_data['income_category'],
            transaction_date=transaction_dt.strftime("%Y-%m-%d %H:%M:%S")
        )
        await message.answer(f"✅ Доход записан.", parse_mode="HTML", reply_markup=get_book_menu_keyboard(user_data['current_book_name']))
        await state.set_state(None)
    except ValueError:
        await message.answer("Неверный формат. Введите ДД.ММ.ГГГГ или нажмите 'Сегодня'.")

async def handle_add_expense_to_book_button(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    if not user_data.get('current_book_id'):
        await message.answer("Сначала выберите книгу из меню 'Мои книги 📚'.", reply_markup=get_finance_keyboard())
        return
    await message.answer(f"Введите сумму расхода для «{hbold(user_data.get('current_book_name'))}»:", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await state.set_state(FinanceStates.awaiting_expense_amount)

async def process_expense_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        if amount <= 0: raise ValueError
        await state.update_data(expense_amount=amount)
        await message.answer("Введите описание расхода:")
        await state.set_state(FinanceStates.awaiting_expense_description)
    except ValueError:
        await message.answer("Неверная сумма.")

async def process_expense_description(message: types.Message, state: FSMContext):
    await state.update_data(expense_description=(message.text.strip() or "Без описания"))
    await message.answer("Введите категорию (или 'нет'):")
    await state.set_state(FinanceStates.awaiting_expense_category)

async def process_expense_category(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, введите название категории текстом.")
        return
    category = message.text.strip()
    await state.update_data(expense_category=("Прочие" if category.lower() == 'нет' else category))
    await message.answer("Введите дату транзакции в формате 'ДД.ММ.ГГГГ' или нажмите кнопку 'Сегодня'.", reply_markup=get_date_keyboard())
    await state.set_state(FinanceStates.awaiting_expense_date)

async def process_expense_date(message: types.Message, state: FSMContext):
    try:
        date_str = message.text.strip().lower()
        if date_str == 'сегодня':
            transaction_dt = datetime.datetime.now()
        else:
            transaction_dt = datetime.datetime.strptime(date_str, "%d.%m.%Y")
        
        user_data = await state.get_data()
        if not user_data.get('current_book_id'):
            await message.answer("Сессия выбора книги истекла. Пожалуйста, выберите книгу заново.", reply_markup=get_finance_keyboard())
            await state.clear()
            return

        await add_transaction(
            user_id=message.from_user.id,
            book_id=user_data['current_book_id'],
            type='expense',
            amount=user_data['expense_amount'],
            description=user_data['expense_description'],
            category=user_data['expense_category'],
            transaction_date=transaction_dt.strftime("%Y-%m-%d %H:%M:%S")
        )
        await message.answer(f"✅ Расход записан.", parse_mode="HTML", reply_markup=get_book_menu_keyboard(user_data['current_book_name']))
        await state.set_state(None)
    except ValueError:
        await message.answer("Неверный формат. Введите ДД.ММ.ГГГГ или нажмите 'Сегодня'.")

async def handle_scan_qr_button(message: types.Message, state: FSMContext):
    """Запрашивает фото QR-кода."""
    user_data = await state.get_data()
    if not user_data.get('current_book_id'):
        await message.answer("Сначала выберите книгу из меню 'Мои книги 📚'.", reply_markup=get_finance_keyboard())
        return
    await message.answer("Пожалуйста, отправьте фотографию с QR-кодом чека.", reply_markup=ReplyKeyboardRemove())
    await state.set_state(FinanceStates.awaiting_qr_photo)


async def process_qr_photo(message: types.Message, state: FSMContext):
    """Обрабатывает полученное фото с QR-кодом с помощью Gemini AI."""
    if not message.photo:
        await message.answer("Пожалуйста, отправьте именно фотографию.")
        return

    await message.answer("🤖 Анализирую чек с помощью ИИ, это может занять несколько секунд...")

    photo_file = await message.bot.get_file(message.photo[-1].file_id)
    photo_bytes = await message.bot.download_file(photo_file.file_path)
    
    try:
        img = Image.open(io.BytesIO(photo_bytes.read()))
        decoded_objects = decode(img)

        if not decoded_objects:
            await message.answer("QR-код на фото не найден. Попробуйте сделать более четкое фото.")
            return

        qr_url = decoded_objects[0].data.decode("utf-8")
        logger.info(f"Распознан URL из QR: {qr_url}")
        
        # ПРОВЕРКА НА ДУБЛИКАТ
        if await check_if_url_exists(qr_url):
            await message.answer("❌ Этот чек уже был добавлен в базу данных ранее.")
            # Сбрасываем состояние и возвращаем основную клавиатуру для книги
            user_data = await state.get_data()
            await state.set_state(None)
            await message.answer("Выберите действие:", reply_markup=get_book_menu_keyboard(user_data['current_book_name']))
            return

        if "ofd.soliq.uz" not in qr_url:
            raise ValueError("QR-код не является фискальным чеком soliq.uz.")

        async with aiohttp.ClientSession() as session:
            async with session.get(qr_url) as response:
                if response.status != 200:
                    raise ConnectionError(f"Не удалось получить доступ к чеку. Статус: {response.status}")
                html_content = await response.text()

        soup = BeautifulSoup(html_content, 'lxml')
        check_text = soup.body.get_text(separator='\n', strip=True)

        prompt = f"""
        Ты — эксперт по анализу фискальных чеков из Узбекистана. Проанализируй следующий текст, извлеченный со страницы чека.
        Твоя задача — вернуть JSON объект со следующей структурой:
        - "total_sum": число, итоговая сумма чека (найди строку "Jami to`lov").
        - "check_date": строка, дата и время в формате "YYYY-MM-DD HH:MM:SS".
        - "items": массив объектов, где каждый объект представляет товар со следующими ключами: "name", "quantity", "price_total".

        Если не можешь найти какое-то значение, используй null. Не выдумывай данные.
        В поле "check_date" используй дату и время с чека, а не текущие.

        Вот текст чека:
        ---
        {check_text}
        ---
        """
        
        logger.info("Отправка запроса в Gemini AI для анализа чека.")
        response = await gemini_model.generate_content_async(prompt)
        
        json_text = response.text.replace('```json', '').replace('```', '').strip()
        parsed_data = json.loads(json_text)
        logger.info(f"Получены структурированные данные от Gemini: {parsed_data}")

        total_sum = float(parsed_data.get("total_sum", 0))
        check_date_str = parsed_data.get("check_date")
        items = parsed_data.get("items", [])

        if total_sum <= 0 or not check_date_str or not items:
            raise ValueError("ИИ не смог извлечь все необходимые данные из чека.")

        transaction_dt = datetime.datetime.fromisoformat(check_date_str)
        
        description_items = [f"Чек от {transaction_dt.strftime('%d.%m.%Y')}"]
        for item in items:
            name = item.get("name", "Неизвестный товар")
            quantity = float(item.get("quantity", 1.0))
            price_total = float(item.get("price_total", 0.0))
            price_per_unit = price_total / quantity if quantity != 0 else 0
            description_items.append(
                f"- {name} ({quantity} шт x {price_per_unit:,.2f}) = {price_total:,.2f} сум"
            )
        
        description = "\n".join(description_items)

        await state.update_data(
            qr_amount=total_sum,
            qr_description=description,
            qr_date=transaction_dt.strftime("%Y-%m-%d %H:%M:%S"),
            qr_check_url=qr_url # Сохраняем URL для защиты от дубликатов
        )
        
        await message.answer(
            f"🧾Сумма по чеку: {hbold(f'{total_sum:,.2f} сум')} от {transaction_dt.strftime('%d.%m.%Y')}. "
            f"\n\n{hbold('Позиции:')}\n{description}\n\n"
            f"Введите категорию для этого расхода.",
            parse_mode="HTML"
        )
        await state.set_state(FinanceStates.awaiting_qr_category)

    except Exception as e:
        logger.error(f"Ошибка обработки фото с QR: {e}", exc_info=True)
        await message.answer(f"Не удалось обработать QR-код. Попробуйте еще раз или введите расход вручную.\nОшибка: `{e}`")


async def process_qr_category(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, введите название категории текстом.")
        return
        
    category = message.text.strip()
    user_data = await state.get_data()
    
    if not user_data.get('current_book_id'):
        await message.answer("Сессия выбора книги истекла. Пожалуйста, выберите книгу заново.", reply_markup=get_finance_keyboard())
        await state.clear()
        return

    await add_transaction(
        user_id=message.from_user.id,
        book_id=user_data['current_book_id'],
        type='expense',
        amount=user_data['qr_amount'],
        description=user_data['qr_description'],
        category=category,
        transaction_date=user_data['qr_date'],
        check_url=user_data['qr_check_url'] # Сохраняем URL
    )
    await message.answer(f"✅ Расход по QR записан в категорию «{hbold(category)}».", parse_mode="HTML", reply_markup=get_book_menu_keyboard(user_data['current_book_name']))
    await state.clear()

async def handle_book_balance_button(message: types.Message, state: FSMContext):
    # ... (код без изменений)
    user_data = await state.get_data()
    book_id = user_data.get('current_book_id')
    book_name = user_data.get('current_book_name')
    book_currency = user_data.get('current_book_currency')
    
    if not book_id:
        await message.answer("Пожалуйста, сначала выберите книгу из меню 'Мои книги 📚'.", reply_markup=get_finance_keyboard())
        return
        
    symbol = get_currency_symbol(book_currency)
    total_income, total_expense = await get_book_balance_summary(message.from_user.id, book_id)
    balance = total_income - total_expense
    await message.answer(f"📊 Баланс «{hbold(book_name)}»:\n⬆️ Доходы: {total_income:.2f} {symbol}\n⬇️ Расходы: {total_expense:.2f} {symbol}\n💰 Итог: {hbold(f'{balance:.2f} {symbol}')}", parse_mode="HTML")

async def handle_book_report_button(message: types.Message, state: FSMContext):
    # ... (код без изменений)
    user_data = await state.get_data()
    if not user_data.get('current_book_id'):
        await message.answer("Пожалуйста, сначала выберите книгу из меню 'Мои книги 📚'.", reply_markup=get_finance_keyboard())
        return
    await message.answer("Выберите формат отчета:", reply_markup=get_report_format_keyboard())
    await state.set_state(FinanceStates.choosing_report_format_for_book)

async def choose_report_format_for_book(callback: types.CallbackQuery, state: FSMContext):
    # ... (код без изменений)
    report_format = callback.data.split(":")[1]
    if report_format == "cancel":
        await callback.message.edit_text("Создание отчета отменено.")
        await state.set_state(None)
        return
    
    user_data = await state.get_data()
    book_id = user_data.get('current_book_id')
    book_name = user_data.get('current_book_name')
    book_currency = user_data.get('current_book_currency')
    
    if not book_id:
        await callback.message.edit_text("Сессия выбора книги истекла. Пожалуйста, выберите книгу заново.")
        await state.clear()
        return
        
    transactions = await get_transactions_by_book(callback.from_user.id, book_id)
    if not transactions:
        await callback.message.edit_text(f"В книге «{hbold(book_name)}» нет транзакций.", parse_mode="HTML")
        await state.set_state(None)
        return

    await callback.message.edit_text(f"Готовлю {report_format.upper()} отчет...")
    file_name_prefix = f"report_{book_name}_{datetime.date.today()}"
    
    total_income = sum(t['amount'] for t in transactions if t['type'] == 'income')
    total_expense = sum(t['amount'] for t in transactions if t['type'] == 'expense')
    balance = total_income - total_expense

    if report_format == "csv":
        string_io = io.StringIO()
        type_map = {"income": "Доход", "expense": "Расход"}
        writer = csv.writer(string_io)
        writer.writerow(["ID", "Дата", "Тип", "Сумма", "Валюта", "Категория", "Описание"])
        for t in transactions:
            writer.writerow([t['id'], t['transaction_date'], type_map.get(t['type'], t['type']), t['amount'], book_currency, t['category'], t['description']])
        
        writer.writerow([]) 
        writer.writerow(['', '', 'Общая сумма Доходов', f'{total_income:.2f}', book_currency])
        writer.writerow(['', '', 'Общая сумма Расходов', f'{total_expense:.2f}', book_currency])
        writer.writerow(['', '', 'Баланс', f'{balance:.2f}', book_currency])

        file = BufferedInputFile(string_io.getvalue().encode('utf-8-sig'), filename=f"{file_name_prefix}.csv")
    
    elif report_format == "pdf":
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=1.5*cm, rightMargin=1.5*cm)
        
        styles = getSampleStyleSheet()
        income_color = colors.HexColor("#000080")
        expense_color = colors.HexColor("#FF0000")
        title_color = colors.HexColor("#0000CD")

        title_style = ParagraphStyle(name='TitleStyle', fontName=FONT_NAME_BOLD, fontSize=16, alignment=TA_CENTER, spaceAfter=12)
        header_style = ParagraphStyle(name='HeaderStyle', fontName=FONT_NAME_BOLD, fontSize=10, alignment=TA_CENTER, textColor=colors.whitesmoke)
        
        base_body_style = ParagraphStyle(name='BaseBody', fontName=FONT_NAME, fontSize=9, alignment=TA_LEFT)
        income_style = ParagraphStyle(name='IncomeStyle', parent=base_body_style, textColor=income_color)
        expense_style = ParagraphStyle(name='ExpenseStyle', parent=base_body_style, textColor=expense_color)

        summary_label_style = ParagraphStyle(name='SummaryLabel', fontName=FONT_NAME_BOLD, fontSize=10, alignment=TA_RIGHT)
        summary_value_style = ParagraphStyle(name='SummaryValue', fontName=FONT_NAME, fontSize=10, alignment=TA_LEFT)
        
        type_map = {"income": "Доход", "expense": "Расход"}
        headers = ["ID", "Дата", "Тип", "Сумма", "Категория", "Описание"]
        data = [[Paragraph(h, header_style) for h in headers]]

        for t in transactions:
            row_style = income_style if t['type'] == 'income' else expense_style
            row = [
                Paragraph(str(t['id']), row_style),
                Paragraph(datetime.datetime.fromisoformat(t['transaction_date']).strftime('%d.%m.%y %H:%M'), row_style),
                Paragraph(type_map.get(t['type'], t['type']), row_style),
                Paragraph(f"{t['amount']:.2f}", row_style),
                Paragraph(t['category'] or '', row_style),
                Paragraph(t['description'] or '', row_style),
            ]
            data.append(row)

        data.append(['', '', '', '', '', ''])
        currency_str = get_currency_symbol(book_currency)
        data.append([
            '', '', Paragraph('Общая сумма Доходов', summary_label_style), Paragraph(f'{total_income:.2f} {currency_str}', summary_value_style), '', ''
        ])
        data.append([
            '', '', Paragraph('Общая сумма Расходов', summary_label_style), Paragraph(f'{total_expense:.2f} {currency_str}', summary_value_style), '', ''
        ])
        data.append([
            '', '', Paragraph('Баланс', summary_label_style), Paragraph(f'{balance:.2f} {currency_str}', summary_value_style), '', ''
        ])

        table = Table(data, colWidths=[cm, 2.5*cm, 3.5*cm, 3*cm, 3*cm, 4*cm])
        
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('GRID', (0, 0), (-1, -5), 1, colors.black),
            ('GRID', (2, -3), (3, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('SPAN', (3, -4), (5, -4)),
            ('SPAN', (0, -4), (1, -4)),
            ('BACKGROUND', (2, -1), (3, -1), colors.lightgrey),
        ]))
        
        title_text = f"Отчет по книге: <font color='{title_color.hexval()}'>{book_name}</font>"
        title_paragraph = Paragraph(title_text, title_style)
        
        elements = [title_paragraph, table]
        doc.build(elements)
        file = BufferedInputFile(buffer.getvalue(), filename=f"{file_name_prefix}.pdf")

    await callback.message.answer_document(file, caption=f"Ваш {report_format.upper()} отчет.")
    await state.set_state(None)

async def handle_edit_transaction_button(message: types.Message, state: FSMContext):
    # ... (код без изменений)
    user_data = await state.get_data()
    book_id = user_data.get('current_book_id')
    book_currency = user_data.get('current_book_currency')
    
    if not book_id:
        await message.answer("Пожалуйста, сначала выберите книгу из меню 'Мои книги 📚'.", reply_markup=get_finance_keyboard())
        return
        
    transactions = await get_transactions_by_book(message.from_user.id, book_id)
    if not transactions:
        await message.answer("В этой книге еще нет транзакций.", reply_markup=get_book_menu_keyboard(user_data.get('current_book_name')))
        return

    response_lines = [f"{hbold('Последние 15 транзакций:')}\n"]
    type_map = {"income": "Доход", "expense": "Расход"}
    for t in transactions[:15]:
        date_str = datetime.datetime.fromisoformat(t['transaction_date']).strftime('%d.%m %H:%M')
        response_lines.append(f"ID: {hbold(t['id'])} | {date_str} | {type_map.get(t['type'], t['type'])} | {t['amount']:.2f} {get_currency_symbol(book_currency)} | {t['description'] or ''}")
    
    await message.answer("\n".join(response_lines), parse_mode="HTML")
    await message.answer("Введите ID транзакции для редактирования:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(FinanceStates.awaiting_transaction_to_edit)

async def process_transaction_to_edit_id(message: types.Message, state: FSMContext):
    # ... (код без изменений)
    try:
        transaction_id = int(message.text.strip())
        transaction = await get_transaction_by_id(message.from_user.id, transaction_id)
        if not transaction:
            await message.answer(f"Транзакция с ID {transaction_id} не найдена.", reply_markup=get_finance_keyboard())
            await state.clear()
            return
        
        await state.update_data(editing_transaction_id=transaction_id)
        book = await get_book_by_id(message.from_user.id, transaction['book_id'])
        symbol = get_currency_symbol(book['currency'])
        date_str = datetime.datetime.fromisoformat(transaction['transaction_date']).strftime('%d.%m.%Y %H:%M')
        type_map = {"income": "Доход", "expense": "Расход"}

        await message.answer(
            f"Редактирование транзакции ID {hbold(transaction_id)}:\n"
            f"Тип: {type_map.get(transaction['type'], transaction['type'])}, Сумма: {transaction['amount']} {symbol}\n"
            f"Категория: {transaction['category']}, Описание: {transaction['description']}\n"
            f"Дата: {date_str}\n\n"
            "Что вы хотите сделать?",
            reply_markup=get_edit_transaction_field_keyboard(), parse_mode="HTML"
        )
        await state.set_state(FinanceStates.choosing_edit_transaction_field)
    except ValueError:
        await message.answer("ID должен быть числом.")

async def choose_edit_transaction_field(callback: types.CallbackQuery, state: FSMContext):
    # ... (код без изменений)
    action = callback.data.split(":")[1]
    await callback.message.edit_reply_markup(reply_markup=None)

    if action == "cancel":
        await callback.message.answer("Редактирование отменено.", reply_markup=get_finance_keyboard())
        await state.clear()
        return
    
    if action == "delete":
        user_data = await state.get_data()
        transaction_id = user_data.get('editing_transaction_id')
        if await delete_transaction(callback.from_user.id, transaction_id):
            await callback.message.answer(f"✅ Транзакция ID {transaction_id} удалена.", reply_markup=get_finance_keyboard())
        else:
            await callback.message.answer(f"❌ Ошибка удаления.", reply_markup=get_finance_keyboard())
        await state.clear()
        return

    field_map = {
        "type": ("Какой новый тип? ('доход' или 'расход')", FinanceStates.editing_transaction_type),
        "amount": ("Введите новую сумму:", FinanceStates.editing_transaction_amount),
        "description": ("Введите новое описание:", FinanceStates.editing_transaction_description),
        "category": ("Введите новую категорию:", FinanceStates.editing_transaction_category),
        "date": ("Введите новую дату и время (ДД.ММ.ГГГГ ЧЧ:ММ):", FinanceStates.editing_transaction_date)
    }
    prompt_text, next_state = field_map[action]
    await callback.message.answer(prompt_text, reply_markup=ReplyKeyboardRemove())
    await state.set_state(next_state)
    await callback.answer()

async def process_editing_transaction_type(message: types.Message, state: FSMContext):
    # ... (код без изменений)
    new_type_raw = message.text.strip().lower()
    new_type_db = "income" if new_type_raw in ["доход", "income"] else "expense" if new_type_raw in ["расход", "expense"] else None
    if new_type_db is None:
        await message.answer("Неверный тип. Введите 'доход' или 'расход'.")
        return

    user_data = await state.get_data()
    transaction_id = user_data['editing_transaction_id']
    await update_transaction(message.from_user.id, transaction_id, 'type', new_type_db)
    await message.answer(f"✅ Тип транзакции ID {transaction_id} обновлен.", reply_markup=get_finance_keyboard())
    await state.clear()

async def process_editing_transaction_amount(message: types.Message, state: FSMContext):
    # ... (код без изменений)
    try:
        amount = float(message.text.strip())
        if amount <= 0: raise ValueError
        user_data = await state.get_data()
        transaction_id = user_data['editing_transaction_id']
        await update_transaction(message.from_user.id, transaction_id, 'amount', amount)
        await message.answer(f"✅ Сумма для транзакции ID {transaction_id} обновлена.", reply_markup=get_finance_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("Неверная сумма.")

async def process_editing_transaction_description(message: types.Message, state: FSMContext):
    # ... (код без изменений)
    description = message.text.strip()
    user_data = await state.get_data()
    transaction_id = user_data['editing_transaction_id']
    await update_transaction(message.from_user.id, transaction_id, 'description', description)
    await message.answer(f"✅ Описание для транзакции ID {transaction_id} обновлено.", reply_markup=get_finance_keyboard())
    await state.clear()

async def process_editing_transaction_category(message: types.Message, state: FSMContext):
    # ... (код без изменений)
    category = message.text.strip()
    user_data = await state.get_data()
    transaction_id = user_data['editing_transaction_id']
    await update_transaction(message.from_user.id, transaction_id, 'category', category)
    await message.answer(f"✅ Категория для транзакции ID {transaction_id} обновлена.", reply_markup=get_finance_keyboard())
    await state.clear()

async def process_editing_transaction_date(message: types.Message, state: FSMContext):
    # ... (код без изменений)
    try:
        dt_obj = datetime.datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        db_date_str = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
        user_data = await state.get_data()
        transaction_id = user_data['editing_transaction_id']
        await update_transaction(message.from_user.id, transaction_id, 'transaction_date', db_date_str)
        await message.answer(f"✅ Дата для транзакции ID {transaction_id} обновлена.", reply_markup=get_finance_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("Неверный формат. Введите дату как ДД.ММ.ГГГГ ЧЧ:ММ.")