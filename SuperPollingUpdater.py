import asyncio
import logging
import os
import re
import sqlite3
import subprocess
from asyncio.subprocess import PIPE

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

API_TOKEN = "8076299335:AAHUUu-SEsmoyAAINdF0NQeXJkCgMK1RobY"
ADMIN_ID = 5873723609
FILES_DIR = "uploaded_bots"

logging.basicConfig(level=logging.INFO)
os.makedirs(FILES_DIR, exist_ok=True)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# --- DB connection ---
conn = sqlite3.connect("users.db", check_same_thread=False)  # check_same_thread=False - async muhitda xavfsizroq
cursor = conn.cursor()

def check_and_add_banned_column():
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    if "banned" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
        conn.commit()
        logging.info("Added 'banned' column to 'users' table.")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    approved INTEGER DEFAULT 0
)
""")
conn.commit()

check_and_add_banned_column()

def is_user_approved(user_id: int) -> bool:
    cursor.execute("SELECT approved FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row is not None and row[0] == 1

def is_user_banned(user_id: int) -> bool:
    cursor.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row is not None and row[0] == 1

def approve_user(user_id: int):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET approved = 1, banned = 0 WHERE user_id = ?", (user_id,))
    conn.commit()

def ban_user(user_id: int):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET banned = 1, approved = 0 WHERE user_id = ?", (user_id,))
    conn.commit()

def unban_user(user_id: int):
    cursor.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_banned_users():
    cursor.execute("SELECT user_id FROM users WHERE banned = 1")
    return [row[0] for row in cursor.fetchall()]

# --- Kutubxonalarni ajratib olish funksiyasi ---
def extract_libraries(file_path: str) -> list[str]:
    libs = set()
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            match1 = re.match(r"^import\s+([a-zA-Z0-9_]+)", line)
            if match1:
                libs.add(match1.group(1))
                continue
            match2 = re.match(r"^from\s+([a-zA-Z0-9_]+)\s+import\s+", line)
            if match2:
                libs.add(match2.group(1))
    return sorted(libs)

# --- State flag for pip install flow ---
# To keep track of users who are expected to send pip install library name
pip_install_waiting = set()

# --- /start komandasi ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id

    if is_user_banned(user_id):
        return await message.answer("🚫 Siz botdan foydalanishdan banlangansiz.")

    if is_user_approved(user_id):
        return await message.answer("✅ Siz tasdiqlangansiz.\nIltimos, <b>.py</b> fayl yuboring.")

    user = message.from_user
    text = (
        f"🆕 <b>Yangi foydalanuvchi:</b>\n"
        f"👤 Ism: {user.full_name}\n"
        f"🔗 Username: @{user.username if user.username else 'yo‘q'}\n"
        f"🆔 ID: <code>{user.id}</code>\n\n"
        f"❓ Tasdiqlaysizmi yoki ban qilasizmi?"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve:{user_id}"),
                InlineKeyboardButton(text="❌ Banlash", callback_data=f"ban:{user_id}")
            ]
        ]
    )
    await bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=keyboard)
    await message.answer("⏳ So‘rovingiz yuborildi. Admin tasdiqlamaguncha kuting.")

# --- Callback approve ---
@dp.callback_query(F.data.startswith("approve:"))
async def approve_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⛔ Sizda ruxsat yo‘q.", show_alert=True)

    user_id = int(callback.data.split(":")[1])
    approve_user(user_id)

    await bot.send_message(chat_id=user_id, text="✅ Siz tasdiqlandingiz! Endi .py fayl yuboring.")
    await callback.message.edit_text("✅ Foydalanuvchi tasdiqlandi.")
    await callback.answer()

# --- Callback ban ---
@dp.callback_query(F.data.startswith("ban:"))
async def ban_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⛔ Sizda ruxsat yo‘q.", show_alert=True)

    user_id = int(callback.data.split(":")[1])
    ban_user(user_id)

    await bot.send_message(chat_id=user_id, text="🚫 Siz botdan foydalanishdan banlangansiz.")
    await callback.message.edit_text("❌ Foydalanuvchi ban qilindi.")
    await callback.answer()

# --- /unban komandasi ---
@dp.message(Command("unban"))
async def unban_user_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔ Sizda ruxsat yo‘q.")

    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        return await message.answer("❗ To‘g‘ri foydalaning: <code>/unban user_id</code>")

    user_id = int(args[1])
    unban_user(user_id)
    await message.answer(f"✅ Foydalanuvchi <code>{user_id}</code> unban qilindi.")

# --- /banned komandasi ---
@dp.message(Command("banned"))
async def banned_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("⛔ Sizda ruxsat yo‘q.")

    banned_users = get_banned_users()
    if not banned_users:
        return await message.answer("✅ Banlangan foydalanuvchilar yo‘q.")

    text = "<b>🚫 Banlangan foydalanuvchilar:</b>\n"
    text += "\n".join([f"• <code>{uid}</code>" for uid in banned_users])
    await message.answer(text)

# --- Fayl qabul qilish ---
@dp.message(F.document)
async def handle_file(message: types.Message):
    user_id = message.from_user.id

    if is_user_banned(user_id):
        return await message.answer("🚫 Siz banlangansiz.")
    if not is_user_approved(user_id):
        return await message.answer("⏳ Siz hali tasdiqlanmadingiz.")

    document = message.document
    if not document.file_name.endswith(".py"):
        return await message.answer("⚠️ Faqat .py fayl yuboring.")

    user_dir = os.path.join(FILES_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    file_path = os.path.join(user_dir, document.file_name)
    log_path = file_path + ".log"
    pid_path = file_path + ".pid"

    await bot.download(document, destination=file_path)

    # Kutubxonalarni ajratib olish
    libraries = extract_libraries(file_path)
    if libraries:
        libs_text = "📚 Ushbu faylda import qilingan kutubxonalar:\n" + "\n".join(f"• {lib}" for lib in libraries)
    else:
        libs_text = "📚 Ushbu faylda hech qanday kutubxona import qilinmagan."

    # Faylni fon rejimda ishga tushirish
    # nohup va & bilan jarayonni orqaga o'tkazamiz va PIDni yozamiz
    subprocess.Popen(
        f"nohup python3 {file_path} > {log_path} 2>&1 & echo $! > {pid_path}",
        shell=True
    )

    await message.answer(f"✅ Fayl saqlandi: <code>{document.file_name}</code>\n🚀 Fon rejimda ishga tushdi.")
    await message.answer(libs_text)

# --- /mybots komandasi ---
@dp.message(Command("mybots"))
async def my_bots(message: types.Message):
    user_id = message.from_user.id

    if is_user_banned(user_id):
        return await message.answer("🚫 Siz banlangansiz.")
    if not is_user_approved(user_id):
        return await message.answer("⏳ Siz hali tasdiqlanmadingiz.")

    user_dir = os.path.join(FILES_DIR, str(user_id))
    if not os.path.exists(user_dir):
        return await message.answer("📂 Hech qanday fayl topilmadi.")

    files = [f for f in os.listdir(user_dir) if f.endswith(".py")]
    if not files:
        return await message.answer("📂 Hech qanday ishga tushirilgan fayl yo‘q.")

    for filename in files:
        file_path = os.path.join(user_dir, filename)
        pid_path = file_path + ".pid"

        buttons = [InlineKeyboardButton(text="📥 Log", callback_data=f"log:{filename}")]
        if os.path.exists(pid_path):
            buttons.append(InlineKeyboardButton(text="🔴 To‘xtatish", callback_data=f"stop:{filename}"))

        markup = InlineKeyboardMarkup(inline_keyboard=[buttons])
        await message.answer(f"🤖 <code>{filename}</code>", reply_markup=markup)

# --- Log ko‘rish ---
@dp.callback_query(F.data.startswith("log:"))
async def log_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    filename = callback.data.split(":")[1]
    file_path = os.path.join(FILES_DIR, str(user_id), filename + ".log")

    if not os.path.exists(file_path):
        return await callback.answer("❌ Log fayli topilmadi.", show_alert=True)

    await callback.message.answer_document(FSInputFile(file_path), caption="📥 Log fayli")
    await callback.answer()

# --- To‘xtatish ---
@dp.callback_query(F.data.startswith("stop:"))
async def stop_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    filename = callback.data.split(":")[1]
    pid_path = os.path.join(FILES_DIR, str(user_id), filename + ".pid")

    if not os.path.exists(pid_path):
        return await callback.answer("❌ PID topilmadi.", show_alert=True)

    with open(pid_path, "r") as f:
        pid = f.read().strip()

    try:
        os.kill(int(pid), 9)
    except ProcessLookupError:
        pass

    os.remove(pid_path)

    await callback.answer("🛑 Bot to‘xtatildi.")
    await callback.message.edit_text(f"🔴 <code>{filename}</code> to‘xtatildi.")

# --- /libraries komandasi ---
@dp.message(Command("libraries"))
async def list_installed_libraries(message: types.Message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        return await message.answer("🚫 Siz banlangansiz.")
    if not is_user_approved(user_id):
        return await message.answer("⏳ Siz hali tasdiqlanmadingiz.")

    proc = await asyncio.create_subprocess_exec("pip", "list", stdout=PIPE, stderr=PIPE)
    stdout, stderr = await proc.communicate()

    if stderr:
        err_text = stderr.decode().strip()
        if err_text:
            return await message.answer(f"❌ Xatolik yuz berdi:\n<code>{err_text}</code>")

    libs_text = stdout.decode().strip()
    if len(libs_text) > 4000:
        filename = "libraries.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(libs_text)
        await message.answer_document(types.FSInputFile(filename), caption="📦 O‘rnatilgan kutubxonalar ro‘yxati")
        os.remove(filename)
    else:
        await message.answer(f"<b>📦 O‘rnatilgan kutubxonalar:</b>\n<pre>{libs_text}</pre>")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📥 Kutubxona o‘rnatish", callback_data="pip_install_start")]
    ])
    await message.answer("Quyidagi tugmani bosib, kutubxona nomini yuboring:", reply_markup=keyboard)

# --- Callback: pip install boshlash ---
@dp.callback_query(F.data == "pip_install_start")
async def pip_install_start(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if is_user_banned(user_id):
        return await callback.answer("🚫 Siz banlangansiz.", show_alert=True)
    if not is_user_approved(user_id):
        return await callback.answer("⏳ Siz hali tasdiqlanmadingiz.", show_alert=True)

    pip_install_waiting.add(user_id)
    await callback.answer("📥 Kutubxona nomini yuboring.")
    await callback.message.answer("Iltimos, o‘rnatmoqchi bo‘lgan kutubxona nomini yuboring:")

# --- Kutubxona nomini qabul qilish ---
@dp.message()
async def handle_pip_install_lib(message: types.Message):
    user_id = message.from_user.id
    if user_id not in pip_install_waiting:
        return  # Fallback uchun boshqa xabarlarni qabul qilamiz

    lib_name = message.text.strip()
    if not lib_name:
        return await message.answer("❗ Iltimos, to‘g‘ri kutubxona nomini yuboring.")

    await message.answer(f"⌛ `{lib_name}` kutubxonasini o‘rnatish boshlandi, biroz kuting...")

    proc = await asyncio.create_subprocess_exec(
        "pip", "install", lib_name,
        stdout=PIPE, stderr=PIPE
    )
    stdout, stderr = await proc.communicate()

    pip_install_waiting.discard(user_id)

    out = stdout.decode()
    err = stderr.decode()
    result_msg = ""
    if out:
        result_msg += f"📥 Natija:\n<pre>{out}</pre>\n"
    if err:
        result_msg += f"⚠️ Xatolar:\n<pre>{err}</pre>"

    if not result_msg.strip():
        result_msg = "✅ O‘rnatish muvaffaqiyatli yakunlandi."

    if len(result_msg) > 4000:
        file_name = f"pip_install_{lib_name}.txt"
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(out + "\n" + err)
        await message.answer_document(types.FSInputFile(file_name), caption=f"`{lib_name}` o‘rnatish logi")
        os.remove(file_name)
    else:
        await message.answer(result_msg, parse_mode=ParseMode.HTML)

# --- /cancel komandasi ---
@dp.message(Command("cancel"))
async def cancel_pip_install(message: types.Message):
    user_id = message.from_user.id
    if user_id in pip_install_waiting:
        pip_install_waiting.discard(user_id)
        await message.answer("❌ Kutubxona o‘rnatish bekor qilindi.")
    else:
        await message.answer("⚠️ Bekor qilish uchun hech qanday jarayon mavjud emas.")

# --- Fallback boshqa xabarlar uchun ---
@dp.message()
async def fallback_message(message: types.Message):
    user_id = message.from_user.id

    if is_user_banned(user_id):
        return await message.answer("🚫 Siz banlangansiz.")
    if not is_user_approved(user_id):
        return await message.answer("⏳ Siz hali tasdiqlanmadingiz.")

    if user_id in pip_install_waiting:
        return await message.answer("❗ Iltimos, kutubxona nomini yuboring yoki /cancel bilan bekor qiling.")

    await message.answer("✅ Siz tasdiqlangansiz.\nIltimos, <b>.py</b> fayl yuboring.")

# --- Botni ishga tushurish ---
if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))