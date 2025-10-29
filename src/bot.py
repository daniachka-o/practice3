# bot.py
import os
import telebot
import requests
import logging
from gigachat_client import GigaChatClient

# Load environment variables from .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Create .env with BOT_TOKEN or set env var.")

bot = telebot.TeleBot(BOT_TOKEN)
logging.basicConfig(filename='bot.log', level=logging.INFO)
YANDEX_GEOCODE_API_KEY = os.environ.get('YANDEX_GEOCODE_API_KEY')
YANDEX_GEOCODE_URL = os.environ.get('YANDEX_GEOCODE_URL', 'https://geocode-maps.yandex.ru/1.x/')
YANDEX_WEATHER_API_KEY = os.environ.get('YANDEX_WEATHER_API_KEY')
HOROSCOPE_API_URL = os.environ.get('HOROSCOPE_API_URL', 'https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily')
YANDEX_WEATHER_URL = os.environ.get('YANDEX_WEATHER_URL', 'https://api.weather.yandex.ru/v2/informers')

# Optional: GigaChat client-credentials flow
GIGACHAT_CLIENT_ID = os.environ.get('GIGACHAT_CLIENT_ID')
GIGACHAT_CLIENT_SECRET = os.environ.get('GIGACHAT_CLIENT_SECRET')
GIGACHAT_AUTH_URL = os.environ.get('GIGACHAT_AUTH_URL')
GIGACHAT_URL = os.environ.get('GIGACHAT_URL')
GIGACHAT_MODELS_URL = os.environ.get('GIGACHAT_MODELS_URL')

gigachat_client = None
if GIGACHAT_CLIENT_ID and GIGACHAT_CLIENT_SECRET and GIGACHAT_AUTH_URL and GIGACHAT_URL:
    gigachat_client = GigaChatClient(
        client_id=GIGACHAT_CLIENT_ID,
        client_secret=GIGACHAT_CLIENT_SECRET,
        auth_url=GIGACHAT_AUTH_URL,
        api_url=GIGACHAT_URL,
        models_url=GIGACHAT_MODELS_URL,
        verify_ssl=True,
    )

@bot.message_handler(commands=['старт', 'привет'], content_types=['text'])
def send_welcome(message):
    bot.reply_to(message, "Привет, как дела?")

@bot.message_handler(commands=['гороскоп', 'horoscope'], content_types=['text'])
def sign_handler(message):
    text = ("Какой твой знак зодиака?\nВыбери один: Овен, Телец, Близнецы, Рак, Лев, Дева, Весы, Скорпион, Стрелец, Козерог, Водолей, Рыбы.")
    sent_msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    logging.info(f"User: {message.chat.id}, Text: {message.text}")
    bot.register_next_step_handler(sent_msg, day_handler)

def is_horoscope_context(message) -> bool:
    if not getattr(message, 'text', None):
        return False
    text = message.text.lower()
    zodiac = [
        'овен','телец','близнецы','рак','лев','дева',
        'весы','скорпион','стрелец','козерог','водолей','рыбы'
    ]
    return any(z in text for z in zodiac) or 'horoscope' in text

def is_weather_context(message) -> bool:
    if not getattr(message, 'text', None):
        return False
    text = message.text.lower()
    return 'weather' in text or 'погода' in text

@bot.message_handler(content_types=['text'],
                    func=lambda msg: isinstance(getattr(msg, 'text', None), str)
                    and not msg.text.startswith('/')
                    and not is_horoscope_context(msg) and not is_weather_context(msg))
def llm_reply(message):
    user_query = message.text
    if gigachat_client:
        try:
            resp = gigachat_client.send_chat(user_query)
            answer = resp['choices'][0]['message']['content']
        except Exception as e:
            answer = f"GigaChat error: {e}"
    else:
        answer = "GigaChat не настроен. Обратитесь к администратору."
    bot.reply_to(message, answer)

@bot.message_handler(commands=['weather'], content_types=['text'])
def weather_handler(message):
    sent_msg = bot.send_message(message.chat.id, "Укажите город для прогноза погоды:")
    bot.register_next_step_handler(sent_msg, city_weather)

def city_weather(message):
    city = message.text
    lat, lon = geocode_city(city)
    forecast = get_weather(lat, lon)
    bot.send_message(message.chat.id, f"Погода в {city}: {forecast}")


def day_handler(message):
    sign = message.text
    text = ("Какой день вам нужен?\nВыберите один: СЕГОДНЯ, ЗАВТРА, ВЧЕРА, "
            "или дату в формате ГГГГ-ММ-ДД.")
    sent_msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(sent_msg, fetch_horoscope, sign.capitalize())

def fetch_horoscope(message, sign):
    day = message.text
    horoscope = get_daily_horoscope(sign, day)
    data = horoscope["data"]
    horoscope_message = (
        f'*Horoscope:* {data["horoscope_data"]}\n*Sign:* {sign}\n*Day:* {data["date"]}'
    )
    bot.send_message(message.chat.id, "Вот ваш гороскоп!")
    bot.send_message(message.chat.id, horoscope_message, parse_mode="Markdown")

def get_daily_horoscope(sign: str, day: str) -> dict:
    url = HOROSCOPE_API_URL
    params = {"sign": sign, "day": day}
    response = requests.get(url, params=params)
    return response.json()

def geocode_city(city: str) -> tuple:
    url = YANDEX_GEOCODE_URL
    params = {
        "geocode": city,
        "format": "json",
        "apikey": YANDEX_GEOCODE_API_KEY or ""
    }
    res = requests.get(url, params=params).json()
    pos = res['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']['Point']['pos']
    lon, lat = pos.split()
    return float(lat), float(lon)

def get_weather(lat: float, lon: float) -> str:
    url = YANDEX_WEATHER_URL
    if not YANDEX_WEATHER_API_KEY:
        return "Yandex Weather API key is not configured."
    headers = {"X-Yandex-API-Key": YANDEX_WEATHER_API_KEY}
    params = {"lat": lat, "lon": lon}
    resp = requests.get(url, headers=headers, params=params).json()
    fact = resp['fact']
    weather = f"{fact['temp']}°C, {fact['condition']}"
    return weather

bot.infinity_polling()

