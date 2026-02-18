import telebot
import json
import difflib
import os

token = os.environ.get('TOKEN')
bot = telebot.TeleBot(token, parse_mode='Markdown')

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

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, 'введи имя персонажа и номер тира')

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.split()
    tier_requested = None
    
    if text[-1].isdigit():
        tier_requested = int(text[-1])
        name_input = ' '.join(text[:-1])
    else:
        name_input = ' '.join(text)

    char_names = [c['name'] for c in characters]
    match = difflib.get_close_matches(name_input, char_names, n=1, cutoff=0.5)
    
    if not match:
        bot.send_message(message.chat.id, 'персонаж не найден')
        return

    target_name = match[0]
    char_data = next(c for c in characters if c['name'] == target_name)
    
    # Достаем роль и сторону (если их нет в JSON, ставим прочерк)
    role = char_data.get('role', 'персонаж')
    alignment = char_data.get('alignment', '')
    
    response = f'*{target_name}*\n'
    response += f'_{role}, {alignment}_\n\n'
    
    found_any_tier = False
    for level in char_data['gear_levels']:
        tier = level['tier']
        if tier_requested and tier != tier_requested:
            continue
            
        found_any_tier = True
        items = level['gear']
        response += f'тир {tier}\n'
        
        # Начало цитаты (blockquote в Markdown V2 или просто > в обычном)
        gear_text = ''
        for item_id in items:
            item_name = gear_dictionary.get(item_id, item_id)
            gear_text += f'— {item_name}\n'
        
        # Оформляем список предметов как цитату
        response += f'> {gear_text}\n'
    
    if not found_any_tier and tier_requested:
        bot.send_message(message.chat.id, f'тир {tier_requested} не найден')
        return

    bot.send_message(message.chat.id, response.strip())

bot.polling(none_stop=True)
