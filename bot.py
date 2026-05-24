# -*- coding: utf-8 -*-
"""
Replai — WhatsApp бот с polling
Green API + Claude AI
Работает на бесплатном тарифе
"""

import anthropic
import requests
import time
import os
import threading
from flask import Flask, jsonify

# ============================================
# НАСТРОЙКИ
# ============================================
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "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")
GREEN_ID = os.environ.get("GREEN_API_ID", "7107627445")
GREEN_TOKEN = os.environ.get("GREEN_API_TOKEN", "d954efc94a7b4f09ad0dcd944a99eec861e8c53c22e943edb1")
BASE_URL = f"https://7107.api.greenapi.com/waInstance{GREEN_ID}"

SYSTEM = """You are Aika, a friendly assistant for beauty salon Beauty Studio Astana. ALWAYS reply in Russian.

Be warm, use 1-2 emojis. Short replies. Like a good friend.

Salon:
- Address: Astana, Kabanbay batyr 15, 2nd floor
- Phone: +7 707 123-45-67
- Hours: Mon-Sat 9:00-21:00, Sun 10:00-19:00

Services (tenge):
- Manicure classic: 4000
- Manicure gel: 8000
- Pedicure classic: 6000
- Pedicure gel: 10000
- Nail extensions: 15000
- Haircut: 5000
- Root coloring: 12000
- Full coloring: 18000-35000
- Brow lamination: 6000
- Lash extensions: 8000-12000
- Face cleaning: 12000

Masters: Aigerim-nails, Dana-hair, Saule-brows/lashes

When booking collect: service, date+time, name, phone."""

# ============================================

app = Flask(__name__)
claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
conversations = {}
running = True


def receive_notification():
    """Получаем одно уведомление из очереди"""
    url = f"{BASE_URL}/receiveNotification/{GREEN_TOKEN}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data
    except Exception as e:
        print(f"Receive error: {e}")
    return None


def delete_notification(receipt_id):
    """Удаляем уведомление из очереди после обработки"""
    url = f"{BASE_URL}/deleteNotification/{GREEN_TOKEN}/{receipt_id}"
    try:
        requests.delete(url, timeout=10)
    except Exception as e:
        print(f"Delete error: {e}")


def send_message(chat_id, text):
    """Отправляем сообщение"""
    url = f"{BASE_URL}/sendMessage/{GREEN_TOKEN}"
    payload = {"chatId": chat_id, "message": text}
    try:
        r = requests.post(url, json=payload, timeout=15)
        return r.status_code == 200
    except Exception as e:
        print(f"Send error: {e}")
        return False


def get_ai_reply(chat_id, user_message):
    """Получаем ответ от Claude"""
    if chat_id not in conversations:
        conversations[chat_id] = []

    conversations[chat_id].append({"role": "user", "content": user_message})
    history = conversations[chat_id][-20:]

    try:
        response = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=SYSTEM,
            messages=history
        )
        reply = response.content[0].text
        conversations[chat_id].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        print(f"Claude error: {e}")
        return "Извините, ошибка. Позвоните: +7 707 123-45-67"


def process_notification(data):
    """Обрабатываем уведомление"""
    try:
        body = data.get("body", {})
        webhook_type = body.get("typeWebhook", "")

        if webhook_type != "incomingMessageReceived":
            return

        msg_data = body.get("messageData", {})
        if msg_data.get("typeMessage") != "textMessage":
            return

        text = msg_data.get("textMessageData", {}).get("textMessage", "")
        sender = body.get("senderData", {}).get("chatId", "")

        if not text or not sender:
            return

        print(f"IN [{sender[-8:]}]: {text}")

        reply = get_ai_reply(sender, text)
        print(f"OUT: {reply[:60]}")

        send_message(sender, reply)

    except Exception as e:
        print(f"Process error: {e}")


def polling_loop():
    """Основной цикл опроса Green API"""
    print("Polling started...")
    while running:
        try:
            data = receive_notification()
            if data and data.get("receiptId"):
                receipt_id = data["receiptId"]
                process_notification(data)
                delete_notification(receipt_id)
            else:
                time.sleep(2)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(5)


# Flask для Render (нужен чтобы сервис не засыпал)
@app.route("/")
def index():
    return jsonify({"status": "running", "bot": "Beauty Studio Astana"})

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # Запускаем polling в отдельном потоке
    poll_thread = threading.Thread(target=polling_loop, daemon=True)
    poll_thread.start()

    port = int(os.environ.get("PORT", 5000))
    print(f"Replai bot started on port {port}")
    app.run(host="0.0.0.0", port=port)
