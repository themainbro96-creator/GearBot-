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

def get_alignment_data(alignment_id):
    if alignment_id == 2:
        return "🔵", "Light Side"
    elif alignment_id == 3:
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
        emoji, side = get_alignment_data(char.get('alignment'))
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Configuration", callback_data=f"config_{char['base_id']}"))

        if tier_requested:
            t_idx = max(1, min(tier_requested, len(char['gear_levels']))) - 1
            gear_ids = char['gear_levels'][t_idx]['gear']
            items = "\n".join([f"— {gear_dict.get(g, g)}" for g in gear_ids])
            
            caption = (
                f"**{char['name']}**\n"
                f"__{role}, {emoji} {side}__\n\n"
                f"**Tier {t_idx + 1}**\n"
                f"<blockquote>\n{items}\n</blockquote>"
            )
            bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="MarkdownV2" if "<blockquote>" not in caption else "HTML", reply_markup=markup)
            
            # В Telegram MarkdownV2 не дружит с blockquote, поэтому дублируем чистым HTML для надежности
            final_html = (
                f"<b>{char['name']}</b>\n"
                f"<i>{role}, {emoji} {side}</i>\n\n"
                f"<b>Tier {t_idx + 1}</b>\n"
                f"<blockquote>{items}</blockquote>"
            )
            bot.edit_message_caption(chat_id=message.chat.id, message_id=message.id+1, caption=final_html, parse_mode="HTML", reply_markup=markup)
        else:
            bot.send_photo(message.chat.id, char['image'], caption=f"<b>{char['name']}</b>\n<i>{role}, {emoji} {side}</i>", parse_mode="HTML")
            
            full_report = ""
            for i in range(len(char['gear_levels'])):
                gear_ids = char['gear_levels'][i]['gear']
                items = "\n".join([f"— {gear_dict.get(g, g)}" for g in gear_ids])
                tier_block = f"<b>Tier {i+1}</b>\n<blockquote>{items}</blockquote>\n"
                
                if len(full_report) + len(tier_block) > 4000:
                    bot.send_message(message.chat.id, full_report, parse_mode="HTML")
                    full_report = ""
                full_report += tier_block
            
            bot.send_message(message.chat.id, full_report, parse_mode="HTML", reply_markup=markup)
    else:
        bot.reply_to(message, "Unit not found. Please try again.")

app = Flask('')
@app.route('/')
def home(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.remove_webhook()
    bot.infinity_polling()
