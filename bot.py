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

# --- КОНФИГ ---
TOKEN = os.environ.get('TOKEN')
bot = telebot.TeleBot(TOKEN)
translator = GoogleTranslator(source='en', target='ru')
ADMINS = ['temkazavr', 'example00']
start_time = time.time()

# Кэш в оперативной памяти (сбросится при перезагрузке на Render)
user_data = {} # {chat_id: 'lang'}
user_ids = set()
gear_cache = {} # {'en_name': 'ru_name'}
search_cache = {} # Кэш для имен героев

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
        print(f"Ошибка загрузки: {e}")
        return [], [], {}

chars_data, gear_data, loc = load_base_data()
gear_dict = {item['base_id']: item['name'] for item in gear_data}
char_names = [c['name'] for c in chars_data]

# --- ЛОГИКА ПЕРЕВОДА ---

def get_cached_translation(text, category="gear"):
    """Перевод с сохранением во временный массив"""
    if not text: return text
    # Проверяем локализацию
    if text in loc.get('ru', {}).get('gear_materials', {}):
        return loc['ru']['gear_materials'][text]
    
    # Проверяем временный кэш
    if text in gear_cache:
        return gear_cache[text]
    
    # Переводим
    try:
        translated = translator.translate(text)
        gear_cache[text] = translated
        return translated
    except:
        return text

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

# --- ИНТЕРФЕЙС ---

def make_main_kb(lang):
    markup = types.InlineKeyboardMarkup()
    btns = loc[lang]['buttons']
    markup.add(types.InlineKeyboardButton(btns['configuration'], callback_data="conf_sys"))
    return markup

def make_suggest_kb(suggestions):
    markup = types.InlineKeyboardMarkup()
    for s in suggestions:
        markup.add(types.InlineKeyboardButton(s, callback_data=f"search_{s}"))
    return markup

# --- ОБРАБОТЧИКИ ---

@bot.message_handler(commands=['start'])
def start(message):
    user_ids.add(message.chat.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru"),
        types.InlineKeyboardButton("🇬🇧 Английский", callback_data="setlang_en")
    )
    bot.send_message(message.chat.id, "Выбери язык / Choose language:", reply_markup=markup)

@bot.message_handler(commands=['settings'])
def settings(message):
    start(message)

@bot.message_handler(commands=['config'])
def config_cmd(message):
    if message.from_user.username not in ADMINS: return
    uptime = f"{int(time.time() - start_time)}s"
    info = (f"🛠 <b>Конфиг</b>\n— Аптайм: {uptime}\n"
            f"— Юзеров: {len(user_ids)}\n— Кэш гира: {len(gear_cache)}")
    bot.send_message(message.chat.id, info, parse_mode="HTML")

@bot.message_handler(commands=['post'])
def post_cmd(message):
    if message.from_user.username not in ADMINS or not message.reply_to_message:
        return
    count = 0
    for uid in user_ids:
        try:
            bot.copy_message(uid, message.chat.id, message.reply_to_message.message_id)
            count += 1
        except: continue
    bot.send_message(message.chat.id, f"Разослано: {count}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    user_ids.add(chat_id)
    lang = user_data.get(chat_id, 'ru')
    
    # Игнорируем команды внутри поиска
    if message.text.startswith('/'): return

    wait_msg = bot.send_message(chat_id, "⏳")
    
    raw = message.text.strip()
    parts = raw.split()
    tier_val, query = None, raw
    if len(parts) > 1 and parts[-1].isdigit():
        tier_val, query = int(parts[-1]), " ".join(parts[:-1])

    query_eng = get_english_query(query)
    # Ищем топ-3 совпадения
    matches = process.extract(query_eng, char_names, limit=3)
    best_match, score = matches[0][0], matches[0][1]
    
    if score > 70:
        char = next(c for c in chars_data if c['name'] == best_match)
        
        if tier_val:
            t_idx = min(max(tier_val, 1), len(char['gear_levels'])) - 1
            items = []
            for g_id in char['gear_levels'][t_idx]['gear']:
                orig = gear_dict.get(g_id, g_id)
                trans = get_cached_translation(orig) if lang == 'ru' else orig
                items.append(f"— {trans}")
            
            caption = f"<b>{best_match}</b>\n<b>Тир {t_idx+1}</b>\n\n<blockquote>" + "\n".join(items) + "</blockquote>"
        else:
            # Сводка всего гира (упростим для скорости)
            name_ru = get_cached_translation(char['name']) if lang == 'ru' else char['name']
            caption = f"<b>{name_ru}</b>\n\nНапиши 'имя номер', чтобы увидеть детали конкретного тира."

        bot.delete_message(chat_id, wait_msg.message_id)
        bot.send_photo(chat_id, char['image'], caption=caption, parse_mode="HTML", reply_markup=make_main_kb(lang))
    else:
        bot.delete_message(chat_id, wait_msg.message_id)
        suggestions = [m[0] for m in matches]
        msg_text = "Юнит не найден, напиши снова. Возможно ты искал кого-то из ниже перечисленных:"
        bot.send_message(chat_id, msg_text, reply_markup=make_suggest_kb(suggestions))

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith("setlang_"):
        l = call.data.split('_')[1]
        user_data[call.message.chat.id] = l
        bot.answer_callback_query(call.id, "Готово!")
        bot.edit_message_text(loc[l]['phrases']['lang_set_msg'], call.message.chat.id, call.message.message_id)
    
    elif call.data.startswith("search_"):
        name = call.data.replace("search_", "")
        call.message.text = name
        handle_message(call.message)

    elif call.data == "conf_sys":
        config_cmd(call.message)

# --- ЗАПУСК ---
app = Flask('')
@app.route('/')
def home(): return "OK"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()
