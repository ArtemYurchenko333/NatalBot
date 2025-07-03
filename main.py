import logging
import os
import psycopg2 # Импортируем библиотеку для работы с PostgreSQL
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import google.generativeai as genai

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Переменные для состояний разговора ---
GET_BIRTH_DATE = 0
GET_BIRTH_CITY = 1

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL") # Новая переменная для URL базы данных

# Проверка наличия всех необходимых переменных окружения
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не установлен в переменных окружения.")
    exit(1)
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY не установлен в переменных окружения.")
    exit(1)
if not DATABASE_URL:
    logger.error("DATABASE_URL не установлен в переменных окружения.")
    exit(1)

# --- Инициализация Gemini API ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-2.0-flash')

# --- Функции для работы с базой данных ---

def get_db_connection():
    """Устанавливает соединение с базой данных PostgreSQL."""
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("Успешно подключено к базе данных PostgreSQL.")
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        return None

def create_table_if_not_exists():
    """Создает таблицу natal_readings, если она еще не существует."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS natal_readings (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    birth_date VARCHAR(10) NOT NULL,
                    birth_city VARCHAR(255) NOT NULL,
                    gemini_response TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            logger.info("Таблица natal_readings проверена/создана.")
        except Exception as e:
            logger.error(f"Ошибка при создании таблицы: {e}")
        finally:
            if conn:
                conn.close()

async def save_reading_to_db(user_id: int, birth_date: str, birth_city: str, gemini_response: str):
    """Сохраняет данные натальной карты в базу данных."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO natal_readings (user_id, birth_date, birth_city, gemini_response)
                VALUES (%s, %s, %s, %s);
            """, (user_id, birth_date, birth_city, gemini_response))
            conn.commit()
            logger.info(f"Запись для пользователя {user_id} успешно сохранена в БД.")
        except Exception as e:
            logger.error(f"Ошибка при сохранении в базу данных: {e}")
        finally:
            if conn:
                conn.close()

# --- Функции-обработчики команд и сообщений ---

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отправляет приветственное сообщение и запрашивает дату рождения."""
    user = update.effective_user
    await update.message.reply_html(
        f"Привет, {user.mention_html()}! Я могу помочь тебе узнать немного о твоей натальной карте. "
        "Пожалуйста, введи свою дату рождения в формате ДД.ММ.ГГГГ (например, 01.01.2000):"
    )
    return GET_BIRTH_DATE

# Обработчик для получения даты рождения
async def get_birth_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает дату рождения и запрашивает город."""
    user_birth_date = update.message.text
    context.user_data['birth_date'] = user_birth_date
    await update.message.reply_text(
        "Отлично! Теперь, пожалуйста, введи город твоего рождения:"
    )
    return GET_BIRTH_CITY

# Обработчик для получения города рождения и отправки запроса в Gemini
async def get_birth_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает город рождения, формирует запрос для Gemini и отправляет ответ."""
    user = update.effective_user
    user_id = user.id
    user_birth_city = update.message.text
    birth_date = context.user_data['birth_date']

    await update.message.reply_text("Спасибо! Генерирую информацию по твоей натальной карте. Это может занять немного времени...")

    prompt_text = (
        f"Создай очень краткую и обобщенную натальную карту для человека, "
        f"родившегося {birth_date} в городе {user_birth_city}. "
        "Включи общие характеристики личности, основные планетарные влияния (например, знак зодиака по Солнцу, асцендент, лунный знак - если возможно из общих данных)."
        "Представь информацию в формате, удобном для чтения, без излишних астрологических терминов."
    )

    gemini_response_text = "" # Инициализируем пустой строкой
    try:
        response = model.generate_content(
            prompt_text,
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )
        gemini_response_text = response.text
        await update.message.reply_text(gemini_response_text)

        # Сохраняем данные в базу данных после успешного получения ответа
        await save_reading_to_db(user_id, birth_date, user_birth_city, gemini_response_text)

    except Exception as e:
        logger.error(f"Ошибка при обращении к Gemini API: {e}")
        await update.message.reply_text(
            "Извини, произошла ошибка при получении информации от Gemini. Попробуй еще раз позже."
        )

    return ConversationHandler.END

# Обработчик для команды /cancel (отмена разговора)
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет и завершает текущий разговор."""
    user = update.effective_user
    logger.info(f"Пользователь {user.first_name} отменил разговор.")
    await update.message.reply_text(
        'Диалог отменен. Если хочешь начать сначала, используй команду /start.'
    )
    return ConversationHandler.END

# Обработчик для неизвестных команд
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Извини, я не понял эту команду. Попробуй /start, чтобы начать.")

# --- Основная функция для запуска бота ---
def main() -> None:
    """Запускает бота."""
    # Создаем таблицу, если ее нет, при запуске бота
    create_table_if_not_exists()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_BIRTH_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birth_date)],
            GET_BIRTH_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birth_city)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.COMMAND | filters.TEXT, unknown)],
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Бот запущен. Ожидание сообщений...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
