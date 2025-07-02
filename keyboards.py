# keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мои планы 🗓️"), KeyboardButton(text="Мои документы 📁")],
            [KeyboardButton(text="Мои финансы 💰")],
            [KeyboardButton(text="Скрыть меню ❌")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def get_plans_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить план ➕"), KeyboardButton(text="Планы на сегодня ☀️")],
            [KeyboardButton(text="Все планы 📝"), KeyboardButton(text="Редактировать план ✏️")],
            [KeyboardButton(text="Удалить план 🗑️"), KeyboardButton(text="Выполнить план ✅")],
            [KeyboardButton(text="Установить напоминание ⏰"), KeyboardButton(text="Главное меню 🏠")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def get_docs_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Список файлов 📄"), KeyboardButton(text="Получить файл 📥")],
            [KeyboardButton(text="Редактировать файл ✏️"), KeyboardButton(text="Поиск в док.")],
            [KeyboardButton(text="Удалить док. 🗑️")],
            [KeyboardButton(text="Главное меню 🏠")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def get_finance_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Создать книгу 📖"), KeyboardButton(text="Мои книги 📚")],
            [KeyboardButton(text="Удалить книгу 🗑️"), KeyboardButton(text="Редактировать книгу ✏️")],
            [KeyboardButton(text="Главное меню 🏠")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def get_book_menu_keyboard(book_name: str):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"Добавить доход в {book_name} ⬆️")],
            [KeyboardButton(text=f"Добавить расход в {book_name} ⬇️")],
            [KeyboardButton(text="💸 Сканировать QR расхода")],
            [KeyboardButton(text=f"Баланс {book_name} 📊"), KeyboardButton(text=f"Отчет {book_name} 📈")],
            [KeyboardButton(text="Редактировать транзакцию 📝")],
            [KeyboardButton(text="Назад к книгам 🔙")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def get_date_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Сегодня")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def get_books_list_keyboard(books: list, action_prefix: str = "select_book"):
    keyboard_buttons = []
    if books:
        for book in books:
            keyboard_buttons.append([InlineKeyboardButton(text=f"{book['name']} ({book['currency']})", callback_data=f"{action_prefix}:{book['id']}")])
    keyboard_buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="books:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

def get_report_format_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="CSV", callback_data="report_format:csv")],
        [InlineKeyboardButton(text="PDF", callback_data="report_format:pdf")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="report_format:cancel")]
    ])

def get_currency_selection_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 USD", callback_data="currency:USD")],
        [InlineKeyboardButton(text="🇺🇿 UZS", callback_data="currency:UZS")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="currency:cancel")]
    ])

def get_edit_book_field_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Название книги", callback_data="edit_book_field:name")],
        [InlineKeyboardButton(text="Валюта книги", callback_data="edit_book_field:currency")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_book_field:cancel")]
    ])

def get_edit_transaction_field_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Тип (Доход/Расход)", callback_data="edit_transaction_field:type")],
        [InlineKeyboardButton(text="Сумма", callback_data="edit_transaction_field:amount")],
        [InlineKeyboardButton(text="Описание", callback_data="edit_transaction_field:description")],
        [InlineKeyboardButton(text="Категория", callback_data="edit_transaction_field:category")],
        [InlineKeyboardButton(text="Дата/Время", callback_data="edit_transaction_field:date")],
        [InlineKeyboardButton(text="🗑️ Удалить транзакцию", callback_data="edit_transaction_field:delete")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_transaction_field:cancel")]
    ])

def get_edit_file_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Название файла", callback_data="edit_file:name")],
        [InlineKeyboardButton(text="Категорию файла", callback_data="edit_file:category")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_file:cancel")]
    ])

def get_batch_categorize_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Готово ✅")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_remove_keyboard():
    return ReplyKeyboardRemove()

def get_delete_document_choice_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗂️ Категорию целиком", callback_data="delete_doc_type:category")],
        [InlineKeyboardButton(text="📄 Один или несколько файлов", callback_data="delete_doc_type:file")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="delete_doc_type:cancel")]
    ])

def get_categories_for_delete_keyboard(categories: list):
    buttons = [[InlineKeyboardButton(text=c['category'], callback_data=f"delete_doc_cat:{c['category']}")] for c in categories]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="delete_doc_cat:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_category_choice_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗂️ Выбрать существующую", callback_data="cat_choice:select_existing")],
        [InlineKeyboardButton(text="➕ Создать новую", callback_data="cat_choice:create_new")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cat_choice:cancel")]
    ])