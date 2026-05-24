# -*- coding: utf-8 -*-
import anthropic
import requests
import time
import os
import threading
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
    """Отправляем сообщение через UltraMsg"""
    try:
        r = requests.post(
            f"{ULTRA_URL}/messages/chat",
            data={
                "token": ULTRA_TOKEN,
                "to": phone,
                "body": text,
                "priority": "10"
            },
            timeout=30
        )
        print(f"Send status: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"Send error: {e}")
        return False


def get_ai_reply(phone, text):
    """Получаем ответ от Claude"""
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


def set_webhook(webhook_url):
    """Устанавливаем вебхук в UltraMsg"""
    try:
        r = requests.post(
            f"{ULTRA_URL}/instance/settings",
            data={
                "token": ULTRA_TOKEN,
                "webhookUrl": webhook_url,
                "sendDelay": "1",
                "webhook_message_received": "true",
                "webhook_message_sent": "false",
            },
            timeout=15
        )
        print(f"Webhook set: {r.status_code} - {r.text}")
        return r.status_code == 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return False


@app.route("/webhook", methods=["POST"])
def webhook():
    """Принимаем входящие сообщения от UltraMsg"""
    try:
        data = request.get_json() or request.form.to_dict()
        print(f"Webhook received: {data}")

        msg_type = data.get("type", "")
        if msg_type != "chat":
            return jsonify({"status": "ignored"}), 200

        text = data.get("body", "")
        phone = data.get("from", "")

        # Игнорируем исходящие
        if data.get("fromMe") == "true" or data.get("fromMe") is True:
            return jsonify({"status": "outgoing"}), 200

        if not text or not phone:
            return jsonify({"status": "empty"}), 200

        print(f"IN [{phone}]: {text}")
        reply = get_ai_reply(phone, text)
        send_message(phone, reply)
        print(f"OUT: {reply[:60]}")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 200


@app.route("/")
def index():
    return jsonify({"status": "running", "instance": ULTRA_INSTANCE})


@app.route("/set-webhook")
def setup_webhook():
    """Установить вебхук"""
    url = request.args.get("url", "")
    if not url:
        host = request.host_url.rstrip("/")
        url = f"{host}/webhook"
    success = set_webhook(url)
    return jsonify({"status": "ok" if success else "error", "webhook": url})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Replai bot starting on port {port}")
    print(f"UltraMsg instance: {ULTRA_INSTANCE}")
    app.run(host="0.0.0.0", port=port)
