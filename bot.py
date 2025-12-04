import os
import re
import uuid
import subprocess
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackContext

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Store user sessions
sessions = {}


# ------------------- FIX MULTI-LINE INPUT STRINGS -------------------
def fix_multiline_input_strings(code):
    """
    Converts actual newline characters inside input("...") strings
    back into \\n so Python does not break the string.
    """
    new_code = ""
    inside_string = False
    string_char = ""

    for ch in code:
        # Detect if entering or exiting a string
        if ch in ['"', "'"]:
            if not inside_string:
                inside_string = True
                string_char = ch
            elif inside_string and ch == string_char:
                inside_string = False

        # Replace real newline inside strings with \n
        if inside_string and ch == "\n":
            new_code += "\\n"
        else:
            new_code += ch

    return new_code


# ------------------- FIX BADLY FORMATTED ONE-LINE CODE -------------------
def fix_code_formatting(code):
    # Add new line after ) 
    code = code.replace(") ", ")\n")

    # Add newline after colon patterns
    code = code.replace(": ", ":\n")

    # Convert semicolons to newlines
    code = code.replace(";", "\n")

    # Ensure print/input begin on new line
    code = re.sub(r'\)\s*(print|input)', r')\n\1', code)

    # Clean extra spaces & blank lines
    lines = [l.strip() for l in code.split("\n") if l.strip()]
    return "\n".join(lines)


# ------------------- EXTRACT INPUT PROMPTS -------------------
def extract_prompts(code):
    return re.findall(r'input\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', code)


# ------------------- RUN PYTHON CODE -------------------
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
            timeout=30
        )
        output = result.stdout + result.stderr

    except subprocess.TimeoutExpired:
        output = "❌ Execution timed out."

    os.remove(temp)
    return output if output.strip() else "No output."


# ------------------- /start COMMAND -------------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Welcome to **Code Runner Bot!**\n"
        "Send me **Python code** and I will run it.\n"
        "Supports:\n"
        "• `input()` prompts\n"
        "• Multi-line input text\n"
        "• One-line pasted code auto-fixing\n"
        "• Complex loops, conditions, match-case etc.\n\n"
        "Just send code directly."
    )


# ------------------- MESSAGE HANDLER -------------------
def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text

    # ---------- USER IS PROVIDING INPUTS ----------
    if chat_id in sessions and sessions[chat_id]["awaiting"]:
        sessions[chat_id]["inputs"].append(text)

        if len(sessions[chat_id]["inputs"]) == sessions[chat_id]["need"]:
            code = sessions[chat_id]["code"]
            output = run_python(code, sessions[chat_id]["inputs"])
            update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
            sessions.pop(chat_id)
        else:
            next_prompt = sessions[chat_id]["prompts"][len(sessions[chat_id]["inputs"])]
            update.message.reply_text(next_prompt)
        return

    # ---------- NEW PYTHON CODE RECEIVED ----------
    # Fix formatting and broken multi-line strings
    code = fix_code_formatting(text)
    code = fix_multiline_input_strings(code)

    prompts = extract_prompts(code)
    need = len(prompts)

    # If no input() calls → run immediately
    if need == 0:
        output = run_python(code, [])
        update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
        return

    # Save session for multiple inputs
    sessions[chat_id] = {
        "code": code,
        "inputs": [],
        "need": need,
        "prompts": prompts,
        "awaiting": True
    }

    # Send first prompt
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
