import telebot
import json
import difflib
import os

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
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join('\\' + c if c in escape_chars else c for c in str(text))

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
    
    role = char_data.get('role', 'персонаж')
    alignment = char_data.get('alignment', '')
    char_image = char_data.get('image', '')

    # Логика выбора эмодзи стороны
    side_emoji = '⚪️'
    if 'Light Side' in alignment:
        side_emoji = '🔵'
    elif 'Dark Side' in alignment:
        side_emoji = '🔴'
    elif 'Neutral' in alignment:
        side_emoji = '⚪️'
    
    response = f'*{escape_md(target_name)}*\n'
    response += f'_{escape_md(role)}, {side_emoji} {escape_md(alignment)}_\n\n'
    
    found_any_tier = False
    for level in char_data['gear_levels']:
        tier = level['tier']
        if tier_requested and tier != tier_requested:
            continue
            
        found_any_tier = True
        items = level['gear']
        response += f'тир {tier}\n'
        
        gear_text = ''
        for item_id in items:
            item_name = gear_dictionary.get(item_id, item_id)
            gear_text += f'\> {escape_md(item_name)}\n'
        
        response += gear_text + '\n'
    
    if not found_any_tier:
        bot.send_message(message.chat.id, 'тир не найден')
        return

    # Отправляем фото с текстом в подписи
    if char_image:
        try:
            bot.send_photo(message.chat.id, char_image, caption=response.strip())
        except:
            # Если ссылка на фото битая, отправляем просто текст
            bot.send_message(message.chat.id, response.strip())
    else:
        bot.send_message(message.chat.id, response.strip())

bot.polling(none_stop=True)
