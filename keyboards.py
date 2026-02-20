# keyboards.py
from telebot import types
from config import ADMIN_ID

def main_menu_keyboard(user_id=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_games = types.InlineKeyboardButton("🎲 Danh sách game", callback_data="games_list")
    btn_account = types.InlineKeyboardButton("👤 Tài Khoản", callback_data="account")
    btn_deposit = types.InlineKeyboardButton("💵 Nạp Tiền", callback_data="deposit")
    btn_withdraw = types.InlineKeyboardButton("💸 Rút Tiền", callback_data="withdraw")
    btn_referral = types.InlineKeyboardButton("👥 Giới Thiệu", callback_data="referral")
    btn_giftcode = types.InlineKeyboardButton("🎁 Giftcode", callback_data="giftcode")
    btn_bonus = types.InlineKeyboardButton("🌺 Bonus", callback_data="bonus")
    btn_support = types.InlineKeyboardButton("💬 Hổ trợ", callback_data="support")
    
    # New Buttons
    btn_mission = types.InlineKeyboardButton("🎯 Nhiệm Vụ", callback_data="missions")
    btn_promo = types.InlineKeyboardButton("🔥 Khuyến Mãi", callback_data="promotions")
    btn_top = types.InlineKeyboardButton("🏆 BXH Đại Gia", callback_data="top_rich")
    
    # Row 1: Main Games (Important)
    markup.add(btn_games)
    
    # Row 2: Account & Balance
    markup.add(btn_deposit, btn_withdraw)
    markup.add(btn_account)
    
    # Row 3: Events & Social
    markup.add(btn_mission, btn_referral)
    markup.add(btn_giftcode, btn_bonus)
    markup.add(btn_promo, btn_top)
    
    # Row 4: Support
    markup.add(btn_support)

    if user_id == ADMIN_ID:
        btn_admin = types.InlineKeyboardButton("🛠 ADMIN PANEL", callback_data="admin_panel")
        markup.add(btn_admin)

    return markup

def create_bet_keyboard(game_type):
    """Helper to create betting keyboard for different games."""
    markup = types.InlineKeyboardMarkup(row_width=4)
    # Generic Money Rows
    # Generic Money Rows (Clean & Compact)
    markup.row(
        types.InlineKeyboardButton("1k", callback_data="add_bet_1000"),
        types.InlineKeyboardButton("5k", callback_data="add_bet_5000"),
        types.InlineKeyboardButton("10k", callback_data="add_bet_10000"),
        types.InlineKeyboardButton("20k", callback_data="add_bet_20000")
    )
    markup.row(
        types.InlineKeyboardButton("50k", callback_data="add_bet_50000"),
        types.InlineKeyboardButton("100k", callback_data="add_bet_100000"),
        types.InlineKeyboardButton("500k", callback_data="add_bet_500000"),
        types.InlineKeyboardButton("💎 ALL-IN", callback_data="add_bet_all")
    )
    markup.add(types.InlineKeyboardButton("🗑 XÓA CƯỢC", callback_data="add_bet_reset"))
    
    # Game Specific Action Rows - Big Buttons
    if game_type == "taixiu":
        markup.row(
            types.InlineKeyboardButton("⚫ XỈU (0-4)", callback_data="bet_fair_xiu"),
            types.InlineKeyboardButton("🟣 TÀI (5-9)", callback_data="bet_fair_tai")
        )
    elif game_type == "chanle":
        markup.row(
            types.InlineKeyboardButton("🔵 CHẴN (0,2..)", callback_data="bet_fair_chan"),
            types.InlineKeyboardButton("🟠 LẺ (1,3..)", callback_data="bet_fair_le")
        )
    elif game_type == "xien":
        markup.add(
            types.InlineKeyboardButton("🎯 NHẬP SỐ DỰ ĐOÁN", callback_data="bet_fair_xien_input")
        )
        
    markup.add(
        types.InlineKeyboardButton("📜 Luật Chơi", callback_data=f"rules_{game_type}"),
        types.InlineKeyboardButton("🔙 Quay lại Sảnh", callback_data="games_list")
    )
    return markup
