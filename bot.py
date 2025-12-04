import os
import requests
import subprocess
import uuid
import re
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Count input() calls
def count_inputs(code):
    return len(re.findall(r"input\s*\(", code))

# Execute Python code with inputs
def run_python(code, inputs):
    temp = f"temp_{uuid.uuid4().hex[:8]}.py"
    with open(temp, "w") as f:
        f.write(code)

    input_data = "\n".join(inputs) + "\n"

    try:
        result = subprocess.run(
            ["python3", temp],
            input=input_data,
            text=True,
            capture_output=True,
            timeout=25
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        output = "❌ Execution timed out."

    os.remove(temp)
    return output if output.strip() else "No output."


# Store user steps
sessions = {}

def send(chat_id, text):
    requests.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })


@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" not in data:
        return "OK"

    msg = data["message"]
    chat_id = msg["chat"]["id"]

    if "text" in msg:
        text = msg["text"]

        # Start command
        if text == "/start":
            send(chat_id,
                 "👋 Welcome to the Code Runner Bot!\n"
                 "Send Python code (text) and I will execute it.\n"
                 "Supports `input()` automatically.")
            return "OK"

        # If user is providing input for code
        if chat_id in sessions and sessions[chat_id]["awaiting_inputs"]:
            sessions[chat_id]["inputs"].append(text)

            if len(sessions[chat_id]["inputs"]) == sessions[chat_id]["needed"]:
                code = sessions[chat_id]["code"]
                output = run_python(code, sessions[chat_id]["inputs"])
                send(chat_id, f"```\n{output}\n```")
                sessions.pop(chat_id)
            else:
                send(chat_id, f"Input {len(sessions[chat_id]['inputs'])+1}:")
            return "OK"

        # New code entered
        code = text
        needed = count_inputs(code)

        if needed == 0:
            output = run_python(code, [])
            send(chat_id, f"```\n{output}\n```")
        else:
            sessions[chat_id] = {
                "code": code,
                "needed": needed,
                "inputs": [],
                "awaiting_inputs": True
            }
            send(chat_id, f"Your code needs {needed} inputs.\nSend Input 1:")
        return "OK"

    return "OK"


@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"


if __name__ == "__main__":
    app.run()
