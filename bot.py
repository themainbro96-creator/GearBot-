import telebot
import json
import os
import re
import time
from flask import Flask
from threading import Thread
from telebot import types
from fuzzywuzzy import process
from deep_translator import GoogleTranslator

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get('TOKEN')
bot = telebot.TeleBot(TOKEN)
translator = GoogleTranslator(source='en', target='ru')
ADMINS = ['temkazavr', 'example00']  # Список админов без @
start_time = time.time()

# Временное хранилище в памяти
user_ids = set() 
search_cache = {} # Кэш имен персонажей и их описаний

def load_base_data():
    try:
        with open('Swgoh_Characters.json', 'r', encoding='utf-8') as f:
            chars = json.loads(json.load(f)['text'])
        with open('Swgoh_Gear.json', 'r', encoding='utf-8') as f:
            gear = json.loads(json.load(f)['text'])
        with open('localization.json', 'r', encoding='utf-8') as f:
            loc_data = json.load(f)
        return chars, gear, loc_data
    except Exception as e:
        print(f"Ошибка загрузки базы: {e}")
        return [], [], {}

chars_data, gear_data, loc = load_base_data()
gear_dict = {item['base_id']: item['name'] for item in gear_data}
char_names = [c['name'] for c in chars_data]

# --- ЛОГИКА ПЕРЕВОДА ---

def get_english_query(query):
    query_clean = query.lower().strip()
    if not re.search('[а-яА-Я]', query_clean):
        return query_clean
    if query_clean in search_cache:
        return search_cache[query_clean]
    try:
        translated = GoogleTranslator(source='ru', target='en').translate(query_clean)
        search_cache[query_clean] = translated
        return translated
    except: return query_clean

def translate_info(text, category):
    """Перевод только имен и описаний юнитов"""
    if text in loc.get('ru', {}).get(category, {}):
        return loc['ru'][category][text]
    
    cache_key = f"{category}:{text}"
    if cache_key in search_cache:
        return search_cache[cache_key]
    
    try:
        translated = translator.translate(text)
        search_cache[cache_key] = translated
        return translated
    except: return text

# --- ФОРМАТИРОВАНИЕ ---

def format_gear_text(char):
    name = translate_info(char['name'], 'characters')
    desc = translate_info(char.get('description', 'Юнит'), 'descriptions')
    
    res = f"<b>{name}</b>\n<i>{desc}</i>\n\n"
    for i, level in enumerate(char['gear_levels']):
        # Материалы НЕ ПЕРЕВОДИМ, берем как есть
        items = [f"— {gear_dict.get(g, g)}" for g in level['gear']]
        res += f"<b>Тир {i+1}</b>\n<blockquote>" + "\n".join(items) + "</blockquote>\n"
    return res

# --- КОМАНДЫ ---

@bot.message_handler(commands=['start'])
def start(message):
    user_ids.add(message.chat.id)
    bot.send_message(message.chat.id, f"Привет, {message.from_user.first_name}! Напиши имя персонажа, чтобы узнать его снаряжение.")

@bot.message_handler(commands=['config'])
def config_cmd(message):
    if message.from_user.username not in ADMINS: return
    uptime = f"{int(time.time() - start_time)}s"
    info = (
        f"🛠 <b>Конфиг разработчика</b>\n"
        f"— Аптайм: <code>{uptime}</code>\n"
        f"— Юзеров в сессии: <code>{len(user_ids)}</code>\n"
        f"— Кэш памяти: <code>{len(search_cache)} записей</code>"
    )
    bot.send_message(message.chat.id, info, parse_mode="HTML")

# --- РАССЫЛКА (/post) ---
@bot.message_handler(commands=['post'])
def post_cmd(message):
    if message.from_user.username not in ADMINS:
        return
    
    msg_to_send = message.reply_to_message
    if not msg_to_send:
        bot.reply_to(message, "Ответь командой /post на сообщение, которое хочешь разослать.")
        return

    count = 0
    for uid in user_ids:
        try:
            bot.copy_message(uid, message.chat.id, msg_to_send.message_id)
            count += 1
        except: continue
    
    bot.send_message(message.chat.id, f"✅ Рассылка завершена. Получили: {count} пользователей.")

# --- ПОИСК ---

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_ids.add(message.chat.id) # Добавляем в список для рассылки
    wait_msg = bot.send_message(message.chat.id, "⏳")
    
    raw = message.text.strip()
    parts = raw.split()
    tier_val, query = None, raw
    if len(parts) > 1 and parts[-1].isdigit():
        tier_val, query = int(parts[-1]), " ".join(parts[:-1])

    query_eng = get_english_query(query)
    best, score = process.extractOne(query_eng, char_names)
    
    if score > 60:
        char = next(c for c in chars_data if c['name'] == best)
        
        if tier_val:
            t_idx = min(max(tier_val, 1), len(char['gear_levels'])) - 1
            items = [f"— {gear_dict.get(g, g)}" for g in char['gear_levels'][t_idx]['gear']]
            caption = (f"<b>{translate_info(char['name'], 'characters')}</b>\n"
                       f"<b>Тир {t_idx+1}</b>\n\n"
                       f"<blockquote>" + "\n".join(items) + "</blockquote>")
        else:
            caption = format_gear_text(char)

        bot.delete_message(message.chat.id, wait_msg.message_id)
        
        if len(caption) > 1024:
            bot.send_photo(message.chat.id, char['image'])
            bot.send_message(message.chat.id, caption[:4096], parse_mode="HTML")
        else:
            bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="HTML")
    else:
        bot.delete_message(message.chat.id, wait_msg.message_id)
        bot.reply_to(message, "Юнит не найден.")

# --- ЗАПУСК ---
app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
