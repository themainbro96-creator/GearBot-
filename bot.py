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
    # Загрузка и распаковка JSON (учитывая структуру {"text": "[...]"})
    with open('Swgoh_Characters.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        chars = json.loads(data['text'])
    
    with open('Swgoh_Gear.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        gear = json.loads(data['text'])
        
    return chars, gear

chars_data, gear_data = load_data()
# Словарь для быстрого поиска названий снаряжения
gear_dict = {item['base_id']: item['name'] for item in gear_data}
# Список имен для поиска совпадений
char_names = [c['name'] for c in chars_data]

def get_char_info(char):
    desc = char.get('description', '').lower()
    # Определяем сторону по описанию (в SWGOH API это обычно там)
    if "dark side" in desc:
        emoji, side = "🔴", "Dark Side"
    elif "light side" in desc:
        emoji, side = "🔵", "Light Side"
    else:
        emoji, side = "⚪️", "Neutral"
    
    # Роль (обычно первое слово в описании или можно вытащить из данных)
    role = "Unit"
    if "attacker" in desc: role = "Attacker"
    elif "support" in desc: role = "Support"
    elif "tank" in desc: role = "Tank"
    elif "healer" in desc: role = "Healer"
    
    return role, emoji, side

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "напиши имя юнита и номер тира (при необходимости), а я выдам тебе информацию о его снаряжении")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip()
    
    # Логика: отделяем имя от номера тира (например, "Fennec 8")
    parts = text.split()
    tier = 1 # по умолчанию 1 тир
    search_query = text

    if len(parts) > 1 and parts[-1].isdigit():
        tier = int(parts[-1])
        search_query = " ".join(parts[:-1])
    
    # Поиск самого похожего имени
    best_match, score = process.extractOne(search_query, char_names)
    
    if score > 60: # Если совпадение больше 60%
        char = next(c for c in chars_data if c['name'] == best_match)
        
        # Ограничиваем тир от 1 до 13
        tier = max(1, min(tier, 13))
        gear_ids = char['gear_levels'][tier-1]['gear']
        
        role, side_emoji, side_name = get_char_info(char)
        
        # Собираем список снаряжения
        gear_list_str = ""
        for g_id in gear_ids:
            name = gear_dict.get(g_id, f"Unknown Gear ({g_id})")
            gear_list_str += f"— {name}\n"

        # Формируем HTML сообщение (blockquote работает только в HTML)
        caption = (
            f"<b>{char['name']}</b>\n"
            f"<i>{role}, {side_emoji} {side_name}</i>\n\n"
            f"<blockquote>"
            f"{gear_list_str.strip()}"
            f"</blockquote>"
        )

        # Кнопка
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Configuration", callback_data=f"conf_{char['base_id']}"))

        # Отправка фото с описанием
        try:
            bot.send_photo(
                message.chat.id,
                char['image'],
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup
            )
        except Exception as e:
            bot.reply_to(message, f"Ошибка при отправке данных: {e}")
    else:
        bot.reply_to(message, "Юнит не найден. Попробуй написать точнее (на английском).")

# --- Секция для Render (Keep Alive) ---
server = Flask('')

@server.route('/')
def home():
    return "Bot is running"

def run():
    server.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    # Запускаем фласк в отдельном потоке
    Thread(target=run).start()
    print("Бот запущен...")
    bot.infinity_polling()
