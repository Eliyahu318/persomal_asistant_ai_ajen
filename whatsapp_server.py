from flask import Flask, request

app = Flask(__name__)


@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form["Body"]
    sender = request.form["From"]
    print(f"📩 {sender}: {incoming_msg}")
    return "OK", 200


if __name__ == "__main__":
    app.run(port=5000)
