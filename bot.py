import telebot
import json
import os
from flask import Flask
from threading import Thread
from telebot import types
from fuzzywuzzy import process
from deep_translator import GoogleTranslator

TOKEN = os.environ.get('TOKEN')
bot = telebot.TeleBot(TOKEN)
translator = GoogleTranslator(source='en', target='ru')

LANGUAGES_FILE = 'user_languages.json'

def load_user_languages():
    if os.path.exists(LANGUAGES_FILE):
        try:
            with open(LANGUAGES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {str(k): v for k, v in data.items()}
        except: return {}
    return {}

def save_user_languages(langs):
    with open(LANGUAGES_FILE, 'w', encoding='utf-8') as f:
        json.dump(langs, f, ensure_ascii=False)

user_languages = load_user_languages()

def load_data():
    with open('Swgoh_Characters.json', 'r', encoding='utf-8') as f:
        chars = json.loads(json.load(f)['text'])
    with open('Swgoh_Gear.json', 'r', encoding='utf-8') as f:
        gear = json.loads(json.load(f)['text'])
    try:
        with open('Relic_Requirements.json', 'r', encoding='utf-8') as f:
            relics = json.load(f)
    except: relics = {}
    try:
        with open('localization.json', 'r', encoding='utf-8') as f:
            loc_data = json.load(f)
    except: loc_data = {}
    return chars, gear, relics, loc_data

chars_data, gear_data, relic_reqs, loc = load_data()
gear_dict = {item['base_id']: item['name'] for item in gear_data}
char_names = [c['name'] for c in chars_data]

def get_char_by_id(char_id):
    return next((c for c in chars_data if c['base_id'] == char_id), None)

def translate_item(text, lang, category):
    if lang == 'en': return text
    # Проверка в локальном JSON (приоритет)
    if text in loc['ru'].get(category, {}):
        return loc['ru'][category][text]
    # Автоперевод для остального (гир и т.д.)
    try: return translator.translate(text)
    except: return text

def format_gear_text(char, lang='en'):
    # Имя жирным, Описание курсивом
    name = translate_item(char['name'], lang, 'characters')
    desc = translate_item(char.get('description', 'Unit'), lang, 'descriptions')
    
    t_text = loc[lang]['phrases']['tier']
    res = f"<b>{name}</b>\n<i>{desc}</i>\n\n"
    
    for i, level in enumerate(char['gear_levels']):
        items = []
        for g_id in level['gear']:
            orig_name = gear_dict.get(g_id, g_id)
            translated_name = translate_item(orig_name, lang, 'gear_materials')
            items.append(f"— {translated_name}")
        
        res += f"<b>{t_text} {i+1}</b>\n<blockquote>" + "\n".join(items) + "</blockquote>\n"
    return res

def format_relic_text(char, lang='en'):
    name = translate_item(char['name'], lang, 'characters')
    desc = translate_item(char.get('description', 'Unit'), lang, 'descriptions')
    
    ph = loc[lang]['phrases']
    res = f"<b>{name}</b>\n<i>{desc}</i>\n\n<b>{ph['relic_reqs']}</b>\n\n"
    
    for r, reqs in relic_reqs.items():
        r_label = ph['relic_tier']
        if not reqs:
            res += f"<b>{r_label} {r}</b>\n<blockquote>{ph['base_g13']}</blockquote>\n"
        else:
            items_list = []
            for m_name, count in reqs.items():
                trans_m = translate_item(m_name, lang, 'relic_materials')
                if m_name == "Credits":
                    items_list.append(f"— {trans_m}: {count:,}")
                else:
                    items_list.append(f"— {trans_m}: {count}")
            res += f"<b>{r_label} {r}</b>\n<blockquote>" + "\n".join(items_list) + "</blockquote>\n"
    return res

def make_kb(char_id, view="gear", lang='en'):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = loc[lang]['buttons']
    btn_conf = types.InlineKeyboardButton(btns['configuration'], callback_data=f"conf_{char_id}")
    
    if view == "gear":
        toggle_btn = types.InlineKeyboardButton(btns['relic_tiers'], callback_data=f"relic_{char_id}")
    else:
        toggle_btn = types.InlineKeyboardButton(btns['gear_tiers'], callback_data=f"gear_{char_id}")
    
    markup.add(btn_conf, toggle_btn)
    return markup

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

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = str(message.chat.id)
    lang = user_languages.get(chat_id, 'en')
    raw = message.text.strip().upper()
    parts = raw.split()
    tier_val, is_relic, query = None, False, raw
    
    if len(parts) > 1:
        last = parts[-1]
        if last.startswith('R') and last[1:].isdigit():
            tier_val, is_relic, query = int(last[1:]), True, " ".join(parts[:-1])
        elif last.isdigit():
            tier_val, is_relic, query = int(last), False, " ".join(parts[:-1])

    best, score = process.extractOne(query, char_names)
    if score > 60:
        char = next(c for c in chars_data if c['name'] == best)
        ph = loc[lang]['phrases']
        
        if is_relic or tier_val:
            name_d = translate_item(char['name'], lang, 'characters')
            desc_d = translate_item(char.get('description', 'Unit'), lang, 'descriptions')
            header = f"<b>{name_d}</b>\n<i>{desc_d}</i>\n\n"
            
            if is_relic:
                r_lvl = str(min(max(tier_val, 0), 10))
                req = relic_reqs.get(r_lvl, {})
                if not req: 
                    items_str = ph['base_g13']
                else:
                    items_list = []
                    for k, v in req.items():
                        trans_k = translate_item(k, lang, 'relic_materials')
                        if k == "Credits":
                            items_list.append(f"— {trans_k}: {v:,}")
                        else:
                            items_list.append(f"— {trans_k}: {v}")
                    items_str = "\n".join(items_list)
                caption = f"{header}<b>{ph['relic_tier']} {r_lvl}</b>\n<blockquote>{items_str}</blockquote>"
            else:
                t_idx = min(max(tier_val, 1), len(char['gear_levels'])) - 1
                g_list = "\n".join([f"— {translate_item(gear_dict.get(g, g), lang, 'gear_materials')}" for g in char['gear_levels'][t_idx]['gear']])
                caption = f"{header}<b>{ph['tier']} {t_idx + 1}</b>\n<blockquote>{g_list}</blockquote>"
        else:
            caption = format_gear_text(char, lang)

        if len(caption) > 1024:
            bot.send_photo(message.chat.id, char['image'])
            bot.send_message(message.chat.id, caption, parse_mode="HTML", reply_markup=make_kb(char['base_id'], "relic" if is_relic else "gear", lang))
        else:
            bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="HTML", reply_markup=make_kb(char['base_id'], "relic" if is_relic else "gear", lang))
    else:
        bot.reply_to(message, loc[lang]['phrases']['unit_not_found'])

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = str(call.message.chat.id)
    
    if call.data.startswith("setlang_"):
        new_lang = call.data.split('_')[1]
        user_languages[chat_id] = new_lang
        save_user_languages(user_languages)
        msg = loc[new_lang]['phrases']['lang_set_msg']
        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, parse_mode="HTML")
        return

    lang = user_languages.get(chat_id, 'en')
    data_parts = call.data.split('_')
    act, c_id = data_parts[0], "_".join(data_parts[1:])
    char = get_char_by_id(c_id)
    if not char: return
    
    txt = format_relic_text(char, lang) if act == "relic" else format_gear_text(char, lang)
    kb = make_kb(c_id, act, lang)

    try:
        if call.message.photo and len(txt) <= 1024:
            bot.edit_message_caption(txt, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=kb)
        else:
            bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=kb)
    except: pass

app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.remove_webhook()
    bot.infinity_polling()
