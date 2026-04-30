import sqlite3
import uuid
import asyncio

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

BOT_TOKEN = "8647406477:AAFHrFnnWe4jDop71hrVntLzgWFclGUN9bA"
ADMIN_ID = 7096713883

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== DB =====
conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS coupons (
    id TEXT PRIMARY KEY,
    name TEXT,
    price INTEGER,
    is_active INTEGER DEFAULT 1
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS coupon_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id TEXT,
    code TEXT,
    is_used INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    user_id INTEGER,
    coupon_id TEXT,
    amount INTEGER,
    status TEXT
)
""")

conn.commit()

# ===== HELPERS =====

def get_coupons():
    cursor.execute("SELECT id, name FROM coupons WHERE is_active=1")
    return cursor.fetchall()

def get_stock(cid):
    cursor.execute("SELECT COUNT(*) FROM coupon_codes WHERE coupon_id=? AND is_used=0", (cid,))
    return cursor.fetchone()[0]

def get_code(cid):
    cursor.execute("SELECT id, code FROM coupon_codes WHERE coupon_id=? AND is_used=0 LIMIT 1", (cid,))
    row = cursor.fetchone()
    if not row:
        return None
    id_, code = row
    cursor.execute("UPDATE coupon_codes SET is_used=1 WHERE id=?", (id_,))
    conn.commit()
    return code

# ===== START =====

@dp.message(Command("start"))
async def start(msg: types.Message):
    items = get_coupons()
    if not items:
        await msg.answer("❌ No coupons available.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"buy_{cid}")]
        for cid, name in items
    ])
    await msg.answer("🧾 Select Coupon:", reply_markup=kb)

# ===== SELECT =====

@dp.callback_query(F.data.startswith("buy_"))
async def select(call: types.CallbackQuery):
    cid = call.data.replace("buy_", "")

    cursor.execute("SELECT name, price FROM coupons WHERE id=?", (cid,))
    data = cursor.fetchone()
    if not data:
        return

    name, price = data
    stock = get_stock(cid)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Pay", callback_data=f"pay_{cid}")]
    ])

    await call.message.edit_text(
        f"🎯 {name}\n📦 Stock: {stock}\n💰 Price: ₹{price}",
        reply_markup=kb
    )

# ===== CREATE ORDER =====

@dp.callback_query(F.data.startswith("pay_"))
async def pay(call: types.CallbackQuery):
    cid = call.data.replace("pay_", "")

    cursor.execute("SELECT price FROM coupons WHERE id=?", (cid,))
    row = cursor.fetchone()
    if not row:
        return

    price = row[0]
    order_id = "ORD" + str(uuid.uuid4())[:6]

    cursor.execute(
        "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
        (order_id, call.from_user.id, cid, price, "pending")
    )
    conn.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ I've Paid", callback_data=f"paid_{order_id}")]
    ])

    await call.message.answer(
        f"💳 Pay via UPI\n\nUPI: yourupi@paytm\nAmount: ₹{price}\n\nOrder: {order_id}",
        reply_markup=kb
    )

# ===== USER PAID =====

@dp.callback_query(F.data.startswith("paid_"))
async def paid(call: types.CallbackQuery):
    order_id = call.data.replace("paid_", "")

    cursor.execute("UPDATE orders SET status='waiting' WHERE order_id=?", (order_id,))
    conn.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{order_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{order_id}")
        ]
    ])

    await bot.send_message(ADMIN_ID, f"🆕 Order: {order_id}", reply_markup=kb)
    await call.message.answer("⏳ Waiting for admin approval...")

# ===== APPROVE =====

@dp.callback_query(F.data.startswith("approve_"))
async def approve(call: types.CallbackQuery):
    order_id = call.data.replace("approve_", "")

    cursor.execute("SELECT user_id, coupon_id FROM orders WHERE order_id=?", (order_id,))
    row = cursor.fetchone()
    if not row:
        return

    user_id, cid = row
    code = get_code(cid)

    if not code:
        await bot.send_message(user_id, "❌ Out of stock")
        return

    await bot.send_message(user_id, f"🎉 Coupon:\n{code}")

    cursor.execute("UPDATE orders SET status='paid' WHERE order_id=?", (order_id,))
    conn.commit()

    await call.message.edit_text("✅ Approved & Delivered")

# ===== REJECT =====

@dp.callback_query(F.data.startswith("reject_"))
async def reject(call: types.CallbackQuery):
    order_id = call.data.replace("reject_", "")

    cursor.execute("SELECT user_id FROM orders WHERE order_id=?", (order_id,))
    row = cursor.fetchone()

    if row:
        await bot.send_message(row[0], "❌ Payment not received")

    cursor.execute("UPDATE orders SET status='rejected' WHERE order_id=?", (order_id,))
    conn.commit()

    await call.message.edit_text("❌ Rejected")

# ===== RUN =====

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
