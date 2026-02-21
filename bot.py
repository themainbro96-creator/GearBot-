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
VERSION = "2.5.0 (Turbo Speed)"

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
    except: pass

user_languages = load_json(LANG_FILE)
search_cache = load_json(CACHE_FILE) # Здесь храним и имена, и описания, и ГИР!

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
        return [], [], {}

chars_data, gear_data, loc = load_base_data()
gear_dict = {item['base_id']: item['name'] for item in gear_data}
char_names = [c['name'] for c in chars_data]

# --- СУПЕР-БЫСТРАЯ ЛОГИКА ПЕРЕВОДА ---

def smart_translate(text, lang, category):
    """
    Алгоритм: 
    1. Если язык английский -> сразу возврат.
    2. Если есть в localization.json -> мгновенный возврат.
    3. Если есть в кэше (памяти) -> мгновенный возврат.
    4. Если нет нигде -> переводим ОДИН РАЗ и запоминаем навсегда.
    """
    if lang == 'en' or not text:
        return text
    
    # 1. Проверка в локализации (твой файл)
    if text in loc.get('ru', {}).get(category, {}):
        return loc['ru'][category][text]
    
    # 2. Проверка в кэше перевода (память)
    cache_key = f"{category}:{text}"
    if cache_key in search_cache:
        return search_cache[cache_key]
    
    # 3. Крайний случай - Google (только один раз для нового предмета)
    try:
        # Для гира можно вообще отключить автоперевод, если хочешь 0 задержек:
        # if category == 'gear_materials': return text 
        
        translated = translator.translate(text)
        search_cache[cache_key] = translated
        save_json(CACHE_FILE, search_cache)
        return translated
    except:
        return text

def get_english_query(query):
    """Перевод поискового запроса юзера (напр. 'Падме' -> 'Padme')"""
    query_clean = query.lower().strip()
    if not re.search('[а-яА-Я]', query_clean):
        return query_clean
    
    cache_key = f"search:{query_clean}"
    if cache_key in search_cache:
        return search_cache[cache_key]
    
    try:
        translated = GoogleTranslator(source='ru', target='en').translate(query_clean)
        search_cache[cache_key] = translated
        save_json(CACHE_FILE, search_cache)
        return translated
    except: return query_clean

# --- ФОРМАТИРОВАНИЕ ---

def format_gear_text(char, lang='en'):
    name = smart_translate(char['name'], lang, 'characters')
    desc = smart_translate(char.get('description', 'Unit'), lang, 'descriptions')
    t_text = loc[lang]['phrases']['tier']
    
    res = f"<b>{name}</b>\n<i>{desc}</i>\n\n"
    for i, level in enumerate(char['gear_levels']):
        items = []
        for g_id in level['gear']:
            orig_name = gear_dict.get(g_id, g_id)
            # Ищем перевод в локализации или кэше
            trans_name = smart_translate(orig_name, lang, 'gear_materials')
            items.append(f"— {trans_name}")
        res += f"<b>{t_text} {i+1}</b>\n<blockquote>" + "\n".join(items) + "</blockquote>\n"
    return res

# Остальные функции (make_kb, команды /start, /config) остаются такими же...
# [Вставь здесь команды из прошлого кода]

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
        
        # Отправка...
        if len(caption) > 1024:
            bot.send_photo(message.chat.id, char['image'])
            bot.send_message(message.chat.id, caption[:4096], parse_mode="HTML", reply_markup=make_kb(char['base_id'], lang))
        else:
            bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="HTML", reply_markup=make_kb(char['base_id'], lang))
    else:
        bot.delete_message(message.chat.id, wait_msg.message_id)
        bot.reply_to(message, loc[lang]['phrases']['unit_not_found'])

# [Flask и запуск]
