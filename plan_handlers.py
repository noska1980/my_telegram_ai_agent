# plan_handlers.py
import datetime
import re
import aiosqlite
import pytz
from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.utils.markdown import hbold, hstrikethrough
from aiogram.filters import StateFilter

from config import DB_NAME, USER_TIMEZONE_STR, logger
from db import add_plan_to_db, get_all_user_plans, get_plan_by_id, get_plans_for_date, get_attachments_for_plan
from scheduler_jobs import scheduler, send_reminder_job
from filters import IsAuthorizedUser
from keyboards import get_plans_keyboard, get_main_keyboard, get_date_keyboard

# --- Определения состояний (FSM) ---
class AddPlanStates(StatesGroup):
    awaiting_date = State()
    awaiting_topic = State()
    awaiting_plan_content = State()
    awaiting_reminder_time = State()

class EditPlanStates(StatesGroup):
    awaiting_id = State()
    choosing_edit_field = State()
    editing_text = State()
    editing_date = State()
    editing_topic = State()

class DeletePlanStates(StatesGroup):
    awaiting_ids = State()

class CompletePlanStates(StatesGroup):
    awaiting_ids = State()

class SetReminderStates(StatesGroup):
    awaiting_id = State()
    awaiting_time = State()

# --- ОБРАБОТЧИКИ КНОПОК МЕНЮ ПЛАНОВ ---

async def handle_add_plan_button(message: types.Message, state: FSMContext):
    """Начинает диалог добавления плана, запрашивая дату."""
    logger.info(f"Получено нажатие 'Добавить план ➕' от пользователя {message.from_user.id}")
    await message.answer("На какую дату вы хотите добавить план? Введите в формате ДД.ММ.ГГГГ или нажмите кнопку 'Сегодня':", reply_markup=get_date_keyboard())
    await state.set_state(AddPlanStates.awaiting_date)

async def handle_today_plans_button(message: types.Message):
    """Показывает планы на сегодня."""
    from telegram_handlers import display_multiple_plans
    logger.info(f"Получено нажатие 'Планы на сегодня ☀️' от пользователя {message.from_user.id}")
    user_id = message.from_user.id
    today_date_str = datetime.date.today().strftime("%Y-%m-%d")
    plans = await get_plans_for_date(user_id, today_date_str)
    if not plans:
        await message.answer(f"На сегодня ({datetime.date.today().strftime('%d.%m.%Y г.')}) планов нет.", reply_markup=get_plans_keyboard())
        return
    today_display_date = datetime.date.today().strftime("%d.%m.%Y г.")
    await display_multiple_plans(message, plans, f"Планы на сегодня ({hbold(today_display_date)}):")
    await message.answer("Вы можете выбрать другое действие:", reply_markup=get_plans_keyboard())

async def handle_all_plans_button(message: types.Message):
    """Показывает все планы пользователя."""
    from telegram_handlers import display_multiple_plans
    logger.info(f"Получено нажатие 'Все планы 📝' от пользователя {message.from_user.id}")
    user_id = message.from_user.id
    plans = await get_all_user_plans(user_id)
    if not plans:
        await message.answer("У вас еще нет планов.", reply_markup=get_plans_keyboard())
        return
    await display_multiple_plans(message, plans, "Все ваши планы:")
    await message.answer("Вы можете выбрать другое действие:", reply_markup=get_plans_keyboard())

async def handle_edit_plan_button(message: types.Message, state: FSMContext):
    """Запускает FSM для редактирования плана."""
    logger.info(f"Получено нажатие 'Редактировать план ✏️' от пользователя {message.from_user.id}")
    await message.answer("Введите ID плана, который хотите отредактировать:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(EditPlanStates.awaiting_id)

async def handle_delete_plan_button(message: types.Message, state: FSMContext):
    """Запускает FSM для удаления плана."""
    logger.info(f"Получено нажатие 'Удалить план 🗑️' от пользователя {message.from_user.id}")
    await message.answer("Введите ID плана (или нескольких ID через запятую/пробел) для удаления:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(DeletePlanStates.awaiting_ids)

async def handle_complete_plan_button(message: types.Message, state: FSMContext):
    """Запускает FSM для отметки о выполнении."""
    logger.info(f"Получено нажатие 'Выполнить план ✅' от пользователя {message.from_user.id}")
    await message.answer("Введите ID плана (или нескольких) для отметки о выполнении:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CompletePlanStates.awaiting_ids)

async def handle_set_reminder_button(message: types.Message, state: FSMContext):
    """Запускает FSM для установки напоминания."""
    logger.info(f"Получено нажатие 'Установить напоминание ⏰' от пользователя {message.from_user.id}")
    await message.answer("Введите ID плана, для которого нужно напоминание:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(SetReminderStates.awaiting_id)

# --- ОБРАБОТЧИКИ СОСТОЯНИЙ (FSM) ---

async def add_plan_date_received(message: types.Message, state: FSMContext):
    """Обрабатывает полученную дату и запрашивает тему плана."""
    logger.info(f"Получена дата плана от пользователя {message.from_user.id}: {message.text}")
    date_str = message.text.strip()
    try:
        if date_str.lower() == 'сегодня':
            date_obj = datetime.datetime.now()
            logger.info("Выбрана текущая дата по кнопке.")
        else:
            date_obj = datetime.datetime.strptime(date_str, "%d.%m.%Y")

        db_date_str = date_obj.strftime("%Y-%m-%d")
        display_date_str = date_obj.strftime("%d.%m.%Y г.")
        await state.update_data(plan_date_db=db_date_str, display_date=display_date_str)
        await message.answer(f"Дата {display_date_str}. Теперь введите тему плана:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(AddPlanStates.awaiting_topic)
    except ValueError:
        await message.answer("Неверный формат даты. Введите дату в формате ДД.ММ.ГГГГ или нажмите кнопку 'Сегодня'.", reply_markup=get_date_keyboard())


async def add_plan_topic_received(message: types.Message, state: FSMContext):
    """Обрабатывает полученную тему и запрашивает контент плана."""
    topic_text = message.text.strip()
    if not topic_text:
        await message.answer("Тема плана не может быть пустой. Пожалуйста, введите тему:", reply_markup=get_plans_keyboard())
        return
    await state.update_data(plan_topic=topic_text)
    display_date = (await state.get_data()).get('display_date')
    logger.info(f"Получена тема плана от пользователя {message.from_user.id}: '{topic_text}'")
    await message.answer(f"Тема: «{topic_text}». Теперь введите текст плана, "
                         f"или прикрепите голосовое сообщение/фото к плану:")
    await state.set_state(AddPlanStates.awaiting_plan_content)

async def add_plan_content_received(message: types.Message, state: FSMContext):
    """Получает текст, фото или голосовое сообщение и запрашивает время напоминания."""
    user_data = await state.get_data()
    display_date = user_data.get('display_date')
    user_id = message.from_user.id

    plan_text = ""
    telegram_file_id = None
    file_type = None

    if message.text:
        plan_text = message.text.strip()
        logger.info(f"Получен текстовый контент плана от пользователя {user_id}: '{plan_text}'")
    elif message.photo:
        photo = message.photo[-1]
        telegram_file_id = photo.file_id
        file_type = "photo"
        plan_text = message.caption or f"Фото к плану от {display_date}"
        logger.info(f"Получена фотография для плана от пользователя {user_id}: ID {telegram_file_id}")
    elif message.voice:
        voice = message.voice
        telegram_file_id = voice.file_id
        file_type = "voice"
        plan_text = message.caption or f"Голосовое сообщение к плану от {display_date}"
        logger.info(f"Получено голосовое сообщение для плана от пользователя {user_id}: ID {telegram_file_id}")
    else:
        await message.answer("Неподдерживаемый тип контента. Пожалуйста, введите текст, прикрепите фото или голосовое сообщение.", reply_markup=get_plans_keyboard())
        await state.clear()
        return

    if not plan_text and not telegram_file_id:
        await message.answer("Текст плана или вложение не может быть пустым. Пожалуйста, введите текст, прикрепите фото или голосовое сообщение.", reply_markup=get_plans_keyboard())
        await state.clear()
        return

    await state.update_data(plan_text=plan_text, telegram_file_id=telegram_file_id, file_type=file_type)

    await message.answer("Во сколько нужно напомнить о плане? Введите время в формате ЧЧ:ММ (например, 22:30). Если напоминание не нужно, введите 'нет'.")
    await state.set_state(AddPlanStates.awaiting_reminder_time)

# ... (остальной код файла без изменений)
async def add_plan_reminder_time_received(message: types.Message, state: FSMContext):
    """Получает время напоминания, сохраняет план и завершает диалог."""
    user_data = await state.get_data()
    plan_date_db = user_data.get('plan_date_db')
    display_date = user_data.get('display_date')
    plan_topic = user_data.get('plan_topic')
    plan_text = user_data.get('plan_text')
    telegram_file_id = user_data.get('telegram_file_id')
    file_type = user_data.get('file_type')
    user_id = message.from_user.id

    reminder_time_str = message.text.strip().lower()
    reminder_datetime_db = None
    
    if reminder_time_str != 'нет':
        match = re.search(r'\d{1,2}:\d{2}', reminder_time_str)
        if not match:
            await message.answer("Неверный формат времени. Введите ЧЧ:ММ (например, 22:30), или 'нет' если напоминание не нужно.", reply_markup=get_plans_keyboard())
            await state.clear()
            return
        
        try:
            tz = pytz.timezone(USER_TIMEZONE_STR)
            dt_naive = datetime.datetime.combine(datetime.datetime.strptime(plan_date_db, "%Y-%m-%d").date(), datetime.datetime.strptime(match.group(0), "%H:%M").time())
            dt_aware = tz.localize(dt_naive)
            
            if dt_aware <= datetime.datetime.now(tz):
                await message.answer("Это время уже прошло. Пожалуйста, введите будущее время или 'нет'.", reply_markup=get_plans_keyboard())
                await state.clear()
                return
            
            reminder_datetime_db = dt_naive.strftime("%Y-%m-%d %H:%M:%S")
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге времени напоминания: {e}", exc_info=True)
            await message.answer("Ошибка при обработке времени напоминания. Пожалуйста, введите корректное время или 'нет'.", reply_markup=get_plans_keyboard())
            await state.clear()
            return
    
    plan_id = await add_plan_to_db(user_id, plan_date_db, plan_topic, plan_text, reminder_datetime=reminder_datetime_db)

    if telegram_file_id:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO user_files (user_id, telegram_file_id, original_file_name, file_type, plan_id) VALUES (?, ?, ?, ?, ?)",
                (user_id, telegram_file_id, f"plan_attachment_{plan_id}.{file_type}", file_type, plan_id)
            )
            await db.commit()
        await message.answer(f"✅ План с вложением «{plan_topic}» на {display_date} успешно добавлен (ID: {plan_id}).", reply_markup=get_plans_keyboard(), parse_mode="HTML")
    else:
        await message.answer(f"✅ План «{plan_topic}» на {display_date} успешно добавлен (ID: {plan_id}).", reply_markup=get_plans_keyboard(), parse_mode="HTML")

    if reminder_datetime_db:
        tz = pytz.timezone(USER_TIMEZONE_STR)
        dt_naive = datetime.datetime.strptime(reminder_datetime_db, "%Y-%m-%d %H:%M:%S")
        dt_aware = tz.localize(dt_naive)
        
        job_id = f"reminder_{user_id}_{plan_id}"
        scheduler.add_job(
            send_reminder_job,
            trigger='date',
            run_date=dt_aware,
            args=[user_id, plan_id, plan_topic, plan_text, telegram_file_id, file_type],
            id=job_id,
            replace_existing=True
        )
        logger.info(f"Напоминание для плана ID {plan_id} установлено на {dt_aware.strftime('%H:%M')}.")
    
    await state.clear()

async def edit_plan_id_received(message: types.Message, state: FSMContext):
    logger.info(f"Получен ID плана для редактирования от пользователя {message.from_user.id}: {message.text}")
    if not message.text.isdigit():
        await message.answer("ID должен быть числом.", reply_markup=get_plans_keyboard())
        await state.clear()
        return
    plan = await get_plan_by_id(message.from_user.id, int(message.text))
    if not plan:
        await message.answer(f"План с ID {message.text} не найден.", reply_markup=get_plans_keyboard())
        await state.clear()
        return
    await state.update_data(
        plan_id=plan['id'],
        plan_text=plan['plan_text'],
        plan_date=plan['plan_date'],
        plan_topic=plan['plan_topic']
    )
    display_date = datetime.datetime.strptime(plan['plan_date'], "%Y-%m-%d").strftime("%d.%m.%Y г.")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Текст", callback_data="edit:text"),
         InlineKeyboardButton(text="📖 Тема", callback_data="edit:topic")],
        [InlineKeyboardButton(text="📅 Дата", callback_data="edit:date"),
         InlineKeyboardButton(text="⏰ Напоминание", callback_data="edit:reminder")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit:cancel")]
    ])
    await message.answer(
        f"Редактирование плана ID {plan['id']}:\n"
        f"**Тема:** {plan['plan_topic']}\n"
        f"**Текст:** {plan['plan_text']}\n"
        f"**Дата:** {display_date}\n\nЧто изменить?",
        reply_markup=keyboard, parse_mode="Markdown"
    )
    await state.set_state(EditPlanStates.choosing_edit_field)

async def choose_edit_field(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    await callback.message.edit_reply_markup(reply_markup=None)
    user_data = await state.get_data()
    plan_id = user_data.get('plan_id')
    
    if action == "text":
        await callback.message.answer("Введите новый текст:")
        await state.set_state(EditPlanStates.editing_text)
    elif action == "date":
        await callback.message.answer("Введите новую дату (ДД.ММ.ГГГГ):")
        await state.set_state(EditPlanStates.editing_date)
    elif action == "topic":
        await callback.message.answer("Введите новую тему:")
        await state.set_state(EditPlanStates.editing_topic)
    elif action == "reminder":
        attachments = await get_attachments_for_plan(plan_id)
        telegram_file_id = attachments[0]['telegram_file_id'] if attachments else None
        file_type = attachments[0]['file_type'] if attachments else None
        
        await state.update_data(
            telegram_file_id=telegram_file_id,
            file_type=file_type
        )
            
        await callback.message.answer("Введите новое время напоминания (ЧЧ:ММ) или 'нет', чтобы удалить:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(SetReminderStates.awaiting_time)
    else:
        await callback.message.answer("Отменено.", reply_markup=get_plans_keyboard())
        await state.clear()
    await callback.answer()

async def update_plan_text(message: types.Message, state: FSMContext):
    logger.info(f"Получен новый текст плана для редактирования от пользователя {message.from_user.id}: {message.text}")
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE plans SET plan_text = ? WHERE id = ?", (message.text, data['plan_id']))
        await db.commit()
    await message.answer(f"✅ Текст плана ID {data['plan_id']} обновлен.", reply_markup=get_plans_keyboard())
    await state.clear()

async def update_plan_date(message: types.Message, state: FSMContext):
    logger.info(f"Получена новая дата плана для редактирования от пользователя {message.from_user.id}: {message.text}")
    data = await state.get_data()
    try:
        db_date = datetime.datetime.strptime(message.text, "%d.%m.%Y").strftime("%Y-%m-%d")
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE plans SET plan_date = ? WHERE id = ?", (db_date, data['plan_id']))
            await db.commit()
        await message.answer(f"✅ Дата плана ID {data['plan_id']} обновлена.", reply_markup=get_plans_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("Неверный формат. Введите дату как ДД.ММ.ГГГГ.", reply_markup=get_plans_keyboard())

async def update_plan_topic(message: types.Message, state: FSMContext):
    logger.info(f"Получена новая тема плана для редактирования от пользователя {message.from_user.id}: {message.text}")
    data = await state.get_data()
    new_topic = message.text.strip()
    if not new_topic:
        await message.answer("Тема плана не может быть пустой. Попробуйте еще раз.", reply_markup=get_plans_keyboard())
        return
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE plans SET plan_topic = ? WHERE id = ?", (new_topic, data['plan_id']))
        await db.commit()
    await message.answer(f"✅ Тема плана ID {data['plan_id']} обновлена на: «{new_topic}».", reply_markup=get_plans_keyboard())
    await state.clear()

async def set_reminder_time_received(message: types.Message, state: FSMContext):
    logger.info(f"Получено время напоминания от пользователя {message.from_user.id}: {message.text}")
    data = await state.get_data()
    
    plan_id = data.get('plan_id')
    user_id = message.from_user.id
    plan_text = data.get('plan_text')
    plan_topic = data.get('plan_topic')
    telegram_file_id = data.get('telegram_file_id')
    file_type = data.get('file_type')

    time_str = message.text.strip().lower()
    reminder_datetime_db = None
    
    if time_str != 'нет':
        match = re.search(r'\d{1,2}:\d{2}', time_str)
        if not match:
            await message.answer("Неверный формат времени. Введите ЧЧ:ММ (например, 22:30), или 'нет' если напоминание не нужно.", reply_markup=get_plans_keyboard())
            await state.clear()
            return
        
        try:
            tz = pytz.timezone(USER_TIMEZONE_STR)
            plan_date_str = data.get('plan_date_db') or data.get('plan_date')
            dt_naive = datetime.datetime.combine(datetime.datetime.strptime(plan_date_str, "%Y-%m-%d").date(), datetime.datetime.strptime(match.group(0), "%H:%M").time())
            dt_aware = tz.localize(dt_naive)
            
            if dt_aware <= datetime.datetime.now(tz):
                await message.answer("Это время уже прошло. Пожалуйста, введите будущее время или 'нет'.", reply_markup=get_plans_keyboard())
                await state.clear()
                return
            
            reminder_datetime_db = dt_naive.strftime("%Y-%m-%d %H:%M:%S")
            job_id = f"reminder_{user_id}_{plan_id}"
            scheduler.add_job(
                send_reminder_job,
                trigger='date',
                run_date=dt_aware,
                args=[user_id, plan_id, plan_topic, plan_text, telegram_file_id, file_type],
                id=job_id,
                replace_existing=True
            )
            await message.answer(f"✅ Напоминание установлено на {dt_aware.strftime('%H:%M')}.", reply_markup=get_plans_keyboard())
        except Exception as e:
            logger.error(f"Ошибка при установке напоминания: {e}", exc_info=True)
            await message.answer("Ошибка установки напоминания.", reply_markup=get_plans_keyboard())
            await state.clear()
            return
    else:
        job_id = f"reminder_{user_id}_{plan_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"Напоминание для плана ID {plan_id} удалено.")
        await message.answer(f"✅ Напоминание для плана ID {plan_id} удалено.", reply_markup=get_plans_keyboard())

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE plans SET reminder_datetime = ? WHERE id = ?", (reminder_datetime_db, plan_id))
        await db.commit()
    await state.clear()

async def delete_plans_ids_received(message: types.Message, state: FSMContext):
    from telegram_handlers import display_multiple_plans
    logger.info(f"Получены ID для удаления плана от пользователя {message.from_user.id}: {message.text}")
    ids = [int(pid) for pid in re.split(r'[,\s]+', message.text) if pid.isdigit()]
    if not ids:
        await message.answer("ID не найдены. Введите один или несколько ID.", reply_markup=get_plans_keyboard())
        await state.clear()
        return
    deleted_count = 0
    async with aiosqlite.connect(DB_NAME) as db:
        for plan_id in ids:
            cursor = await db.execute("DELETE FROM plans WHERE id = ? AND user_id = ?", (plan_id, message.from_user.id))
            if cursor.rowcount > 0:
                deleted_count += 1
                await db.execute("DELETE FROM user_files WHERE plan_id = ?", (plan_id,))
                if scheduler.get_job(f"reminder_{message.from_user.id}_{plan_id}"):
                    scheduler.remove_job(f"reminder_{message.from_user.id}_{plan_id}")
        await db.commit()
    await message.answer(f"✅ Удалено планов: {deleted_count}.", reply_markup=get_plans_keyboard())
    all_plans = await get_all_user_plans(message.from_user.id)
    if all_plans:
        await display_multiple_plans(message, all_plans, "Все ваши планы:")
    await state.clear()

async def complete_plans_ids_received(message: types.Message, state: FSMContext):
    from telegram_handlers import display_multiple_plans
    logger.info(f"Получены ID для отметки о выполнении плана от пользователя {message.from_user.id}: {message.text}")
    ids = [int(pid) for pid in re.split(r'[,\s]+', message.text) if pid.isdigit()]
    if not ids:
        await message.answer("ID не найдены. Введите один или несколько ID.", reply_markup=get_plans_keyboard())
        await state.clear()
        return
    updated_count = 0
    async with aiosqlite.connect(DB_NAME) as db:
        for plan_id in ids:
            cursor = await db.execute("UPDATE plans SET is_completed = 1 - is_completed WHERE id = ? AND user_id = ?", (plan_id, message.from_user.id))
            if cursor.rowcount > 0: updated_count += 1
        await db.commit()
    await message.answer(f"✅ Статус обновлен для {updated_count} планов.", reply_markup=get_plans_keyboard())
    all_plans = await get_all_user_plans(message.from_user.id)
    if all_plans:
        await display_multiple_plans(message, all_plans, "Все ваши планы:")
    await state.clear()

async def set_reminder_id_received(message: types.Message, state: FSMContext):
    logger.info(f"Получен ID плана для напоминания от пользователя {message.from_user.id}: {message.text}")
    if not message.text.isdigit():
        await message.answer("ID должен быть числом.", reply_markup=get_plans_keyboard())
        await state.clear()
        return
    plan = await get_plan_by_id(message.from_user.id, int(message.text))
    if not plan:
        await message.answer(f"План с ID {message.text} не найден.", reply_markup=get_plans_keyboard())
        await state.clear()
        return
    
    display_date = datetime.datetime.strptime(plan['plan_date'], "%Y-%m-%d").strftime("%d.%m.%Y г.")
    attachments = await get_attachments_for_plan(plan['id'])
    telegram_file_id = attachments[0]['telegram_file_id'] if attachments else None
    file_type = attachments[0]['file_type'] if attachments else None
    
    await state.update_data(
        plan_id=plan['id'], 
        plan_text=plan['plan_text'], 
        plan_date=plan['plan_date'],
        plan_topic=plan['plan_topic'],
        telegram_file_id=telegram_file_id,
        file_type=file_type
    )
    await message.answer(f"Напоминание для плана ID {plan['id']}:\n**Тема:** {plan['plan_topic']}\n**Текст:** {plan['plan_text']}\n**Дата:** {display_date}\n\nВо сколько напомнить (ЧЧ:ММ)?", parse_mode="Markdown")
    await state.set_state(SetReminderStates.awaiting_time)