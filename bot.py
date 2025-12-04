import os
import re
import uuid
import subprocess
from telegram import Update, Document
from telegram.ext import (
    Updater,
    MessageHandler,
    Filters,
    CommandHandler,
    CallbackContext,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Per-chat sessions for pending inputs
sessions = {}


# ----------------- Helpers ----------------- #

def sanitize_text_code(text: str) -> str:
    """
    If user sends code in a Markdown ``` block, strip the fences.
    Otherwise, return text as-is.
    """
    text = text.rstrip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop first line (``` or ```python)
        if lines:
            lines = lines[1:]
        # drop last line if it is ```*
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return text


def extract_display_prompts(code: str):
    """
    Extract the text inside input("...") for display to user.
    We do NOT modify the original code; this is only for prompts.
    """
    raw = re.findall(r'input\s*\(\s*[\'"]([^\'"]*)[\'"]\s*\)', code)
    prompts = []
    for p in raw:
        # Turn escaped \n into real newline, then flatten for Telegram display
        p = p.replace("\\n", "\n")
        p = p.replace("\n", " ")
        p = p.strip()
        if not p:
            p = "Enter value:"  # fallback
        prompts.append(p)
    return prompts


def run_python(code: str, inputs: list[str]) -> str:
    """
    Run Python code in a temp file with the given list of inputs.
    """
    temp_name = f"temp_{uuid.uuid4().hex[:8]}.py"
    with open(temp_name, "w", encoding="utf-8") as f:
        f.write(code)

    input_data = "\n".join(inputs) + ("\n" if inputs else "")

    try:
        result = subprocess.run(
            ["python3", temp_name],
            input=input_data,
            text=True,
            capture_output=True,
            timeout=30,
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        output = "❌ Execution timed out."

    try:
        os.remove(temp_name)
    except Exception:
        pass

    return output.strip() or "No output."


# ----------------- Handlers ----------------- #

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 **ProgramBOT – Python Code Runner**\n\n"
        "Send Python code and I will run it.\n\n"
        "Tips:\n"
        "• For best results, send code as a **.py file from VS Code**, or\n"
        "• Paste code inside a Markdown block:\n"
        "  ```python\n"
        "  # your code here\n"
        "  ```\n\n"
        "I support multiple `input()` calls and will ask each prompt."
    )


def handle_text(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    text = update.message.text

    # If we're currently collecting inputs for this chat
    if chat_id in sessions and sessions[chat_id]["awaiting"]:
        sess = sessions[chat_id]
        sess["inputs"].append(text)

        if len(sess["inputs"]) >= sess["need"]:
            # All inputs collected – run code
            output = run_python(sess["code"], sess["inputs"])
            update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
            sessions.pop(chat_id, None)
        else:
            # Ask next prompt
            next_prompt = sess["prompts"][len(sess["inputs"])]
            update.message.reply_text(next_prompt)
        return

    # New code as text
    code = sanitize_text_code(text)
    process_new_code(update, code)


def handle_document(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    doc: Document = update.message.document

    filename = doc.file_name or ""
    if not filename.lower().endswith(".py"):
        update.message.reply_text("❌ Please send a `.py` file or plain Python code.")
        return

    # Download file
    file = context.bot.get_file(doc.file_id)
    temp_name = f"upload_{uuid.uuid4().hex[:8]}.py"
    file.download(custom_path=temp_name)

    try:
        with open(temp_name, "r", encoding="utf-8") as f:
            code = f.read()
    finally:
        try:
            os.remove(temp_name)
        except Exception:
            pass

    process_new_code(update, code)


def process_new_code(update: Update, code: str):
    """
    Handle fresh code (either text or file).
    Decide if we need to ask for inputs or run immediately.
    """
    chat_id = update.message.chat_id

    prompts = extract_display_prompts(code)
    need = len(prompts)

    if need == 0:
        # No input() – run directly
        output = run_python(code, [])
        update.message.reply_text(f"```\n{output}\n```", parse_mode="Markdown")
        return

    # Store session to collect input values
    sessions[chat_id] = {
        "code": code,
        "prompts": prompts,
        "need": need,
        "inputs": [],
        "awaiting": True,
    }

    # Ask first prompt
    update.message.reply_text(prompts[0])


# ----------------- Main ----------------- #

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.document & ~Filters.command, handle_document))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
