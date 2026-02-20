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

def load_data():
    with open('Swgoh_Characters.json', 'r', encoding='utf-8') as f:
        chars = json.loads(json.load(f)['text'])
    with open('Swgoh_Gear.json', 'r', encoding='utf-8') as f:
        gear = json.loads(json.load(f)['text'])
    try:
        with open('Relic_Requirements.json', 'r', encoding='utf-8') as f:
            relics = json.load(f)
    except: relics = {}
    return chars, gear, relics

chars_data, gear_data, relic_reqs = load_data()
gear_dict = {item['base_id']: item['name'] for item in gear_data}
char_names = [c['name'] for c in chars_data]

def get_char_by_id(char_id):
    return next((c for c in chars_data if c['base_id'] == char_id), None)

def get_trans(text):
    try: return translator.translate(text)
    except: return text

def format_gear_text(char):
    desc_ru = get_trans(char.get('description', 'Unit'))
    res = f"<b>{char['name']}</b>\n<i>{desc_ru}</i>\n\n"
    for i, level in enumerate(char['gear_levels']):
        items = "\n".join([f"— {gear_dict.get(g, g)}" for g in level['gear']])
        res += f"<b>Tier {i+1}</b>\n<blockquote>{items}</blockquote>\n"
    return res

def format_relic_text(char):
    desc_ru = get_trans(char.get('description', 'Unit'))
    res = f"<b>{char['name']}</b>\n<i>{desc_ru}</i>\n\n<b>Relic Requirements (0-10):</b>\n\n"
    for r, reqs in relic_reqs.items():
        if not reqs:
            res += f"<b>Relic Tier {r}</b>\n<blockquote>Base G13 Status</blockquote>\n"
        else:
            items = "\n".join([f"— {k}: {v}" for k, v in reqs.items()])
            res += f"<b>Relic Tier {r}</b>\n<blockquote>{items}</blockquote>\n"
    return res

def make_kb(char_id, view="gear"):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_conf = types.InlineKeyboardButton("Configuration", callback_data=f"conf_{char_id}")
    toggle_text = "➡️ Relic Tiers" if view == "gear" else "⬅️ Gear Tiers"
    toggle_data = f"relic_{char_id}" if view == "gear" else "gear_{char_id}"
    markup.add(btn_conf, types.InlineKeyboardButton(toggle_text, callback_data=toggle_data))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Write the unit name and tier number (if needed), and I will give you information about its gear.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    raw = message.text.strip().upper()
    parts = raw.split()
    tier_val, is_relic, query = None, False, raw
    
    if len(parts) > 1:
        if parts[-1].startswith('R') and parts[-1][1:].isdigit():
            tier_val, is_relic, query = int(parts[-1][1:]), True, " ".join(parts[:-1])
        elif parts[-1].isdigit():
            tier_val, is_relic, query = int(parts[-1]), False, " ".join(parts[:-1])

    best, score = process.extractOne(query, char_names)
    if score > 60:
        char = next(c for c in chars_data if c['name'] == best)
        desc_ru = get_trans(char.get('description', 'Unit'))
        header = f"<b>{char['name']}</b>\n<i>{desc_ru}</i>\n\n"
        
        if is_relic or tier_val:
            if is_relic:
                r_lvl = str(min(max(tier_val, 0), 10))
                req = relic_reqs.get(r_lvl, {})
                items = "\n".join([f"— {k}: {v}" for k, v in req.items()]) if req else "Base G13 Status"
                caption = f"{header}<b>Relic Tier {r_lvl}</b>\n<blockquote>{items}</blockquote>"
            else:
                t_idx = min(max(tier_val, 1), len(char['gear_levels'])) - 1
                g_list = "\n".join([f"— {gear_dict.get(g, g)}" for g in char['gear_levels'][t_idx]['gear']])
                caption = f"{header}<b>Tier {t_idx + 1}</b>\n<blockquote>{g_list}</blockquote>"
        else:
            caption = format_gear_text(char)

        if len(caption) > 1024:
            bot.send_photo(message.chat.id, char['image'])
            bot.send_message(message.chat.id, caption, parse_mode="HTML", reply_markup=make_kb(char['base_id'], "relic" if is_relic else "gear"))
        else:
            bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="HTML", reply_markup=make_kb(char['base_id'], "relic" if is_relic else "gear"))
    else:
        bot.reply_to(message, "Unit not found. Please try again.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    act, c_id = call.data.split('_', 1)
    char = get_char_by_id(c_id)
    if not char: return
    
    txt = format_relic_text(char) if act == "relic" else format_gear_text(char)
    kb = make_kb(c_id, act)

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
