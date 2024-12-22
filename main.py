import telebot
import sqlite3
from langchain_ollama import ChatOllama as OllamaLLM
from telebot import types
import os
import asyncio
import telebot.async_telebot
from dotenv import load_dotenv
import logging
from datetime import datetime

load_dotenv()

TELEGRAM_API_KEY = os.getenv("bot_token")

# Инициализация бота с вашим токеном
bot = telebot.telebot.async_telebot.AsyncTeleBot(TELEGRAM_API_KEY)

# Инициализация Ollama API с указанием модели
ollama_api = OllamaLLM(base_url='http://localhost:11434', model="llama3.2:1b")  # Укажите вашу модель

# Инициализация базы данных SQLite
conn = sqlite3.connect('history.db', check_same_thread=False)
cursor = conn.cursor()

# Логгер
logger = logging.getLogger()
logger.setLevel(logging.INFO)
current_time = datetime.now()
time_string = current_time.strftime("%Y-%m-%d_%H-%M-%S")
file_handler = logging.FileHandler(f'log_{time_string}.log')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Создание таблицы для истории сообщений, если она еще не создана
cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_history (
        user_id INTEGER PRIMARY KEY,
        role TEXT,
        history TEXT
    )
''')
conn.commit()

# Функция для сохранения истории пользователя
def save_history(user_id, role, history):
    cursor.execute('''
        INSERT OR REPLACE INTO user_history (user_id, role, history)
        VALUES (?, ?, ?)
    ''', (user_id, role, history))
    conn.commit()

# Функция для получения истории пользователя
def get_history(user_id):
    cursor.execute('SELECT role, history FROM user_history WHERE user_id = ?', (user_id,))
    return cursor.fetchone()

# Функция для очистки истории пользователя
def clear_history(user_id):
    cursor.execute('DELETE FROM user_history WHERE user_id = ?', (user_id,))
    conn.commit()

# Функция для генерации текста с помощью Ollama
async def generate_text(role, history):
    try:
        input_role = f"{history}\nUser: {role}\nAI:"
        response = ollama_api.invoke(input_role)
        return response
    except Exception as e:
        logger.info(f"Произошла ошибка: {str(e)}")
        return f"Произошла ошибка при генерации текста: {str(e)}"

# Обработчик команды /start
@bot.message_handler(commands=['start'])
async def send_welcome(message):
    user_id = message.from_user.id
    await bot.send_message(user_id, "Привет! Я чат-бот, использующий нейросеть Ollama. Введите ваш запрос.")

# Обработчик команды /clear для очистки истории
@bot.message_handler(commands=['clear'])
async def clear(message):
    user_id = message.from_user.id
    clear_history(user_id)
    await bot.send_message(user_id, "История очищена!")

# Обработчик команды /setrole для изменения промпта
@bot.message_handler(commands=['setrole'])
async def set_role(message):
    try:
        user_id = message.from_user.id
        role = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""
        if not role:
            await bot.send_message(user_id, "Введите роль после команды.")
        else:
            save_history(user_id, role, "")
            await bot.send_message(user_id, f"Новая роль установлена: {role}")
    except Exception as e:
        logger.info(f"Произошла ошибка: {str(e)}")
        await bot.send_message(message.from_user.id, f"Произошла ошибка: {str(e)}")

# Обработчик команды /getrole для просмотра текущего промпта
@bot.message_handler(commands=['getrole'])
async def get_role(message):
    try:
        user_id = message.from_user.id
        user_data = get_history(user_id)
        if user_data:
            role, _ = user_data
            await bot.send_message(user_id, f"Текущая роль: {role}")
        else:
            await bot.send_message(user_id, "Роль не установлена.\nУстановить роль можно командой /setrole [роль]")
    except Exception as e:
        logger.info(f"Произошла ошибка: {str(e)}")
        await bot.send_message(message.from_user.id, f"Произошла ошибка: {str(e)}")

# Обработчик текстовых сообщений
@bot.message_handler(func=lambda message: True)
async def handle_message(message):
    user_id = message.from_user.id
    user_message = message.text

    try:
        await bot.send_message(user_id, "Генерация ответа, пожалуйста подождите...")
        
        # Получаем историю пользователя
        user_data = get_history(user_id)
        if user_data:
            role, history = user_data
        else:
            role = """Ты полезный AI ассистент. В запросе "AI:" это твой предыдущий ответ, "User:" это запрос пользователя."""
            history = ""

        # Генерация текста с помощью Ollama API
        ai_response = await generate_text(user_message, history)
        new_history = f"{history}\nUser: {user_message}\nAI: {ai_response}"

        # Ограничиваем историю до 10 сообщений
        messages = new_history.split('\nAI:')
        if len(messages) > 10:
            new_history = '\nAI:'.join(messages[-10:])

        # Сохраняем историю
        save_history(user_id, role, new_history)

        # Отправляем ответ с поддержкой Markdown
        await bot.send_message(user_id, ai_response.content, parse_mode="Markdown")
        await bot.send_message(user_id, f"Токенов использовано: {ai_response.usage_metadata['output_tokens']}", parse_mode="Markdown")
        logger.info(f"Отправлено сообщение пользователю {user_id}")

    except Exception as e:
        logger.info(f"Произошла ошибка: {str(e)}")
        await bot.send_message(user_id, f"Произошла ошибка: {str(e)}")

logger.info('Бот запущен')
# Запуск бота
asyncio.run(bot.polling())
