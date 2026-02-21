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

# Данные в памяти
user_data = {}  # {chat_id: 'lang'}
user_ids = set()
gear_cache = {} 
search_cache = {} 
pending_post = set() # Список чатов, от которых бот ждет пост

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
        print(f"Ошибка загрузки баз данных: {e}")
        return [], [], {}

chars_data, gear_data, loc = load_base_data()
gear_dict = {item['base_id']: item['name'] for item in gear_data}
char_names = [c['name'] for c in chars_data]

# --- ЛОГИКА ---

def get_cached_translation(text, lang):
    if lang == 'en' or not text: return text
    if text in loc.get('ru', {}).get('gear_materials', {}):
        return loc['ru']['gear_materials'][text]
    if text in gear_cache: return gear_cache[text]
    try:
        translated = translator.translate(text)
        gear_cache[text] = translated
        return translated
    except: return text

def get_english_query(query):
    query_clean = query.lower().strip()
    if not re.search('[а-яА-Я]', query_clean): return query_clean
    if query_clean in search_cache: return search_cache[query_clean]
    try:
        translated = GoogleTranslator(source='ru', target='en').translate(query_clean)
        search_cache[query_clean] = translated
        return translated
    except: return query_clean

# --- ОБРАБОТЧИКИ ---

@bot.message_handler(commands=['start'])
def start(message):
    user_ids.add(message.chat.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru"),
        types.InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en")
    )
    bot.send_message(message.chat.id, "Выбери язык / Choose language:", reply_markup=markup)

@bot.message_handler(commands=['post'])
def post_init(message):
    if message.from_user.username in ADMINS:
        pending_post.add(message.chat.id)
        bot.send_message(message.chat.id, "Напиши пост и отправь мне")

@bot.message_handler(func=lambda message: True, content_types=['text', 'photo', 'video', 'animation', 'document'])
def handle_all_messages(message):
    chat_id = message.chat.id
    user_ids.add(chat_id)
    
    # Режим рассылки
    if chat_id in pending_post and message.from_user.username in ADMINS:
        pending_post.remove(chat_id)
        count = 0
        for uid in user_ids:
            try:
                # copy_message копирует сообщение 1 в 1 со всеми картинками и шрифтами
                bot.copy_message(uid, chat_id, message.message_id)
                count += 1
            except: continue
        bot.send_message(chat_id, f"✅ Рассылка завершена. Получили: {count} пользователей.")
        return

    # Если это не текст или это другая команда, дальше не идем
    if not message.text or message.text.startswith('/'): return

    lang = user_data.get(chat_id, 'ru')
    wait_msg = bot.send_message(chat_id, "⏳")
    
    raw = message.text.strip()
    parts = raw.split()
    tier_val, query = None, raw
    if len(parts) > 1 and parts[-1].isdigit():
        tier_val, query = int(parts[-1]), " ".join(parts[:-1])

    query_eng = get_english_query(query)
    matches = process.extract(query_eng, char_names, limit=3)
    best_match, score = matches[0][0], matches[0][1]
    
    if score > 70:
        char = next(c for c in chars_data if c['name'] == best_match)
        if tier_val:
            t_idx = min(max(tier_val, 1), len(char['gear_levels'])) - 1
            items = []
            for g_id in char['gear_levels'][t_idx]['gear']:
                orig = gear_dict.get(g_id, g_id)
                items.append(f"— {get_cached_translation(orig, lang)}")
            
            char_name_display = best_match if lang == 'en' else get_cached_translation(best_match, lang)
            caption = f"<b>{char_name_display}</b>\n<b>Тир {t_idx+1}</b>\n\n<blockquote>" + "\n".join(items) + "</blockquote>"
        else:
            char_name_display = best_match if lang == 'en' else get_cached_translation(best_match, lang)
            hint = "Напиши 'имя номер', чтобы увидеть детали конкретного тира." if lang == 'ru' else "Type 'name number' to see specific tier details."
            caption = f"<b>{char_name_display}</b>\n\n{hint}"

        bot.delete_message(chat_id, wait_msg.message_id)
        bot.send_photo(chat_id, char['image'], caption=caption, parse_mode="HTML")
    else:
        bot.delete_message(chat_id, wait_msg.message_id)
        markup = types.InlineKeyboardMarkup()
        for m in matches:
            markup.add(types.InlineKeyboardButton(m[0], callback_data=f"search_{m[0]}"))
        
        error_msg = "Юнит не найден, напиши снова. Возможно ты искал кого-то из ниже перечисленных:" if lang == 'ru' else "Unit not found, try again. Maybe you were looking for one of these:"
        bot.send_message(chat_id, error_msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    if call.data.startswith("setlang_"):
        l = call.data.split('_')[1]
        user_data[chat_id] = l
        msg = "Язык установлен!" if l == 'ru' else "Language set!"
        bot.edit_message_text(msg, chat_id, call.message.message_id)
    elif call.data.startswith("search_"):
        name = call.data.replace("search_", "")
        # Имитируем сообщение от пользователя для повторного поиска
        call.message.text = name
        handle_all_messages(call.message)

# --- ВЕБ-СЕРВЕР ---
app = Flask('')
@app.route('/')
def home(): return "OK"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()
