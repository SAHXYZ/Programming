import os
import re
import uuid
import subprocess
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, CallbackContext

BOT_TOKEN = os.getenv("BOT_TOKEN")

# User sessions for storing inputs
sessions = {}


# --------------------- FIX MULTI-LINE STRINGS ---------------------
def fix_multiline_input_strings(code):
    """
    Converts actual newlines inside quotes into \n so Python does not break strings.
    """
    new_code = ""
    inside = False
    quote = ""

    for ch in code:
        if ch in ['"', "'"]:
            if not inside:
                inside = True
                quote = ch
            elif inside and ch == quote:
                inside = False

        if inside and ch == "\n":
            new_code += "\\n"   # convert real newline to \n
        else:
            new_code += ch

    return new_code


# --------------------- CLEAN BAD FORMATTING ---------------------
def fix_code_formatting(code):
    code = code.replace(") ", ")\n")
    code = code.replace(": ", ":\n")
    code = code.replace(";", "\n")
    code = re.sub(r'\)\s*(print|input)', r')\n\1', code)

    lines = [l.strip() for l in code.split("\n")]
    return "\n".join([l for l in lines if l])


# --------------------- AUTO INDENT RECONSTRUCTION ---------------------
def auto_indent(code):
    """
    Rebuild indentation for one-line code.
    Supports if, elif, else, for, while, match, case, def, class, try, except, finally.
    """
    keywords = {
        "if", "elif", "else", "for", "while",
        "match", "case", "def", "class",
        "try", "except", "finally"
    }

    # Split by keywords (while preserving them)
    tokens = re.split(r'\b(if|elif|else|for|while|match|case|def|class|try|except|finally)\b', code)
    result = ""
    indent = 0
    i = 0

    while i < len(tokens):
        part = tokens[i]

        if part in keywords:
            kw = part
            rest = tokens[i + 1] if i + 1 < len(tokens) else ""
            line = kw + rest

            result += ("    " * indent) + line.strip() + "\n"

            if ":" in line:
                indent += 1

            i += 2
        else:
            lines = part.split("\n")
            for ln in lines:
                if ln.strip():
                    result += ("    " * indent) + ln.strip() + "\n"
            i += 1

    return result


# --------------------- EXTRACT CLEAN PROMPTS ---------------------
def extract_prompts(code):
    raw = re.findall(r'input\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', code)

    clean = []
    for p in raw:
        # Convert escaped \n into real newline
        p = p.replace("\\n", "\n")

        # Remove ALL newlines for Telegram prompt
        p = p.replace("\n", " ")

        clean.append(p.strip())

    return clean


# --------------------- RUN PYTHON ---------------------
def run_python(code, inputs):
    temp = f"temp_{uuid.uuid4().hex[:8]}.py"

    with open(temp, "w") as f:
        f.write(code)

    input_text = "\n".join(inputs) + "\n"

    try:
        result = subprocess.run(
            ["python3", temp],
            input=input_text,
            text=True,
            capture_output=True,
            timeout=25
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        output = "❌ Execution Timeout"

    os.remove(temp)
    return output if output.strip() else "No output."


# --------------------- /start COMMAND ---------------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Welcome to **ProgramBOT – Python Code Runner**!\n\n"
        "Send your Python code and I will execute it.\n\n"
        "Supports:\n"
        "✔ input() prompts\n"
        "✔ auto-indent fixing\n"
        "✔ multi-line input strings\n"
        "✔ complex programs (loops, match-case)\n"
        "✔ one-line messy code\n\n"
        "Send your code now."
    )


# --------------------- HANDLE EVERY MESSAGE ---------------------
def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text

    # ------- If user is giving input() values -------
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

    # ------- New code received -------
    code = text

    # Formatting pipeline
    code = fix_multiline_input_strings(code)
    code = fix_code_formatting(code)
    code = auto_indent(code)

    prompts = extract_prompts(code)
    need = len(prompts)

    if need == 0:
        output = run_python(code, [])
        update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
        return

    # Save session
    sessions[chat_id] = {
        "code": code,
        "inputs": [],
        "need": need,
        "prompts": prompts,
        "awaiting": True
    }

    update.message.reply_text(prompts[0])


# --------------------- MAIN ---------------------
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
