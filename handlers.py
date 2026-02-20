# handlers.py
import datetime
import random
from telebot import types
from loader import bot
from config import ADMIN_ID, VIP_LEVELS
from database import get_user_context, modify_user_data, get_data_snapshot, save_data_snapshot, log_transaction, log_admin_action, get_system_stats, add_withdrawal_request
from keyboards import main_menu_keyboard, create_bet_keyboard
from games import process_game_result
from utils import check_cooldown

# --- MAIN MENU & NAVIGATION ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    _, user = get_user_context(user_id)
    
    # Check Ban
    if not check_ban_status(user, message): return
    
    # Force Bank Link
    if 'bank_info' not in user:
        msg = bot.reply_to(message, "👋 Chào mừng! Để bảo mật và rút tiền nhanh chóng, bạn cần liên kết ngân hàng trước khi chơi.\n\n🏦 Nhập Tên Ngân Hàng của bạn (Ví dụ: MB Bank):")
        bot.register_next_step_handler(msg, process_link_bank_name)
        return

    bot.reply_to(message, 
        f"👋 **XIN CHÀO {message.from_user.first_name}** 👋\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"💰 **Số dư:** `{user['balance']:,} VND`\n"
        f"💎 **Trạng thái:** _Đã liên kết_\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👇 _Chọn chức năng bên dưới:_", 
        reply_markup=main_menu_keyboard(user_id), parse_mode="Markdown")

def process_link_bank_name(message):
    bank_name = message.text
    msg = bot.reply_to(message, "💳 Nhập Số Tài Khoản (STK):")
    bot.register_next_step_handler(msg, process_link_bank_stk, bank_name)

def process_link_bank_stk(message, bank_name):
    stk = message.text
    msg = bot.reply_to(message, "👤 Nhập Tên Chủ Tài Khoản (CTK) (Viết hoa không dấu):")
    bot.register_next_step_handler(msg, process_link_stk_final, bank_name, stk)

def process_link_stk_final(message, bank_name, stk):
    ctk = message.text.upper().strip()
    # Basic Validation
    if len(bank_name) > 50 or len(stk) > 30 or len(ctk) > 50:
         bot.reply_to(message, "❌ Thông tin quá dài! Vui lòng nhập lại.")
         return
    if not stk.isdigit():
         bot.reply_to(message, "❌ Số tài khoản chỉ được chứa số!")
         return
    
    user_id = message.from_user.id
    
    def bank_link_logic(user):
        user['bank_info'] = {
            'bank': bank_name,
            'stk': stk,
            'ctk': ctk
        }
        return True

    modify_user_data(user_id, bank_link_logic)
    
    bot.reply_to(message, "✅ Liên kết thành công! Hãy bắt đầu trải nghiệm.", reply_markup=main_menu_keyboard(user_id))

# Decorator-like check for callback
def check_bank_linked(user, call):
    if 'bank_info' not in user:
        bot.answer_callback_query(call.id, "⚠️ Vui lòng gõ /start để liên kết ngân hàng trước!", show_alert=True)
        return False
    return True

def check_ban_status(user, obj):
    if user.get('banned_until'):
        try:
            ban_time_str = user['banned_until']
            # Support both isoformat string and other formats if needed
            if isinstance(ban_time_str, str):
                ban_time = datetime.datetime.fromisoformat(ban_time_str)
            elif isinstance(ban_time_str, datetime.datetime):
                ban_time = ban_time_str
            else:
                return True # Invalid format, ignore.

            if ban_time > datetime.datetime.now():
                reason = user.get('ban_reason', 'Vi phạm quy định')
                time_str = ban_time.strftime('%H:%M %d/%m')
                msg_text = f"⛔ TÀI KHOẢN BỊ KHÓA\nLý do: {reason}\nMở lại: {time_str}"
                
                if isinstance(obj, types.CallbackQuery):
                    bot.answer_callback_query(obj.id, msg_text, show_alert=True)
                else:
                    bot.reply_to(obj, msg_text)
                return False
        except Exception as e:
            print(f"Check Ban Error: {e}")
            pass
    return True

@bot.callback_query_handler(func=lambda call: call.data == "main_menu")
def on_main_menu(call):
    _, user = get_user_context(call.from_user.id)
    if not check_ban_status(user, call): return
    if not check_bank_linked(user, call): return

    msg = (
        f"🏠 **MENU CHÍNH**\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👤 ID: `{call.from_user.id}`\n"
        f"💰 Số dư: `{user['balance']:,} VND`\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          text=msg, reply_markup=main_menu_keyboard(call.from_user.id), parse_mode="Markdown")

# --- GAMES LIST & INTERFACE ---

@bot.callback_query_handler(func=lambda call: call.data == "games_list")
def on_games_list(call):
    _, user = get_user_context(call.from_user.id)
    if not check_ban_status(user, call): return
    # No bank check needed just to see games, theoretically
    # if not check_bank_linked(user, call): return

    markup = types.InlineKeyboardMarkup(row_width=2)
    # Row 1
    markup.add(
        types.InlineKeyboardButton("🎲 Tài Xỉu", callback_data="play_taixiu"),
        types.InlineKeyboardButton("🔴 Chẵn Lẻ", callback_data="play_chanle")
    )
    # Row 2
    markup.add(
        types.InlineKeyboardButton("🎯 Xiên", callback_data="play_xien")
    )
    markup.add(types.InlineKeyboardButton("🔙 Menu Chính", callback_data="main_menu"))
    
    msg = (
        "🎮 **SẢNH GAME GIẢI TRÍ** 🎮\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "👇 _Chọn trò chơi yêu thích bên dưới:_"
    )
    try:
         bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                               text=msg, reply_markup=markup, parse_mode="Markdown")
    except:
         bot.send_message(call.message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "missions")
def on_missions(call):
    bot.answer_callback_query(call.id, "🚧 Tính năng Nhiệm Vụ đang phát triển!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "promotions")
def on_promotions(call):
    bot.answer_callback_query(call.id, "🚧 Tính năng Khuyến Mãi đang phát triển!", show_alert=True)

def update_game_interface(call, user, game_type):
    if game_type == "taixiu": name = "TÀI XỈU"
    elif game_type == "chanle": name = "CHẴN LẺ"
    elif game_type == "xien": name = "LÔ XIÊN"
    msg = (
        f"🎲 **{name} (Blockchain)**\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"💵 **Đang cược:** `{user.get('current_bet',0):,} VND`\n"
        f"💰 **Số dư:** `{user['balance']:,} VND`\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👇 _Đặt cược ngay:_"
    )
    
    import telebot.apihelper
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                              text=msg, reply_markup=create_bet_keyboard(game_type), parse_mode="Markdown")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            print(f"Update Interface Error: {e}")
            
@bot.callback_query_handler(func=lambda call: call.data in ["play_taixiu", "play_chanle", "play_xien"])
def on_play_game(call):
    if not check_cooldown(call.from_user.id, 0.5): # 0.5s debounce
        bot.answer_callback_query(call.id, "⏳ Từ từ nhan em!", show_alert=False)
        return

    data, user = get_user_context(call.from_user.id)
    user['current_bet'] = 0 # Reset when entering
    save_data_snapshot(data)
    
    if call.data == "play_taixiu":
        update_game_interface(call, user, "taixiu")
    elif call.data == "play_chanle":
        update_game_interface(call, user, "chanle")
    elif call.data == "play_xien":
        update_game_interface(call, user, "xien")

# --- BETTING SYSTEM ---

@bot.callback_query_handler(func=lambda call: call.data.startswith("add_bet_"))
def on_add_bet(call):
    if not check_cooldown(call.from_user.id, 0.1): # 0.1s fast debounce
         bot.answer_callback_query(call.id, "...", show_alert=False)
         return

    amount_str = call.data.split("_")[-1]
    
    def add_bet_logic(user):
        if amount_str == "all":
            user['current_bet'] = user['balance']
        elif amount_str == "reset":
            user['current_bet'] = 0
        else:
            amount = int(amount_str)
            if user['current_bet'] + amount <= user['balance']:
                 user['current_bet'] += amount
            else:
                 bot.answer_callback_query(call.id, "Số dư không đủ!", show_alert=True)
                 return False # Do not save
        return True # Save

    # Use modify_user_data to persist changes
    updated_user = modify_user_data(call.from_user.id, add_bet_logic)
    
    # Refresh Interface
    msg_text = call.message.text
    if "CHẴN LẺ" in msg_text: game_type = "chanle"
    elif "TÀI XỈU" in msg_text: game_type = "taixiu"
    elif "LÔ XIÊN" in msg_text: game_type = "xien"
    else: game_type = "taixiu"
    update_game_interface(call, updated_user, game_type)

# --- GAME EXECUTION ---

@bot.callback_query_handler(func=lambda call: call.data.startswith("bet_fair_"))
def on_bet_execution(call):
    if not check_cooldown(call.from_user.id, 1.0): # 1s Cooldown crucial to prevent double bet
        bot.answer_callback_query(call.id, "⏳ Chậm lại xíu nào!", show_alert=True)
        return

    # check if user wants to play xien
    if call.data == "bet_fair_xien_input":
        data, user = get_user_context(call.from_user.id)
        if user.get('current_bet', 0) <= 0:
            bot.answer_callback_query(call.id, "Vui lòng chọn tiền cược!", show_alert=True)
            return
        if user['current_bet'] > user['balance']:
            bot.answer_callback_query(call.id, "Số dư không đủ!", show_alert=True)
            return

        msg = bot.send_message(call.message.chat.id, "🎯 Nhập số từ 00 đến 99 mà bạn muốn cược:")
        bot.register_next_step_handler(msg, process_xien_input, user)
        bot.answer_callback_query(call.id)
        return

    # bet_fair_xiu, bet_fair_tai, bet_fair_chan, bet_fair_le
    action = call.data.replace("bet_fair_", "")
    
    data, user = get_user_context(call.from_user.id)
    
    if action in ["tai", "xiu"]:
        process_game_result(call, user, "taixiu", action)
    elif action in ["chan", "le"]:
        process_game_result(call, user, "chanle", action)

def process_xien_input(message, user):
    user_input = message.text.strip()
    if not user_input.isdigit() or not (0 <= int(user_input) <= 99) or len(user_input) != 2:
        bot.reply_to(message, "❌ Số không hợp lệ! Vui lòng nhập 2 chữ số (VD: 05, 99).")
        return
    
    # fake a call object so process_game_result works since it needs it
    class DummyCall:
        def __init__(self, message, from_user):
            self.message = message
            self.from_user = from_user
            self.id = "dummy_id"
    
    dummy_call = DummyCall(message, message.from_user)
    action = f"xien_{user_input}"
    process_game_result(dummy_call, user, "xien", user_input)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rules_"))
def on_game_rules_display(call):
    game_type = call.data.replace("rules_", "")
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Quay lại Game", callback_data=f"play_{game_type}"))
    
    if game_type == "taixiu":
        msg = (
            "📜 **LUẬT CHƠI TÀI XỈU**\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
            "Chúng tôi sử dụng mã **Hash** của Block trên Blockchain để xác định kết quả (minh bạch 100%).\n\n"
            "**Cách tính:** Lấy ký tự số cuối cùng của Hash.\n"
            "👉 **XỈU:** Nếu số cuối là **0 - 1 - 2 - 3 - 4**\n"
            "👉 **TÀI:** Nếu số cuối là **5 - 6 - 7 - 8 - 9**\n\n"
            "🏆 **Tỷ lệ trả thưởng:** 1 ăn 1.95 (hoặc theo cấu hình VIP)."
        )
    elif game_type == "chanle":
        msg = (
            "📜 **LUẬT CHƠI CHẴN LẺ**\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
            "Dựa trên mã **Hash** của Block Blockchain.\n\n"
            "**Cách tính:** Lấy ký tự số cuối cùng của Hash.\n"
            "👉 **CHẴN:** Nếu số là **0, 2, 4, 6, 8**\n"
            "👉 **LẺ:** Nếu số là **1, 3, 5, 7, 9**\n\n"
            "🏆 **Tỷ lệ trả thưởng:** 1 ăn 1.95."
        )
    elif game_type == "xien":
        msg = (
            "📜 **LUẬT CHƠI LÔ XIÊN**\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
            "Mỗi phiên sẽ lấy mã **Hash** của Block trên Blockchain để xác định kết quả.\n\n"
            "**Cách tính:** Lấy 2 ký tự số cuối cùng của Hash.\n"
            "� Người chơi sẽ dự đoán đúng 2 con số này (từ 00 đến 99).\n\n"
            "🏆 **Tỷ lệ trả thưởng:** 1 ăn 70."
        )
    else:
        msg = "Trò chơi chưa có hướng dẫn."

    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          text=msg, reply_markup=markup, parse_mode="Markdown")

# --- ACCOUNT & HISTORY ---

@bot.callback_query_handler(func=lambda call: call.data == "account")
def on_account(call):
    _, user = get_user_context(call.from_user.id)
    vip_level = user.get('vip_level', 0)
    total_bet = user.get('total_bet', 0)
    
    # Calculate VIP
    next_vip = vip_level + 1
    vip_msg = ""
    if next_vip in VIP_LEVELS:
        req_bet, _ = VIP_LEVELS[next_vip]
        remain = req_bet - total_bet
        if remain <= 0:
                vip_msg = f"\n🚀 **Sắp lên VIP {next_vip}!** (Đủ điều kiện)"
        else:
                percent = (total_bet / req_bet) * 100
                vip_msg = f"\n📈 **VIP Progress:** {percent:.2f}% (Thiếu {remain:,})"
    else:
        vip_msg = "\n🔥 **MAX VIP LEVEL**"

    msg = (
        f"👤 **THÔNG TIN TÀI KHOẢN**\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🆔 **ID:** `{call.from_user.id}`\n"
        f"👑 **Cấp độ:** `VIP {vip_level}`\n"
        f"💰 **Số dư:** `{user['balance']:,} VND`\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"📊 **THỐNG KÊ**\n"
        f"📥 Tổng nạp: `{user.get('total_deposit', 0):,} VND`\n"
        f"📤 Tổng rút: `{user.get('total_withdraw', 0):,} VND`\n"
        f"🎲 Tổng cược: `{total_bet:,} VND`\n"
        f"🔄 Cược cần: `{user.get('required_wager', 0):,} VND`\n"
        f"{vip_msg}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🏦 **NGÂN HÀNG LIÊN KẾT**\n"
        f"🏛 {user.get('bank_info', {}).get('bank', 'Chưa LK')}\n"
        f"💳 `{user.get('bank_info', {}).get('stk', '---')}`\n"
        f"👤 {user.get('bank_info', {}).get('ctk', '---')}\n"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📥 LS Nạp", callback_data="history_deposit"),
        types.InlineKeyboardButton("📤 LS Rút", callback_data="history_withdraw")
    )
    markup.add(types.InlineKeyboardButton("🎲 LS Chơi", callback_data="history_game"))
    markup.add(types.InlineKeyboardButton("💳 Thay đổi Ngân hàng", callback_data="change_bank"))
    markup.add(types.InlineKeyboardButton("🔙 Quay lại", callback_data="main_menu"))
    
    try:
         bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg, reply_markup=markup, parse_mode="Markdown")
    except:
         bot.send_message(call.message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "change_bank")
def on_change_bank(call):
    msg = bot.send_message(call.message.chat.id, "🏦 **LIÊN KẾT NGÂN HÀNG**\n\nNhập Tên Ngân Hàng của bạn (Ví dụ: MB Bank):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_link_bank_name)

@bot.callback_query_handler(func=lambda call: call.data in ["history_deposit", "history_withdraw", "history_game"])
def on_history(call):
    _, user = get_user_context(call.from_user.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Menu Tài Khoản", callback_data="account"))
    
    if call.data == "history_deposit":
        history = user.get('deposit_history', [])
        msg = "📥 **Lịch sử Nạp tiền:**\n" + "\n".join(history[-10:]) if history else "📭 Lịch sử nạp trống."
    elif call.data == "history_withdraw":
        history = user.get('withdraw_history', [])
        msg = "📤 **Lịch sử Rút tiền:**\n" + "\n".join(history[-10:]) if history else "📭 Lịch sử rút trống."
    else:
        history = user.get('history', [])
        msg = "🎲 **Lịch sử Cược (15 gần nhất):**\n" + "\n".join(history[-15:]) if history else "📭 Lịch sử chơi trống."
        
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg, reply_markup=markup, parse_mode="Markdown")

# --- OTHER FEATURES (DEPOSIT, WITHDRAW, GIFTCODE) ---

@bot.callback_query_handler(func=lambda call: call.data == "deposit")
@bot.callback_query_handler(func=lambda call: call.data == "deposit")
def on_deposit(call):
    _, user = get_user_context(call.from_user.id)
    if not check_bank_linked(user, call): return
    
    from database import get_setting
    bank_name = get_setting('bank_name', 'MB Bank')
    bank_stk = get_setting('bank_stk', '0000123456789')
    bank_ctk = get_setting('bank_ctk', 'NGUYEN VAN A')
    
    msg = (
        f"💳 **NẠP TIỀN VÀO TÀI KHOẢN**\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🏦 **Ngân hàng:** `{bank_name}`\n"
        f"💳 **Số TK:** `{bank_stk}`\n"
        f"👤 **Chủ TK:** `{bank_ctk}`\n"
        f"📝 **Nội dung:** `NAP {call.from_user.id}`\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"⚠️ _Vui lòng ghi đúng nội dung để hệ thống tự động cộng tiền (1-3 phút)_"
    )
    bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "withdraw")
def on_withdraw(call):
    _, user = get_user_context(call.from_user.id)
    if not check_bank_linked(user, call): return
    msg = bot.send_message(call.message.chat.id, "💸 **RÚT TIỀN**\n\nNhập số tiền bạn muốn rút (VD: 50000):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_withdraw_amount)

def process_withdraw_amount(message):
    try:
        amount = int(message.text)
        if amount < 50000:
             bot.reply_to(message, "❌ Số tiền rút tối thiểu là 50,000 VND.")
             return

        user_id = message.from_user.id
        _, user = get_user_context(user_id)
        
        if amount > user['balance']:
             bot.reply_to(message, "❌ Số dư không đủ.")
             return
             
        # Check Wager Requirement
        req_wager = user.get('required_wager', 0)
        if req_wager > 0:
             bot.reply_to(message, f"⛔ Bạn chưa đủ điều kiện rút tiền!\nCần cược thêm: {req_wager:,} VND")
             return

        # Auto fill if linked?
        if 'bank_info' in user:
             info = user['bank_info']
             # Call final step directly
             process_withdraw_ctk(message, amount, info['bank'], info['stk']) 
             return

        msg = bot.reply_to(message, "🏦 Nhập Tên Ngân Hàng (Ví dụ: MB Bank, Vietcombank):")
        bot.register_next_step_handler(msg, process_withdraw_bank, amount)
    except ValueError:
        bot.reply_to(message, "❌ Vui lòng nhập số hợp lệ.")
    except Exception:
        bot.reply_to(message, "❌ Lỗi không xác định.")

def process_withdraw_bank(message, amount):
    bank_name = message.text
    msg = bot.reply_to(message, "💳 Nhập Số Tài Khoản (STK):")
    bot.register_next_step_handler(msg, process_withdraw_stk, amount, bank_name)

def process_withdraw_stk(message, amount, bank_name):
    stk = message.text.strip()
    if not stk.isdigit():
        bot.reply_to(message, "❌ Số tài khoản phải là số. Vui lòng thử lại lệnh rút tiền.")
        return

    msg = bot.reply_to(message, "👤 Nhập Tên Chủ Tài Khoản (CTK) (Viết hoa không dấu):")
    bot.register_next_step_handler(msg, process_withdraw_ctk, amount, bank_name, stk)

def process_withdraw_ctk(message, amount, bank_name, stk):
    user_id = message.from_user.id
    ctk_input = message.text.upper().strip()
    
    # Input Validation
    if len(bank_name) > 50 or len(stk) > 30 or len(ctk_input) > 50:
         bot.reply_to(message, "❌ Thông tin ngân hàng không hợp lệ (quá dài).")
         return
    # STK verified in previous step
    
    # Context for outside lock
    ctx = {"msg_success": None, "msg_admin": None, "req_id": None}

    # Updated withdrawal logic for SQL
    from database import modify_user_data, add_withdrawal_request

    def withdraw_deduct(user):
        # Determine CTK
        ctk = ""
        if 'bank_info' in user and user['bank_info'].get('stk') == stk:
             ctk = user['bank_info']['ctk']
        else:
             ctk = ctk_input
             
        if user['balance'] < amount:
            ctx['error'] = "❌ Số dư không đủ (đã thay đổi)."
            return False

        user['balance'] -= amount
        user['total_withdraw'] += amount
        
        wd_time = datetime.datetime.now().strftime("%H:%M %d/%m")
        req_id = f"{user_id}_{int(datetime.datetime.now().timestamp())}"
        
        user['withdraw_history'].append(f"⏳ {wd_time} | -{amount:,} | Đang chờ")
        
        ctx['req_id'] = req_id
        ctx['ctk'] = ctk
        ctx['wd_time'] = wd_time
        ctx['status'] = 'pending'
        return True

    updated_user = modify_user_data(user_id, withdraw_deduct)

    if 'error' in ctx:
        bot.reply_to(message, ctx['error'], reply_markup=main_menu_keyboard(user_id))
        return
    
    if not ctx.get('req_id'): # Should not happen if True returned
         return

    # Create withdrawal record
    wd_record = {
        "id": ctx['req_id'],
        "user_id": user_id,
        "amount": amount,
        "bank_name": bank_name,
        "stk": stk,
        "ctk": ctx['ctk'],
        "time": ctx['wd_time'],
        "status": "pending"
    }
    add_withdrawal_request(wd_record)

    # Prepare messages
    msg_success = (
        f"✅ **TẠO LỆNH RÚT THÀNH CÔNG**\n"
        f"💰 Số tiền: {amount:,} VND\n"
        f"🏦 Về: {bank_name}\n"
        f"💳 STK: `{stk}`\n"
        f"👤 CTK: {ctx['ctk']}\n\n"
        f"Vui lòng chờ Admin duyệt (1-5 phút)."
    )
    
    msg_admin = (
        f"🔔 **QUẢN LÝ RÚT TIỀN**\n"
        f"👤 ID: `{user_id}`\n"
        f"💰 Rút: {amount:,} VND\n"
        f"🏦 Bank: {bank_name}\n"
        f"💳 STK: `{stk}`\n"
        f"👤 CTK: {ctx['ctk']}\n"
        f"⏳ Lúc: {ctx['wd_time']}"
    )
    ctx['msg_success'] = msg_success
    ctx['msg_admin'] = msg_admin

    # SEND MESSAGES OUTSIDE LOCK
    bot.reply_to(message, ctx['msg_success'], parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))
    
    markup_adm = types.InlineKeyboardMarkup()
    markup_adm.add(
        types.InlineKeyboardButton("✅ Duyệt Ngay", callback_data=f"adm_wd_ok_{ctx['req_id']}"),
        types.InlineKeyboardButton("❌ Huỷ & Note", callback_data=f"adm_wd_no_{ctx['req_id']}")
    )
    try:
        bot.send_message(ADMIN_ID, ctx['msg_admin'], parse_mode="Markdown", reply_markup=markup_adm)
    except: pass

@bot.callback_query_handler(func=lambda call: call.data == "giftcode")
def on_giftcode(call):
    msg = bot.send_message(call.message.chat.id, "🎁 **GIFTCODE**\n\nNhập mã Giftcode của bạn:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_giftcode_input)

def process_giftcode_input(message):
    code = message.text.upper().strip()
    user_id = message.from_user.id
    
    # Updated Giftcode Logic
    from database import modify_user_data, update_giftcode_usage, get_data_snapshot

    # Shared state
    gc_ctx = {"code": code, "success": False, "msg": "", "used_count": 0, "qty": 0}

    def giftcode_logic(user):
        # We need to fetch giftcode data. 
        # CAUTION: Fetching inside modify_user_data (which holds lock) is safe but we need access to DB.
        # get_data_snapshot calls DB.
        data = get_data_snapshot()
        valid_codes = data.get("giftcodes", {})
        
        if code in valid_codes:
            gc_data = valid_codes[code]
            
            if code in user['used_giftcodes']:
                 gc_ctx["msg"] = "❌ Bạn đã sử dụng mã này rồi!"
                 return False

            if gc_data.get('expires'):
                try:
                    exp_time = datetime.datetime.fromisoformat(gc_data['expires'])
                    if datetime.datetime.now() > exp_time:
                         gc_ctx["msg"] = "❌ Mã Giftcode đã hết hạn!"
                         return False
                except: pass
            
            qty = gc_data.get('quantity', 0)
            used = gc_data.get('used', 0)
            if qty > 0 and used >= qty:
                 gc_ctx["msg"] = "❌ Mã Giftcode đã hết lượt sử dụng!"
                 return False

            reward = gc_data['amount']
            wager_mult = gc_data.get('wager', 1)
            
            user['balance'] += reward
            user['used_giftcodes'].append(code)
            
            # Update local ctx to use outside
            gc_ctx['used_count'] = used + 1
            gc_ctx['qty'] = qty
            gc_ctx['reward'] = reward
            gc_ctx['req_bet'] = reward * wager_mult
            
            req_bet = reward * wager_mult
            if 'required_wager' not in user: user['required_wager'] = 0
            user['required_wager'] += req_bet
            
            gc_ctx["success"] = True
            return True
        else:
            gc_ctx["msg"] = "❌ Mã Giftcode không tồn tại."
            return False

    modify_user_data(user_id, giftcode_logic)

    if gc_ctx["success"]:
        # Update Giftcode Usage in DB
        update_giftcode_usage(code, gc_ctx['used_count'], gc_ctx['qty'])
        bot.reply_to(message, f"🎉 Nhận thành công {gc_ctx['reward']:,} VND!\n⚠️ Yêu cầu cược thêm: {gc_ctx['req_bet']:,} VND để rút.", reply_markup=main_menu_keyboard(user_id))
    else:
        bot.reply_to(message, gc_ctx["msg"], reply_markup=main_menu_keyboard(user_id))


@bot.callback_query_handler(func=lambda call: call.data == "bonus")
def on_bonus(call):
    now = datetime.datetime.now()
    user_id = call.from_user.id
    
    result = {"success": False, "msg": ""}
    
    def bonus_logic(user):
        last_bonus = user['last_bonus']
        if last_bonus and isinstance(last_bonus, str):
             try: last_bonus = datetime.datetime.fromisoformat(last_bonus)
             except: last_bonus = None
             
        if last_bonus and last_bonus.date() == now.date():
             result["success"] = False
             result["msg"] = "❌ Bạn đã nhận thưởng hôm nay rồi!"
             return False
        else:
            user['balance'] += 5000
            user['last_bonus'] = now
            result["success"] = True
            result["msg"] = "✅ Điểm danh thành công! +5,000 VND"
            return True

    modify_user_data(user_id, bonus_logic)
    
    if result["success"]:
        bot.answer_callback_query(call.id, text="🎉 Điểm danh thành công! Nhận 5,000 VND.", show_alert=True)
        bot.send_message(call.message.chat.id, result["msg"])
    else:
        bot.answer_callback_query(call.id, text=result["msg"], show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "referral")
def on_referral(call):
    ref_link = f"https://t.me/{bot.get_me().username}?start={call.from_user.id}"
    msg = (
        f"🤝 **GIỚI THIỆU BẠN BÈ**\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🔗 **Link của bạn:**\n`{ref_link}`\n\n"
        f"💰 **Hoa hồng:** 10% giá trị nạp của Ref\n"
        f"👉 _Chia sẻ link ngay để nhận thưởng trọn đời!_"
    )
    bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

def process_link_bank_name(message):
    bank_name = message.text
    msg = bot.reply_to(message, "💳 Nhập Số Tài Khoản (STK) của bạn:")
    bot.register_next_step_handler(msg, process_link_bank_stk, bank_name)

def process_link_bank_stk(message, bank_name):
    stk = message.text.strip()
    if not stk.isdigit():
        bot.reply_to(message, "❌ Số tài khoản phải là số! Vui lòng thực hiện lại.")
        return
    msg = bot.reply_to(message, "👤 Nhập Tên Chủ Tài Khoản (CTK) (Viết hoa không dấu):")
    bot.register_next_step_handler(msg, process_link_bank_ctk, bank_name, stk)

def process_link_bank_ctk(message, bank_name, stk):
    ctk = message.text.upper().strip()
    user_id = message.from_user.id
    
    def save_bank(user):
        user['bank_info'] = {
            "bank": bank_name,
            "stk": stk,
            "ctk": ctk
        }
        return True
        
    from database import modify_user_data
    modify_user_data(user_id, save_bank)
    
    bot.reply_to(message, f"✅ **LIÊN KẾT THÀNH CÔNG**\n\n🏦 {bank_name}\n💳 {stk}\n👤 {ctk}", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "support")
def on_support(call):
    markup = types.InlineKeyboardMarkup()
    btn_admin = types.InlineKeyboardButton("Liên hệ Admin", url="https://t.me/admin_username_here")
    markup.add(btn_admin)
    bot.send_message(call.message.chat.id, "💬 Hỗ trợ trực tuyến 24/7.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "top_rich")
def on_top_rich(call):
    from database import get_top_users
    # Fetch top 10
    sorted_users = get_top_users(10)
    
    if not sorted_users:
         bot.answer_callback_query(call.id, "📭 Chưa có dữ liệu!", show_alert=True)
         return

    msg = "🏆 **BẢNG XẾP HẠNG ĐẠI GIA** 🏆\n\n"
    rank_icons = ["🥇", "🥈", "🥉"]
    
    for i, (uid, balance) in enumerate(sorted_users):
         rank = i + 1
         icon = rank_icons[i] if i < 3 else f"#{rank}"
         masked_id = str(uid)[:4] + "***" + str(uid)[-2:]
         msg += f"{icon} `{masked_id}`: {balance:,} VND\n"
         
    msg += "\n(Cập nhật liên tục theo thời gian thực)"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Menu Chính", callback_data="main_menu"))
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg, reply_markup=markup, parse_mode="Markdown")

# --- ADMIN PROCESS FUNCTIONS (Must be defined before being referenced) ---

def process_admin_balance_change(message, action_type):
    if message.from_user.id != ADMIN_ID: return
    try:
        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "❌ Sai cú pháp!")
            return
            
        target_id = int(args[0])
        amount = int(args[1])
        
        ctx = {"msg": "", "success": False}

        def balance_logic(user):
            if action_type == "admin_add_balance":
                user['balance'] += amount
                if 'total_deposit' not in user: user['total_deposit'] = 0
                user['total_deposit'] += amount 
                
                # Add Wagering Requirement (x1 Deposit)
                if 'required_wager' not in user: user['required_wager'] = 0
                user['required_wager'] += amount

                dep_time = datetime.datetime.now().strftime("%H:%M %d/%m")
                user['deposit_history'].append(f"⏰ {dep_time} | +{amount:,} | Admin cộng")
                
                ctx["msg"] = f"✅ Đã cộng {amount:,} VND cho ID `{target_id}`."
                ctx["success"] = True
                return True

            elif action_type == "admin_sub_balance":
                if user['balance'] < amount:
                     ctx["msg"] = "❌ Số dư không đủ."
                     return False
                user['balance'] -= amount
                ctx["msg"] = f"✅ Đã trừ {amount:,} VND của ID `{target_id}`."
                ctx["success"] = True
                return True
            return False

        updated_user = modify_user_data(target_id, balance_logic)
        
        bot.reply_to(message, ctx["msg"])
        
        if ctx["success"]:
            if action_type == "admin_add_balance":
                try: bot.send_message(target_id, f"✅ **NẠP TIỀN THÀNH CÔNG**\n💰 Số tiền nạp: {amount:,} VND")
                except: pass
                log_transaction(target_id, "DEPOSIT_ADMIN", amount, "ADMIN", "COMPLETED")
                log_admin_action(message.from_user.id, "ADD_BALANCE", target_id, f"Amount: {amount}")
            else:
                log_transaction(target_id, "SUBTRACT_ADMIN", amount, "ADMIN", "COMPLETED")
                log_admin_action(message.from_user.id, "SUB_BALANCE", target_id, f"Amount: {amount}")

    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def process_admin_broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    if message.text.lower() == "cancel": return
    
    from database import get_all_user_ids
    user_ids = get_all_user_ids()
    
    count = 0
    bot.reply_to(message, f"⏳ Đang gửi cho {len(user_ids)} người...")
    
    for uid in user_ids:
        try:
            bot.send_message(uid, f"📢 **THÔNG BÁO**\n\n{message.text}", parse_mode="Markdown")
            count += 1
        except: pass
    bot.reply_to(message, f"✅ Đã gửi thành công cho {count} người.")

def process_create_giftcode(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        code = parts[0].upper()
        amount = int(parts[1])
        quantity = int(parts[2]) if len(parts) > 2 else 999999
        wager = int(parts[3]) if len(parts) > 3 else 1
        hours = int(parts[4]) if len(parts) > 4 else 720
        
        data = get_data_snapshot()
        if "giftcodes" not in data: data["giftcodes"] = {}
        
        expire_dt = datetime.datetime.now() + datetime.timedelta(hours=hours)
        data["giftcodes"][code] = {"amount": amount, "quantity": quantity, "wager": wager, "expires": expire_dt.isoformat(), "used": 0}
        save_data_snapshot(data)
        bot.reply_to(message, f"✅ Tạo Giftcode `{code}` thành công.")
        log_admin_action(message.from_user.id, "CREATE_GIFTCODE", details=f"Code: {code}, Amount: {amount}")
    except:
        bot.reply_to(message, "❌ Lỗi định dạng.")

def process_admin_reset_balance(message):
    try:
        if message.from_user.id != ADMIN_ID: return
        target = message.text.strip()
        
        if target == "ALL":
             from database import reset_all_users
             if reset_all_users():
                 bot.reply_to(message, "✅ Đã Reset Balance All Users về 0!")
                 log_admin_action(message.from_user.id, "RESET_ALL", "ALL", "Reset All to 0")
             else:
                 bot.reply_to(message, "❌ Lỗi Database khi reset all.")
             return

        target_id = int(target)
        def reset_logic(user):
            user['balance'] = 0
            user['current_bet'] = 0
            user['required_wager'] = 0
            return True
        
        modify_user_data(target_id, reset_logic)
        bot.reply_to(message, f"✅ Đã Reset ID `{target}` về 0!")
        log_admin_action(message.from_user.id, "RESET_BALANCE", target, "Reset to 0")

    except ValueError:
        bot.reply_to(message, "❌ ID phải là số.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def main_menu_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # Check maintenance mode
    if is_maintenance_mode(user_id):
        markup.add(types.InlineKeyboardButton("⚠️ HỆ THỐNG ĐANG BẢO TRÌ ⚠️", callback_data="maintenance_info"))
        if user_id == ADMIN_ID:
            markup.add(types.InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel"))
        return markup

    # NEW LAYOUT based on USER REQUEST
    # Row 1: Danh sach game (Full width)
    markup.add(types.InlineKeyboardButton("🎲 Danh sách game", callback_data="games_list"))
    
    # Row 2: Nap Tien | Rut Tien
    markup.add(
        types.InlineKeyboardButton("💵 Nạp Tiền", callback_data="deposit"),
        types.InlineKeyboardButton("💸 Rút Tiền", callback_data="withdraw")
    )
    
    # Row 3: Tai Khoan (Full width)
    markup.add(types.InlineKeyboardButton("👤 Tài Khoản", callback_data="account"))
    
    # Row 4: Nhiem Vu | Gioi Thieu
    markup.add(
        types.InlineKeyboardButton("🎯 Nhiệm Vụ", callback_data="missions"),
        types.InlineKeyboardButton("👥 Giới Thiệu", callback_data="referral")
    )
    
    # Row 5: Giftcode | Bonus
    markup.add(
        types.InlineKeyboardButton("🎁 Giftcode", callback_data="giftcode"),
        types.InlineKeyboardButton("🌺 Bonus", callback_data="bonus")
    )
    
    # Row 6: Khuyen Mai | BXH Dai Gia
    markup.add(
        types.InlineKeyboardButton("🔥 Khuyến Mãi", callback_data="promotions"),
        types.InlineKeyboardButton("🏆 BXH Đại Gia", callback_data="top_rich")
    )
    
    # Row 7: Ho Tro
    markup.add(types.InlineKeyboardButton("💬 Hỗ trợ", callback_data="support"))

    if user_id == ADMIN_ID:
        markup.add(types.InlineKeyboardButton("🛠 ADMIN PANEL", callback_data="admin_panel"))
        
    return markup

def is_maintenance_mode(user_id):
    if user_id == ADMIN_ID: return False
    from database import get_setting
    return get_setting('maintenance_mode', '0') == '1'

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    try:
        user_id = message.from_user.id
        
        if is_maintenance_mode(user_id):
            bot.reply_to(message, "⚠️ **HỆ THỐNG ĐANG BẢO TRÌ**\n\nVui lòng quay lại sau!", parse_mode="Markdown")
            return

        # Check referral
        args = message.text.split()
        if len(args) > 1:
            try:
                ref_id = int(args[1])
                # Logic to process referral...
            except: pass
            
        _, user = get_user_context(user_id)
        balance = f"{user.get('balance', 0):,}"
        bank_status = "✅ Đã lên kết" if user.get('bank_info') else "❌ Chưa liên kết"
        
        msg = (
            f"👋 **XIN CHÀO {message.from_user.first_name}** 👋\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"💰 **Số dư:** `{balance} VND`\n"
            f"💎 **Trạng thái:** {bank_status}\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"👇 _Chọn chức năng bên dưới:_"
        )
        
        bot.send_message(message.chat.id, msg, reply_markup=main_menu_keyboard(user_id), parse_mode="Markdown")
    except Exception as e:
        print(f"Error in start: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("play_"))
def on_play_game(call):
    user_id = call.from_user.id
    if is_maintenance_mode(user_id):
        bot.answer_callback_query(call.id, "⚠️ Hệ thống đang bảo trì!", show_alert=True)
        return

    game_type = call.data.split("_")[1]
    
    # Check Game Status
    from database import get_setting
    if get_setting(f'game_{game_type}', '1') == '0':
         bot.answer_callback_query(call.id, "⚠️ Trò chơi này đang tạm đóng!", show_alert=True)
         return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    # ... logic continues as before ...
    
def process_admin_view_user(message):
    try:
        if message.from_user.id != ADMIN_ID: return
        target = message.text.strip()
        try:
             target_id = int(target)
        except:
             bot.reply_to(message, "❌ ID không hợp lệ.")
             return

        _, u = get_user_context(target_id)
        
        bank = u.get('bank_info', {})
        msg = (
            f"🔍 **CHI TIẾT NGƯỜI DÙNG**\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"🆔 ID: `{target}`\n"
            f"💰 Balance: `{u['balance']:,}`\n"
            f"👑 VIP Level: `{u.get('vip_level', 0)}`\n"
            f"📥 Total Deposit: `{u.get('total_deposit', 0):,}`\n"
            f"📤 Total Withdraw: `{u.get('total_withdraw', 0):,}`\n"
            f"🎲 Total Bet: `{u.get('total_bet', 0):,}`\n"
            f"🔄 Wager Req: `{u.get('required_wager', 0):,}`\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"🏦 Bank: {bank.get('bank', 'None')} - {bank.get('stk', 'None')}\n"
            f"👤 Name: {bank.get('ctk', 'None')}\n"
        )
        bot.reply_to(message, msg, parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def process_admin_ban_user(message):
    try:
        if message.from_user.id != ADMIN_ID: return
        parts = message.text.split(" ", 2) 
        if len(parts) < 3:
             bot.reply_to(message, "❌ Sai cú pháp! (ID GIỜ LÝ_DO)")
             return
             
        target_id = int(parts[0].strip())
        hours = int(parts[1])
        reason = parts[2]
        
        # Calculate Ban Time
        if hours >= 99999:
             ban_until = datetime.datetime(2099, 12, 31).isoformat()
             duration_text = "VĨNH VIỄN"
        else:
             ban_until = (datetime.datetime.now() + datetime.timedelta(hours=hours)).isoformat()
             duration_text = f"{hours} giờ"

        def ban_logic(user):
            user['banned_until'] = ban_until
            user['ban_reason'] = reason
            return True

        modify_user_data(target_id, ban_logic)
        
        bot.reply_to(message, f"✅ Đã BAN user `{target_id}`\n⏳ Thời hạn: {duration_text}\n📝 Lý do: {reason}", parse_mode="Markdown")
        try: bot.send_message(target_id, f"⛔ TÀI KHOẢN CỦA BẠN ĐÃ BỊ KHÓA\n⏳ Thời hạn: {duration_text}\n📝 Lý do: {reason}")
        except: pass
        
    except ValueError:
        bot.reply_to(message, "❌ Lỗi định dạng số.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def process_admin_unban_user(message):
    try:
        if message.from_user.id != ADMIN_ID: return
        target_id = int(message.text.strip())
        
        def unban_logic(user):
            if 'banned_until' in user:
                del user['banned_until']
            if 'ban_reason' in user:
                del user['ban_reason']
            return True
            
        modify_user_data(target_id, unban_logic)
        bot.reply_to(message, f"✅ Đã MỞ KHÓA cho user `{target_id}`.", parse_mode="Markdown")
        try: bot.send_message(target_id, "✅ Tài khoản của bạn đã được mở khóa.")
        except: pass
        
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def process_adjust_user_rate(message):
    try:
        if message.from_user.id != ADMIN_ID: return
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "❌ Sai cú pháp! (ID TỈ_LỆ)")
            return
            
        target_id = int(parts[0])
        rate = int(parts[1])
        
        if rate < -1 or rate > 100:
            bot.reply_to(message, "❌ Tỉ lệ phải từ 0-100 (hoặc -1).")
            return
            
        def rate_logic(user):
            user['win_rate'] = rate
            return True
            
        modify_user_data(target_id, rate_logic)
        
        rate_text = f"{rate}%" if rate >= 0 else "Mặc định (Global)"
        bot.reply_to(message, f"✅ Đã chỉnh tỉ lệ thắng cho ID `{target_id}` thành: **{rate_text}**", parse_mode="Markdown")
        log_admin_action(message.from_user.id, "ADJUST_USER_RATE", target_id, f"Rate: {rate}")
        
    except ValueError:
        bot.reply_to(message, "❌ Lỗi định dạng số.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def process_adjust_all_rate(message):
    try:
        if message.from_user.id != ADMIN_ID: return
        rate = int(message.text)
        
        if rate < 0 or rate > 100:
            bot.reply_to(message, "❌ Tỉ lệ phải từ 0-100.")
            return
            
        data = get_data_snapshot()
        if "settings" not in data: data["settings"] = {}
        data["settings"]["global_win_rate"] = rate
        save_data_snapshot(data)
        
        bot.reply_to(message, f"✅ Đã chỉnh tỉ lệ thắng TOÀN SERVER thành: **{rate}%**", parse_mode="Markdown")
        log_admin_action(message.from_user.id, "ADJUST_GLOBAL_RATE", "ALL", f"Rate: {rate}")
        
    except ValueError:
        bot.reply_to(message, "❌ Lỗi định dạng số.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

# --- ADMIN PANEL ---

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def on_admin_action(call):
    user_id = call.from_user.id
    if user_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Bạn không có quyền truy cập!", show_alert=True)
        return

    if call.data == "admin_panel":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("👥 DS Người dùng", callback_data="admin_users"),
            types.InlineKeyboardButton("📋 Duyệt Rút", callback_data="admin_withdraw_list")
        )
        markup.add(
            types.InlineKeyboardButton("➕ Cộng tiền", callback_data="admin_add_balance"),
            types.InlineKeyboardButton("➖ Trừ tiền", callback_data="admin_sub_balance")
        )
        markup.add(
             types.InlineKeyboardButton("📢 Gửi thông báo", callback_data="admin_broadcast"),
             types.InlineKeyboardButton("🎁 Tạo Giftcode", callback_data="admin_create_giftcode")
        )
        markup.add(types.InlineKeyboardButton("📋 QL Giftcode", callback_data="admin_manage_giftcodes"))
        markup.add(types.InlineKeyboardButton("🔙 Menu Chính", callback_data="main_menu"))
        
        data = get_data_snapshot()
        user_cnt = len(data.get("users", {}))
        pending_cnt = len(data.get("withdrawals", []))
        
        msg = (
            f"🛠 **ADMIN PANEL MANAGER**\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"👥 **Thành viên:** `{user_cnt}`\n"
            f"⏳ **Chờ rút:** `{pending_cnt}` đơn\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"👇 _Chọn chức năng quản lý bên dưới:_"
        )
        markup.add(
            types.InlineKeyboardButton("🔄 Reset User Balance", callback_data="admin_reset_user"),
            types.InlineKeyboardButton("🔍 User Detail", callback_data="admin_user_detail")
        )
        markup.add(types.InlineKeyboardButton("🎮 Chỉnh KQ (User/All)", callback_data="admin_adjust_result"))
        markup.add(types.InlineKeyboardButton("📊 Thống Kê System", callback_data="admin_stats"))
        markup.add(types.InlineKeyboardButton("🚫 Ban/Unban User", callback_data="admin_ban_menu"))
        try:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass

    elif call.data == "admin_stats":
        stats = get_system_stats()
        
        profit_color = "🟢" if stats['system_profit'] >= 0 else "🔴"
        
        msg = (
            f"📊 **HỆ THỐNG THỐNG KÊ**\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"👥 **Tổng User:** `{stats['total_users']}`\n"
            f"💰 **Tổng Nạp:** `{stats['total_deposit']:,} VND`\n"
            f"💸 **Tổng Rút:** `{stats['total_withdraw']:,} VND`\n"
            f"🎰 **Tổng Cược:** `{stats['total_bet']:,} VND`\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"🏦 **User Balance (Nợ):** `{stats['total_balance']:,} VND`\n"
            f"⏳ **Pending Rút:** `{stats['pending_withdrawals']}` đơn\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"{profit_color} **Lợi Nhuận Thực:** `{stats['system_profit']:,} VND`\n"
            f"_(Nạp - Rút - Số dư User)_"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats"))
        markup.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel"))
        
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                              text=msg, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "admin_ban_menu":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🔒 Ban User", callback_data="admin_ban_user"),
            types.InlineKeyboardButton("🔓 Unban User", callback_data="admin_unban_user")
        )
        markup.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                              text="🚫 **BAN MANAGEMENT**\nChọn chức năng:", reply_markup=markup, parse_mode="Markdown")

    elif call.data == "admin_adjust_result":
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("👤 Chỉnh User", callback_data="admin_adjust_user_start"),
            types.InlineKeyboardButton("🌐 Chỉnh All", callback_data="admin_adjust_all_start")
        )
        markup.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel"))
        
        # Show current Global Rate
        data = get_data_snapshot()
        g_rate = data.get("settings", {}).get("global_win_rate", 30)
        
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                              text=f"⚙️ **CHỈNH TỈ LỆ THẮNG**\nHiện tại (Global): **{g_rate}%**\nChọn chế độ:", reply_markup=markup, parse_mode="Markdown")

    elif call.data == "admin_adjust_user_start":
        msg = bot.send_message(call.message.chat.id, 
            "👤 **CHỈNH TỈ LỆ USER**\nNhập theo cú pháp:\n`ID TỈ_LỆ`\nVí dụ: `123456789 80` (80% thắng)\nNhập `ID -1` để hoàn tác (dùng Global).", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_adjust_user_rate)

    elif call.data == "admin_adjust_all_start":
        msg = bot.send_message(call.message.chat.id, 
            "🌐 **CHỈNH TỈ LỆ CHUNG (ALL)**\nNhập tỉ lệ thắng mới (0-100):\nVí dụ: `30`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_adjust_all_rate)


    elif call.data == "admin_ban_user":
        msg = bot.send_message(call.message.chat.id, 
            "🔒 **BAN USER**\nNhập thông tin theo cú pháp:\n`ID GIỜ LÝ_DO`\n\nVí dụ: `123456789 24 Spam bot`\n(Nhập 99999 cho vĩnh viễn)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_admin_ban_user)

    elif call.data == "admin_unban_user":
        msg = bot.send_message(call.message.chat.id, "🔓 **UNBAN USER**\nNhập ID người dùng cần mở khóa:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_admin_unban_user)

    elif call.data == "admin_reset_user":
        msg = bot.send_message(call.message.chat.id, "⚠️ **CẢNH BÁO**\nNhập ID người dùng để **RESET** số dư về 0 (hoặc 'ALL' để reset toàn bộ server):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_admin_reset_balance)

    elif call.data == "admin_user_detail":
        msg = bot.send_message(call.message.chat.id, "🔍 Nhập ID người dùng để xem chi tiết:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_admin_view_user)

    elif call.data == "admin_users":
        from database import get_top_users
        sorted_users = get_top_users(10)
        msg = "👥 **Danh sách người dùng (Top 10 Balance):**\n"
        for uid, balance in sorted_users:
            msg += f"- ID `{uid}`: {balance:,} VND\n"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "admin_withdraw_list":
        data = get_data_snapshot()
        pending_list = data.get("withdrawals", [])
        if not pending_list:
             bot.answer_callback_query(call.id, "✅ Không có đơn rút nào đang chờ.", show_alert=True)
             return
        msg = "📝 **DANH SÁCH RÚT TIỀN CHỜ DUYỆT:**\n"
        markup = types.InlineKeyboardMarkup()
        for req in pending_list:
            bank = req.get('bank_name', 'Bank')
            stk = req.get('stk', 'STK')
            msg += f"- ID `{req['user_id']}` | {req['amount']:,}đ | {bank}-{stk}\n"
            markup.add(
                types.InlineKeyboardButton(f"✅ Duyệt {req['amount']//1000}k", callback_data=f"adm_wd_ok_{req['id']}"),
                types.InlineKeyboardButton(f"❌ Hủy", callback_data=f"adm_wd_no_{req['id']}")
            )
        markup.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg, reply_markup=markup, parse_mode="Markdown")

    elif call.data in ["admin_add_balance", "admin_sub_balance"]:
        action = "cộng" if call.data == "admin_add_balance" else "trừ"
        msg = bot.send_message(call.message.chat.id, f"✏️ Nhập ID người dùng và số tiền muốn {action} (cách nhau bởi dấu cách).\nVí dụ: `123456789 50000`")
        bot.register_next_step_handler(msg, process_admin_balance_change, call.data)
        
    elif call.data == "admin_broadcast":
        msg = bot.send_message(call.message.chat.id, "📢 Nhập nội dung tin nhắn muốn gửi (hoặc gõ 'Cancel' để hủy):")
        bot.register_next_step_handler(msg, process_admin_broadcast)
        
    elif call.data == "admin_create_giftcode":
        msg = bot.send_message(call.message.chat.id, 
            "🎁 Soạn tin theo cú pháp:\n`CODE SỐ_TIỀN SỐ_LƯỢNG VÒNG_CƯỢC HẠN_DÙNG(giờ)`\n\nVí dụ: `TANTHU 50000 100 3 24`")
        bot.register_next_step_handler(msg, process_create_giftcode)
        
    elif call.data == "admin_manage_giftcodes":
        data = get_data_snapshot()
        gcs = data.get("giftcodes", {})
        if not gcs:
            bot.answer_callback_query(call.id, "📭 Chưa có Giftcode nào!", show_alert=True)
            return
        msg = "📋 **DANH SÁCH GIFTCODE**\n"
        markup = types.InlineKeyboardMarkup()
        for code, info in gcs.items():
            remain = info['quantity'] - info.get('used', 0)
            status = "🟢" if remain > 0 else "🔴"
            msg += f"{status} `{code}` | {info['amount']:,}đ | Còn: {remain}/{info['quantity']}\n"
            markup.add(types.InlineKeyboardButton(f"🗑 Xóa {code}", callback_data=f"del_gc_{code}"))
        markup.add(types.InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_wd_"))
def on_admin_withdraw_action(call):
    user_id = call.from_user.id
    if user_id != ADMIN_ID: return
    
    parts = call.data.split("_", 3)
    action = parts[2]
    req_id = parts[3]
    
    # We fetch req from DB
    data = get_data_snapshot()
    pending_list = data.get("withdrawals", [])
    req = next((r for r in pending_list if r["id"] == req_id), None)
    
    if not req:
         bot.answer_callback_query(call.id, "❌ Đơn này không còn tồn tại!", show_alert=True)
         return
         
    target_uid = req['user_id']
    amount = req['amount']
    
    if action == "ok":
        def approve_logic(user):
            new_hist = []
            for h in user['withdraw_history']:
                if req_id in h: new_hist.append(h.replace("Đang chờ", "✅ Thành công"))
                else: new_hist.append(h)
            user['withdraw_history'] = new_hist
            return True

        modify_user_data(target_uid, approve_logic)
        
        # Update Request Status
        req['status'] = 'completed'
        add_withdrawal_request(req)
        
        bot.answer_callback_query(call.id, "✅ Đã duyệt rút tiền!", show_alert=True)
        try: bot.send_message(target_uid, f"✅ **RÚT TIỀN THÀNH CÔNG**\n\n💰 Số tiền: {amount:,} VND\nTiền đã được chuyển về tài khoản.")
        except: pass
        
        log_transaction(target_uid, "WITHDRAW", amount, "BANK", "COMPLETED")
        log_admin_action(user_id, "APPROVE_WITHDRAW", target_uid, f"Amount: {amount}")
        
        # Refresh List if needed
        # call.data = "admin_withdraw_list"
        # on_admin_action(call)

    elif action == "no":
        msg = bot.send_message(call.message.chat.id, f"📝 Nhập lý do từ chối cho đơn `{req_id}`:")
        bot.register_next_step_handler(msg, process_reject_reason, req_id)
        return 

def process_reject_reason(message, req_id):
    if message.from_user.id != ADMIN_ID: return
    reason = message.text
    
    data = get_data_snapshot()
    pending_list = data.get("withdrawals", [])
    req = next((r for r in pending_list if r["id"] == req_id), None)
    
    if not req:
         bot.reply_to(message, "❌ Đơn này không còn tồn tại!")
         return

    target_uid = req['user_id']
    amount = req['amount']
    
    def reject_logic(user):
        user['balance'] += amount
        user['total_withdraw'] -= amount 
        new_hist = []
        for h in user['withdraw_history']:
            if req_id in h: new_hist.append(h.replace("Đang chờ", f"❌ Từ chối: {reason}"))
            else: new_hist.append(h)
        user['withdraw_history'] = new_hist
        return True

    modify_user_data(target_uid, reject_logic)
    
    # Update Request Status
    req['status'] = 'rejected'
    add_withdrawal_request(req)
    
    bot.reply_to(message, f"✅ Đã từ chối đơn rút tiền!\nLý do: {reason}")
    try: bot.send_message(target_uid, f"❌ **YÊU CẦU RÚT TIỀN BỊ TỪ CHỐI**\n\n💰 Số tiền: {amount:,} VND\n📝 Lý do: {reason}\n\nTiền đã được hoàn lại vào số dư.")
    except: pass
    
    log_admin_action(message.from_user.id, "REJECT_WITHDRAW", target_uid, f"Amount: {amount}, Reason: {reason}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_gc_"))
def on_del_gc(call):
    if call.from_user.id != ADMIN_ID: return
    code = call.data.split("del_gc_")[1]
    
    from database import delete_giftcode
    delete_giftcode(code)
    
    bot.answer_callback_query(call.id, f"✅ Đã xóa mã {code}", show_alert=True)
    # Refresh
    call.data = "admin_manage_giftcodes"
    on_admin_action(call)

def process_admin_balance_change(message, action_type):
    if message.from_user.id != ADMIN_ID: return
    try:
        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "❌ Sai cú pháp!")
            return
            
        target_id = int(args[0])
        amount = int(args[1])
        
        ctx = {"msg": "", "success": False}

        def balance_logic(user):
            if action_type == "admin_add_balance":
                user['balance'] += amount
                if 'total_deposit' not in user: user['total_deposit'] = 0
                user['total_deposit'] += amount 
                
                # Add Wagering Requirement (x1 Deposit)
                if 'required_wager' not in user: user['required_wager'] = 0
                user['required_wager'] += amount

                dep_time = datetime.datetime.now().strftime("%H:%M %d/%m")
                user['deposit_history'].append(f"⏰ {dep_time} | +{amount:,} | Admin cộng")
                
                ctx["msg"] = f"✅ Đã cộng {amount:,} VND cho ID `{target_id}`."
                ctx["success"] = True
                return True

            elif action_type == "admin_sub_balance":
                if user['balance'] < amount:
                     ctx["msg"] = "❌ Số dư không đủ."
                     return False
                user['balance'] -= amount
                ctx["msg"] = f"✅ Đã trừ {amount:,} VND của ID `{target_id}`."
                ctx["success"] = True
                return True
            return False

        updated_user = modify_user_data(target_id, balance_logic)
        
        bot.reply_to(message, ctx["msg"])
        
        if ctx["success"]:
            if action_type == "admin_add_balance":
                try: bot.send_message(target_id, f"✅ **NẠP TIỀN THÀNH CÔNG**\n💰 Số tiền nạp: {amount:,} VND")
                except: pass
                log_transaction(target_id, "DEPOSIT_ADMIN", amount, "ADMIN", "COMPLETED")
                log_admin_action(message.from_user.id, "ADD_BALANCE", target_id, f"Amount: {amount}")
            else:
                log_transaction(target_id, "SUBTRACT_ADMIN", amount, "ADMIN", "COMPLETED")
                log_admin_action(message.from_user.id, "SUB_BALANCE", target_id, f"Amount: {amount}")

    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def process_admin_broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    if message.text.lower() == "cancel": return
    
    from database import get_all_user_ids
    user_ids = get_all_user_ids()
    
    count = 0
    bot.reply_to(message, f"⏳ Đang gửi cho {len(user_ids)} người...")
    
    for uid in user_ids:
        try:
            bot.send_message(uid, f"📢 **THÔNG BÁO**\n\n{message.text}", parse_mode="Markdown")
            count += 1
        except: pass
    bot.reply_to(message, f"✅ Đã gửi thành công cho {count} người.")

def process_create_giftcode(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        code = parts[0].upper()
        amount = int(parts[1])
        quantity = int(parts[2]) if len(parts) > 2 else 999999
        wager = int(parts[3]) if len(parts) > 3 else 1
        hours = int(parts[4]) if len(parts) > 4 else 720
        
        data = get_data_snapshot()
        if "giftcodes" not in data: data["giftcodes"] = {}
        
        expire_dt = datetime.datetime.now() + datetime.timedelta(hours=hours)
        data["giftcodes"][code] = {"amount": amount, "quantity": quantity, "wager": wager, "expires": expire_dt.isoformat(), "used": 0}
        save_data_snapshot(data)
        bot.reply_to(message, f"✅ Tạo Giftcode `{code}` thành công.")
        log_admin_action(message.from_user.id, "CREATE_GIFTCODE", details=f"Code: {code}, Amount: {amount}")
    except:
        bot.reply_to(message, "❌ Lỗi định dạng.")

def process_admin_reset_balance(message):
    try:
        if message.from_user.id != ADMIN_ID: return
        target = message.text.strip()
        
        if target == "ALL":
             from database import reset_all_users
             if reset_all_users():
                 bot.reply_to(message, "✅ Đã Reset Balance All Users về 0!")
                 log_admin_action(message.from_user.id, "RESET_ALL", "ALL", "Reset All to 0")
             else:
                 bot.reply_to(message, "❌ Lỗi Database khi reset all.")
             return

        target_id = int(target)
        def reset_logic(user):
            user['balance'] = 0
            user['current_bet'] = 0
            user['required_wager'] = 0
            return True
        
        modify_user_data(target_id, reset_logic)
        bot.reply_to(message, f"✅ Đã Reset ID `{target}` về 0!")
        log_admin_action(message.from_user.id, "RESET_BALANCE", target, "Reset to 0")

    except ValueError:
        bot.reply_to(message, "❌ ID phải là số.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

# ... (process_admin_view_user, process_admin_ban_user, process_admin_unban_user remain same) ...

# ... (process_adjust_user_rate logic) ...
def process_adjust_user_rate(message):
    try:
        if message.from_user.id != ADMIN_ID: return
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "❌ Sai cú pháp! (ID TỈ_LỆ)")
            return
            
        target_id = int(parts[0])
        rate = int(parts[1])
        
        if rate < -1 or rate > 100:
            bot.reply_to(message, "❌ Tỉ lệ phải từ 0-100 (hoặc -1).")
            return
            
        def rate_logic(user):
            user['win_rate'] = rate
            return True
            
        modify_user_data(target_id, rate_logic)
        
        rate_text = f"{rate}%" if rate >= 0 else "Mặc định (Global)"
        bot.reply_to(message, f"✅ Đã chỉnh tỉ lệ thắng cho ID `{target_id}` thành: **{rate_text}**", parse_mode="Markdown")
        log_admin_action(message.from_user.id, "ADJUST_USER_RATE", target_id, f"Rate: {rate}")
        
    except ValueError:
        bot.reply_to(message, "❌ ID hoặc Tỉ lệ phải là số.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def process_adjust_all_rate(message):
    try:
        if message.from_user.id != ADMIN_ID: return
        rate = int(message.text)
        
        if rate < 0 or rate > 100:
            bot.reply_to(message, "❌ Tỉ lệ phải từ 0-100.")
            return
            
        data = get_data_snapshot()
        # Initialize settings if missing
        if "settings" not in data: data["settings"] = {}
        
        data["settings"]["global_win_rate"] = rate
        save_data_snapshot(data)
        
        bot.reply_to(message, f"✅ Đã chỉnh tỉ lệ thắng TOÀN SERVER thành: **{rate}%**", parse_mode="Markdown")
        log_admin_action(message.from_user.id, "ADJUST_GLOBAL_RATE", "ALL", f"Rate: {rate}")
        
    except ValueError:
        bot.reply_to(message, "❌ Lỗi định dạng số.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")
