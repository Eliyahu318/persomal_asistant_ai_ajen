"""import os
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from assistant import PersonalAssistant

app = Flask(__name__)
assistant = PersonalAssistant.load_state(name="twilio_user", confirm_callback=lambda msg: "כן")

@app.route("/", methods=["GET"])
def root():
    # עונה ל‑Render Health‑Check
    return "🟢 OK", 200


@app.route("/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    ...
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    print(f"📩 הודעה מ-{from_number}: {incoming_msg}")   # ← החזרנו!

    # incoming_msg = request.values.get("Body", "").strip()
    response_text = assistant.process_user_input(incoming_msg)

    twiml = MessagingResponse()
    twiml.message(response_text)
    # החזרת XML + הכותרת המתאימה
    return Response(str(twiml), mimetype="application/xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4000))   # ← Render יספק PORT
    app.run(debug=True, host="0.0.0.0", port=port)"""


# whatsapp_server.py
import os
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from assistant import PersonalAssistant

app = Flask(__name__)


pending_confirmations = {}
assistant = PersonalAssistant.load_state(
    name="twilio_user",
    confirm_callback=lambda msg: "המתנה לאישור"  # placeholder – הסוכן לא יענה באמת, רק ננהל מבחוץ
)


def confirm_callback(msg, from_number=None):
    # לא באמת עונה, רק שומר פעולה למעקב
    pending_confirmations[from_number] = msg
    return "המתנה לאישור"


@app.route("/", methods=["GET"])
def root():
    return "🟢 OK", 200


@app.route("/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    print(f"📩 הודעה מ-{from_number}: {incoming_msg}")

    # שלב 1 – בדיקת "כן"/"לא" עבור פעולה בהמתנה
    if from_number in pending_confirmations:
        confirmation = incoming_msg
        if confirmation in ["כן", "לא"]:
            response_text = assistant.process_user_input(confirmation)
            del pending_confirmations[from_number]
        else:
            response_text = "ענה בבקשה 'כן' או 'לא'."
    else:
        response_text = assistant.process_user_input(incoming_msg)
        twiml = MessagingResponse()
        twiml.message(response_text)
        return Response(str(twiml), mimetype="application/xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4000))
    app.run(debug=True, host="0.0.0.0", port=port)

