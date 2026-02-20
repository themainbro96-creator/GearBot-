import telebot
import json
import os
from flask import Flask
from threading import Thread
from telebot import types
from fuzzywuzzy import process

TOKEN = os.environ.get('TOKEN')
bot = telebot.TeleBot(TOKEN)

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

def get_char_header(char):
    role = char.get('description', 'Unit').split(',')[0]
    align = char.get('alignment', 1)
    mapping = {2: ("🔵", "Light Side"), 3: ("🔴", "Dark Side")}
    emoji, side = mapping.get(align, ("⚪️", "Neutral"))
    return f"**{char['name']}**\n__{role}, {emoji} {side}__"

def make_keyboard(char_id, show_relics=False):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_conf = types.InlineKeyboardButton("Configuration", callback_data=f"conf_{char_id}")
    if show_relics:
        btn_toggle = types.InlineKeyboardButton("⬅️ Gear Tiers", callback_data=f"show_gear_{char_id}")
    else:
        btn_toggle = types.InlineKeyboardButton("➡️ Relic Tiers", callback_data=f"show_relic_{char_id}")
    markup.add(btn_conf, btn_toggle)
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Write the unit name and tier/relic (e.g. Leia 12 or Leia R7).")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip().upper()
    parts = text.split()
    
    tier_val, is_relic = None, False
    if len(parts) > 1:
        last = parts[-1]
        if last.startswith('R') and last[1:].isdigit():
            tier_val, is_relic, search_query = int(last[1:]), True, " ".join(parts[:-1])
        elif last.isdigit():
            tier_val, is_relic, search_query = int(last), False, " ".join(parts[:-1])
        else: search_query = text
    else: search_query = text

    best_match, score = process.extractOne(search_query, char_names)
    if score > 60:
        char = next(c for c in chars_data if c['name'] == best_match)
        header = get_char_header(char)
        
        if is_relic or tier_val:
            if is_relic:
                r_lvl = str(min(max(tier_val, 0), 10))
                req = relic_reqs.get(r_lvl, {})
                items = "\n".join([f"— {k}: {v}" for k, v in req.items()]) if req else "No additional resources (Base G13)"
                res = f"{header}\n\n**Relic Tier {r_lvl}**\n<blockquote>\n{items}\n</blockquote>"
            else:
                t_idx = min(max(tier_val, 1), len(char['gear_levels'])) - 1
                items = "\n".join([f"— {gear_dict.get(g, g)}" for g in char['gear_levels'][t_idx]['gear']])
                res = f"{header}\n\n**Tier {t_idx + 1}**\n<blockquote>\n{items}\n</blockquote>"
            bot.send_photo(message.chat.id, char['image'], caption=res, parse_mode="HTML", reply_markup=make_keyboard(char['base_id'], is_relic))
        else:
            # Сводка всех тиров
            full_text = header + "\n\n"
            for i, level in enumerate(char['gear_levels']):
                items = "\n".join([f"— {gear_dict.get(g, g)}" for g in level['gear']])
                full_text += f"**Tier {i+1}**\n<blockquote>\n{items}\n</blockquote>\n"
            
            if len(full_text) <= 1024:
                bot.send_photo(message.chat.id, char['image'], caption=full_text, parse_mode="HTML", reply_markup=make_keyboard(char['base_id']))
            else:
                bot.send_photo(message.chat.id, char['image'], caption=header, parse_mode="HTML")
                bot.send_message(message.chat.id, full_text, parse_mode="HTML", reply_markup=make_keyboard(char['base_id']))
    else:
        bot.reply_to(message, "Unit not found.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    action, char_id = call.data.split('_', 1)
    char = next((c for c in chars_data if c['base_id'] == char_id), None)
    if not char: return

    header = get_char_header(char)
    if action == "show_relic":
        res = f"{header}\n\n**Relic Tiers (0-10)**\n"
        for r, items in relic_reqs.items():
            content = ", ".join([f"{k} x{v}" for k, v in items.items()]) if items else "Base status"
            res += f"**R{r}**: {content}\n\n"
        bot.edit_message_caption(res, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=make_keyboard(char_id, True))
    
    elif action == "show_gear":
        # Возвращаем краткую сводку или последний тир
        res = f"{header}\n\n**Gear Tiers 1-12**\n(Send unit name to see full list)"
        bot.edit_message_caption(res, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=make_keyboard(char_id, False))

app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.remove_webhook()
    bot.infinity_polling()
