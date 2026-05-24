# -*- coding: utf-8 -*-
import anthropic
import requests
import os
from flask import Flask, jsonify, request

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "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")
ULTRA_INSTANCE = os.environ.get("ULTRA_INSTANCE", "instance177387")
ULTRA_TOKEN = os.environ.get("ULTRA_TOKEN", "ujszdo4hedkfw64p")
ULTRA_URL = f"https://api.ultramsg.com/{ULTRA_INSTANCE}"

SYSTEM = """You are Aika, a friendly assistant for beauty salon Beauty Studio Astana. ALWAYS reply in Russian.
Be warm, use 1-2 emojis. Short replies. Like a good friend.
Salon: Astana, Kabanbay batyr 15. Phone: +7 707 123-45-67. Hours: Mon-Sat 9-21, Sun 10-19.
Services (tenge): manicure 4000, gel manicure 8000, pedicure 6000, haircut 5000, brow lamination 6000, lash extensions 8000-12000.
When booking collect: service, date+time, name, phone."""

app = Flask(__name__)
claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
conversations = {}


def send_message(phone, text):
    try:
        r = requests.post(
            f"{ULTRA_URL}/messages/chat",
            data={"token": ULTRA_TOKEN, "to": phone, "body": text, "priority": "10"},
            timeout=30
        )
        print(f"Send to {phone}: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"Send error: {e}")
        return False


def get_ai_reply(phone, text):
    if phone not in conversations:
        conversations[phone] = []
    conversations[phone].append({"role": "user", "content": text})
    try:
        r = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=SYSTEM,
            messages=conversations[phone][-20:]
        )
        reply = r.content[0].text
        conversations[phone].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        print(f"Claude error: {e}")
        return "Извините, ошибка. Позвоните: +7 707 123-45-67"


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True) or {}
        print(f"Webhook: {data}")

        # Игнорируем исходящие
        if data.get("fromMe") is True or str(data.get("fromMe", "")).lower() == "true":
            return jsonify({"status": "outgoing"}), 200

        # Получаем текст и отправителя
        text = data.get("body", "").strip()
        phone = data.get("from", "").strip()

        # UltraMsg иногда шлёт в data вложенный объект
        if not text and "data" in data:
            d = data["data"]
            text = d.get("body", "").strip()
            phone = d.get("from", phone).strip()

        if not text or not phone:
            return jsonify({"status": "empty"}), 200

        # Игнорируем системные сообщения
        if data.get("type", "") not in ["chat", ""]:
            return jsonify({"status": "not_chat"}), 200

        print(f"IN [{phone}]: {text}")
        reply = get_ai_reply(phone, text)
        send_message(phone, reply)
        print(f"OUT: {reply[:80]}")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 200


@app.route("/")
def index():
    return jsonify({"status": "running", "instance": ULTRA_INSTANCE})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Replai bot starting on port {port}")
    print(f"UltraMsg instance: {ULTRA_INSTANCE}")
    app.run(host="0.0.0.0", port=port)
