import telebot
import json
import os
from flask import Flask
from threading import Thread
from telebot import types
from fuzzywuzzy import process

# Токен из секретов Render
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

def get_char_info(char):
    # Точное определение стороны по полю alignment
    # 2 - Light, 3 - Dark, остальные - Neutral
    align = char.get('alignment', 1)
    if align == 2:
        emoji, side = "🔵", "Light Side"
    elif align == 3:
        emoji, side = "🔴", "Dark Side"
    else:
        emoji, side = "⚪️", "Neutral"
    
    # Роль (берем из description, так как там "Attacker", "Support" и т.д.)
    desc = char.get('description', 'Unit')
    role = desc.split()[0].replace(',', '') # Берем первое слово
    return role, emoji, side

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "напиши имя юнита и номер тира (при необходимости), а я выдам тебе информацию о его снаряжении")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    parts = text.split()
    
    tier_requested = None
    search_query = text

    # Если последнее слово - число, значит это запрос конкретного тира
    if len(parts) > 1 and parts[-1].isdigit():
        tier_requested = int(parts[-1])
        search_query = " ".join(parts[:-1])
    
    # Поиск персонажа
    best_match, score = process.extractOne(search_query, char_names)
    
    if score > 60:
        char = next(c for c in chars_data if c['name'] == best_match)
        role, side_emoji, side_name = get_char_info(char)
        
        base_header = f"*{char['name']}*\n_{role}, {side_emoji} {side_name}_"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Configuration", callback_data=f"c_{char['base_id']}"))

        if tier_requested:
            # СТРОГО ОДИН ТИР
            t_idx = max(1, min(tier_requested, 13)) - 1
            gear_ids = char['gear_levels'][t_idx]['gear']
            gear_list = "\n".join([f"— {gear_dict.get(g_id, g_id)}" for g_id in gear_ids])
            
            caption = f"{base_header}\n\n<blockquote>{gear_list}</blockquote>"
            bot.send_photo(message.chat.id, char['image'], caption=caption, parse_mode="HTML", reply_markup=markup)
        
        else:
            # ВСЕ ТИРЫ (Full Summary)
            bot.send_photo(message.chat.id, char['image'], caption=base_header, parse_mode="HTML")
            
            full_summary = ""
            for i in range(13):
                g_ids = char['gear_levels'][i]['gear']
                items = [gear_dict.get(g_id, "???") for g_id in g_ids]
                tier_text = f"<b>Tier {i+1}:</b>\n— " + "\n— ".join(items) + "\n\n"
                
                # Telegram лимит 4096 символов, если текст длинный — дробим
                if len(full_summary) + len(tier_text) > 3800:
                    bot.send_message(message.chat.id, full_summary, parse_mode="HTML")
                    full_summary = ""
                full_summary += tier_text
            
            bot.send_message(message.chat.id, full_summary, parse_mode="HTML", reply_markup=markup)
    else:
        bot.reply_to(message, "Юнит не найден.")

# --- Render Keep-Alive ---
server = Flask('')
@server.route('/')
def home(): return "OK"
def run(): server.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.remove_webhook()
    print("Бот запущен...")
    bot.infinity_polling()
