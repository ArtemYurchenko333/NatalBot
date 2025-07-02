import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import google.generativeai as genai

# --- Настройка логирования ---
# Это поможет тебе видеть, что происходит с ботом, если возникнут ошибки.
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Переменные для состояний разговора ---
# Эти переменные определяют шаги в нашем диалоге с пользователем.
GET_BIRTH_DATE = 0
GET_BIRTH_CITY = 1

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("TELEGRAM_BOT_TOKEN")

# --- Инициализация Gemini API ---
genai.configure(api_key=GEMINI_API_KEY)
# Выбираем модель Gemini, которую будем использовать.
# 'gemini-pro' - хорошая универсальная модель.
model = genai.GenerativeModel('models/gemini-1.5-flash')

# --- Функции-обработчики команд и сообщений ---

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отправляет приветственное сообщение и запрашивает дату рождения."""
    user = update.effective_user
    await update.message.reply_html(
        f"Привет, {user.mention_html()}! Я могу помочь тебе узнать немного о твоей натальной карте. "
        "Пожалуйста, введи свою дату рождения в формате ДД.ММ.ГГГГ (например, 01.01.2000):"
    )
    # Устанавливаем следующее состояние разговора
    return GET_BIRTH_DATE

# Обработчик для получения даты рождения
async def get_birth_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает дату рождения и запрашивает город."""
    user_birth_date = update.message.text
    # Здесь можно добавить проверку формата даты, если нужно.
    context.user_data['birth_date'] = user_birth_date
    await update.message.reply_text(
        "Отлично! Теперь, пожалуйста, введи город твоего рождения:"
    )
    # Переходим к следующему состоянию
    return GET_BIRTH_CITY

# Обработчик для получения города рождения и отправки запроса в Gemini
async def get_birth_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает город рождения, формирует запрос для Gemini и отправляет ответ."""
    user_birth_city = update.message.text
    birth_date = context.user_data['birth_date']

    await update.message.reply_text("Спасибо! Генерирую информацию по твоей натальной карте. Это может занять немного времени...")

    # Формируем промт для Gemini
    # Здесь ты можешь быть более конкретным в запросе к Gemini,
    # чтобы получить желаемый формат натальной карты.
    prompt_text = (
        f"Создай очень краткую и обобщенную натальную карту для человека, "
        f"родившегося {birth_date} в городе {user_birth_city}. "
        "Включи общие характеристики личности, основные планетарные влияния (например, знак зодиака по Солнцу, асцендент, лунный знак - если возможно из общих данных)."
        "Представь информацию в формате, удобном для чтения, без излишних астрологических терминов."
    )

    try:
        # Отправляем запрос в Gemini
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
        # Отправляем ответ от Gemini пользователю
        await update.message.reply_text(gemini_response_text)
    except Exception as e:
        logger.error(f"Ошибка при обращении к Gemini API: {e}")
        await update.message.reply_text(
            "Извини, произошла ошибка при получении информации от Gemini. Попробуй еще раз позже."
        )

    # Завершаем разговор
    return ConversationHandler.END

# Обработчик для команды /cancel (отмена разговора)
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет и завершает текущий разговор."""
    user = update.effective_user
    logger.info(f"Пользователь {user.first_name} отменил разговор.")
    await update.message.reply_text(
        'Диалог отменен. Если хочешь начать сначала, используй команду /start.'
    )
    # Завершаем разговор
    return ConversationHandler.END

# Обработчик для неизвестных команд
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Извини, я не понял эту команду. Попробуй /start, чтобы начать.")

# --- Основная функция для запуска бота ---
def main() -> None:
    """Запускает бота."""
    # Создаем объект Application и передаем ему токен бота.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Создаем ConversationHandler для управления потоком диалога
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_BIRTH_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birth_date)],
            GET_BIRTH_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birth_city)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.COMMAND | filters.TEXT, unknown)],
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.COMMAND, unknown)) # Добавляем обработчик для неизвестных команд вне ConversationHandler

    # Запускаем бота
    logger.info("Бот запущен. Ожидание сообщений...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()