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
translator_ru = GoogleTranslator(source='en', target='ru')
translator_en = GoogleTranslator(source='ru', target='en')
ADMINS = ['temkazavr', 'example00']

# Оперативная память (сбрасывается при перезагрузке сервера)
user_languages = {}
translation_mem = {} # Здесь храним вообще всё: имена, описания, материалы
user_ids = set()

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
        print(f"Ошибка загрузки данных: {e}")
        return [], [], {}

chars_data, gear_data, loc = load_base_data()
gear_dict = {item['base_id']: item['name'] for item in gear_data}
char_names = [c['name'] for c in chars_data]

# --- СИСТЕМА ПЕРЕВОДА ---

def get_smart_translation(text, target_lang, category="general"):
    if target_lang == 'en': return text
    
    # Сначала ищем в файле локализации
    if text in loc.get('ru', {}).get(category, {}):
        return loc['ru'][category][text]
    
    # Потом ищем в оперативной памяти
    mem_key = f"{category}:{text}"
    if mem_key in translation_mem:
        return translation_mem[mem_key]
    
    # Если нет - переводим и запоминаем
    try:
        translated = translator_ru.translate(text)
        translation_mem[mem_key] = translated
        return translated
    except:
        return text

def get_english_query(query):
    query_clean = query.lower().strip()
    if not re.search('[а-яА-Я]', query_clean):
        return query_clean
    
    mem_key = f"search:{query_clean}"
    if mem_key in translation_mem:
        return translation_mem[mem_key]
    
    try:
        translated = translator_en.translate(query_clean)
        translation_mem[mem_key] = translated
        return translated
    except: return query_clean

# --- ФОРМАТИРОВАНИЕ ---

def format_gear_text(char, lang='en'):
    name = get_smart_translation(char['name'], lang, 'characters')
    desc = get_smart_translation(char.get('description', 'Unit'), lang, 'descriptions')
    t_text = loc[lang]['phrases']['tier']
    
    res = f"<b>{name}</b>\n<i>{desc}</i>\n\n"
    for i, level in enumerate(char['gear_levels']):
        items = []
        for g_id in level['gear']:
            orig_name = gear_dict.get(g_id, g_id)
            trans_item = get_smart_translation(orig_name, lang, 'gear_materials')
            items.append(f"— {trans_item}")
        res += f"<b>{t_text} {i+1}</b>\n<blockquote>" + "\n".join(items) + "</blockquote>\n"
    return res

# --- ОБРАБОТЧИКИ ---

@bot.message_handler(commands=['start', 'settings'])
def start_settings(message):
    user_ids.add(message.chat.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("English", callback_data="setlang_en"),
        types.InlineKeyboardButton("Русский", callback_data="setlang_ru")
    )
    bot.send_message(message.chat.id, "Choose your language / Выберите язык:", reply_markup=markup)

@bot.message_handler(commands=['post'])
def post_broadcast(message):
    if message.from_user.username not in ADMINS: return
    if not message.reply_to_message:
        bot.reply_to(message, "Ответьте /post на сообщение для рассылки.")
        return
    
    success = 0
    for uid in list(user_ids):
        try:
            bot.copy_message(uid, message.chat.id, message.reply_to_message.message_id)
            success += 1
        except: continue
    bot.send_message(message.chat.id, f"✅ Рассылка завершена. Доставлено: {success}")

@bot.message_handler(func=lambda message: not message.text.startswith('/'))
def handle_search(message):
    user_ids.add(message.chat.id)
    lang = user_languages.get(str(message.chat.id), 'en')
    
    # ⏳ Отправляем часы
    wait_msg = bot.send_message(message.chat.id, "⏳")
    
    raw = message.text.strip()
    parts = raw.split()
    tier_val, query = None, raw
    if len(parts) > 1 and parts[-1].isdigit():
        tier_val, query = int(parts[-1]), " ".join(parts[:-1])

    query_eng = get_english_query(query)
    # Поиск 3 вариантов на случай неудачи
    matches = process.extract(query_eng, char_names, limit=3)
    best_match, score = matches[0]
    
    if score > 60:
        char = next(c for c in chars_data if c['name'] == best_match)
        ph = loc[lang]['phrases']
        
        if tier_val:
            t_idx = min(max(tier_val, 1), len(char['gear_levels'])) - 1
            items = [f"— {get_smart_translation(gear_dict.get(g, g), lang, 'gear_materials')}" for g in char['gear_levels'][t_idx]['gear']]
            caption = (f"<b>{get_smart_translation(char['name'], lang, 'characters')}</b>\n"
                       f"<b>{ph['tier']} {t_idx+1}</b>\n\n"
                       f"<blockquote>" + "\n".join(items) + "</blockquote>")
        else:
            caption = format_gear_text(char, lang)

        bot.delete_message(message.chat.id, wait_msg.message_id)
        
        if len(caption) > 1024:
            bot.send_photo(message.chat.id, char['image'])
            bot.send_message(message.chat.id, caption[:4096], parse_mode="HTML")
        else:
            bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="HTML")
    else:
        bot.delete_message(message.chat.id, wait_msg.message_id)
        
        # Если не найден, предлагаем варианты
        markup = types.InlineKeyboardMarkup()
        for m_name, m_score in matches:
            # Отображаем в кнопках переведенные имена
            display_name = get_smart_translation(m_name, lang, 'characters')
            markup.add(types.InlineKeyboardButton(display_name, callback_data=f"search_{m_name}"))
        
        fail_text = "Юнит не найден, напиши снова. Возможно ты искал кого-то из ниже перечисленных:" if lang == 'ru' else "Unit not found, try again. Maybe you were looking for one of these:"
        bot.send_message(message.chat.id, fail_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = str(call.message.chat.id)
    
    if call.data.startswith("setlang_"):
        new_lang = call.data.split('_')[1]
        user_languages[chat_id] = new_lang
        msg = loc[new_lang]['phrases']['lang_set_msg']
        bot.edit_message_text(msg, chat_id, call.message.message_id, parse_mode="HTML")
        
    elif call.data.startswith("search_"):
        # Имитируем ввод текста при нажатии на кнопку варианта
        char_name = call.data.split('_')[1]
        call.message.text = char_name
        bot.delete_message(chat_id, call.message.message_id)
        handle_search(call.message)

# --- FLASK ---
app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
