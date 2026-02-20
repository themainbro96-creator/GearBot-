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
    return chars, gear

chars_data, gear_data = load_data()
gear_dict = {item['base_id']: item['name'] for item in gear_data}
char_names = [c['name'] for c in chars_data]

def get_side_info(align_id):
    if align_id == 2:
        return "🔵", "Light Side"
    if align_id == 3:
        return "🔴", "Dark Side"
    return "⚪️", "Neutral"

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Write the unit name and tier number (if needed), and I will give you information about its gear.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    parts = text.split()
    
    tier_requested = None
    if len(parts) > 1 and parts[-1].isdigit():
        tier_requested = int(parts[-1])
        search_query = " ".join(parts[:-1])
    else:
        search_query = text

    best_match, score = process.extractOne(search_query, char_names)
    
    if score > 60:
        char = next(c for c in chars_data if c['name'] == best_match)
        role = char.get('description', 'Unit').split(',')[0]
        emoji, side = get_side_info(char.get('alignment'))
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Configuration", callback_data=f"c_{char['base_id']}"))

        header = f"**{char['name']}**\n__{role}, {emoji} {side}__\n\n"

        if tier_requested:
            t_idx = max(1, min(tier_requested, len(char['gear_levels']))) - 1
            g_list = "\n".join([f"— {gear_dict.get(g, g)}" for g in char['gear_levels'][t_idx]['gear']])
            caption = f"{header}**Tier {t_idx + 1}**\n<blockquote>\n{g_list}\n</blockquote>"
            bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="HTML", reply_markup=markup)
        else:
            full_gear_text = header
            for i in range(len(char['gear_levels'])):
                g_list = "\n".join([f"— {gear_dict.get(g, g)}" for g in char['gear_levels'][i]['gear']])
                full_gear_text += f"**Tier {i+1}**\n<blockquote>\n{g_list}\n</blockquote>\n"
            
            # Если текст влезает в лимит подписи к фото (1024), шлем вместе
            if len(full_gear_text) <= 1024:
                bot.send_photo(message.chat.id, char['image'], caption=full_gear_text, parse_mode="HTML", reply_markup=markup)
            else:
                # Если слишком длинно, шлем фото с заголовком, а следом — весь список
                bot.send_photo(message.chat.id, char['image'], caption=header, parse_mode="HTML")
                # Telegram не даст отправить больше 4096 в одном сообщении, на всякий случай дробим
                if len(full_gear_text) > 4000:
                    for x in range(0, len(full_gear_text), 4000):
                        bot.send_message(message.chat.id, full_gear_text[x:x+4000], parse_mode="HTML")
                else:
                    bot.send_message(message.chat.id, full_gear_text, parse_mode="HTML", reply_markup=markup)
    else:
        bot.reply_to(message, "Unit not found.")

app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.remove_webhook()
    bot.infinity_polling()
