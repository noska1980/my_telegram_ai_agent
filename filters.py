# filters.py
from aiogram import types
from aiogram.filters import Filter
from config import OWNER_TELEGRAM_ID, AUTHORIZED_USERS, LOGIN_PASSWORD
from keyboards import get_main_keyboard, get_remove_keyboard

class IsAuthorizedUser(Filter):
    """
    Фильтр для проверки, авторизован ли пользователь.
    Проверяет по ID владельца или по наличию в списке авторизованных.
    Также обрабатывает логин по паролю.
    """
    async def __call__(self, message: types.Message) -> bool:
        user_id = message.from_user.id
        
        # Если ID владельца не задан, разрешаем доступ всем
        if OWNER_TELEGRAM_ID is None:
            return True
            
        # Проверяем, является ли пользователь владельцем или уже авторизован
        if user_id == OWNER_TELEGRAM_ID or user_id in AUTHORIZED_USERS:
            return True
        else:
            # Если пользователь прислал правильный пароль, авторизуем его
            if message.text and message.text.strip() == LOGIN_PASSWORD:
                AUTHORIZED_USERS.add(user_id)
                await message.answer("✅ Пароль принят.", reply_markup=get_main_keyboard())
                return True
            # В противном случае запрещаем доступ
            else:
                # Отправляем сообщение о запрете доступа только один раз
                if not getattr(message.chat, '_password_prompt_sent', False):
                    await message.answer("❌ Доступ запрещен.", reply_markup=get_remove_keyboard())
                    setattr(message.chat, '_password_prompt_sent', True)
                return False