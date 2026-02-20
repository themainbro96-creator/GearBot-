import telebot
import json
import os
from flask import Flask
from threading import Thread
from telebot import types
from fuzzywuzzy import process

# Берем токен из секретов Render
TOKEN = os.environ.get('TOKEN')
bot = telebot.TeleBot(TOKEN)

def load_data():
    with open('Swgoh_Characters.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        chars = json.loads(data['text'])
    with open('Swgoh_Gear.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        gear = json.loads(data['text'])
    return chars, gear

chars_data, gear_data = load_data()
gear_dict = {item['base_id']: item['name'] for item in gear_data}
char_names = [c['name'] for c in chars_data]

def get_char_details(char):
    desc = char.get('description', '').lower()
    # Проверка стороны
    if "dark side" in desc:
        emoji, side = "🔴", "Dark Side"
    elif "light side" in desc:
        emoji, side = "🔵", "Light Side"
    else:
        emoji, side = "⚪️", "Neutral"
    
    # Определение роли
    role = "Unit"
    roles = ["Attacker", "Support", "Tank", "Healer", "Leader"]
    for r in roles:
        if r.lower() in desc:
            role = r
            break
            
    return role, emoji, side

def format_gear_list(char, tier_idx):
    gear_ids = char['gear_levels'][tier_idx]['gear']
    items = [gear_dict.get(g_id, f"Unknown ({g_id})") for g_id in gear_ids]
    return " — " + "\n — ".join(items)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "напиши имя юнита и номер тира (при необходимости), а я выдам тебе информацию о его снаряжении")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    parts = text.split()
    
    tier_requested = None
    search_query = text

    # Проверяем, указан ли тир в конце
    if len(parts) > 1 and parts[-1].isdigit():
        tier_requested = int(parts[-1])
        search_query = " ".join(parts[:-1])
    
    best_match, score = process.extractOne(search_query, char_names)
    
    if score > 60:
        char = next(c for c in chars_data if c['name'] == best_match)
        role, side_emoji, side_name = get_char_details(char)
        header = f"<b>{char['name']}</b>\n<i>{role}, {side_emoji} {side_name}</i>\n\n"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Configuration", callback_data=f"conf_{char['base_id']}"))

        if tier_requested:
            # Одиночный тир
            t_idx = max(1, min(tier_requested, 13)) - 1
            gear_list = format_gear_list(char, t_idx)
            full_message = f"{header}<b>Tier {t_idx + 1}</b>\n<blockquote>{gear_list}</blockquote>"
        else:
            # Полная сводка (все 13 тиров)
            full_message = f"{header}<b>Full Gear Summary (Tier 1-13):</b>\n"
            for i in range(13):
                items = [gear_dict.get(g_id, "???") for g_id in char['gear_levels'][i]['gear']]
                # В полной сводке пишем в одну строку для компактности
                full_message += f"<b>T{i+1}:</b> {', '.join(items)}\n\n"

        try:
            # Если сообщение слишком длинное (больше 1024 символов для caption), 
            # отправляем картинку отдельно, а текст отдельно.
            if len(full_message) > 1000:
                bot.send_photo(message.chat.id, char['image'])
                bot.send_message(message.chat.id, full_message, parse_mode="HTML", reply_markup=markup)
            else:
                bot.send_photo(message.chat.id, char['image'], caption=full_message, parse_mode="HTML", reply_markup=markup)
        except Exception as e:
            bot.reply_to(message, "Произошла ошибка при выводе данных. Возможно, персонаж слишком сложный!")
    else:
        bot.reply_to(message, "Юнит не найден. Попробуй еще раз.")

# --- Render Keep-Alive ---
server = Flask('')
@server.route('/')
def home(): return "OK"
def run(): server.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run).start()
    bot.infinity_polling()
