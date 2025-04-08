import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
import random
import sqlite3
from datetime import datetime

# Thay YOUR_TOKEN bằng token bot của bạn từ BotFather
TOKEN = '7581133159:AAFEqSen9d32dCYVRO_pXLhPyIZW2gBb1Kk'
ADMIN_ID = 7780640154
GROUP_CHAT_IDS = ['@kenhchinhcoinrobot', '@nhomchatcoinrobot', '@odaycokeongon']  # Danh sách các nhóm
BOT_STOPPED = False  # Biến toàn cục để theo dõi trạng thái bot

# Khởi tạo cơ sở dữ liệu SQLite
def init_db():
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id INTEGER PRIMARY KEY, username TEXT, balance INTEGER, join_date TEXT, ref_count INTEGER, blocked INTEGER DEFAULT 0, joined_group INTEGER DEFAULT 0)''')
        try:
            c.execute("ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN joined_group INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        c.execute('''CREATE TABLE IF NOT EXISTS giftcodes 
                     (code TEXT PRIMARY KEY, value INTEGER, uses INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS withdrawals 
                     (user_id INTEGER, amount INTEGER, bank_info TEXT, status TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS menu_messages 
                     (user_id INTEGER PRIMARY KEY, message_id INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_giftcode_usage 
                     (user_id INTEGER, code TEXT, PRIMARY KEY (user_id, code))''')
        conn.commit()
    except Exception as e:
        print(f"❌ Lỗi khi khởi tạo cơ sở dữ liệu: {str(e)}")
    finally:
        conn.close()

# Lấy thông tin user
def get_user_info(user_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE id=?", (user_id,))
        user = c.fetchone()
        if not user:
            c.execute("INSERT INTO users (id, username, balance, join_date, ref_count, blocked, joined_group) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (user_id, '', 0, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 0, 0, 0))
            conn.commit()
            user = (user_id, '', 0, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 0, 0, 0)
        return user
    except Exception as e:
        print(f"❌ Lỗi khi lấy thông tin user {user_id}: {str(e)}")
        return None
    finally:
        conn.close()

# Kiểm tra user có bị chặn không
def is_blocked(user_id):
    user = get_user_info(user_id)
    return user[5] == 1 if user else False

# Kiểm tra user đã tham gia tất cả các nhóm chưa (dùng API Telegram)
def check_all_group_membership(context, user_id):
    for group_id in GROUP_CHAT_IDS:
        try:
            member = context.bot.get_chat_member(chat_id=group_id, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except telegram.error.TelegramError as e:
            print(f"❌ Lỗi khi kiểm tra nhóm {group_id} cho user {user_id}: {str(e)}")
            return False
    return True

# Kiểm tra user đã được đánh dấu tham gia tất cả nhóm chưa (trong cơ sở dữ liệu)
def has_joined_all_groups(user_id):
    user = get_user_info(user_id)
    return user[6] == 1 if user else False

# Cập nhật trạng thái tham gia nhóm
def set_joined_group(user_id, status):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("UPDATE users SET joined_group = ? WHERE id = ?", (status, user_id))
        conn.commit()
    except Exception as e:
        print(f"❌ Lỗi khi cập nhật trạng thái tham gia nhóm cho user {user_id}: {str(e)}")
    finally:
        conn.close()

# Kiểm tra user đã sử dụng giftcode chưa
def has_used_giftcode(user_id, code):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM user_giftcode_usage WHERE user_id=? AND code=?", (user_id, code))
        result = c.fetchone()
        return result is not None
    except Exception as e:
        print(f"❌ Lỗi khi kiểm tra giftcode usage cho user {user_id}: {str(e)}")
        return False
    finally:
        conn.close()

# Ghi lại việc sử dụng giftcode của user
def record_giftcode_usage(user_id, code):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT INTO user_giftcode_usage (user_id, code) VALUES (?, ?)", (user_id, code))
        conn.commit()
    except Exception as e:
        print(f"❌ Lỗi khi ghi lại giftcode usage cho user {user_id}: {str(e)}")
    finally:
        conn.close()

# Lấy message_id của menu cũ
def get_menu_message_id(user_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT message_id FROM menu_messages WHERE user_id=?", (user_id,))
        result = c.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"❌ Lỗi khi lấy message_id cho user {user_id}: {str(e)}")
        return None
    finally:
        conn.close()

# Lưu message_id của menu mới
def save_menu_message_id(user_id, message_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO menu_messages (user_id, message_id) VALUES (?, ?)", (user_id, message_id))
        conn.commit()
    except Exception as e:
        print(f"❌ Lỗi khi lưu message_id cho user {user_id}: {str(e)}")
    finally:
        conn.close()

# Xóa menu cũ nếu có
def delete_old_menu(context, user_id, chat_id):
    old_message_id = get_menu_message_id(user_id)
    if old_message_id:
        try:
            context.bot.delete_message(chat_id=chat_id, message_id=old_message_id)
        except Exception as e:
            print(f"❌ Lỗi khi xóa menu cũ cho user {user_id}: {str(e)}")

# Yêu cầu tham gia tất cả nhóm
def request_join_all_groups(update, context, user_id):
    keyboard = [
        [InlineKeyboardButton(f"📢 Tham gia {GROUP_CHAT_IDS[0]}", url=f"https://t.me/{GROUP_CHAT_IDS[0][1:]}")],
        [InlineKeyboardButton(f"📢 Tham gia {GROUP_CHAT_IDS[1]}", url=f"https://t.me/{GROUP_CHAT_IDS[1][1:]}")],
        [InlineKeyboardButton(f"📢 Tham gia {GROUP_CHAT_IDS[2]}", url=f"https://t.me/{GROUP_CHAT_IDS[2][1:]}")],
        [InlineKeyboardButton("✅ Xác nhận", callback_data='verify_group')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        update.message.reply_text(
            f"📌 *Vui lòng tham gia tất cả các nhóm sau để sử dụng bot!*\n"
            f"👉 Nhấn nút bên dưới để tham gia từng nhóm, sau đó nhấn 'Xác nhận'.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        update.callback_query.message.edit_text(
            f"📌 *Vui lòng tham gia tất cả các nhóm sau để sử dụng bot!*\n"
            f"👉 Nhấn nút bên dưới để tham gia từng nhóm, sau đó nhấn 'Xác nhận'.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

# Menu chính
def main_menu(update, context, user_id, chat_id):
    global BOT_STOPPED
    if BOT_STOPPED and user_id != ADMIN_ID:
        update.message.reply_text("⛔ *Bot hiện đang tạm dừng hoạt động!* Vui lòng chờ admin khởi động lại.", parse_mode=ParseMode.MARKDOWN)
        return
    if is_blocked(user_id):
        update.message.reply_text("🚫 *Tài khoản của bạn đã bị chặn!* Vui lòng liên hệ admin để được hỗ trợ!", parse_mode=ParseMode.MARKDOWN)
        return
    if not has_joined_all_groups(user_id):
        request_join_all_groups(update, context, user_id)
        return
    keyboard = [
        [InlineKeyboardButton("👤 Tài khoản", callback_data='account'),
         InlineKeyboardButton("💸 Rút tiền", callback_data='withdraw')],
        [InlineKeyboardButton("📩 Mời bạn bè", callback_data='invite'),
         InlineKeyboardButton("🎰 Vòng quay", callback_data='spin')],
        [InlineKeyboardButton("🎁 Giftcode", callback_data='giftcode')]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("📊 Thống kê", callback_data='stats'),
                         InlineKeyboardButton("📜 Danh sách lệnh", callback_data='admin_commands')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        delete_old_menu(context, user_id, chat_id)
        message = update.message.reply_text(
            "✨ *Chào mừng bạn đến với Bot!* ✨\nChọn một tính năng bên dưới để bắt đầu:", 
            reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
        )
        save_menu_message_id(user_id, message.message_id)
    else:
        update.callback_query.message.edit_text(
            "✨ *Chào mừng bạn đến với Bot!* ✨\nChọn một tính năng bên dưới để bắt đầu:", 
            reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
        )

# Xử lý nút
def button(update, context):
    global BOT_STOPPED
    query = update.callback_query
    user_id = query.from_user.id
    if BOT_STOPPED and user_id != ADMIN_ID:
        query.message.edit_text("⛔ *Bot hiện đang tạm dừng hoạt động!* Vui lòng chờ admin khởi động lại.", parse_mode=ParseMode.MARKDOWN)
        return
    if is_blocked(user_id):
        query.message.edit_text("🚫 *Tài khoản của bạn đã bị chặn!* Vui lòng liên hệ admin để được hỗ trợ!", parse_mode=ParseMode.MARKDOWN)
        return

    if query.data == 'verify_group':
        if check_all_group_membership(context, user_id):
            set_joined_group(user_id, 1)
            main_menu(update, context, user_id, query.message.chat_id)
        else:
            query.message.edit_text(
                "❌ *Bạn chưa tham gia đủ tất cả các nhóm!* Vui lòng tham gia tất cả trước khi xác nhận.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"📢 Tham gia {GROUP_CHAT_IDS[0]}", url=f"https://t.me/{GROUP_CHAT_IDS[0][1:]}")],
                    [InlineKeyboardButton(f"📢 Tham gia {GROUP_CHAT_IDS[1]}", url=f"https://t.me/{GROUP_CHAT_IDS[1][1:]}")],
                    [InlineKeyboardButton(f"📢 Tham gia {GROUP_CHAT_IDS[2]}", url=f"https://t.me/{GROUP_CHAT_IDS[2][1:]}")],
                    [InlineKeyboardButton("✅ Xác nhận", callback_data='verify_group')]
                ]),
                parse_mode=ParseMode.MARKDOWN
            )
        return

    if not has_joined_all_groups(user_id):
        request_join_all_groups(update, context, user_id)
        return

    user = get_user_info(user_id)
    if not user:
        query.message.edit_text("❌ *Lỗi khi lấy thông tin user!* Vui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)
        return

    if query.data == 'account':
        text = (f"👤 *Thông tin tài khoản* 👤\n"
                f"📛 *Tên*: {user[1] if user[1] else 'N/A'}\n"
                f"🆔 *ID*: {user[0]}\n"
                f"💰 *Số dư*: {user[2]} xu\n"
                f"📅 *Tham gia*: {user[3]}")
        query.message.edit_text(
            text, 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data='back')]]), 
            parse_mode=ParseMode.MARKDOWN
        )

    elif query.data == 'withdraw':
        text = (f"💸 *Rút tiền* 💸\n"
                f"💰 *Số dư*: {user[2]} xu\n"
                f"📉 *Rút tối thiểu*: 400,000 xu\n"
                f"🔄 *Tỉ lệ*: 100,000 xu = 1,500 VND\n"
                f"📝 *Lệnh rút*: `/bank số_xu STK ngân_hàng tên`")
        query.message.edit_text(
            text, 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data='back')]]), 
            parse_mode=ParseMode.MARKDOWN
        )

    elif query.data == 'invite':
        try:
            bot_username = context.bot.username
            if not bot_username:
                raise ValueError("Bot chưa được đặt username! Vui lòng đặt username qua BotFather.")
            ref_link = f"https://t.me/{bot_username}?start={user_id}"
            share_button = InlineKeyboardButton(
                "📤 Chia sẻ link", 
                url=f"https://t.me/share/url?url={ref_link}&text=Mời bạn tham gia bot để nhận thưởng 50,000 xu!"
            )
            keyboard = [
                [share_button],
                [InlineKeyboardButton("🔙 Quay lại", callback_data='back')]
            ]
            text = (f"📩 *Mời bạn bè* 📩\n"
                    f"🔗 *Link mời*: `{ref_link}`\n"
                    f"🎁 *Thưởng*: 50,000 xu/người\n"
                    f"📌 Nhấn nút bên dưới để chia sẻ link!")
            query.message.edit_text(
                text, 
                reply_markup=InlineKeyboardMarkup(keyboard), 
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            query.message.edit_text(
                f"❌ *Lỗi khi tạo link mời!* Vui lòng thử lại sau.\nChi tiết lỗi: {str(e)}\n📌 Vui lòng kiểm tra xem bot đã được đặt username qua BotFather chưa!", 
                parse_mode=ParseMode.MARKDOWN
            )

    elif query.data == 'spin':
        text = (f"🎰 *Vòng quay may mắn* 🎰\n"
                f"📋 *Yêu cầu*: Mời 6 user để nhận 1 lượt quay\n"
                f"🎮 *Tham gia*: Nhập `/quay`")
        query.message.edit_text(
            text, 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data='back')]]), 
            parse_mode=ParseMode.MARKDOWN
        )

    elif query.data == 'giftcode':
        text = (f"🎁 *Giftcode* 🎁\n"
                f"📝 *Nhập code*: `/giftcode mã_code`")
        query.message.edit_text(
            text, 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data='back')]]), 
            parse_mode=ParseMode.MARKDOWN
        )

    elif query.data == 'stats' and user_id == ADMIN_ID:
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("SELECT id, username, balance, ref_count FROM users")
            users = c.fetchall()
            conn.close()
            
            if not users:
                text = "📊 *Thống kê user* 📊\nChưa có người dùng nào trong hệ thống!"
            else:
                text = "📊 *Thống kê user* 📊\n"
                text += "┌───────────────┬───────────────┬───────────────┬───────────────┐\n"
                text += "│ 🆔 ID         │ 📛 User       │ 💰 Số dư      │ 📩 Người mời  │\n"
                text += "├───────────────┼───────────────┼───────────────┼───────────────┤\n"
                for u in users:
                    user_id, username, balance, ref_count = u
                    username = (username if username else 'N/A')[:10]  # Giới hạn độ dài username
                    text += f"│ {user_id:<13} │ {username:<13} │ {balance:<13} │ {ref_count:<13} │\n"
                text += "└───────────────┴───────────────┴───────────────┴───────────────┘"
            query.message.edit_text(
                text, 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data='back')]]), 
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            query.message.edit_text(
                f"❌ *Lỗi khi truy xuất thống kê!* Chi tiết: {str(e)}\nVui lòng thử lại sau.", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data='back')]]), 
                parse_mode=ParseMode.MARKDOWN
            )

    elif query.data == 'admin_commands' and user_id == ADMIN_ID:
        text = ("📜 *Danh sách lệnh admin* 📜\n"
                "🔹 `/code nội_dung số_xu lượt_nhập` - Tạo giftcode\n"
                "🔹 `/send alluser/id_user nội_dung` - Gửi thông báo\n"
                "🔹 `/block id_user` - Chặn người dùng\n"
                "🔹 `/unblock id_user` - Mở chặn người dùng\n"
                "🔹 `/user` - Xem danh sách tất cả user\n"
                "🔹 `/ktracode mã_code` - Kiểm tra thông tin giftcode\n"
                "🔹 `/stop` - Tạm dừng bot với tất cả user (trừ admin)\n"
                "🔹 `/unstop` - Khởi động lại bot")
        query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Quay lại", callback_data='back')]]),
            parse_mode=ParseMode.MARKDOWN
        )

    elif query.data == 'back':
        main_menu(update, context, user_id, query.message.chat_id)

# Xử lý lệnh /start
def start(update, context):
    global BOT_STOPPED
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if BOT_STOPPED and user_id != ADMIN_ID:
        update.message.reply_text("⛔ *Bot hiện đang tạm dừng hoạt động!* Vui lòng chờ admin khởi động lại.", parse_mode=ParseMode.MARKDOWN)
        return
    if is_blocked(user_id):
        update.message.reply_text("🚫 *Tài khoản của bạn đã bị chặn!* Vui lòng liên hệ admin để được hỗ trợ!", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("UPDATE users SET username = ? WHERE id = ?", (update.message.from_user.username or 'N/A', user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Lỗi khi cập nhật username cho user {user_id}: {str(e)}")
        update.message.reply_text("❌ *Lỗi hệ thống!* Vui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)
        return

    if len(context.args) > 0:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id and has_joined_all_groups(referrer_id):  # Chỉ cộng thưởng nếu referrer đã tham gia đủ nhóm
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute("UPDATE users SET ref_count = ref_count + 1, balance = balance + 50000 WHERE id=?", (referrer_id,))
                conn.commit()
                conn.close()
                try:
                    context.bot.send_message(
                        referrer_id, 
                        f"🎉 *Chúc mừng!* Bạn đã mời thành công *{update.message.from_user.username or 'N/A'}*!\n💰 Bạn nhận được *50,000 xu*!", 
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    update.message.reply_text(
                        f"⚠️ *Không thể gửi thông báo đến người mời!* (ID: {referrer_id})\nChi tiết lỗi: {str(e)}", 
                        parse_mode=ParseMode.MARKDOWN
                    )
        except ValueError:
            update.message.reply_text("❌ *Link mời không hợp lệ!*", parse_mode=ParseMode.MARKDOWN)
    if not has_joined_all_groups(user_id):
        request_join_all_groups(update, context, user_id)
    else:
        main_menu(update, context, user_id, chat_id)

# Xử lý lệnh /menu
def show_menu(update, context):
    global BOT_STOPPED
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if BOT_STOPPED and user_id != ADMIN_ID:
        update.message.reply_text("⛔ *Bot hiện đang tạm dừng hoạt động!* Vui lòng chờ admin khởi động lại.", parse_mode=ParseMode.MARKDOWN)
        return
    if is_blocked(user_id):
        update.message.reply_text("🚫 *Tài khoản của bạn đã bị chặn!* Vui lòng liên hệ admin để được hỗ trợ!", parse_mode=ParseMode.MARKDOWN)
        return
    if not has_joined_all_groups(user_id):
        request_join_all_groups(update, context, user_id)
        return
    main_menu(update, context, user_id, chat_id)

# Xử lý lệnh /bank
def bank(update, context):
    global BOT_STOPPED
    user_id = update.message.from_user.id
    if BOT_STOPPED and user_id != ADMIN_ID:
        update.message.reply_text("⛔ *Bot hiện đang tạm dừng hoạt động!* Vui lòng chờ admin khởi động lại.", parse_mode=ParseMode.MARKDOWN)
        return
    if is_blocked(user_id):
        update.message.reply_text("🚫 *Tài khoản của bạn đã bị chặn!* Vui lòng liên hệ admin để được hỗ trợ!", parse_mode=ParseMode.MARKDOWN)
        return
    if not has_joined_all_groups(user_id):
        request_join_all_groups(update, context, user_id)
        return
    user = get_user_info(user_id)
    if not user:
        update.message.reply_text("❌ *Lỗi khi lấy thông tin user!* Vui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)
        return
    args = context.args
    if len(args) < 4:
        update.message.reply_text("❌ *Sai định dạng!* Vui lòng nhập: `/bank số_xu STK ngân_hàng tên`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        amount = int(args[0])
        if user[2] < amount or amount < 400000:
            update.message.reply_text("❌ *Số dư không đủ!* Cần tối thiểu *400,000 xu* để rút!", parse_mode=ParseMode.MARKDOWN)
            return
        bank_info = ' '.join(args[1:])
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT INTO withdrawals (user_id, amount, bank_info, status) VALUES (?, ?, ?, ?)", 
                  (user_id, amount, bank_info, 'pending'))
        c.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, user_id))
        conn.commit()
        conn.close()
        keyboard = [
            [InlineKeyboardButton("✅ Duyệt", callback_data=f'approve_{user_id}_{amount}'),
             InlineKeyboardButton("❌ Chối", callback_data=f'deny_{user_id}_{amount}')]
        ]
        context.bot.send_message(
            ADMIN_ID, 
            f"📋 *Yêu cầu rút tiền từ {user_id}*\n💰 *Số xu*: {amount}\n🏦 *Thông tin*: {bank_info}", 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode=ParseMode.MARKDOWN
        )
        update.message.reply_text("✅ *Yêu cầu rút tiền đã được gửi!* Vui lòng chờ admin duyệt.", parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        update.message.reply_text("❌ *Số xu không hợp lệ!* Vui lòng nhập số nguyên.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        update.message.reply_text(f"❌ *Lỗi hệ thống!* Chi tiết: {str(e)}\nVui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)

# Xử lý duyệt/chối rút tiền
def handle_withdrawal(update, context):
    query = update.callback_query
    data = query.data.split('_')
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    if data[0] == 'approve':
        user_id, amount = int(data[1]), int(data[2])
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("UPDATE withdrawals SET status = 'approved' WHERE user_id=? AND amount=?", (user_id, amount))
            conn.commit()
            conn.close()
            context.bot.send_message(
                user_id, 
                f"✅ *Đơn rút tiền thành công!*\n💰 *Số xu*: {amount}\n📌 Vui lòng kiểm tra tài khoản!", 
                parse_mode=ParseMode.MARKDOWN
            )
            # Xóa tin nhắn yêu cầu rút tiền
            try:
                context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except telegram.error.TelegramError as e:
                print(f"❌ Lỗi khi xóa tin nhắn yêu cầu rút tiền: {str(e)}")
            # Gửi thông báo đến tất cả user không bị chặn
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("SELECT id FROM users WHERE blocked=0")
            users = c.fetchall()
            conn.close()
            for user in users:
                if user[0] == user_id:  # Bỏ qua user đã gửi yêu cầu (vì đã nhận thông báo riêng)
                    continue
                try:
                    context.bot.send_message(
                        user[0], 
                        f"📢 *Thông báo rút tiền* 📢\n✅ Admin đã duyệt đơn rút *{amount} xu* của user *{user_id}*!", 
                        parse_mode=ParseMode.MARKDOWN
                    )
                except telegram.error.TelegramError as e:
                    print(f"❌ Lỗi khi gửi thông báo rút tiền đến user {user[0]}: {str(e)}")
        except Exception as e:
            print(f"❌ Lỗi khi duyệt đơn rút tiền cho user {user_id}: {str(e)}")

    elif data[0] == 'deny':
        user_id, amount = int(data[1]), int(data[2])
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("UPDATE withdrawals SET status = 'denied' WHERE user_id=? AND amount=?", (user_id, amount))
            c.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, user_id))
            conn.commit()
            conn.close()
            context.bot.send_message(
                user_id, 
                f"❌ *Đơn rút {amount} xu bị từ chối!*\n📌 Số xu đã được hoàn lại.", 
                parse_mode=ParseMode.MARKDOWN
            )
            # Xóa tin nhắn yêu cầu rút tiền
            try:
                context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except telegram.error.TelegramError as e:
                print(f"❌ Lỗi khi xóa tin nhắn yêu cầu rút tiền: {str(e)}")
            # Gửi thông báo đến tất cả user không bị chặn
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("SELECT id FROM users WHERE blocked=0")
            users = c.fetchall()
            conn.close()
            for user in users:
                if user[0] == user_id:  # Bỏ qua user đã gửi yêu cầu (vì đã nhận thông báo riêng)
                    continue
                try:
                    context.bot.send_message(
                        user[0], 
                        f"📢 *Thông báo rút tiền* 📢\n❌ Admin đã từ chối đơn rút *{amount} xu* của user *{user_id}*!", 
                        parse_mode=ParseMode.MARKDOWN
                    )
                except telegram.error.TelegramError as e:
                    print(f"❌ Lỗi khi gửi thông báo rút tiền đến user {user[0]}: {str(e)}")
        except Exception as e:
            print(f"❌ Lỗi khi từ chối đơn rút tiền cho user {user_id}: {str(e)}")

# Xử lý lệnh /quay
def spin(update, context):
    global BOT_STOPPED
    user_id = update.message.from_user.id
    if BOT_STOPPED and user_id != ADMIN_ID:
        update.message.reply_text("⛔ *Bot hiện đang tạm dừng hoạt động!* Vui lòng chờ admin khởi động lại.", parse_mode=ParseMode.MARKDOWN)
        return
    if is_blocked(user_id):
        update.message.reply_text("🚫 *Tài khoản của bạn đã bị chặn!* Vui lòng liên hệ admin để được hỗ trợ!", parse_mode=ParseMode.MARKDOWN)
        return
    if not has_joined_all_groups(user_id):
        request_join_all_groups(update, context, user_id)
        return
    user = get_user_info(user_id)
    if not user:
        update.message.reply_text("❌ *Lỗi khi lấy thông tin user!* Vui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)
        return
    if user[4] < 6:
        update.message.reply_text("❌ *Chưa đủ điều kiện!* Bạn cần mời ít nhất *6 người* để quay!", parse_mode=ParseMode.MARKDOWN)
        return
    prize = random.randint(1000, 5000)
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + ?, ref_count = ref_count - 6 WHERE id=?", (prize, user_id))
        conn.commit()
        conn.close()
        update.message.reply_text(
            f"🎉 *Chúc mừng!* Bạn quay trúng *{prize} xu*! 🎰\n💰 Số dư mới: *{user[2] + prize} xu*", 
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        update.message.reply_text(f"❌ *Lỗi hệ thống!* Chi tiết: {str(e)}\nVui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)

# Xử lý lệnh /giftcode
def giftcode(update, context):
    global BOT_STOPPED
    user_id = update.message.from_user.id
    if BOT_STOPPED and user_id != ADMIN_ID:
        update.message.reply_text("⛔ *Bot hiện đang tạm dừng hoạt động!* Vui lòng chờ admin khởi động lại.", parse_mode=ParseMode.MARKDOWN)
        return
    if is_blocked(user_id):
        update.message.reply_text("🚫 *Tài khoản của bạn đã bị chặn!* Vui lòng liên hệ admin để được hỗ trợ!", parse_mode=ParseMode.MARKDOWN)
        return
    if not has_joined_all_groups(user_id):
        request_join_all_groups(update, context, user_id)
        return
    if len(context.args) < 1:
        update.message.reply_text("❌ *Sai định dạng!* Vui lòng nhập: `/giftcode mã_code`", parse_mode=ParseMode.MARKDOWN)
        return
    code = context.args[0]
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM giftcodes WHERE code=?", (code,))
        gift = c.fetchone()
        if not gift:
            update.message.reply_text("❌ *Mã giftcode không tồn tại!* Vui lòng kiểm tra lại.", parse_mode=ParseMode.MARKDOWN)
            conn.close()
            return
        if gift[2] <= 0:
            update.message.reply_text("😔 *Mã đã hết lượt sử dụng!* Chúc bạn may mắn lần sau!", parse_mode=ParseMode.MARKDOWN)
            conn.close()
            return
        if has_used_giftcode(user_id, code):
            update.message.reply_text("❌ *Bạn đã sử dụng mã này rồi!* Mỗi người chỉ được sử dụng một mã một lần.", parse_mode=ParseMode.MARKDOWN)
            conn.close()
            return
        c.execute("UPDATE giftcodes SET uses = uses - 1 WHERE code=?", (code,))
        c.execute("UPDATE users SET balance = balance + ? WHERE id=?", (gift[1], user_id))
        record_giftcode_usage(user_id, code)
        conn.commit()
        conn.close()
        update.message.reply_text(
            f"🎁 *Nhận thành công!* Bạn được *{gift[1]} xu* từ mã *{code}*!", 
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        update.message.reply_text(f"❌ *Lỗi hệ thống!* Chi tiết: {str(e)}\nVui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)

# Xử lý lệnh /ktracode (admin) - Kiểm tra thông tin giftcode
def check_giftcode(update, context):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        update.message.reply_text("❌ *Bạn không có quyền sử dụng lệnh này!* Chỉ admin mới có thể sử dụng.", parse_mode=ParseMode.MARKDOWN)
        return
    if len(context.args) < 1:
        update.message.reply_text("❌ *Sai định dạng!* Vui lòng nhập: `/ktracode mã_code`", parse_mode=ParseMode.MARKDOWN)
        return
    code = context.args[0]
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM giftcodes WHERE code=?", (code,))
        gift = c.fetchone()
        if not gift:
            update.message.reply_text("❌ *Mã giftcode không tồn tại!* Vui lòng kiểm tra lại.", parse_mode=ParseMode.MARKDOWN)
            conn.close()
            return
        c.execute("SELECT user_id FROM user_giftcode_usage WHERE code=?", (code,))
        users = c.fetchall()
        conn.close()
        text = (f"🎁 *Thông tin giftcode* 🎁\n"
                f"📌 *Mã*: {code}\n"
                f"💰 *Giá trị*: {gift[1]} xu\n"
                f"🔄 *Lượt nhập còn lại*: {gift[2]}\n"
                f"👥 *Người đã sử dụng*: \n")
        if not users:
            text += "Chưa có ai sử dụng mã này."
        else:
            for user in users:
                user_info = get_user_info(user[0])
                if user_info:
                    text += f"- {user_info[1] if user_info[1] else 'N/A'} (ID: {user_info[0]})\n"
                else:
                    text += f"- User ID: {user[0]} (Không tìm thấy thông tin)\n"
        update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        update.message.reply_text(f"❌ *Lỗi hệ thống!* Chi tiết: {str(e)}\nVui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)

# Xử lý lệnh /code (admin)
def create_giftcode(update, context):
    if update.message.from_user.id != ADMIN_ID:
        return
    args = context.args
    if len(args) < 3:
        update.message.reply_text("❌ *Sai định dạng!* Vui lòng nhập: `/code nội_dung số_xu lượt_nhập`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        code, value, uses = args[0], int(args[1]), int(args[2])
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO giftcodes (code, value, uses) VALUES (?, ?, ?)", (code, value, uses))
        conn.commit()
        conn.close()
        update.message.reply_text(
            f"🎁 *Tạo giftcode thành công!*\n📌 *Mã*: {code}\n💰 *Giá trị*: {value} xu\n🔄 *Lượt nhập*: {uses}", 
            parse_mode=ParseMode.MARKDOWN
        )
        # Gửi thông báo đến tất cả user không bị chặn
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE blocked=0")
        users = c.fetchall()
        conn.close()
        for user in users:
            try:
                context.bot.send_message(
                    user[0], 
                    f"🎉 *Giftcode mới!* 🎉\n📌 *Mã*: {code}\n💰 *Giá trị*: {value} xu\n🔄 *Lượt nhập còn lại*: {uses}\nNhanh tay nhập code bằng lệnh `/giftcode {code}`!", 
                    parse_mode=ParseMode.MARKDOWN
                )
            except telegram.error.TelegramError as e:
                print(f"❌ Lỗi khi gửi thông báo giftcode đến user {user[0]}: {str(e)}")
    except ValueError:
        update.message.reply_text("❌ *Số xu hoặc lượt nhập không hợp lệ!* Vui lòng nhập số nguyên.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        update.message.reply_text(f"❌ *Lỗi hệ thống!* Chi tiết: {str(e)}\nVui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)

# Xử lý lệnh /send (admin)
def send_message(update, context):
    if update.message.from_user.id != ADMIN_ID:
        return
    args = context.args
    if len(args) < 2:
        update.message.reply_text("❌ *Sai định dạng!* Vui lòng nhập: `/send alluser/id_user nội_dung`", parse_mode=ParseMode.MARKDOWN)
        return
    target = args[0]
    message = ' '.join(args[1:])
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        if target == 'alluser':
            c.execute("SELECT id FROM users WHERE blocked=0")
            users = c.fetchall()
            for user in users:
                try:
                    context.bot.send_message(user[0], f"📢 *Thông báo từ admin* 📢\n{message}", parse_mode=ParseMode.MARKDOWN)
                except telegram.error.TelegramError as e:
                    print(f"❌ Lỗi khi gửi thông báo đến user {user[0]}: {str(e)}")
            update.message.reply_text("✅ *Đã gửi tin nhắn đến tất cả user!*", parse_mode=ParseMode.MARKDOWN)
        else:
            user_id = int(target)
            context.bot.send_message(user_id, f"📢 *Thông báo từ admin* 📢\n{message}", parse_mode=ParseMode.MARKDOWN)
            update.message.reply_text(f"✅ *Đã gửi tin nhắn đến user {user_id}!*", parse_mode=ParseMode.MARKDOWN)
        conn.close()
    except ValueError:
        update.message.reply_text("❌ *ID user không hợp lệ!*", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        update.message.reply_text(f"❌ *Lỗi hệ thống!* Chi tiết: {str(e)}\nVui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)

# Xử lý lệnh /block (admin)
def block_user(update, context):
    if update.message.from_user.id != ADMIN_ID:
        return
    args = context.args
    if len(args) < 1:
        update.message.reply_text("❌ *Sai định dạng!* Vui lòng nhập: `/block id_user`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        user_id = int(args[0])
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("UPDATE users SET blocked = 1 WHERE id=?", (user_id,))
        conn.commit()
        conn.close()
        context.bot.send_message(
            user_id, 
            "🚫 *Tài khoản của bạn đã bị chặn!* Vui lòng liên hệ admin để được hỗ trợ!", 
            parse_mode=ParseMode.MARKDOWN
        )
        update.message.reply_text(f"✅ *Đã chặn user {user_id}!*", parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        update.message.reply_text("❌ *ID user không hợp lệ!*", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        update.message.reply_text(f"❌ *Lỗi hệ thống!* Chi tiết: {str(e)}\nVui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)

# Xử lý lệnh /unblock (admin)
def unblock_user(update, context):
    if update.message.from_user.id != ADMIN_ID:
        return
    args = context.args
    if len(args) < 1:
        update.message.reply_text("❌ *Sai định dạng!* Vui lòng nhập: `/unblock id_user`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        user_id = int(args[0])
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("UPDATE users SET blocked = 0 WHERE id=?", (user_id,))
        conn.commit()
        conn.close()
        context.bot.send_message(
            user_id, 
            "✅ *Tài khoản của bạn đã được mở chặn!* Bạn có thể sử dụng bot như bình thường!", 
            parse_mode=ParseMode.MARKDOWN
        )
        update.message.reply_text(f"✅ *Đã mở chặn user {user_id}!*", parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        update.message.reply_text("❌ *ID user không hợp lệ!*", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        update.message.reply_text(f"❌ *Lỗi hệ thống!* Chi tiết: {str(e)}\nVui lòng thử lại sau.", parse_mode=ParseMode.MARKDOWN)

# Xử lý lệnh /user (admin) - Hiển thị danh sách tất cả user
def list_users(update, context):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        update.message.reply_text("❌ *Bạn không có quyền sử dụng lệnh này!* Chỉ admin mới có thể sử dụng.", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT id, username, balance, ref_count FROM users")
        users = c.fetchall()
        conn.close()
        
        if not users:
            update.message.reply_text("📋 *Danh sách user* 📋\nChưa có người dùng nào trong hệ thống!", parse_mode=ParseMode.MARKDOWN)
        else:
            text = "📋 *Danh sách user* 📋\n"
            text += "┌───────────────┬───────────────┬───────────────┬───────────────┐\n"
            text += "│ 🆔 ID         │ 📛 User       │ 💰 Số dư      │ 📩 Người mời  │\n"
            text += "├───────────────┼───────────────┼───────────────┼───────────────┤\n"
            for u in users:
                user_id, username, balance, ref_count = u
                username = (username if username else 'N/A')[:10]  # Giới hạn độ dài username
                text += f"│ {user_id:<13} │ {username:<13} │ {balance:<13} │ {ref_count:<13} │\n"
            text += "└───────────────┴───────────────┴───────────────┴───────────────┘"
            update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        update.message.reply_text(
            f"❌ *Lỗi khi truy xuất danh sách user!* Chi tiết: {str(e)}\nVui lòng thử lại sau.", 
            parse_mode=ParseMode.MARKDOWN
        )

# Xử lý lệnh /stop (admin) - Tạm dừng bot với tất cả user trừ admin
def stop_bot(update, context):
    global BOT_STOPPED
    if update.message.from_user.id != ADMIN_ID:
        update.message.reply_text("❌ *Bạn không có quyền sử dụng lệnh này!* Chỉ admin mới có thể sử dụng.", parse_mode=ParseMode.MARKDOWN)
        return
    if BOT_STOPPED:
        update.message.reply_text("⛔ *Bot đã đang tạm dừng!* Sử dụng `/unstop` để khởi động lại.", parse_mode=ParseMode.MARKDOWN)
    else:
        BOT_STOPPED = True
        update.message.reply_text("⛔ *Bot đã tạm dừng hoạt động với tất cả user (trừ admin)!* Sử dụng `/unstop` để khởi động lại.", parse_mode=ParseMode.MARKDOWN)

# Xử lý lệnh /unstop (admin) - Khởi động lại bot
def unstop_bot(update, context):
    global BOT_STOPPED
    if update.message.from_user.id != ADMIN_ID:
        update.message.reply_text("❌ *Bạn không có quyền sử dụng lệnh này!* Chỉ admin mới có thể sử dụng.", parse_mode=ParseMode.MARKDOWN)
        return
    if not BOT_STOPPED:
        update.message.reply_text("✅ *Bot đang hoạt động!* Không cần khởi động lại.", parse_mode=ParseMode.MARKDOWN)
    else:
        BOT_STOPPED = False
        update.message.reply_text("✅ *Bot đã được khởi động lại!* Tất cả user có thể sử dụng bình thường.", parse_mode=ParseMode.MARKDOWN)

def main():
    init_db()
    try:
        updater = Updater(TOKEN, use_context=True)
    except Exception as e:
        print(f"❌ Lỗi khi khởi động bot: {str(e)}\nKiểm tra token hoặc kết nối mạng!")
        return
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("menu", show_menu))
    dp.add_handler(CommandHandler("bank", bank))
    dp.add_handler(CommandHandler("quay", spin))
    dp.add_handler(CommandHandler("giftcode", giftcode))
    dp.add_handler(CommandHandler("code", create_giftcode))
    dp.add_handler(CommandHandler("ktracode", check_giftcode))
    dp.add_handler(CommandHandler("send", send_message))
    dp.add_handler(CommandHandler("block", block_user))
    dp.add_handler(CommandHandler("unblock", unblock_user))
    dp.add_handler(CommandHandler("user", list_users))
    dp.add_handler(CommandHandler("stop", stop_bot))
    dp.add_handler(CommandHandler("unstop", unstop_bot))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(CallbackQueryHandler(handle_withdrawal, pattern='^(approve|deny)_'))
    print("✅ Bot đang khởi động...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()