# -*- coding: utf-8 -*-
"""
Replai — универсальный WhatsApp бот
Green API + Claude AI
"""

from flask import Flask, request, jsonify
import anthropic
import requests
import json
import os

# ============================================
# НАСТРОЙКИ
# ============================================
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "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")
GREEN_API_ID = os.environ.get("GREEN_API_ID", "7107627445")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN", "d954efc94a7b4f09ad0dcd944a99eec861e8c53c22e943edb1")
GREEN_API_URL = f"https://7107.api.greenapi.com"

# ============================================
# НАСТРОЙКИ БИЗНЕСА — меняй под каждого клиента
# ============================================
BUSINESS = {
    "name": "Beauty Studio Astana",
    "type": "салон красоты",
    "address": "Астана, ул. Кабанбай батыра, 15, 2 этаж",
    "phone": "+7 (707) 123-45-67",
    "hours": "Пн-Сб: 9:00-21:00, Вс: 10:00-19:00",
    "services": """
- Маникюр классический — 4 000 ₸
- Маникюр + гель-лак — 8 000 ₸
- Педикюр классический — 6 000 ₸
- Педикюр + гель-лак — 10 000 ₸
- Наращивание ногтей — 15 000 ₸
- Стрижка женская — 5 000 ₸
- Окрашивание (корни) — 12 000 ₸
- Окрашивание (полное) — 18 000-35 000 ₸
- Ламинирование бровей — 6 000 ₸
- Наращивание ресниц (классика) — 8 000 ₸
- Наращивание ресниц (объём) — 12 000 ₸
- Чистка лица — 12 000 ₸
""",
    "extra": "Мастера: Айгерим (ногти), Дана (волосы), Сауле (брови и ресницы)"
}

SYSTEM_PROMPT = f"""Ты — дружелюбный AI-ассистент {BUSINESS['type']} «{BUSINESS['name']}».

Общайся тепло и по-дружески, используй 1-2 эмодзи. Пиши коротко и по делу.
Никогда не говори как робот — только живой разговорный стиль.

ИНФОРМАЦИЯ:
📍 {BUSINESS['address']}
📞 {BUSINESS['phone']}
🕐 {BUSINESS['hours']}

УСЛУГИ И ЦЕНЫ:
{BUSINESS['services']}

{BUSINESS['extra']}

ТВОИ ЗАДАЧИ:
1. Отвечать на вопросы об услугах и ценах
2. Помогать записаться — спрашивай: услугу, дату/время, имя, телефон
3. Если не знаешь ответа — предложи позвонить: {BUSINESS['phone']}

Всегда отвечай на русском языке."""

# ============================================

app = Flask(__name__)
claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
conversations = {}


def send_message(chat_id, text):
    """Отправляем сообщение через Green API"""
    url = f"{GREEN_API_URL}/waInstance{GREEN_API_ID}/sendMessage/{GREEN_API_TOKEN}"
    payload = {
        "chatId": chat_id,
        "message": text
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        print(f"Sent to {chat_id}: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"Send error: {e}")
        return False


def get_ai_reply(chat_id, user_message):
    """Получаем ответ от Claude"""
    if chat_id not in conversations:
        conversations[chat_id] = []

    conversations[chat_id].append({
        "role": "user",
        "content": user_message
    })

    # Храним последние 20 сообщений
    history = conversations[chat_id][-20:]

    response = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=history
    )

    reply = response.content[0].text

    conversations[chat_id].append({
        "role": "assistant",
        "content": reply
    })

    return reply


@app.route("/webhook", methods=["POST"])
def webhook():
    """Принимаем входящие сообщения от Green API"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "no data"}), 200

        # Игнорируем не текстовые сообщения
        if data.get("typeWebhook") != "incomingMessageReceived":
            return jsonify({"status": "ignored"}), 200

        msg_data = data.get("messageData", {})
        if msg_data.get("typeMessage") != "textMessage":
            return jsonify({"status": "not text"}), 200

        # Получаем текст и отправителя
        text = msg_data.get("textMessageData", {}).get("textMessage", "")
        sender = data.get("senderData", {}).get("chatId", "")

        if not text or not sender:
            return jsonify({"status": "empty"}), 200

        print(f"IN [{sender}]: {text}")

        # Получаем ответ от AI
        reply = get_ai_reply(sender, text)
        print(f"OUT: {reply[:80]}")

        # Отправляем ответ
        send_message(sender, reply)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 200


@app.route("/")
def index():
    return jsonify({
        "status": "running",
        "bot": BUSINESS["name"]
    })


@app.route("/set-webhook", methods=["GET"])
def set_webhook():
    """Устанавливаем вебхук в Green API"""
    webhook_url = request.args.get("url")
    if not webhook_url:
        return "Pass ?url=https://your-server.com/webhook", 400

    api_url = f"{GREEN_API_URL}/waInstance{GREEN_API_ID}/setSettings/{GREEN_API_TOKEN}"
    payload = {"webhookUrl": webhook_url}
    r = requests.post(api_url, json=payload)
    return jsonify({"status": r.status_code, "response": r.text})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Replai bot starting on port {port}")
    print(f"Business: {BUSINESS['name']}")
    app.run(host="0.0.0.0", port=port)
