# ==========================================================
# 🤖 AI Trader Assistant by Ali (v2025)
# ==========================================================
import os
import time
import hmac
import json
import hashlib
import requests
from threading import Thread
from datetime import datetime
from dotenv import load_dotenv
from telebot import TeleBot, types
from keep_alive import keep_alive

def quick_symbol_kb(prefix: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"]
    row = []
    for i, sym in enumerate(symbols, 1):
        row.append(types.InlineKeyboardButton(sym.replace("USDT", ""), callback_data=f"{prefix}_{sym}"))
        if i % 2 == 0:
            kb.row(*row); row = []
    if row:
        kb.row(*row)
    return kb

load_dotenv()

API_KEY = os.getenv("MEXC_API_KEY", "")
API_SECRET = os.getenv("MEXC_API_SECRET", "")
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = int(os.getenv("TG_CHAT_ID", "0"))

print("🔍 Проверка переменных:")
print(f"API_KEY: {API_KEY}")
print(f"API_SECRET: {'✓' if API_SECRET else '❌ нет'}")
print(f"TG_TOKEN: {TG_TOKEN}")
print(f"TG_CHAT_ID: {TG_CHAT_ID}")

bot = TeleBot(TG_TOKEN)

BASE_URL = "https://api.mexc.com"
CHECK_INTERVAL_SEC = 600
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0

def send_msg(text: str):
    try:
        bot.send_message(TG_CHAT_ID, text)
    except Exception as e:
        print("Ошибка отправки сообщения:", e)

def mexc_public_get(path, params=None):
    r = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
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

@bot.message_handler(commands=['start'])
def cmd_start(m):
    bot.send_message(m.chat.id, "👋 Привет! Я AI трейдер-ассистент MEXC. Используй /price, /volume, /rsi, /top, /news.")

@bot.message_handler(commands=['price'])
def cmd_price(m):
    parts = m.text.split()
    if len(parts) == 1:
        bot.send_message(m.chat.id, "Выберите монету:", reply_markup=quick_symbol_kb("price"))
        return
    symbol = parts[1].upper() + "USDT" if not parts[1].upper().endswith("USDT") else parts[1].upper()
    try:
        price = get_price(symbol)
        bot.send_message(m.chat.id, f"💱 {symbol} = {price:g} USDT")
    except Exception as e:
        bot.send_message(m.chat.id, f"Ошибка: {e}")

@bot.message_handler(commands=['news'])
def cmd_news(m):
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        data = requests.get(url, timeout=10).json().get("Data", [])[:5]
        if not data:
            bot.send_message(m.chat.id, "❌ Новости не найдены.")
            return
        text = "📰 <b>Последние новости:</b>

" + "\n\n".join([f"{i+1}. <a href='{n['url']}'>{n['title']}</a>" for i,n in enumerate(data)])
        bot.send_message(m.chat.id, text, parse_mode="HTML")
    except Exception as e:
        bot.send_message(m.chat.id, f"Ошибка загрузки новостей: {e}")

def send_startup_report():
    try:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        report = ["📊 Автоотчёт при запуске:"]
        for s in symbols:
            closes = get_klines(s)
            rsi_val = calc_rsi(closes, RSI_PERIOD)
            ticker = mexc_public_get("/api/v3/ticker/24hr", {"symbol": s})
            volume = float(ticker.get("quoteVolume", 0))
            price = float(ticker.get("lastPrice", 0))
            report.append(f"{s}: RSI={rsi_val:.2f} | Vol={volume:,.0f} | Price={price:.2f}")
        send_msg("\n".join(report))
    except Exception as e:
        send_msg(f"Ошибка автоотчёта: {e}")

def main_loop():
    while True:
        time.sleep(CHECK_INTERVAL_SEC)

if __name__ == "__main__":
    keep_alive()
    send_startup_report()
    print("🤖 Бот запущен и слушает команды...")
    Thread(target=main_loop, daemon=True).start()
    bot.polling(none_stop=True)
