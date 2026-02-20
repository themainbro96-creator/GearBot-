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
    except:
        relics = {}
    return chars, gear, relics

chars_data, gear_data, relic_reqs = load_data()
gear_dict = {item['base_id']: item['name'] for item in gear_data}
char_names = [c['name'] for c in chars_data]

def get_char_by_id(char_id):
    return next((c for c in chars_data if c['base_id'] == char_id), None)

def get_side_info(align_id):
    mapping = {2: ("🔵", "Light Side"), 3: ("🔴", "Dark Side")}
    return mapping.get(align_id, ("⚪️", "Neutral"))

def format_gear_text(char):
    emoji, side = get_side_info(char.get('alignment'))
    role = char.get('description', 'Unit').split(',')[0]
    
    text = f"**{char['name']}**\n__{role}, {emoji} {side}__\n\n"
    for i, level in enumerate(char['gear_levels']):
        items = "\n".join([f"— {gear_dict.get(g, g)}" for g in level['gear']])
        text += f"**Tier {i+1}**\n<blockquote>{items}</blockquote>\n"
    return text

def format_relic_text(char):
    emoji, side = get_side_info(char.get('alignment'))
    role = char.get('description', 'Unit').split(',')[0]
    
    text = f"**{char['name']}**\n__{role}, {emoji} {side}__\n\n"
    text += "**Relic Requirements (0-10):**\n\n"
    for r, reqs in relic_reqs.items():
        if not reqs:
            text += f"**Relic Tier {r}**: __Base G13__\n"
        else:
            items = ", ".join([f"{k} x{v}" for k, v in reqs.items()])
            text += f"**Relic Tier {r}**:\n<blockquote>{items}</blockquote>\n"
    return text

def make_keyboard(char_id, current_view="gear"):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_conf = types.InlineKeyboardButton("Configuration", callback_data=f"conf_{char_id}")
    
    if current_view == "gear":
        btn_toggle = types.InlineKeyboardButton("➡️ Relic Tiers", callback_data=f"relic_{char_id}")
    else:
        btn_toggle = types.InlineKeyboardButton("⬅️ Gear Tiers", callback_data=f"gear_{char_id}")
    
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
        char = get_char_by_id(next(c['base_id'] for c in chars_data if c['name'] == best_match))
        
        if is_relic or tier_val:
            emoji, side = get_side_info(char.get('alignment'))
            role = char.get('description', 'Unit').split(',')[0]
            header = f"**{char['name']}**\n__{role}, {emoji} {side}__\n\n"
            
            if is_relic:
                r_lvl = str(min(max(tier_val, 0), 10))
                req = relic_reqs.get(r_lvl, {})
                items = "\n".join([f"— {k}: {v}" for k, v in req.items()]) if req else "Base G13 Status"
                caption = f"{header}**Relic Tier {r_lvl}**\n<blockquote>{items}</blockquote>"
            else:
                t_idx = min(max(tier_val, 1), len(char['gear_levels'])) - 1
                g_list = "\n".join([f"— {gear_dict.get(g, g)}" for g in char['gear_levels'][t_idx]['gear']])
                caption = f"{header}**Tier {t_idx + 1}**\n<blockquote>{g_list}</blockquote>"
            
            bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="HTML", reply_markup=make_keyboard(char['base_id'], "relic" if is_relic else "gear"))
        else:
            # Полная сводка (Gear по умолчанию)
            caption = format_gear_text(char)
            if len(caption) > 1024:
                # Если текст слишком длинный, шлем фото с кратким описанием и текст отдельно
                short_h = f"**{char['name']}**\nFull Gear Report below:"
                bot.send_photo(message.chat.id, char['image'], caption=short_h, parse_mode="HTML")
                bot.send_message(message.chat.id, caption, parse_mode="HTML", reply_markup=make_keyboard(char['base_id'], "gear"))
            else:
                bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="HTML", reply_markup=make_keyboard(char['base_id'], "gear"))
    else:
        bot.reply_to(message, "Unit not found.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    data = call.data.split('_')
    action = data[0]
    char_id = "_".join(data[1:])
    char = get_char_by_id(char_id)
    
    if not char:
        return

    if action == "relic":
        new_caption = format_relic_text(char)
        new_markup = make_keyboard(char_id, "relic")
    elif action == "gear":
        new_caption = format_gear_text(char)
        new_markup = make_keyboard(char_id, "gear")
    else:
        return

    # Редактируем сообщение (подпись к фото или просто текст)
    try:
        if len(new_caption) > 1024 and call.message.photo:
            # Если текст стал слишком длинным для подписи, мы не можем его отредактировать в PhotoMessage
            # Поэтому просто уведомляем или присылаем новым сообщением (редкий случай для реликвий)
            bot.answer_callback_query(call.id, "Text is too long to display here.")
        else:
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=new_caption,
                parse_mode="HTML",
                reply_markup=new_markup
            )
    except Exception:
        # Если это было обычное текстовое сообщение (когда отчет очень длинный)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=new_caption,
            parse_mode="HTML",
            reply_markup=new_markup
        )

app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.remove_webhook()
    bot.infinity_polling()
