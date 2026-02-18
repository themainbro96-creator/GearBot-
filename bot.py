import telebot
import json
import difflib
import os
import sys

# Получаем токен из переменных окружения
TOKEN = os.environ.get('TOKEN')

if not TOKEN:
    print("Ошибка: Переменная TOKEN не найдена в окружении")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode='MarkdownV2')

def load_data():
    try:
        with open('Swgoh_Characters.json', 'r', encoding='utf-8') as f:
            chars_raw = json.load(f)
            chars_list = json.loads(chars_raw['text'])
        
        with open('Swgoh_Gear.json', 'r', encoding='utf-8') as f:
            gear_raw = json.load(f)
            gear_list = json.loads(gear_raw['text'])
        
        gear_map = {item['base_id']: item['name'] for item in gear_list}
        return chars_list, gear_map
    except Exception as e:
        print(f"Ошибка загрузки файлов: {e}")
        return [], {}

characters, gear_dictionary = load_data()

def escape_md(text):
    # Экранируем спецсимволы для MarkdownV2 (кроме > для цитат)
    escape_chars = r'_*[]()~`#+-=|{}.!'
    return ''.join('\\' + c if c in escape_chars else c for c in str(text))

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(
        message.chat.id, 
        'напиши имя юнита и номер тира \(при необходимости\), а я выдам тебе информацию о его снаряжении'
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    msg_parts = message.text.split()
    tier_requested = None
    
    # Проверяем, указан ли тир в конце сообщения
    if msg_parts[-1].isdigit():
        tier_requested = int(msg_parts[-1])
        name_input = ' '.join(msg_parts[:-1])
    else:
        name_input = ' '.join(msg_parts)

    char_names = [c['name'] for c in characters]
    match = difflib.get_close_matches(name_input, char_names, n=1, cutoff=0.5)
    
    if not match:
        bot.send_message(message.chat.id, 'юнит не найден')
        return

    target_name = match[0]
    char_data = next(c for c in characters if c['name'] == target_name)
    
    role = char_data.get('role', 'персонаж')
    alignment = char_data.get('alignment', '')
    char_image = char_data.get('image', '')

    side_emoji = '⚪️'
    if 'Light Side' in alignment: side_emoji = '🔵'
    elif 'Dark Side' in alignment: side_emoji = '🔴'
    
    # Формируем заголовок
    response = f'*{escape_md(target_name)}*\n'
    response += f'_{escape_md(role)}, {side_emoji} {escape_md(alignment)}_\n\n'
    
    slot_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    found_any_tier = False

    for level in char_data['gear_levels']:
        tier = level['tier']
        if tier_requested and tier != tier_requested:
            continue
            
        found_any_tier = True
        tier_label = f'тир {tier}' if tier < 13 else 'Relic'
        response += f'*{escape_md(tier_label)}*\n'
        
        items = level['gear']
        # Начинаем блок цитаты символом > перед каждой строкой предметов
        for i, item_id in enumerate(items):
            item_name = gear_dictionary.get(item_id, item_id)
            num = slot_emojis[i] if i < len(slot_emojis) else "▫️"
            response += f'\>{num} {escape_md(item_name)}\n'
        response += '\n'

    if not found_any_tier:
        bot.send_message(message.chat.id, 'тир не найден')
        return

    final_text = response.strip()

    if char_image:
        try:
            bot.send_photo(message.chat.id, char_image, caption=final_text)
        except Exception:
            bot.send_message(message.chat.id, final_text)
    else:
        bot.send_message(message.chat.id, final_text)

if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
