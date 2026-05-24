# -*- coding: utf-8 -*-
import anthropic
import requests
import time
import os
import threading
from flask import Flask, jsonify

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "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")
GREEN_ID = os.environ.get("GREEN_API_ID", "7107627445")
GREEN_TOKEN = os.environ.get("GREEN_API_TOKEN", "d954efc94a7b4f09ad0dcd944a99eec861e8c53c22e943edb1")
BASE_URL = f"https://7107.api.greenapi.com/waInstance{GREEN_ID}"

SYSTEM = """You are Aika, a friendly assistant for beauty salon Beauty Studio Astana. ALWAYS reply in Russian.
Be warm, use 1-2 emojis. Short replies. Like a good friend.
Salon: Astana, Kabanbay batyr 15. Phone: +7 707 123-45-67. Hours: Mon-Sat 9-21, Sun 10-19.
Services (tenge): manicure 4000, gel manicure 8000, pedicure 6000, haircut 5000, brow lamination 6000, lash extensions 8000-12000.
When booking collect: service, date+time, name, phone."""

app = Flask(__name__)
claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
conversations = {}

session = requests.Session()
session.headers.update({"Connection": "keep-alive"})


def receive_notification():
    try:
        r = session.get(
            f"{BASE_URL}/receiveNotification/{GREEN_TOKEN}",
            timeout=30,
            verify=True
        )
        if r.status_code == 200:
            data = r.json()
            if data:
                return data
    except requests.exceptions.Timeout:
        pass
    except Exception as e:
        print(f"Receive error: {type(e).__name__}: {e}")
    return None


def delete_notification(receipt_id):
    try:
        session.delete(
            f"{BASE_URL}/deleteNotification/{GREEN_TOKEN}/{receipt_id}",
            timeout=15
        )
    except:
        pass


def send_message(chat_id, text):
    try:
        r = session.post(
            f"{BASE_URL}/sendMessage/{GREEN_TOKEN}",
            json={"chatId": chat_id, "message": text},
            timeout=30
        )
        return r.status_code == 200
    except Exception as e:
        print(f"Send error: {e}")
        return False


def get_ai_reply(chat_id, text):
    if chat_id not in conversations:
        conversations[chat_id] = []
    conversations[chat_id].append({"role": "user", "content": text})
    try:
        r = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=SYSTEM,
            messages=conversations[chat_id][-20:]
        )
        reply = r.content[0].text
        conversations[chat_id].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        print(f"Claude error: {e}")
        return "Извините, ошибка. Позвоните: +7 707 123-45-67"


def polling_loop():
    print("Polling started!")
    errors = 0
    while True:
        try:
            data = receive_notification()
            if data and data.get("receiptId"):
                errors = 0
                receipt_id = data["receiptId"]
                body = data.get("body", {})
                if body.get("typeWebhook") == "incomingMessageReceived":
                    msg = body.get("messageData", {})
                    if msg.get("typeMessage") == "textMessage":
                        text = msg.get("textMessageData", {}).get("textMessage", "")
                        sender = body.get("senderData", {}).get("chatId", "")
                        if text and sender:
                            print(f"IN [{sender[-8:]}]: {text}")
                            reply = get_ai_reply(sender, text)
                            if send_message(sender, reply):
                                print(f"OUT: {reply[:60]}")
                delete_notification(receipt_id)
                time.sleep(0.5)
            else:
                time.sleep(3)
        except Exception as e:
            errors += 1
            wait = min(errors * 5, 60)
            print(f"Loop error ({errors}): {e}, waiting {wait}s")
            time.sleep(wait)


poll_thread = threading.Thread(target=polling_loop, daemon=True)
poll_thread.start()


@app.route("/")
def index():
    return jsonify({"status": "running", "polling": "active"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
