
from flask import Flask, render_template, request, jsonify
from telethon import TelegramClient
import asyncio

app = Flask(__name__)
clients = {}

ad_message = """مركز سرعة انجاز 📚للخدمات الطلابية والاكاديمية..."""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_code', methods=['POST'])
def send_code():
    data = request.json
    api_id = data['api_id']
    api_hash = data['api_hash']
    phone = data['phone']

    client = TelegramClient('session', api_id, api_hash)
    asyncio.run(client.start(phone))
    clients[phone] = client
    return jsonify({"status": "ok"})

@app.route('/verify_code', methods=['POST'])
def verify_code():
    data = request.json
    phone = data['phone']
    code = data['code']

    client = clients.get(phone)
    if client:
        asyncio.run(client.sign_in(phone, code))
        return jsonify({"status": "success"})
    return jsonify({"status": "error"})

@app.route('/start_bot', methods=['POST'])
def start_bot():
    data = request.json
    phone = data['phone']
    groups = data['groups'].splitlines()
    client = clients.get(phone)
    if not client:
        return jsonify({"status": "error", "message": "Client not found"})

    async def send_ads():
        while True:
            for link in groups:
                try:
                    entity = await client.get_entity(link.strip())
                    await client.send_message(entity, ad_message, link_preview=False)
                except Exception as e:
                    print(f"Error sending to {link}: {e}")
            await asyncio.sleep(60)

    asyncio.run(send_ads())
    return jsonify({"status": "started"})

if __name__ == "__main__":
    app.run(debug=True)
