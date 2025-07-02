# telegram_handlers.py
import asyncio
import datetime
import os
import tempfile
import aiosqlite
from aiogram import Bot, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hbold, hstrikethrough

from config import DB_NAME, logger
from file_processing import chunk_text, extract_text_from_docx, extract_text_from_pdf
from db import get_attachments_for_plan
from file_handlers import BatchCategorizeStates
from keyboards import get_batch_categorize_keyboard

async def display_multiple_plans(message: types.Message, plans_data: list, title_text: str):
    if not plans_data:
        await message.answer("Планов не найдено.")
        return
    response_parts = [f"{title_text}\n"]
    plans_by_date = {}
    for plan_row in plans_data:
        try:
            plan = dict(plan_row)
            display_date = datetime.datetime.strptime(plan['plan_date'], "%Y-%m-%d").strftime("%d.%m.%Y г.")
            if display_date not in plans_by_date:
                plans_by_date[display_date] = []
            plans_by_date[display_date].append(plan)
        except (ValueError, TypeError):
            continue
            
    if not plans_by_date:
        await message.answer("Нет планов с корректной датой для отображения.")
        return
        
    sorted_dates = sorted(plans_by_date.keys(), key=lambda d: datetime.datetime.strptime(d, "%d.%m.%Y г."))
    full_response_text = []
    for date_str in sorted_dates:
        full_response_text.append(f"\n🗓️ {hbold(date_str)}:")
        for plan in plans_by_date[date_str]:
            status_emoji = "✅" if plan['is_completed'] else "❌"
            text_display = hstrikethrough(plan['plan_topic']) if plan['is_completed'] else hbold(plan['plan_topic'])
            reminder_info = f" (напом.: {datetime.datetime.fromisoformat(plan['reminder_datetime']).strftime('%H:%M')})" if plan.get('reminder_datetime') else ""
            full_response_text.append(f"  {status_emoji} {text_display}: {plan['plan_text']} (ID: {hbold(str(plan['id']))}){reminder_info}")
            attachments = await get_attachments_for_plan(plan['id'])
            if attachments:
                full_response_text.append(f"    [📎 Вложения: {', '.join([a['file_type'] for a in attachments])}]")

    current_message_chunk = ""
    for line in full_response_text:
        if len(current_message_chunk) + len(line) + 1 > 4096:
            await message.answer(current_message_chunk, parse_mode="HTML")
            await asyncio.sleep(0.5)
            current_message_chunk = line
        else:
            current_message_chunk += "\n" + line
            
    if current_message_chunk.strip():
        await message.answer(current_message_chunk, parse_mode="HTML")

async def _save_file_to_db(user_id: int, doc: types.Document) -> int:
    original_file_name = doc.file_name or "document"
    file_extension = original_file_name.rsplit('.', 1)[-1].lower() if '.' in original_file_name else 'unknown'
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO user_files (user_id, telegram_file_id, original_file_name, file_type) VALUES (?, ?, ?, ?)",
            (user_id, doc.file_id, original_file_name, file_extension)
        )
        await db.commit()
        db_file_id = cursor.lastrowid
    
    if file_extension in ["pdf", "docx"]:
        asyncio.create_task(process_document_background(doc.bot, user_id, db_file_id, doc.file_id, original_file_name, file_extension))
    
    return db_file_id

async def handle_document_upload(message: types.Message, state: FSMContext):
    """
    Обрабатывает загрузку документа.
    Проверяет состояние, чтобы определить, первый ли это файл в пачке или последующий.
    """
    db_file_id = await _save_file_to_db(message.from_user.id, message.document)
    current_fsm_state = await state.get_state()

    # Если мы уже в состоянии ожидания файлов, значит это не первый файл
    if current_fsm_state == BatchCategorizeStates.awaiting_files:
        user_data = await state.get_data()
        file_list = user_data.get('files_to_categorize', [])
        file_list.append(db_file_id)
        await state.update_data(files_to_categorize=file_list)
        await message.reply(f"✅ Файл «{message.document.file_name}» добавлен в пачку.")
    # В противном случае, это первый файл
    else:
        await state.update_data(files_to_categorize=[db_file_id])
        await state.set_state(BatchCategorizeStates.awaiting_files)
        await message.answer(
            "Файл получен. Вы можете отправить еще файлы или нажать 'Готово ✅' для назначения категории.",
            reply_markup=get_batch_categorize_keyboard()
        )

async def process_document_background(bot: Bot, user_id: int, db_file_id: int, telegram_file_id: str, original_name: str, file_extension: str):
    downloaded_file_path = None
    try:
        file_info = await bot.get_file(telegram_file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_file:
            await bot.download_file(file_info.file_path, destination=temp_file)
            downloaded_file_path = temp_file.name
        
        text = ""
        if file_extension == "pdf":
            text = await asyncio.to_thread(extract_text_from_pdf, downloaded_file_path)
        elif file_extension == "docx":
            text = await asyncio.to_thread(extract_text_from_docx, downloaded_file_path)
        
        if not text:
            raise ValueError("Текст не извлечен.")
        
        chunks = chunk_text(text)
        async with aiosqlite.connect(DB_NAME) as db:
            for i, chunk in enumerate(chunks):
                await db.execute("INSERT INTO file_chunks (user_file_id, chunk_text, chunk_order) VALUES (?, ?, ?)", (db_file_id, chunk, i))
            await db.execute("UPDATE user_files SET is_processed_for_chunks = 1 WHERE id = ?", (db_file_id,))
            await db.commit()
        await bot.send_message(user_id, f"✅ Анализ файла «{original_name}» завершен. Найдено {len(chunks)} фрагментов.")
    except Exception as e:
        logger.error(f"Ошибка фоновой обработки файла {db_file_id}: {e}", exc_info=True)
        await bot.send_message(user_id, f"❌ Ошибка при анализе файла «{original_name}».")
    finally:
        if downloaded_file_path and os.path.exists(downloaded_file_path):
            os.remove(downloaded_file_path)