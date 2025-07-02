# scheduler_jobs.py
import datetime
import logging

import aiosqlite
from aiogram import Bot
import pytz
from aiogram.utils.markdown import hbold
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from config import DB_NAME, USER_TIMEZONE_STR, logger, user_voice_reply_preference
from keyboards import get_plans_keyboard # Импортируем клавиатуру для напоминаний


# Инициализация планировщика
try:
    user_timezone = pytz.timezone(USER_TIMEZONE_STR)
except pytz.exceptions.UnknownTimeZoneError:
    logger.error(f"Неизвестный часовой пояс: {USER_TIMEZONE_STR}. Используется UTC.")
    user_timezone = pytz.utc

scheduler = AsyncIOScheduler(timezone=user_timezone)

_bot_instance: Bot = None

def set_bot_instance_for_scheduler(bot: Bot):
    global _bot_instance
    _bot_instance = bot
    logger.info("Экземпляр бота установлен для планировщика.")


# ИЗМЕНЕНИЕ: Добавили plan_topic_reminder, telegram_file_id, file_type в аргументы
async def send_reminder_job(
    user_telegram_id: int, plan_db_id: int, plan_topic_reminder: str, plan_text_reminder: str,
    telegram_file_id: str = None, file_type: str = None
):
    logger.info(
        f"Сработало напоминание для пользователя {user_telegram_id} по плану ID "
        f"{plan_db_id}"
    )
    clean_plan_text = plan_text_reminder

    # ИЗМЕНЕНИЕ: Добавлена тема в текст напоминания
    reminder_message_text = (
        f"🔔 {hbold('Напоминание о вашем плане:')}\n"
        f"Тема: {hbold(plan_topic_reminder)}\n"
        f"Описание: «{clean_plan_text}»"
    )

    try:
        if _bot_instance:
            await _bot_instance.send_message(
                chat_id=user_telegram_id,
                text=reminder_message_text,
                parse_mode="HTML",
                reply_markup=get_plans_keyboard()
            )
            logger.info(f"Текстовое напоминание успешно отправлено пользователю {user_telegram_id} для плана ID {plan_db_id}.")

            if telegram_file_id and file_type:
                try:
                    if file_type == 'photo':
                        await _bot_instance.send_photo(chat_id=user_telegram_id, photo=telegram_file_id, caption=f"Вложение к плану ID {plan_db_id}")
                    elif file_type == 'voice':
                        await _bot_instance.send_voice(chat_id=user_telegram_id, voice=telegram_file_id, caption=f"Вложение к плану ID {plan_db_id}")
                    logger.info(f"Вложение типа {file_type} для плана ID {plan_db_id} успешно отправлено.")
                except Exception as e:
                    logger.error(f"Ошибка при отправке вложения {telegram_file_id} типа {file_type} для плана {plan_db_id}: {e}", exc_info=True)
            
        else:
            logger.error("Ошибка: _bot_instance не установлен в send_reminder_job. Напоминание не отправлено.")
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания напрямую для пользователя {user_telegram_id}: {e}", exc_info=True)

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE plans SET is_reminder_sent = 1 WHERE id = ? AND user_id = ?",
            (plan_db_id, user_telegram_id),
        )
        await db.commit()
    logger.info(f"Напоминание для плана ID {plan_db_id} отмечено как отправленное.")


async def auto_archive_old_plans():
    logger.info("Запуск автоархивации старых планов...")
    async with aiosqlite.connect(DB_NAME) as db:
        seven_days_ago = (
            datetime.datetime.now(user_timezone) - datetime.timedelta(days=7)
        ).strftime("%Y-%m-%d")
        await db.execute(
            "UPDATE plans SET is_archived = 1 WHERE plan_date < ? AND is_archived = 0",
            (seven_days_ago,),
        )
        await db.commit()
    logger.info("Автоархивация завершена.")


async def load_reminders_on_startup():
    logger.info("Загрузка активных напоминаний из БД в планировщик...")
    async with aiosqlite.connect(DB_NAME) as db_load:
        # ИЗМЕНЕНИЕ: Добавлены plan_topic, telegram_file_id, file_type в SELECT
        cursor = await db_load.execute(
            "SELECT p.id, p.user_id, p.plan_topic, p.plan_text, p.reminder_datetime, "
            "uf.telegram_file_id, uf.file_type FROM plans p "
            "LEFT JOIN user_files uf ON p.id = uf.plan_id "
            "WHERE p.reminder_datetime IS NOT NULL AND p.is_reminder_sent = 0"
        )
        active_reminders = await cursor.fetchall()

    now_aware = datetime.datetime.now(user_timezone)
    count_loaded = 0
    for plan_id_db, user_id_db, plan_topic_db, plan_text_db, reminder_dt_str_db, tg_file_id, f_type in active_reminders:
        try:
            reminder_dt_obj_naive = datetime.datetime.strptime(
                reminder_dt_str_db, "%Y-%m-%d %H:%M:%S"
            )
            reminder_dt_obj_aware = user_timezone.localize(reminder_dt_obj_naive)
            if reminder_dt_obj_aware > now_aware:
                job_id = f"reminder_{user_id_db}_{plan_id_db}"
                if not scheduler.get_job(job_id):
                    scheduler.add_job(
                        send_reminder_job,
                        trigger=DateTrigger(run_date=reminder_dt_obj_aware),
                        args=[user_id_db, plan_id_db, plan_topic_db, plan_text_db, tg_file_id, f_type],
                        id=job_id,
                        replace_existing=True,
                    )
                    count_loaded += 1
                    logger.info(
                        f"Загружено напоминание из БД: ID {job_id} на "
                        f"{reminder_dt_obj_aware}"
                    )
                else:
                    logger.info(f"Напоминание ID {job_id} уже в планировщике.")
            else:
                async with aiosqlite.connect(DB_NAME) as db_update_expired:
                    logger.warning(
                        "Просроченное неотправленное напоминание для плана ID "
                        f"{plan_id_db} ({reminder_dt_str_db}). Помечаем как "
                        "отправленное."
                    )
                    await db_update_expired.execute(
                        "UPDATE plans SET is_reminder_sent = 1 WHERE id = ?",
                        (plan_id_db,),
                    )
                    await db_update_expired.commit()
        except Exception as e_load_rem:
            logger.error(
                f"Ошибка при загрузке напоминания для плана ID {plan_id_db}: "
                f"{e_load_rem}",
                exc_info=True,
            )
    logger.info(f"Загружено {count_loaded} активных напоминаний в планировщик.")