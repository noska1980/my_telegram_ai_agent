# file_processing.py
import fitz
from docx import Document as DocxDocument
from nltk.tokenize import sent_tokenize
from config import logger
import nltk # Убедимся, что nltk импортирован здесь для download

# Проверка и загрузка NLTK 'punkt' один раз при импорте модуля
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    logger.info("Загрузка NLTK 'punkt'...")
    nltk.download("punkt", quiet=True)
    # Повторная проверка после загрузки, чтобы убедиться
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        logger.warning("NLTK 'punkt' не удалось загрузить после попытки. Некоторые функции могут работать некорректно.")


def extract_text_from_pdf(file_path: str) -> str:
    try:
        with fitz.open(file_path) as doc:
            return "".join(page.get_text() for page in doc)
    except Exception as e:
        logger.error(f"Ошибка при извлечении текста из PDF {file_path}: {e}", exc_info=True)
        return ""

def extract_text_from_docx(file_path: str) -> str:
    try:
        doc = DocxDocument(file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text)
    except Exception as e:
        logger.error(f"Ошибка при извлечении текста из DOCX {file_path}: {e}", exc_info=True)
        return ""

def chunk_text(text: str, chunk_size: int = 1500, chunk_overlap: int = 200) -> list[str]:
    if not text or not text.strip(): return []
    try:
        # Используем sent_tokenize, если 'punkt' доступен
        sentences = sent_tokenize(text, language="russian")
    except Exception:
        logger.warning("NLTK 'punkt' недоступен или произошла ошибка токенизации. Используется примитивный чанкинг.")
        # Примитивный чанкинг как запасной вариант
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size - chunk_overlap)]
    
    chunks, current_chunk = [], ""
    for sentence in sentences:
        # Если добавление предложения превышает размер чанка
        if len(current_chunk) + len(sentence) + 1 > chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = ""
        current_chunk += sentence + " "
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    logger.info(f"Текст разделен на {len(chunks)} чанков.")
    return chunks