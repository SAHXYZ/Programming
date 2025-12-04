import os
import re
import uuid
import subprocess
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackContext

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Store user sessions
sessions = {}


def count_inputs(code):
    return len(re.findall(r"input\s*\(", code))


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
        output = "❌ Execution took too long."

    os.remove(temp)
    return output if output.strip() else "No output."


def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Welcome to Code Runner Bot!\n"
        "Send me Python code and I will run it.\n"
        "Supports input() too."
    )


def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text

    # Waiting for INPUTS
    if chat_id in sessions and sessions[chat_id]["awaiting"]:
        sessions[chat_id]["inputs"].append(text)

        if len(sessions[chat_id]["inputs"]) == sessions[chat_id]["need"]:
            code = sessions[chat_id]["code"]
            output = run_python(code, sessions[chat_id]["inputs"])
            update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")

            sessions.pop(chat_id)
        else:
            update.message.reply_text(
                f"Input {len(sessions[chat_id]['inputs'])+1}:"
            )
        return

    # New Code
    code = text
    need = count_inputs(code)

    if need == 0:
        output = run_python(code, [])
        update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
        return

    sessions[chat_id] = {
        "code": code,
        "inputs": [],
        "need": need,
        "awaiting": True
    }

    update.message.reply_text(
        f"Your code requires {need} inputs.\nSend Input 1:"
    )


def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
