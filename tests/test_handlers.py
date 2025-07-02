# tests/test_handlers.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import User, Chat

# Импортируем тестируемый обработчик
from main import send_welcome
from keyboards import get_main_keyboard # Импортируем клавиатуру для проверки

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_bot():
    """Фикстура для создания мока бота."""
    return MagicMock()

@pytest.fixture
def memory_storage():
    """Фикстура для создания хранилища FSM в памяти."""
    return MemoryStorage()

@pytest.fixture
def user():
    """Фикстура для создания тестового пользователя."""
    return User(id=12345, is_bot=False, first_name="Тестер", last_name="Тестеров", full_name="Тестер Тестеров")

@pytest.fixture
def chat():
    """Фикстура для создания тестового чата."""
    return Chat(id=54321, type="private")


@pytest_asyncio.fixture
async def fsm_context(mock_bot, user, chat, memory_storage):
    """Фикстура для создания контекста состояния FSM."""
    key_data = {
        "bot_id": mock_bot.id,
        "user_id": user.id,
        "chat_id": chat.id,
    }
    storage_key = frozenset(key_data.items())
    state = FSMContext(storage=memory_storage, key=storage_key)
    # Установим какое-то состояние, чтобы проверить, что оно очищается
    await state.set_state("some_state:for_test")
    return state


async def test_send_welcome(user, chat, fsm_context):
    """
    Тест для команды /start с использованием фикстур.
    """
    # 1. Создаем "поддельный" объект Message с помощью фикстур
    message = AsyncMock(spec=types.Message)
    message.from_user = user
    message.chat = chat
    # Явно указываем, что метод .answer() тоже должен быть асинхронным
    message.answer = AsyncMock()

    # 2. Вызываем наш обработчик
    await send_welcome(message, fsm_context)

    # 3. Проверяем результат
    message.answer.assert_called_once()
    args, kwargs = message.answer.call_args

    # Проверяем текст ответа
    assert args[0] == f"Привет, <b>{user.full_name}</b>!"

    # Проверяем, что была передана правильная клавиатура
    assert "reply_markup" in kwargs
    # Можно даже проверить конкретный экземпляр клавиатуры, если get_main_keyboard() не принимает аргументов
    # Это сделает тест более строгим, но и более хрупким.
    # assert kwargs["reply_markup"] == get_main_keyboard()

    # 4. Проверяем, что состояние было очищено
    current_state = await fsm_context.get_state()
    assert current_state is None