# -*- coding: utf-8 -*-
import anthropic
import requests
import os
import json
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ============================================
# НАСТРОЙКИ
# ============================================
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ULTRA_INSTANCE = os.environ.get("ULTRA_INSTANCE", "instance177387")
ULTRA_TOKEN = os.environ.get("ULTRA_TOKEN", "ujszdo4hedkfw64p")
ULTRA_URL = f"https://api.ultramsg.com/{ULTRA_INSTANCE}"

# Google Calendar
CALENDAR_ID = os.environ.get("CALENDAR_ID", "1806b571d00fe7d06dc5be66f2c285887a7993505a6a4b2439675e41687f28d9@group.calendar.google.com")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON", "")

# Номер мастера для уведомлений (замени на реальный)
STAFF_PHONE = os.environ.get("STAFF_PHONE", "77017329955@c.us")

# ============================================

SYSTEM = """You are Aika, a friendly assistant for beauty salon Beauty Studio Astana. ALWAYS reply in Russian.
Be warm, use 1-2 emojis. Short replies. Like a good friend.
Salon: Astana, Kabanbay batyr 15. Phone: +7 707 123-45-67. Hours: Mon-Sat 9-21, Sun 10-19.
Services (tenge): manicure 4000, gel manicure 8000, pedicure 6000, haircut 5000, brow lamination 6000, lash extensions 8000-12000.

BOOKING PROCESS:
When client wants to book - collect step by step: service, date and time, name, phone number.
When you have ALL details confirmed - add this tag at the end of your message:
BOOKING:name|service|date|time|phone|client_whatsapp

Example: BOOKING:Айгуль|Маникюр гель|2026-05-25|14:00|+77001234567|77001234567@c.us

IMPORTANT: date format must be YYYY-MM-DD, time format HH:MM"""

app = Flask(__name__)
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
conversations = {}
sent_reminders = set()


# ============================================
# GOOGLE CALENDAR
# ============================================
def get_calendar_service():
    """Инициализируем Google Calendar API"""
    try:
        if GOOGLE_CREDS_JSON:
            creds_dict = json.loads(GOOGLE_CREDS_JSON)
        else:
            with open("google_creds.json") as f:
                creds_dict = json.load(f)
        
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        print(f"Calendar init error: {e}")
        return None


def create_calendar_event(name, service, date, time_str, client_phone):
    """Создаём событие в Google Calendar"""
    try:
        cal = get_calendar_service()
        if not cal:
            return None

        # Парсим дату и время
        start_dt = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(hours=1)

        event = {
            "summary": f"💅 {service} — {name}",
            "description": f"Клиент: {name}\nУслуга: {service}\nТелефон: {client_phone}",
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Asia/Almaty"
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Asia/Almaty"
            },
            "reminders": {"useDefault": False, "overrides": []}
        }

        result = cal.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        print(f"Calendar event created: {result.get('id')}")
        return result.get("id")

    except Exception as e:
        print(f"Calendar error: {e}")
        return None


def get_upcoming_events():
    """Получаем события на ближайшие 24 часа"""
    try:
        cal = get_calendar_service()
        if not cal:
            return []

        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(hours=24)).isoformat() + "Z"

        events = cal.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        return events.get("items", [])
    except Exception as e:
        print(f"Get events error: {e}")
        return []


# ============================================
# WHATSAPP
# ============================================
def send_message(phone, text):
    """Отправляем сообщение через UltraMsg"""
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


def notify_staff(name, service, date, time_str, client_phone):
    """Уведомляем мастера о новой записи"""
    msg = (
        f"🆕 Новая запись!\n\n"
        f"👤 Клиент: {name}\n"
        f"💅 Услуга: {service}\n"
        f"📅 Дата: {date}\n"
        f"🕐 Время: {time_str}\n"
        f"📞 Телефон: {client_phone}"
    )
    send_message(STAFF_PHONE, msg)
    print(f"Staff notified about booking: {name}")


# ============================================
# НАПОМИНАНИЯ
# ============================================
def reminder_loop():
    """Фоновый поток — проверяет события и шлёт напоминания за час"""
    print("Reminder loop started!")
    while True:
        try:
            events = get_upcoming_events()
            now = datetime.utcnow()

            for event in events:
                event_id = event.get("id")
                start = event.get("start", {}).get("dateTime", "")
                if not start or not event_id:
                    continue

                # Парсим время события
                event_dt = datetime.fromisoformat(start.replace("+05:00", ""))
                event_dt_utc = event_dt - timedelta(hours=5)  # Конвертируем из Алматы в UTC

                # Проверяем — за 50-70 минут до события
                diff = (event_dt_utc - now).total_seconds() / 60
                reminder_key = f"{event_id}_1h"

                if 50 <= diff <= 70 and reminder_key not in sent_reminders:
                    description = event.get("description", "")
                    summary = event.get("summary", "")

                    # Извлекаем телефон из описания
                    client_phone = ""
                    for line in description.split("\n"):
                        if "Телефон:" in line:
                            client_phone = line.replace("Телефон:", "").strip()

                    # Время визита в Алматы
                    visit_time = event_dt.strftime("%H:%M")
                    visit_date = event_dt.strftime("%d.%m.%Y")

                    # Напоминание клиенту
                    if client_phone:
                        client_wa = client_phone.replace("+", "").replace(" ", "") + "@c.us"
                        client_msg = (
                            f"⏰ Напоминаем о вашей записи!\n\n"
                            f"{summary}\n"
                            f"📅 {visit_date} в {visit_time}\n"
                            f"📍 Астана, ул. Кабанбай батыра, 15\n\n"
                            f"Ждём вас! 😊"
                        )
                        send_message(client_wa, client_msg)

                    # Напоминание мастеру
                    staff_msg = (
                        f"⏰ Через час запись!\n\n"
                        f"{summary}\n"
                        f"🕐 В {visit_time}"
                    )
                    send_message(STAFF_PHONE, staff_msg)

                    sent_reminders.add(reminder_key)
                    print(f"Reminder sent for event: {summary}")

        except Exception as e:
            print(f"Reminder loop error: {e}")

        time.sleep(300)  # Проверяем каждые 5 минут


# ============================================
# AI
# ============================================
def get_ai_reply(phone, text):
    """Получаем ответ от Claude"""
    if phone not in conversations:
        conversations[phone] = []
    conversations[phone].append({"role": "user", "content": text})
    try:
        r = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=SYSTEM,
            messages=conversations[phone][-20:]
        )
        reply = r.content[0].text
        conversations[phone].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        print(f"Claude error: {e}")
        return "Извините, ошибка. Позвоните: +7 707 123-45-67"


def process_booking(reply, client_wa):
    """Обрабатываем тег записи из ответа бота"""
    import re
    match = re.search(r'BOOKING:([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^\n]+)', reply)
    if not match:
        return reply

    name, service, date, time_str, phone, wa = [g.strip() for g in match.groups()]

    # Создаём событие в календаре
    event_id = create_calendar_event(name, service, date, time_str, phone)

    # Уведомляем мастера
    notify_staff(name, service, date, time_str, phone)

    # Убираем тег из ответа
    clean_reply = re.sub(r'BOOKING:[^\n]+', '', reply).strip()
    return clean_reply


# ============================================
# WEBHOOK
# ============================================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True) or {}

        if data.get("fromMe") is True or str(data.get("fromMe", "")).lower() == "true":
            return jsonify({"status": "outgoing"}), 200

        text = data.get("body", "").strip()
        phone = data.get("from", "").strip()

        if not text and "data" in data:
            d = data["data"]
            text = d.get("body", "").strip()
            phone = d.get("from", phone).strip()

        if not text or not phone:
            return jsonify({"status": "empty"}), 200

        if data.get("type", "") not in ["chat", ""]:
            return jsonify({"status": "not_chat"}), 200

        print(f"IN [{phone}]: {text}")
        reply = get_ai_reply(phone, text)

        # Проверяем есть ли запись
        if "BOOKING:" in reply:
            reply = process_booking(reply, phone)

        send_message(phone, reply)
        print(f"OUT: {reply[:80]}")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 200


@app.route("/")
def index():
    return jsonify({"status": "running", "instance": ULTRA_INSTANCE})


# Запускаем поток напоминаний
reminder_thread = threading.Thread(target=reminder_loop, daemon=True)
reminder_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Replai bot starting on port {port}")
    app.run(host="0.0.0.0", port=port)
