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
            # Предполагаем, что структура сохранена
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
    # Экранируем спецсимволы для MarkdownV2
    escape_chars = r'_*[]()~`#+-=|{}.!'
    return ''.join('\\' + c if c in escape_chars else c for c in str(text))

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(
        message.chat.id, 
        'Напиши имя юнита и номер тира \(при необходимости\), а я выдам тебе информацию о его снаряжении'
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
        bot.send_message(message.chat.id, 'Юнит не найден')
        return

    target_name = match[0]
    char_data = next(c for c in characters if c['name'] == target_name)
    
    role = char_data.get('role', 'персонаж')
    alignment = char_data.get('alignment', '')
    char_image = char_data.get('image', '')

    side_emoji = '⚪️'
    if 'Light Side' in alignment: side_emoji = '🔵'
    elif 'Dark Side' in alignment: side_emoji = '🔴'
    
    # Формируем основной заголовок
    header = f'*{escape_md(target_name)}*\n'
    header += f'_{escape_md(role)}, {side_emoji} {escape_md(alignment)}_\n\n'
    
    slot_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    found_any_tier = False
    
    # Собираем список всех сообщений (если данных много, они могут не влезть в одну подпись к фото)
    # Но обычно Gear Set персонажа влезает.
    body = ""

    for level in char_data.get('gear_levels', []):
        tier = level['tier']
        if tier_requested and tier != tier_requested:
            continue
            
        found_any_tier = True
        # Тир теперь НЕ жирный
        tier_label = f'тир {tier}' if tier < 13 else 'Relic'
        body += f'{escape_md(tier_label)}\n'
        
        items = level.get('gear', [])
        # Блок цитаты: ставим > в начале каждой строки с предметом
        for i, item_id in enumerate(items):
            item_name = gear_dictionary.get(item_id, item_id)
            num = slot_emojis[i] if i < len(slot_emojis) else "▫️"
            body += f'\>{num} {escape_md(item_name)}\n'
        body += '\n'

    if not found_any_tier:
        bot.send_message(message.chat.id, 'Тир не найден')
        return

    final_text = (header + body).strip()

    # Отправляем фото с текстом. Если текста слишком много (>1024 символа), 
    # Telegram не даст отправить его как подпись, тогда отправим отдельно.
    if char_image:
        try:
            if len(final_text) <= 1024:
                bot.send_photo(message.chat.id, char_image, caption=final_text)
            else:
                # Если текст слишком длинный, шлем фото, а потом текст
                bot.send_photo(message.chat.id, char_image)
                bot.send_message(message.chat.id, final_text)
        except Exception as e:
            print(f"Ошибка при отправке фото: {e}")
            bot.send_message(message.chat.id, final_text)
    else:
        bot.send_message(message.chat.id, final_text)

if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
