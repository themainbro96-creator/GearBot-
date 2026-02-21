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

# Инициализация
TOKEN = os.environ.get('TOKEN')
bot = telebot.TeleBot(TOKEN)
translator = GoogleTranslator(source='en', target='ru')
start_time = time.time()
VERSION = "2.1.0 (No-Relic Edition)"

# Пути к файлам
LANG_FILE = 'user_languages.json'
CACHE_FILE = 'translation_cache.json'

def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return default
    return default

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Загрузка настроек и кэша
user_languages = load_json(LANG_FILE, {})
search_cache = load_json(CACHE_FILE, {})

def load_data():
    with open('Swgoh_Characters.json', 'r', encoding='utf-8') as f:
        chars = json.loads(json.load(f)['text'])
    with open('Swgoh_Gear.json', 'r', encoding='utf-8') as f:
        gear = json.loads(json.load(f)['text'])
    try:
        with open('localization.json', 'r', encoding='utf-8') as f:
            loc_data = json.load(f)
    except: loc_data = {}
    return chars, gear, loc_data

chars_data, gear_data, loc = load_data()
gear_dict = {item['base_id']: item['name'] for item in gear_data}
char_names = [c['name'] for c in chars_data]

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_english_query(query):
    """Переводит русский запрос в английский и кэширует его"""
    query_clean = query.lower().strip()
    if not re.search('[а-яА-Я]', query_clean):
        return query_clean
    
    if query_clean in search_cache:
        return search_cache[query_clean]
    
    try:
        translated = GoogleTranslator(source='ru', target='en').translate(query_clean)
        search_cache[query_clean] = translated
        save_json(CACHE_FILE, search_cache)
        return translated
    except:
        return query_clean

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
        items = []
        for g_id in level['gear']:
            orig_name = gear_dict.get(g_id, g_id)
            trans_name = translate_item(orig_name, lang, 'gear_materials')
            items.append(f"— {trans_name}")
        res += f"<b>{t_text} {i+1}</b>\n<blockquote>" + "\n".join(items) + "</blockquote>\n"
    return res

def make_kb(char_id, lang='en'):
    markup = types.InlineKeyboardMarkup()
    btns = loc[lang]['buttons']
    # Теперь кнопки только для конфига и обновления (можно добавить кнопку "Обновить")
    btn_conf = types.InlineKeyboardButton(btns['configuration'], callback_data=f"conf_sys")
    markup.add(btn_conf)
    return markup

# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start'])
def start(message):
    name = message.from_user.first_name
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru"),
        types.InlineKeyboardButton("🇬🇧 Английский", callback_data="setlang_en")
    )
    bot.send_message(message.chat.id, f"sup, {name}! Choose the language", reply_markup=markup)

@bot.message_handler(commands=['settings'])
def settings(message):
    chat_id = str(message.chat.id)
    lang = user_languages.get(chat_id, 'en')
    text = "Выбери язык" if lang == 'ru' else "Choose the language"
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru"),
        types.InlineKeyboardButton("🇬🇧 Английский", callback_data="setlang_en")
    )
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(commands=['config'])
def config_cmd(message):
    uptime = f"{int(time.time() - start_time)} sec"
    lang = user_languages.get(str(message.chat.id), 'en')
    info = (
        f"🛠 <b>System Config</b>\n"
        f"— Version: <code>{VERSION}</code>\n"
        f"— Uptime: <code>{uptime}</code>\n"
        f"— Cached Names: <code>{len(search_cache)}</code>\n"
        f"— Language: <code>{lang.upper()}</code>\n"
        f"— Database: <code>SWGOH Local JSON</code>"
    )
    bot.send_message(message.chat.id, info, parse_mode="HTML")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = str(message.chat.id)
    lang = user_languages.get(chat_id, 'en')
    raw = message.text.strip()
    parts = raw.split()
    
    tier_val, query = None, raw
    if len(parts) > 1 and parts[-1].isdigit():
        tier_val, query = int(parts[-1]), " ".join(parts[:-1])

    # Умный поиск с учетом русского языка
    query_eng = get_english_query(query)
    best, score = process.extractOne(query_eng, char_names)
    
    if score > 60:
        char = next(c for c in chars_data if c['name'] == best)
        
        if tier_val:
            t_idx = min(max(tier_val, 1), len(char['gear_levels'])) - 1
            g_list = "\n".join([f"— {translate_item(gear_dict.get(g, g), lang, 'gear_materials')}" for g in char['gear_levels'][t_idx]['gear']])
            caption = f"<b>{char['name']}</b>\n<b>Tier {t_idx+1}</b>\n<blockquote>{g_list}</blockquote>"
        else:
            caption = format_gear_text(char, lang)

        if len(caption) > 1024:
            bot.send_photo(message.chat.id, char['image'])
            bot.send_message(message.chat.id, caption, parse_mode="HTML", reply_markup=make_kb(char['base_id'], lang))
        else:
            bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="HTML", reply_markup=make_kb(char['base_id'], lang))
    else:
        bot.reply_to(message, loc[lang]['phrases']['unit_not_found'])

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = str(call.message.chat.id)
    
    if call.data.startswith("setlang_"):
        new_lang = call.data.split('_')[1]
        user_languages[chat_id] = new_lang
        save_json(LANG_FILE, user_languages)
        msg = loc[new_lang]['phrases']['lang_set_msg']
        bot.edit_message_text(msg, chat_id, call.message.message_id, parse_mode="HTML")
        return

    if call.data == "conf_sys":
        # Вызов конфига из кнопки
        config_cmd(call.message)
        return

# --- ЗАПУСК ---
app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.remove_webhook()
    bot.infinity_polling()
