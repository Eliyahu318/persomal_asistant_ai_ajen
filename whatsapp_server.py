import os
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from assistant import PersonalAssistant

app = Flask(__name__)


user_sessions = {}


@app.route("/", methods=["GET"])
def root():
    return "🟢 OK", 200


@app.route("/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "").replace("whatsapp", "")
    print(f"📩 הודעה מ-{from_number}: {incoming_msg}")

    if from_number not in user_sessions:
        user_sessions[from_number] = PersonalAssistant.load_state(name=from_number)


    # שלב 1 – בדיקת "כן"/"לא" עבור פעולה בהמתנה
    # if from_number in pending_confirmations:
    #     confirmation = incoming_msg
    #     if confirmation in ["כן", "לא"]:
    #         response_text = assistant.process_user_input(confirmation)
    #         del pending_confirmations[from_number]
    #     else:
    #         response_text = "ענה בבקשה 'כן' או 'לא'."
    # else:
    response_text = assistant.process_user_input(incoming_msg)
    twiml = MessagingResponse()
    twiml.message(response_text)
    return Response(str(twiml), mimetype="application/xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4000))
    app.run(debug=True, host="0.0.0.0", port=port)