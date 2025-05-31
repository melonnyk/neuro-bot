from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import logging
from aiogram import Bot, Dispatcher, types
import os
import telebot
from telebot import TeleBot, types
from db import update_item
import db
import time
import gspread
from google.oauth2.service_account import Credentials

# --- Health check server ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", 8080), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# --- Google Sheets connect ---
SERVICE_ACCOUNT_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/drive']

credentials = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=SCOPES
)
gc = gspread.authorize(credentials)
sh = gc.open_by_url('https://docs.google.com/spreadsheets/d/1_5g3h6DnyyiTtvMcyc6y5wFsTe8P4WzbH3XZdbqRRwk/edit#gid=0')
questions_ws = sh.worksheet('Вопросы')
scores_ws = sh.worksheet('Баллы')
styles_ws = sh.worksheet('Стили')

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    logging.error("❌ TELEGRAM_TOKEN is not set in environment")
    exit(1)
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)
bot = TeleBot(TOKEN)

# --- Neurophoto test state ---
from collections import defaultdict
TEST_USER_STATE = {}

def get_test_questions():
    rows = questions_ws.get_all_records()
    questions = []
    for row in rows:
        questions.append({
            'number': row['№'],
            'text': row['Вопрос'],
            'type': row['Тип'],
            'options': [opt.strip() for opt in row['Варианты'].split(';')],
        })
    return questions

def get_score_for_answer(q_num, answer):
    rows = scores_ws.get_all_records()
    for row in rows:
        if str(row['№']) == str(q_num) and str(row['Вариант ответа']).strip() == answer.strip():
            return [
                int(row['Минимализм']),
                int(row['Киберпанк']),
                int(row['Сюрреализм']),
                int(row['Ретро']),
                int(row['Неон-поп']),
                int(row['Акварель']),
                int(row['Эко']),
                int(row['Fashion']),
            ]
    return [0]*8

def get_style_by_scores(scores_sum):
    idx = scores_sum.index(max(scores_sum))
    styles = styles_ws.get_all_records()
    style = styles[idx]
    return style['Стиль'], style['Описание'], style['Ссылка на изображение'], style.get('Ссылка на форму заказа', '')

def send_test_question(chat_id, q_idx):
    questions = get_test_questions()
    if q_idx >= len(questions):
        return
    q = questions[q_idx]
    kb = types.InlineKeyboardMarkup()
    for idx, opt in enumerate(q['options']):
        kb.add(types.InlineKeyboardButton(opt, callback_data=f"nstyle:{q_idx}:{idx}"))
    bot.send_message(chat_id, f"{q_idx+1}) {q['text']}", reply_markup=kb)

@bot.callback_query_handler(lambda c: c.data == "cat:Тестирование")
def neuro_test_start(call):
    user_id = call.message.chat.id

# ——— ВСТУПИТЕЛЬНОЕ СООБЩЕНИЕ:
    intro_text = (
        "🧠 <b>Тест: Какой стиль нейрофото тебе подходит?</b>\n\n"
        "Тебя ждёт короткий и увлекательный тест из 10 вопросов. "
        "Отвечай честно и интуитивно — в финале ты получишь стиль нейрофото, который идеально подчёркивает твою индивидуальность!\n\n"
        "Готова? Тогда жми на кнопки 👇"
    )
    bot.send_message(user_id, intro_text, parse_mode="HTML")

    TEST_USER_STATE[user_id] = {
        'answers': [],
        'current': 0,
        'scores': [0]*8
    }
    send_test_question(user_id, 0)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(lambda c: c.data.startswith("nstyle:"))
def neuro_test_step(call):
    user_id = call.message.chat.id
    _, q_idx, opt_idx = call.data.split(":", 2)
    q_idx = int(q_idx)
    opt_idx = int(opt_idx)
    questions = get_test_questions()
    answer = questions[q_idx]['options'][opt_idx]
    state = TEST_USER_STATE.setdefault(user_id, {'answers': [], 'current': 0, 'scores':[0]*8})
    state['answers'].append(answer)
    scores = get_score_for_answer(q_idx+1, answer)

    state['scores'] = [s+int(v) for s,v in zip(state['scores'], scores)]
    next_q = q_idx + 1
    questions = get_test_questions()
    if next_q < len(questions):
        state['current'] = next_q
        send_test_question(user_id, next_q)
    else:
        style_name, style_desc, style_img, style_order = get_style_by_scores(state['scores'])
        msg = f"🌟 Ваш стиль нейрофото: <b>{style_name}</b>\n\n{style_desc}"
        if style_img:
            bot.send_photo(user_id, style_img, caption=msg, parse_mode='HTML')
        else:
            bot.send_message(user_id, msg, parse_mode='HTML')
        if style_order:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Заказать фото", url=style_order))
            bot.send_message(user_id, "Хотите индивидуальное фото в этом стиле? Оформите заявку 👇", reply_markup=kb)
        TEST_USER_STATE.pop(user_id, None)
    bot.answer_callback_query(call.id)

# --- Меню и работа с категориями/пунктами ---
user_states = {}

@bot.message_handler(commands=['start'])
def start(msg):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("📋 Меню"))
    bot.send_message(msg.chat.id,
        "👋 Привет! Я NeuroBot - помощник Ольги Мишиной.\n"
        "Нажмите кнопку внизу, чтобы открыть Меню.",
        reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "📋 Меню")
def show_categories(msg):
    cats = db.list_categories()
    if not cats:
        return bot.reply_to(msg, "Меню пусто. Админ добавляет через /add_item.")
    kb = types.InlineKeyboardMarkup()
    for cat in cats:
        kb.add(types.InlineKeyboardButton(cat, callback_data=f"cat:{cat}"))
    bot.send_message(msg.chat.id, "Выберите категорию:", reply_markup=kb)

@bot.callback_query_handler(lambda c: c.data.startswith("cat:") and c.data != "cat:Тестирование")
def show_items(call):
    cat = call.data.split(":",1)[1]
    items = db.list_items(cat)
    if not items:
        bot.answer_callback_query(call.id, "В этой категории пока нет пунктов.")
        return
    kb = types.InlineKeyboardMarkup()
    for item_id, name, _, _ in items:
        kb.add(types.InlineKeyboardButton(name, callback_data=f"item:{item_id}"))
    # ——— Добавляем кнопку "⬅️ Назад" только здесь:
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu"))
    bot.send_message(call.message.chat.id,
        f"Категория «{cat}»: выберите пункт:",
        reply_markup=kb)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(lambda c: c.data == "back_to_menu")
def back_to_main_menu(call):
    cats = db.list_categories()
    if not cats:
        bot.send_message(call.message.chat.id, "Меню пусто. Админ добавляет через /add_item.")
        return
    kb = types.InlineKeyboardMarkup()
    for cat in cats:
        kb.add(types.InlineKeyboardButton(cat, callback_data=f"cat:{cat}"))
    bot.send_message(call.message.chat.id, "Выберите категорию:", reply_markup=kb)
    bot.answer_callback_query(call.id)

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

# --- Админ: добавление, редактирование, удаление, просмотр пунктов меню (оставлены как были) ---
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

@bot.message_handler(commands=['del_item'])
def cmd_del_item(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.reply_to(msg, "❌ Только админ.")
    parts = msg.text.split()
    if len(parts)!=2 or not parts[1].isdigit():
        return bot.reply_to(msg, "Используйте: /del_item <ID>")
    db.delete_item(int(parts[1]))
    bot.reply_to(msg, "🗑 Пункт удалён.")

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
    if kind == 'file':
        if msg.content_type in ['document', 'video']:
            new_value = (msg.document or msg.video).file_id
        else:
            new_value = st['old_value']
    else:
        if msg.text.lower() != 'skip':
            new_value = msg.text
        else:
            new_value = st['old_value']
    update_item(item_id, name=new_name, value=new_value)
    bot.reply_to(msg, f"✅ Пункт #{item_id} обновлён:\n«{new_name}»")

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
        "/admin_help — Показать этот список команд\n"
    )
    bot.reply_to(msg, help_text)

# --- Эхо на всё остальное ---
@bot.message_handler(func=lambda m: True)
def echo_all(msg):
    bot.reply_to(msg, f"Не понял: {msg.text}")

if __name__ == "__main__":
    bot.remove_webhook()
    logging.info("🗑 Webhook removed, waiting 1s…")
    time.sleep(1)
    threading.Thread(target=run_health_server, daemon=True).start()
    logging.info("🔗 Health server started on 0.0.0.0:8080")
    logging.info("🚀 Bot is starting polling…")
    bot.infinity_polling(timeout=30, long_polling_timeout=60)
