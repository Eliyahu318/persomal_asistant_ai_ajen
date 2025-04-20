# whatsapp_server.py
import os
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from assistant import PersonalAssistant

app = Flask(__name__)
assistant = PersonalAssistant.load_state(name="twilio_user", confirm_callback=lambda msg: "כן")

@app.route("/", methods=["GET"])
def root():
    # עונה ל‑Render Health‑Check
    return "🟢 OK", 200

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    ...
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    print(f"📩 הודעה מ-{from_number}: {incoming_msg}")   # ← החזרנו!

    incoming_msg = request.values.get("Body", "").strip()
    response_text = assistant.process_user_input(incoming_msg)

    twiml = MessagingResponse()
    twiml.message(response_text)
    # החזרת XML + הכותרת המתאימה
    return Response(str(twiml), mimetype="application/xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))   # ← Render יספק PORT
    app.run(host="0.0.0.0", port=port)

