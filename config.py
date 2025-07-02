# config.py
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    logger.critical("КРИТИЧЕСКАЯ ОШИБКА: Не найден TELEGRAM_BOT_TOKEN. Проверьте ваш .env файл.")
    exit(1)

# Ключ для доступа к Gemini AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.critical("КРИТИЧЕСКАЯ ОШИБКА: Не найден GEMINI_API_KEY. Проверьте ваш .env файл.")
    exit(1)


EMBEDDING_MODEL_NAME = "models/embedding-001" # Заглушка, если не используется
DB_NAME = "ai_agent_database.db"
USER_TIMEZONE_STR = "Asia/Tashkent"

OWNER_TELEGRAM_ID_STR = os.getenv("OWNER_TELEGRAM_ID")
OWNER_TELEGRAM_ID = int(OWNER_TELEGRAM_ID_STR) if OWNER_TELEGRAM_ID_STR and OWNER_TELEGRAM_ID_STR.isdigit() else None
if not OWNER_TELEGRAM_ID:
    logger.critical("КРИТИЧЕСКАЯ ОШИБКА: OWNER_TELEGRAM_ID не определен в .env файле.")
    exit(1)

user_voice_reply_preference = {} # Глобальная переменная для настроек пользователя
AUTHORIZED_USERS = set() # Множество для авторизованных пользователей
LOGIN_PASSWORD = "19801985" # Пароль для авторизации