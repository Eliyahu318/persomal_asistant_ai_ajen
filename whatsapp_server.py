from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from assistant import PersonalAssistant  # ייבוא העוזר האישי שלך

# יצירת מופע Flask
app = Flask(__name__)

# יצירת מופע מהעוזר האישי שלך
assistant = PersonalAssistant(name="twilio_user")

# נקודת קצה ל־Twilio WhatsApp Webhook
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    # קבלת הודעה ומספר מהבקשה של טווילו
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")

    print(f"📩 הודעה מ-{from_number}: {incoming_msg}")

    # עיבוד ההודעה בעזרת העוזר האישי
    response_text = assistant.process_user_input(incoming_msg)

    # יצירת תגובה בחזרה ל־Twilio
    reply = MessagingResponse()
    reply.message(response_text)

    return str(reply)


# הפעלה מקומית בעת פיתוח
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
