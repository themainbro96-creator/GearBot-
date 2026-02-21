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

# --- ИНИЦИАЛИЗАЦИЯ ---
TOKEN = os.environ.get('TOKEN')
bot = telebot.TeleBot(TOKEN)
translator = GoogleTranslator(source='en', target='ru')
start_time = time.time()
VERSION = "2.6.0 (No-Save Edition)"

# Кэш в оперативной памяти (сбросится при перезагрузке сервера)
user_languages = {}
search_cache = {}

def load_base_data():
    """Загрузка игровых данных (эти файлы ДОЛЖНЫ быть в GitHub)"""
    try:
        with open('Swgoh_Characters.json', 'r', encoding='utf-8') as f:
            # Читаем структуру swgoh.gg
            data = json.load(f)
            chars = json.loads(data['text']) if 'text' in data else data
        with open('Swgoh_Gear.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            gear = json.loads(data['text']) if 'text' in data else data
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

def smart_translate(text, lang, category):
    if lang == 'en' or not text: return text
    
    # 1. Сначала ищем в твоем файле localization.json
    if text in loc.get('ru', {}).get(category, {}):
        return loc['ru'][category][text]
    
    # 2. Потом ищем в кэше памяти
    cache_key = f"{category}:{text}"
    if cache_key in search_cache:
        return search_cache[cache_key]
    
    # 3. Если нет - переводим (только один раз за сессию)
    try:
        translated = translator.translate(text)
        search_cache[cache_key] = translated
        return translated
    except:
        return text

def get_english_query(query):
    query_clean = query.lower().strip()
    if not re.search('[а-яА-Я]', query_clean):
        return query_clean
    
    cache_key = f"search:{query_clean}"
    if cache_key in search_cache:
        return search_cache[cache_key]
    
    try:
        translated = GoogleTranslator(source='ru', target='en').translate(query_clean)
        search_cache[cache_key] = translated
        return translated
    except: return query_clean

# --- ФОРМАТИРОВАНИЕ ---

def format_gear_text(char, lang='en'):
    name = smart_translate(char['name'], lang, 'characters')
    desc = smart_translate(char.get('description', 'Unit'), lang, 'descriptions')
    t_text = loc[lang]['phrases']['tier']
    
    res = f"<b>{name}</b>\n<i>{desc}</i>\n\n"
    # Для экономии времени/памяти выводим только последние 3 уровня снаряжения 
    # или используйте запрос с номером тира для конкретики
    levels_to_show = char['gear_levels'][-3:] # Показать последние 3
    
    res += f"(Показаны последние уровни. Напишите <b>'{query_clean} 12'</b> для деталей)\n\n"
    
    for i, level in enumerate(levels_to_show):
        level_idx = len(char['gear_levels']) - 3 + i + 1
        items = [f"— {smart_translate(gear_dict.get(g, g), lang, 'gear_materials')}" for g in level['gear']]
        res += f"<b>{t_text} {level_idx}</b>\n<blockquote>" + "\n".join(items) + "</blockquote>\n"
    return res

def make_kb(char_id, lang='en'):
    markup = types.InlineKeyboardMarkup()
    btns = loc[lang]['buttons']
    markup.add(types.InlineKeyboardButton(btns['configuration'], callback_data="conf_sys"))
    return markup

# --- ОБРАБОТЧИКИ ---

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru"),
        types.InlineKeyboardButton("🇬🇧 Английский", callback_data="setlang_en")
    )
    bot.send_message(message.chat.id, f"sup, {message.from_user.first_name}! Выбери язык / Choose language:", reply_markup=markup)

@bot.message_handler(commands=['config'])
def config_cmd(message):
    uptime = f"{int(time.time() - start_time)}s"
    info = (
        f"🛠 <b>System Config</b>\n"
        f"— Version: <code>{VERSION}</code>\n"
        f"— Mode: <code>In-Memory Cache</code>\n"
        f"— Uptime: <code>{uptime}</code>\n"
        f"— Cached items: <code>{len(search_cache)}</code>"
    )
    bot.send_message(message.chat.id, info, parse_mode="HTML")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = str(message.chat.id)
    lang = user_languages.get(chat_id, 'en')
    
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
        ph = loc[lang]['phrases']
        
        if tier_val:
            t_idx = min(max(tier_val, 1), len(char['gear_levels'])) - 1
            items = [f"— {smart_translate(gear_dict.get(g, g), lang, 'gear_materials')}" for g in char['gear_levels'][t_idx]['gear']]
            caption = (f"<b>{smart_translate(char['name'], lang, 'characters')}</b>\n"
                       f"<b>{ph['tier']} {t_idx+1}</b>\n\n"
                       f"<blockquote>" + "\n".join(items) + "</blockquote>")
        else:
            caption = format_gear_text(char, lang)

        bot.delete_message(message.chat.id, wait_msg.message_id)
        
        if len(caption) > 1024:
            bot.send_photo(message.chat.id, char['image'])
            bot.send_message(message.chat.id, caption[:4000], parse_mode="HTML", reply_markup=make_kb(char['base_id'], lang))
        else:
            bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="HTML", reply_markup=make_kb(char['base_id'], lang))
    else:
        bot.delete_message(message.chat.id, wait_msg.message_id)
        bot.reply_to(message, loc[lang]['phrases']['unit_not_found'])

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = str(call.message.chat.id)
    if call.data.startswith("setlang_"):
        new_lang = call.data.split('_')[1]
        user_languages[chat_id] = new_lang
        bot.edit_message_text(loc[new_lang]['phrases']['lang_set_msg'], chat_id, call.message.message_id, parse_mode="HTML")
    elif call.data == "conf_sys":
        config_cmd(call.message)

# --- WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): 
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
