import telebot
import json
import difflib

token = 'ВАШ_ТОКЕН'
bot = telebot.TeleBot(token)

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
    bot.send_message(message.chat.id, 'введи имя персонажа')

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_input = message.text
    char_names = [c['name'] for c in characters]
    
    match = difflib.get_close_matches(user_input, char_names, n=1, cutoff=0.5)
    
    if not match:
        bot.send_message(message.chat.id, 'персонаж не найден')
        return

    target_name = match[0]
    char_data = next(c for c in characters if c['name'] == target_name)
    
    response = f'{target_name}\n\n'
    
    for level in char_data['gear_levels']:
        tier = level['tier']
        items = level['gear']
        
        response += f'тир {tier}\n'
        for item_id in items:
            item_name = gear_dictionary.get(item_id, f'неизвестный предмет {item_id}')
            response += f'— {item_name}\n'
        response += '\n'
    
    if len(response) > 4096:
        for x in range(0, len(response), 4096):
            bot.send_message(message.chat.id, response[x:x+4096])
    else:
        bot.send_message(message.chat.id, response)

bot.polling(none_stop=True)
