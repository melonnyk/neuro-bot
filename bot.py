import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# 1) Определяем класс-обработчик «здоровья»
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Просто возвращаем 200 OK
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

# 2) Функция для запуска HTTP-сервера на порту 8080
def start_health_server():
    server = HTTPServer(("0.0.0.0", 8080), HealthHandler)
    server.serve_forever()

# 3) Стартуем его в отдельном потоке до старта бота
threading.Thread(target=start_health_server, daemon=True).start()

import logging
from aiogram import Bot, Dispatcher, types
import os, logging
import telebot
from telebot import types
from db import update_item
import db
import time
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    logging.error("❌ TELEGRAM_TOKEN is not set in environment")
    exit(1)

# (после импортов)

# === НАЧАЛО БЛОКА: Викторина ===

# Здесь определяем вопросы викторины:
QUIZ_QUESTIONS = [
    {
        "question": "1) Что такое нейрофото?",
        "options": ["Фото через нейросеть", "Курс по фотографии", "Продукт для животных"],
        "correct": 0
    },
    {
        "question": "2) Для чего нужен наш бот?",
        "options": ["Развлечения", "Получения гайдов и заказов", "Игры"],
        "correct": 1
    },
    # Добавьте сколько угодно вопросов по тому же шаблону
]

def send_quiz_question(chat_id, index):
    q = QUIZ_QUESTIONS[index]
    kb = types.InlineKeyboardMarkup()
    for i, opt in enumerate(q["options"]):
        kb.add(types.InlineKeyboardButton(opt, callback_data=f"quiz:{index}:{i}"))
    bot.send_message(chat_id, q["question"], reply_markup=kb)

# === НАЧАЛО: Интерпретации результатов викторины ===
# Формат: (min_score, max_score, текст_интерпретации)
SCORE_INTERPRETATIONS = [
    (0, 1, "😕 К сожалению, вы набрали очень мало баллов. Рекомендуем вернуться к гайдам и попробовать ещё раз."),
    (2, 2, "🙂 Неплохо! Вы освоили базовые понятия, но можно чуть подтянуться."),
    (3, 3, "😊 Отлично! Вы хорошо разбираетесь в теме нейрофото."),
    (4, 5, "🏆 Впечатляет! Вы эксперт в области нейрофото и смело можете делиться знаниями с другими."),
    # Добавьте столько диапазонов, сколько нужно; верхний диапазон может быть >len(QUESTIONS)
]
# === КОНЕЦ: Интерпретации результатов викторины ===

# === КОНЕЦ БЛОКА: Викторина ===

TOKEN    = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)
bot = telebot.TeleBot(TOKEN)

# Глобальное хранилище состояний для всех FSM-сценариев
user_states = {}

# --- /start ---
@bot.message_handler(commands=['start'])
def start(msg):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("📋 Меню"))
    bot.send_message(msg.chat.id,
        "👋 Привет! Я NeuroBot - помощник Ольги Мишиной.\n"
        "Нажмите кнопку внизу, чтобы открыть Меню.",
        reply_markup=kb)

# --- Показать список категорий ---
@bot.message_handler(func=lambda m: m.text == "📋 Меню")
def show_categories(msg):
    cats = db.list_categories()
    if not cats:
        return bot.reply_to(msg, "Меню пусто. Админ добавляет через /add_item.")
    kb = types.InlineKeyboardMarkup()
    for cat in cats:
        kb.add(types.InlineKeyboardButton(cat, callback_data=f"cat:{cat}"))
    bot.send_message(msg.chat.id, "Выберите категорию:", reply_markup=kb)

# --- Показать пункты выбранной категории ---
@bot.callback_query_handler(lambda c: c.data.startswith("cat:"))
def show_items(call):
    cat = call.data.split(":",1)[1]
    # если пользователь выбрал категорию "Тестирование", сразу запускаем викторину
    if cat == "Тестирование":
        # инициализируем состояние викторины
        user_states[call.message.chat.id] = {'step':'quiz','index':0,'score':0}
        send_quiz_question(call.message.chat.id, 0)
        bot.answer_callback_query(call.id)
        return
    items = db.list_items(cat)
    if not items:
        bot.answer_callback_query(call.id, "В этой категории пока нет пунктов.")
        return
    kb = types.InlineKeyboardMarkup()
    for item_id, name, _, _ in items:
        kb.add(types.InlineKeyboardButton(name, callback_data=f"item:{item_id}"))
    bot.send_message(call.message.chat.id,
        f"Категория «{cat}»: выберите пункт:",
        reply_markup=kb)
    bot.answer_callback_query(call.id)

# --- Обработка выбора пункта ---
@bot.callback_query_handler(lambda c: c.data.startswith("item:"))
def handle_item(call):
    item_id = int(call.data.split(":",1)[1])
    rec = db.get_item(item_id)
    if not rec:
        return bot.answer_callback_query(call.id, "Не найдено.")
    name, kind, value = rec
    if kind=="file":
        bot.send_document(call.message.chat.id, value, caption=name)
    else:
        bot.send_message(call.message.chat.id, f"{name}\n\n{value}")
    bot.answer_callback_query(call.id)

# --- Админ: добавление пункта с категорией ---
user_states = {}

@bot.message_handler(commands=['add_item'])
def cmd_add_item(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.reply_to(msg, "❌ Только админ.")
    user_states[msg.chat.id] = {'step':'category'}
    bot.reply_to(msg, "Введите *категорию* пункта:", parse_mode='Markdown')

@bot.message_handler(func=lambda m: user_states.get(m.chat.id,{}).get('step')=='category')
def state_category(msg):
    user_states[msg.chat.id]['category'] = msg.text
    user_states[msg.chat.id]['step'] = 'name'
    bot.reply_to(msg, "Введите *название* пункта:", parse_mode='Markdown')

@bot.message_handler(func=lambda m: user_states.get(m.chat.id,{}).get('step')=='name')
def state_name(msg):
    user_states[msg.chat.id]['name'] = msg.text
    user_states[msg.chat.id]['step'] = 'kind'
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("file", "url")
    bot.reply_to(msg, "Это будет файл или ссылка? Напишите `file` или `url`.", reply_markup=kb)

@bot.message_handler(func=lambda m: user_states.get(m.chat.id,{}).get('step')=='kind')
def state_kind(msg):
    kind = msg.text.lower()
    if kind not in ('file','url'):
        return bot.reply_to(msg, "Нужно `file` или `url`.", parse_mode='Markdown')
    user_states[msg.chat.id]['kind'] = kind
    user_states[msg.chat.id]['step'] = 'value'
    bot.reply_to(msg, "Теперь пришлите файл (документ/видео) или ссылку:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: user_states.get(m.chat.id,{}).get('step')=='value', content_types=['text','document','video'])
def state_value(msg):
    st = user_states.pop(msg.chat.id)
    cat, name, kind = st['category'], st['name'], st['kind']
    if kind=='file':
        fid = msg.document.file_id if msg.document else msg.video.file_id
        db.add_item(cat, name, kind, fid)
    else:
        db.add_item(cat, name, kind, msg.text)
    bot.reply_to(msg, f"✅ Пункт *«{name}»* в категории *«{cat}»* добавлен.", parse_mode='Markdown')

# --- Админ: удалить пункт ---
@bot.message_handler(commands=['del_item'])
def cmd_del_item(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.reply_to(msg, "❌ Только админ.")
    parts = msg.text.split()
    if len(parts)!=2 or not parts[1].isdigit():
        return bot.reply_to(msg, "Используйте: /del_item <ID>")
    db.delete_item(int(parts[1]))
    bot.reply_to(msg, "🗑 Пункт удалён.")

# --- Админ: начать редактирование пункта ---
@bot.message_handler(commands=['edit_item'])
def cmd_edit_item(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.reply_to(msg, "❌ Только админ.")
    parts = msg.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return bot.reply_to(msg, "Используйте: /edit_item <ID>")
    item_id = int(parts[1])
    rec = db.get_item(item_id)
    if not rec:
        return bot.reply_to(msg, "❌ Пункт не найден.")
    name, kind, value = rec
    # Сохраняем начальные данные в состояние
    user_states[msg.chat.id] = {
        'step': 'edit_name',
        'id': item_id,
        'old_name': name,
        'kind': kind,
        'old_value': value
    }
    bot.reply_to(
        msg,
        f"Редактирование #{item_id}:\n"
        f"Старое название: {name}\n"
        "Введите *новое название* или `skip`, чтобы не менять.",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('step') == 'edit_name')
def state_edit_name(msg):
    st = user_states[msg.chat.id]
    if msg.text.lower() != 'skip':
        st['new_name'] = msg.text
    else:
        st['new_name'] = st['old_name']
    st['step'] = 'edit_value'
    if st['kind'] == 'file':
        prompt = "Пришлите *новый файл* (документ/видео) или `skip`, чтобы не менять."
    else:
        prompt = "Введите *новую ссылку* или `skip`, чтобы не менять."
    bot.reply_to(msg, prompt, parse_mode='Markdown')

@bot.message_handler(
    func=lambda m: user_states.get(m.chat.id, {}).get('step') == 'edit_value',
    content_types=['text', 'document', 'video']
)
def state_edit_value(msg):
    st = user_states.pop(msg.chat.id)
    item_id = st['id']
    new_name = st['new_name']
    kind = st['kind']
    # Определяем новое значение
    if kind == 'file':
        if msg.content_type in ['document', 'video']:
            new_value = (msg.document or msg.video).file_id
        else:
            new_value = st['old_value']
    else:  # url
        if msg.text.lower() != 'skip':
            new_value = msg.text
        else:
            new_value = st['old_value']
    # Обновляем запись
    update_item(item_id, name=new_name, value=new_value)
    bot.reply_to(msg, f"✅ Пункт #{item_id} обновлён:\n«{new_name}»")

# --- Админ: посмотреть все пункты меню ---
@bot.message_handler(commands=['list_items'])
def cmd_list_items(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.reply_to(msg, "❌ Только админ может это видеть.")
    items = db.list_all_items()
    if not items:
        return bot.reply_to(msg, "Меню пусто.")
    lines = ["📋 Текущие пункты меню:"]
    for item_id, category, name, kind in items:
        lines.append(f"{item_id}. [{category}] {name} ({kind})")
    bot.reply_to(msg, "\n".join(lines))

# --- Админ: вывод всех команд с описанием ---
@bot.message_handler(commands=['admin_help'])
def cmd_admin_help(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.reply_to(msg, "❌ Только админ.")
    help_text = (
        "📋 Список команд для администратора 📋\n\n"
        "/start — Перезапустить меню бота\n"
        "/add_item — Добавить пункт меню (категория → название → file/url → контент)\n"
        "/del_item <ID> — Удалить пункт с указанным ID\n"
        "/list_items — Показать все пункты меню с их ID, категорией и типом\n"
        "/edit_item <ID> — Отредактировать название и содержимое пункта по ID\n"
        "/quiz — Запустить викторину\n"
        "/admin_help — Показать этот список команд\n"
    )
    bot.reply_to(msg, help_text)

# --- Запуск викторины ---
@bot.message_handler(commands=['quiz'])
def cmd_quiz(msg):
    user_states[msg.chat.id] = {'step':'quiz','index':0,'score':0}
    send_quiz_question(msg.chat.id, 0)

# --- Обработка выбора ответа в викторине ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("quiz:"))
def handle_quiz(call):
    data = call.data.split(":")
    q_index = int(data[1])
    choice = int(data[2])

    st = user_states.get(call.message.chat.id)
    # Проверяем, что пользователь в викторине и на том же вопросе
    if not st or st.get('step') != 'quiz' or st.get('index') != q_index:
        return bot.answer_callback_query(call.id)

    # Проверяем правильность ответа
    if choice == QUIZ_QUESTIONS[q_index]['correct']:
        st['score'] += 1

    # Переходим к следующему вопросу
    next_index = q_index + 1
    total = len(QUIZ_QUESTIONS)
    if next_index < total:
        st['index'] = next_index
        send_quiz_question(call.message.chat.id, next_index)
    else:
        score = st['score']
        # Выбираем интерпретацию по шкале
        interpretation = None
        for min_s, max_s, text in SCORE_INTERPRETATIONS:
            if min_s <= score <= max_s:
                interpretation = text
                break
        if interpretation is None:
            interpretation = f"🎉 Вы набрали {score} из {total} баллов."

        # Отправляем итог с интерпретацией
        bot.send_message(
            call.message.chat.id,
            f"🎉 Викторина завершена!\n"
            f"Ваш результат: {score}/{total}\n\n"
            f"{interpretation}"
        )
        # Удаляем состояние
        user_states.pop(call.message.chat.id, None)

    # Подтверждаем callback, чтобы убрать «часики» у кнопки
    bot.answer_callback_query(call.id)

# --- Эхо на всё остальное ---
@bot.message_handler(func=lambda m: True)
def echo_all(msg):
    bot.reply_to(msg, f"Не понял: {msg.text}")

if __name__ == "__main__":
    # 1. Отрубаем старый вебхук
    bot.remove_webhook()
    logging.info("🗑 Webhook removed, waiting 1s…")
    time.sleep(1)

    # 2. Запускаем HTTP-сервер для health checks
    threading.Thread(target=start_health_server, daemon=True).start()
    logging.info("🔗 Health server started on 0.0.0.0:8080")

    # 3. Запускаем бесконечное опрос polling
    logging.info("🚀 Bot is starting polling…")
    bot.infinity_polling(timeout=30, long_polling_timeout=60)
