from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import anthropic
import json
import re
from datetime import datetime

API_KEY = "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"

USE_SHEETS = False
SHEET_ID = ""
MASTER_PHONE = "whatsapp:+77017329955"
TWILIO_FROM = "whatsapp:+14155238886"
TWILIO_SID = "AC384245e85ba4a2b81728a819f7eb1a45"
TWILIO_TOKEN = "bb74b24cfb58505a3633a9857db26763"

app = Flask(__name__)
client = anthropic.Anthropic(api_key=API_KEY)
history = {}
bookings = []

schedule = {
    "2026-05-02": ["10:00", "11:00", "12:00", "14:00", "15:00", "16:00", "17:00"],
    "2026-05-03": ["09:00", "10:00", "11:00", "13:00", "14:00", "15:00"],
    "2026-05-04": ["10:00", "11:00", "12:00", "14:00", "16:00", "17:00"],
    "2026-05-05": ["09:00", "10:00", "12:00", "13:00", "15:00", "16:00"],
    "2026-05-06": ["10:00", "11:00", "13:00", "14:00", "15:00", "17:00"],
}
booked_slots = {}


def get_free_slots():
    result = {}
    for date, slots in schedule.items():
        booked = booked_slots.get(date, [])
        free = [s for s in slots if s not in booked]
        if free:
            result[date] = free
    return result


def book_slot(date, time, name, service, phone):
    if date not in booked_slots:
        booked_slots[date] = []
    booked_slots[date].append(time)
    booking = {"name": name, "service": service, "date": date, "time": time, "phone": phone, "created": datetime.now().strftime("%d.%m.%Y %H:%M")}
    bookings.append(booking)
    with open("bookings.json", "w", encoding="utf-8") as f:
        json.dump(bookings, f, ensure_ascii=False, indent=2)
    notify_master(booking)
    return booking


def notify_master(booking):
    try:
        from twilio.rest import Client as TC
        tc = TC(TWILIO_SID, TWILIO_TOKEN)
        msg = "New booking!\nClient: {name}\nService: {service}\nDate: {date} at {time}\nPhone: {phone}".format(**booking)
        tc.messages.create(body=msg, from_=TWILIO_FROM, to=MASTER_PHONE)
        print("Master notified")
    except Exception as e:
        print("Notify error:", e)


def slots_text():
    free = get_free_slots()
    if not free:
        return "No free slots available."
    lines = ["Available slots:"]
    for date, slots in list(free.items())[:4]:
        lines.append(date + ": " + ", ".join(slots))
    return "\n".join(lines)


def get_system():
    return """You are Aika, assistant for beauty salon Beauty Studio Astana. ALWAYS reply in Russian.

Be warm, friendly, use 1-2 emojis. Short messages. Like a good friend, not a robot.

Salon: Astana, Kabanbay batyr 15, 2nd floor. Phone: +7 707 123-45-67. Hours: Mon-Sat 9-21, Sun 10-19.

Services: manicure 4000, manicure+gel 8000, pedicure 6000, pedicure+gel 10000, nail extensions 15000, haircut 5000, root coloring 12000, full coloring 18000-35000, brow lamination 6000, lash extensions 8000-12000, face cleaning 12000 (prices in tenge).

Masters: Aigerim-nails, Dana-hair, Saule-brows and lashes.

When booking collect: service, date+time, name, phone. Show available slots when asked about timing.
When you have ALL details confirmed add at message end: BOOKING:name|service|date|time|phone

""" + slots_text()


def process(sender, msg):
    if sender not in history:
        history[sender] = []
    history[sender].append({"role": "user", "content": msg})
    r = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=get_system(),
        messages=history[sender][-16:]
    )
    reply = r.content[0].text
    match = re.search(r'BOOKING:([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^\n]+)', reply)
    if match:
        name, service, date, time, phone = [g.strip() for g in match.groups()]
        book_slot(date, time, name, service, phone)
        reply = re.sub(r'BOOKING:[^\n]+', '', reply).strip()
        print("Booked:", name, service, date, time)
    history[sender].append({"role": "assistant", "content": reply})
    return reply


@app.route('/webhook', methods=['POST'])
def webhook():
    msg = request.values.get('Body', '').strip()
    sender = request.values.get('From', '')
    if not msg:
        return Response('', status=200)
    print("IN:", msg)
    try:
        reply = process(sender, msg)
    except Exception as e:
        print("Error:", e)
        reply = "Извините, ошибка. Позвоните: +7 707 123-45-67"
    print("OUT:", reply[:60])
    resp = MessagingResponse()
    resp.message(reply)
    return Response(str(resp), mimetype='text/xml')


@app.route('/')
def index():
    return 'Bot running'


@app.route('/bookings')
def show_bookings():
    return json.dumps(bookings, ensure_ascii=False, indent=2), 200, {'Content-Type': 'application/json; charset=utf-8'}


@app.route('/schedule')
def show_schedule():
    return json.dumps(get_free_slots(), ensure_ascii=False), 200, {'Content-Type': 'application/json; charset=utf-8'}


if __name__ == '__main__':
    print('Bot started on port 5000')
    app.run(host='0.0.0.0', port=5000)
