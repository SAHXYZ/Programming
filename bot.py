import os
import re
import uuid
import subprocess
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackContext

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Store user sessions
sessions = {}


# ------------------- AUTO FIX USER CODE -------------------
def fix_code_formatting(code):
    # Split at ") " → new line
    code = code.replace(") ", ")\n")

    # Split at ": " (function, input prompt, etc.)
    code = code.replace(": ", ":\n")

    # Split at semicolon
    code = code.replace(";", "\n")

    # Ensure print/input start on new line
    code = re.sub(r'\)\s*(print|input)', r')\n\1', code)

    # Clean multiple spaces/newlines
    lines = [l.strip() for l in code.split("\n") if l.strip()]
    return "\n".join(lines)


# ------------------- EXTRACT INPUT PROMPTS -------------------
def extract_prompts(code):
    return re.findall(r'input\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', code)


# ------------------- EXECUTE PYTHON CODE -------------------
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


# ------------------- /start -------------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Welcome to **Code Runner Bot**!\n"
        "Send me Python code and I will run it.\n"
        "Supports *input()* with correct prompts.\n\n"
        "Paste your Python script ANY way — I will fix formatting automatically."
    )


# ------------------- MESSAGE HANDLER -------------------
def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text

    # --- STEP 1: USER IS GIVING INPUTS ---
    if chat_id in sessions and sessions[chat_id]["awaiting"]:
        sessions[chat_id]["inputs"].append(text)

        # All inputs received
        if len(sessions[chat_id]["inputs"]) == sessions[chat_id]["need"]:
            code = sessions[chat_id]["code"]
            output = run_python(code, sessions[chat_id]["inputs"])
            update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
            sessions.pop(chat_id)
        else:
            # Ask next prompt
            next_prompt = sessions[chat_id]["prompts"][len(sessions[chat_id]["inputs"])]
            update.message.reply_text(next_prompt)
        return

    # --- STEP 2: NEW PYTHON CODE RECEIVED ---
    code = fix_code_formatting(text)
    prompts = extract_prompts(code)
    need = len(prompts)

    # No input() in code → run directly
    if need == 0:
        output = run_python(code, [])
        update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
        return

    # Store code session
    sessions[chat_id] = {
        "code": code,
        "inputs": [],
        "need": need,
        "prompts": prompts,
        "awaiting": True
    }

    # Ask first input prompt
    update.message.reply_text(prompts[0])


# ------------------- MAIN -------------------
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
