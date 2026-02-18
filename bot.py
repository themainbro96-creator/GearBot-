import telebot
import json
import difflib
import os
from telebot import types

token = os.environ.get('TOKEN')
bot = telebot.TeleBot(token, parse_mode='MarkdownV2')

def load_data():
    with open('Swgoh_Characters.json', 'r', encoding='utf-8') as f:
        chars_raw = json.load(f)
        chars_list = json.loads(chars_raw['text'])
    
    with open('Swgoh_Gear.json', 'r', encoding='utf-8') as f:
        gear_raw = json.load(f)
        gear_list = json.loads(gear_raw['text'])
    
    gear_map = {item['base_id']: item['name'] for item in gear_list}
    return chars_list, gear_map

characters, gear_dictionary = load_data()

def escape_md(text):
    # Экранируем спецсимволы для MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join('\\' + c if c in escape_chars else c for c in str(text))

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, 'напиши имя юнита и номер тира \(при необходимости\), а я выдам тебе информацию о его снаряжении')

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    msg_parts = message.text.split()
    tier_requested = None
    
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
    
    header = f'*{escape_md(target_name)}*\n'
    header += f'_{escape_md(role)}, {side_emoji} {escape_md(alignment)}_\n\n'
    
    response = header
    for level in char_data['gear_levels']:
        tier = level['tier']
        
        # Фильтр по тиру, если юзер указал конкретный
        if tier_requested and tier != tier_requested:
            continue
            
        tier_label = f'тир {tier}' if tier < 13 else 'Relic'
        response += f'*{tier_label}*\n'
        
        # Формируем блок цитаты через HTML-подобный синтаксис или символ >
        items_list = ""
        for item_id in level['gear']:
            item_name = gear_dictionary.get(item_id, item_id)
            items_list += f'— {escape_md(item_name)}\n'
        
        # В MarkdownV2 цитата делается так:
        response += f'**>** {items_list}\n'

    # Создаем инлайн-кнопку "Поделиться"
    keyboard = types.InlineKeyboardMarkup()
    share_button = types.InlineKeyboardButton(
        text="Поделиться", 
        switch_inline_query=f"{target_name} {tier_requested if tier_requested else ''}"
    )
    keyboard.add(share_button)

    if char_image:
        try:
            bot.send_photo(message.chat.id, char_image, caption=response, reply_markup=keyboard)
        except:
            bot.send_message(message.chat.id, response, reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, response, reply_markup=keyboard)

bot.polling(none_stop=True)
