# ==========================================================
# 🤖 AI Trader Assistant by Ali (v2025)
# ==========================================================
# Упрощённая и структурированная версия с разделением по логическим блокам.
# ==========================================================

# ----------------------------------------------------------
# 1️⃣ Импорт библиотек
# ----------------------------------------------------------
import os
import time
import hmac
import json
import hashlib
import requests
import psutil
from threading import Thread
from datetime import datetime, timezone
from dotenv import load_dotenv
from telebot import TeleBot, types
from keep_alive import keep_alive

# Быстрый выбор монеты для команд /price /volume /rsi
def quick_symbol_kb(prefix: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"]
    # по две кнопки в ряд
    row = []
    for i, sym in enumerate(symbols, 1):
        row.append(types.InlineKeyboardButton(sym.replace("USDT", ""), callback_data=f"{prefix}_{sym}"))
        if i % 2 == 0:
            kb.row(*row); row = []
    if row:
        kb.row(*row)
    return kb

# ----------------------------------------------------------
# 2️⃣ Загрузка .env и проверка переменных
# ----------------------------------------------------------
load_dotenv(dotenv_path=r"C:\Users\Acer\Desktop\my_project\bot_mind_railway\.env")

API_KEY = os.getenv("MEXC_API_KEY", "")
API_SECRET = os.getenv("MEXC_API_SECRET", "")
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = int(os.getenv("TG_CHAT_ID", "0"))

print("🔍 Проверка переменных:")
print(f"API_KEY: {API_KEY}")
print(f"API_SECRET: {'✓' if API_SECRET else '❌ нет'}")
print(f"TG_TOKEN: {TG_TOKEN}")
print(f"TG_CHAT_ID: {TG_CHAT_ID}")

# ----------------------------------------------------------
# 3️⃣ Инициализация бота и клавиатуры
# ----------------------------------------------------------
bot = TeleBot(TG_TOKEN)
main_menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.row("/news", "/price")
main_menu.row("/volume", "/rsi")
main_menu.row("/top", "/about")


# ----------------------------------------------------------
# 4️⃣ Константы и параметры анализа
# ----------------------------------------------------------
BASE_URL = "https://api.mexc.com"
STATE_FILE = "state.json"
CHECK_INTERVAL_SEC = 600
PRICE_MOVE_THRESHOLD = 3.0
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
MIN_ASSET_AMOUNT = 0.0000001
EXTRA_WATCHLIST = ["BTCUSDT", "ETHUSDT"]

# ----------------------------------------------------------
# 5️⃣ Вспомогательные функции
# ----------------------------------------------------------
def send_msg(text: str):
    """Отправка сообщения в Telegram."""
    if bot and TG_CHAT_ID:
        try:
            bot.send_message(TG_CHAT_ID, text)
        except Exception as e:
            print("Не удалось отправить сообщение в Telegram:", e)
    else:
        print("[TG]", text)


def mexc_public_get(path, params=None):
    r = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def mexc_signed_get(path, params=None):
    if params is None:
        params = {}
    params["timestamp"] = int(time.time() * 1000)
    query = "&".join([f"{k}={params[k]}" for k in sorted(params)])
    signature = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    headers = {"X-MEXC-APIKEY": API_KEY}
    r = requests.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def get_price(symbol: str) -> float:
    data = mexc_public_get("/api/v3/ticker/price", {"symbol": symbol})
    return float(data["price"])


def get_klines(symbol: str, interval="15m", limit=200) -> list[float]:
    data = mexc_public_get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    return [float(k[4]) for k in data]


def calc_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain, avg_loss = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i-1]
        avg_gain = (avg_gain * (period - 1) + max(diff, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0)) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def normalize_symbol(t: str) -> str:
    t = t.strip().upper()
    return t if t.endswith("USDT") else f"{t}USDT"

# ----------------------------------------------------------
# 6️⃣ Команды Telegram
# ----------------------------------------------------------
@bot.message_handler(commands=['start'])
def cmd_start(m):
    bot.send_message(
        m.chat.id,
        "👋 Привет! Я ассистент трейдера MEXC.\n"
        "Я могу показывать цены, RSI, объёмы и отслеживать активы.\n\n"
       "📘 Доступные команды:\n"
       "/news — последние новости крипторынка\n"
       "/price BTC — цена монеты\n"
       "/volume BTC — объём торгов 24ч\n"
       "/rsi BTC — RSI индикатор\n"
       "/top — топ-5 монет по объёму\n"
       "/about — информация о проекте",
       reply_markup=main_menu

    )
# ==========================================================
# 📰 Новости крипторынка (устойчивый источник)
# ==========================================================
@bot.message_handler(commands=['news'])
def cmd_news(m):
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        response = requests.get(url, timeout=10)
        articles = response.json().get("Data", [])[:5]

        if not articles:
            send_msg("❌ Не удалось получить новости. Попробуй позже.")
            return

        text_lines = ["📰 <b>Последние новости крипторынка:</b>\n"]
        for i, item in enumerate(articles, 1):
            title = item.get("title", "Без заголовка")
            link = item.get("url", "")
            text_lines.append(f"{i}. <a href='{link}'>{title}</a>")

        bot.send_message(m.chat.id, "\n\n".join(text_lines), parse_mode="HTML")

    except Exception as e:
        send_msg(f"⚠️ Ошибка при загрузке новостей: {e}")


# ----------------------------------------------------------
# 6.1️⃣ Команды Telegram (основные)
# ----------------------------------------------------------

@bot.message_handler(commands=['price'])
def cmd_price(m):
    parts = m.text.split()
    if len(parts) == 1:
        bot.send_message(
            m.chat.id,
            "Выберите монету или введите, например: /price BTC",
            reply_markup=quick_symbol_kb("price")
        )
        return
    symbol = normalize_symbol(parts[1])
    try:
        price = get_price(symbol)
        bot.send_message(m.chat.id, f"💱 {symbol} = {price:g} USDT")
    except Exception as e:
        bot.send_message(m.chat.id, f"Не удалось получить цену для {symbol}: {e}")


@bot.message_handler(commands=['volume'])
def cmd_volume(m):
    parts = m.text.split()
    if len(parts) == 1:
        bot.send_message(
            m.chat.id,
            "Выберите монету или введите, например: /volume BTC",
            reply_markup=quick_symbol_kb("volume")
        )
        return
    symbol = normalize_symbol(parts[1])
    try:
        stats = mexc_public_get("/api/v3/ticker/24hr", {"symbol": symbol})
        vol = float(stats.get("volume", 0.0))
        qvol = float(stats.get("quoteVolume", 0.0))
        last = float(stats.get("lastPrice", 0.0))
        bot.send_message(m.chat.id, f"📊 Объём 24h {symbol}\nVolume: {vol:g}\nQuoteVolume (USDT): {qvol:g}\nLast: {last:g}")
    except Exception as e:
        bot.send_message(m.chat.id, f"Не удалось получить объём для {symbol}: {e}")


@bot.message_handler(commands=['rsi'])
def cmd_rsi(m):
    parts = m.text.split()
    if len(parts) == 1:
        bot.send_message(
            m.chat.id,
            "Выберите монету для расчёта RSI:",
            reply_markup=quick_symbol_kb("rsi")
        )
        return
    symbol = normalize_symbol(parts[1])
    try:
        closes = get_klines(symbol, interval="15m", limit=200)
        rsi_val = calc_rsi(closes, RSI_PERIOD)
        bot.send_message(m.chat.id, f"📈 RSI({RSI_PERIOD}) для {symbol}: {rsi_val:.2f}")
    except Exception as e:
        bot.send_message(m.chat.id, f"Ошибка получения RSI для {symbol}: {e}")



@bot.message_handler(commands=["volume"])
def cmd_volume(m):
    """Показывает объём торгов за 24 часа"""
    parts = m.text.split()
    if len(parts) == 1:
        bot.send_message(m.chat.id, "⚠️ Укажите монету. Пример: /volume BTC", reply_markup=main_menu)

        return

    symbol = normalize_symbol(parts[1])
    try:
        data = mexc_public_get("/api/v3/ticker/24hr", {"symbol": symbol})
        vol = float(data["quoteVolume"])
        bot.send_message(m.chat.id, f"💹 Объём {symbol} за 24ч: {vol:,.0f} USDT")
    except Exception as e:
        bot.send_message(m.chat.id, f"Ошибка получения объёма для {symbol}: {e}")
@bot.callback_query_handler(func=lambda c: c.data.startswith(("price_", "volume_", "rsi_")))
def on_symbol_quickpick(c):
    try:
        kind, symbol = c.data.split("_", 1)  # kind: price|volume|rsi
        if kind == "price":
            price = get_price(symbol)
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, f"💱 {symbol} = {price:g} USDT")
        elif kind == "volume":
            stats = mexc_public_get("/api/v3/ticker/24hr", {"symbol": symbol})
            vol = float(stats.get("volume", 0.0))
            qvol = float(stats.get("quoteVolume", 0.0))
            last = float(stats.get("lastPrice", 0.0))
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, f"📊 Объём 24h {symbol}\nVolume: {vol:g}\nQuoteVolume (USDT): {qvol:g}\nLast: {last:g}")
        elif kind == "rsi":
            closes = get_klines(symbol, interval="15m", limit=200)
            rsi_val = calc_rsi(closes, RSI_PERIOD)
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, f"📈 RSI({RSI_PERIOD}) для {symbol}: {rsi_val:.2f}")
    except Exception as e:
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, f"Ошибка обработки запроса: {e}")


@bot.message_handler(commands=["top"])
def cmd_top(m):
    """Показывает топ-5 монет по объёму торгов"""
    try:
        data = mexc_public_get("/api/v3/ticker/24hr")
        sorted_data = sorted(data, key=lambda x: float(x["quoteVolume"]), reverse=True)
        top5 = sorted_data[:5]
        msg = ["🏆 Топ-5 монет по объёму за 24 ч:"]
        for i, s in enumerate(top5, 1):
            sym = s["symbol"]
            vol = float(s["quoteVolume"])
            price = float(s["lastPrice"])
            msg.append(f"{i}. {sym}: {vol:,.0f} USDT @ {price:.4f}")
        bot.send_message(m.chat.id, "\n".join(msg))
    except Exception as e:
        bot.send_message(m.chat.id, f"Ошибка получения топ-монет: {e}")


@bot.message_handler(commands=["about"])
def cmd_about(m):
    bot.send_message(
        m.chat.id,
        "🤖 AI Trader Assistant by Ali (2025)\n"
        "Следит за RSI, ценой и объёмами на MEXC.\n"
        "Разработчик: Али 👨‍💻",
    )

# ----------------------------------------------------------
# 7️⃣ Основной цикл
# ----------------------------------------------------------
def main_loop():
    send_msg("✅ Ассистент трейдера запущен.")
    while True:
        time.sleep(CHECK_INTERVAL_SEC)
# ==========================================================


# ==========================================================
# 📊 Автоотчёт при запуске (RSI + объём 24ч)
# ==========================================================
def send_startup_report():
    try:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        lines = ["📊 Автоотчёт при запуске:\n"]
        for sym in symbols:
            # --- RSI ---
            closes = get_klines(sym, interval="15m", limit=200)
            rsi_val = calc_rsi(closes, RSI_PERIOD)
            # --- Объём 24ч ---
            ticker = mexc_public_get("/api/v3/ticker/24hr", {"symbol": sym})
            volume = float(ticker["quoteVolume"])
            price = float(ticker["lastPrice"])
            lines.append(f"{sym}: RSI={rsi_val:.2f} | Vol={volume:,.0f} USDT | Price={price:.4f}")
        send_msg("\n".join(lines))
    except Exception as e:
        send_msg(f"⚠️ Ошибка при автоотчёте: {e}")

# ==========================================================
# 🚀 Точка входа
# ==========================================================
if __name__ == "__main__":
    keep_alive()
    send_startup_report()  # 👆 Автоотчёт при запуске
    print("🤖 Telegram-бот запущен и слушает команды...")
    bg_thread = Thread(target=main_loop, daemon=True)
    bg_thread.start()
    bot.polling(none_stop=True, interval=1)
# ==========================================================
# 🌐 Flask Keep-Alive Server (для Railway)
# ==========================================================
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

flask_thread = Thread(target=run_flask, daemon=True)
flask_thread.start()

