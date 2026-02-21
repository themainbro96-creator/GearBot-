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
VERSION = "2.4.0 (Memory & Emoji)"

# Пути к файлам (убедись, что создал их в GitHub с содержимым {})
LANG_FILE = 'user_languages.json'
CACHE_FILE = 'translation_cache.json'

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_json(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Запись на диск не удалась: {e}")

# Загружаем всё в оперативную память ПРИ СТАРТЕ
user_languages = load_json(LANG_FILE)
search_cache = load_json(CACHE_FILE)

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

# --- ЛОГИКА ---

def get_english_query(query):
    query_clean = query.lower().strip()
    # Если кириллицы нет - не переводим
    if not re.search('[а-яА-Я]', query_clean):
        return query_clean
    
    # ПРОВЕРКА ПАМЯТИ (Это и есть "запоминание")
    if query_clean in search_cache:
        print(f"Взято из кэша: {query_clean}")
        return search_cache[query_clean]
    
    # Если в памяти нет - идем в Google
    try:
        translated = GoogleTranslator(source='ru', target='en').translate(query_clean)
        search_cache[query_clean] = translated
        save_json(CACHE_FILE, search_cache) # Пробуем сохранить для следующего деплоя
        return translated
    except: return query_clean

def translate_item(text, lang, category):
    if lang == 'en': return text
    if text in loc.get('ru', {}).get(category, {}):
        return loc['ru'][category][text]
    try: return translator.translate(text)
    except: return text

def format_gear_text(char, lang='en'):
    name = translate_item(char['name'], lang, 'characters')
    desc = translate_item(char.get('description', 'Unit'), lang, 'descriptions')
    t_text = loc[lang]['phrases']['tier']
    
    res = f"<b>{name}</b>\n<i>{desc}</i>\n\n"
    for i, level in enumerate(char['gear_levels']):
        items = [f"— {translate_item(gear_dict.get(g, g), lang, 'gear_materials')}" for g in level['gear']]
        res += f"<b>{t_text} {i+1}</b>\n<blockquote>" + "\n".join(items) + "</blockquote>\n"
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
    bot.send_message(message.chat.id, f"sup, {message.from_user.first_name}! Choose language:", reply_markup=markup)

@bot.message_handler(commands=['config'])
def config_cmd(message):
    uptime = f"{int(time.time() - start_time)}s"
    lang = user_languages.get(str(message.chat.id), 'en')
    info = (
        f"🛠 <b>System Config</b>\n"
        f"— Version: <code>{VERSION}</code>\n"
        f"— Uptime: <code>{uptime}</code>\n"
        f"— Memory Cache: <code>{len(search_cache)} units</code>\n"
        f"— Your Lang: <code>{lang.upper()}</code>"
    )
    bot.send_message(message.chat.id, info, parse_mode="HTML")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = str(message.chat.id)
    lang = user_languages.get(chat_id, 'en')
    
    # ШАГ 1: ОТПРАВЛЯЕМ ЧАСЫ
    wait_msg = bot.send_message(message.chat.id, "⏳")
    
    raw = message.text.strip()
    parts = raw.split()
    tier_val, query = None, raw
    if len(parts) > 1 and parts[-1].isdigit():
        tier_val, query = int(parts[-1]), " ".join(parts[:-1])

    # ШАГ 2: ИЩЕМ (здесь сработает кэш или перевод)
    query_eng = get_english_query(query)
    best, score = process.extractOne(query_eng, char_names)
    
    if score > 60:
        char = next(c for c in chars_data if c['name'] == best)
        ph = loc[lang]['phrases']
        
        if tier_val:
            t_idx = min(max(tier_val, 1), len(char['gear_levels'])) - 1
            items = [f"— {translate_item(gear_dict.get(g, g), lang, 'gear_materials')}" for g in char['gear_levels'][t_idx]['gear']]
            caption = (f"<b>{translate_item(char['name'], lang, 'characters')}</b>\n"
                       f"<b>{ph['tier']} {t_idx+1}</b>\n\n"
                       f"<blockquote>" + "\n".join(items) + "</blockquote>")
        else:
            caption = format_gear_text(char, lang)

        # ШАГ 3: УДАЛЯЕМ ЧАСЫ И ПРИСЫЛАЕМ РЕЗУЛЬТАТ
        bot.delete_message(message.chat.id, wait_msg.message_id)
        
        if len(caption) > 1024:
            bot.send_photo(message.chat.id, char['image'])
            bot.send_message(message.chat.id, caption, parse_mode="HTML", reply_markup=make_kb(char['base_id'], lang))
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
        save_json(LANG_FILE, user_languages)
        bot.edit_message_text(loc[new_lang]['phrases']['lang_set_msg'], chat_id, call.message.message_id, parse_mode="HTML")
    elif call.data == "conf_sys":
        config_cmd(call.message)

# --- WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
