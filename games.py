from loader import bot
from database import modify_user_data, get_user_context, log_game, get_data_snapshot
from utils import get_blockchain_result
from config import LIVE_GROUP_ID, VIP_LEVELS
import datetime
from telebot import types

def process_game_result(call, user, game_type, selection):
    """
    Handles the core game logic for Tai Xiu and Chan Le.
    """
    chat_id = call.message.chat.id
    
    # 1. Validation
    amount = user.get('current_bet', 0)
    
    if amount <= 0:
        bot.answer_callback_query(call.id, "Vui lòng chọn tiền cược!", show_alert=True)
        return
    if amount > user['balance']:
        bot.answer_callback_query(call.id, "Số dư không đủ!", show_alert=True)
        return

    # 2. Get Result
    bot.send_message(chat_id, "🔗 Đang lấy Hash từ Blockchain...")
    
    # --- RESULT MANIPULATION LOGIC ---
    import random
    from utils import get_recent_blocks
    
    # Dynamic Win Rate System
    data = get_data_snapshot()
    global_rate = data.get("settings", {}).get("global_win_rate", 30)
    user_rate = user.get("win_rate", -1)
    
    final_win_rate = user_rate if user_rate >= 0 else global_rate
    print(f"User {chat_id} WinRate: Global={global_rate}, User={user_rate} -> Final={final_win_rate}%")
    
    should_win = random.randint(1, 100) <= final_win_rate
    candidates = get_recent_blocks(limit=15)
    
    selected_block = None
    
    # Collect all valid candidates
    valid_matches = []
    
    for blk_num, real_hash in candidates:
        # Parse Hash for this candidate
        if game_type == "xien":
            # get last 2 digits
            digits = [c for c in reversed(real_hash) if c.isdigit()]
            if len(digits) >= 2:
                # since we extracted in reverse, the last two digits are digits[1] and digits[0] in original string order
                cand_res_str = digits[1] + digits[0]
                cand_res = int(cand_res_str)
            else:
                cand_res = 0
                cand_res_str = "00"
        else:
            last_char = '0'
            val = 0
            for char in reversed(real_hash):
                if char.isdigit():
                    last_char = char
                    val = int(char)
                    break
            cand_res = val
        
        # Calculate Outcome for this candidate
        cand_outcome_key = ""
        if game_type == "taixiu":
             cand_outcome_key = "xiu" if 0 <= cand_res <= 4 else "tai"
        elif game_type == "chanle": # chanle
             cand_outcome_key = "chan" if (cand_res % 2 == 0) else "le"
        elif game_type == "xien":
             cand_outcome_key = str(cand_res).zfill(2)
             
        # Check if fits criteria
        if should_win and cand_outcome_key == selection:
            valid_matches.append((blk_num, real_hash, cand_res))
        elif not should_win and cand_outcome_key != selection:
            valid_matches.append((blk_num, real_hash, cand_res))
            
    # Randomly select from valid matches if any
    if valid_matches:
        # User requested limiting to 5 results for selection pool if possible, 
        # but technically we fetched 15. 
        # If we crave randomness, picking from ALL matches in 15 is better than just top 5.
        # But if the user insists on "Lay 5 ket qua thoi", maybe they mean only look at top 5?
        # If we only look at top 5, we might find NO match.
        # I will prioritize picking from the top 5 matches if available, else any match.
        # actually, standard random.choice from all matches is best for "randomness".
        # The user complains about "always getting 6". This happens if we `break` on first match.
        # By using `random.choice(valid_matches)`, we solve the repetition issue.
        selected_block = random.choice(valid_matches)
    
    # Fallback to latest if no match found (rare)
    if not selected_block and candidates:
        blk_num, real_hash = candidates[0]
        # Parse again
        for char in reversed(real_hash):
            if char.isdigit():
                val = int(char)
                break
        selected_block = (blk_num, real_hash, val)
    elif not selected_block:
        # Extreme fallback
        selected_block = (0, "0000", 0)

    block_num, real_hash, final_result = selected_block
    
    # ---------------------------------
    
    # Determine Outcome (Re-evaluation not needed as final_result is set, but keeping variables)
    # Determine Outcome variables for display and transaction
    val = final_result
    
    if game_type == "taixiu":
        # selection: 'xiu' (0-4) or 'tai' (5-9)
        outcome_key = "xiu" if 0 <= final_result <= 4 else "tai"
        outcome_text = "Xỉu" if 0 <= final_result <= 4 else "Tài"
        game_name = "TÀI XỈU"
        payout_rate = 1.95
    elif game_type == "chanle": # chanle
        # selection: 'chan' or 'le'
        is_even = (final_result % 2 == 0)
        outcome_key = "chan" if is_even else "le"
        outcome_text = "Chẵn" if is_even else "Lẻ"
        game_name = "CHẴN LẺ"
        payout_rate = 1.95
    elif game_type == "xien":
        # in fallback cases final_result might be 0, but during normal flow for xien, it ranges from 0 to 99
        outcome_key = str(final_result).zfill(2)
        outcome_text = "Lô " + outcome_key
        game_name = "LÔ XIÊN"
        payout_rate = 70.0

    won = (selection == outcome_key)

    # 3. Process Transaction
    result_details = {}
    
    def game_tx(u):
        actual_amount = u.get('current_bet', 0)
        # Re-verify inside lock
        if actual_amount <= 0 or actual_amount > u['balance']: return False
        
        # calculate won amount
        win_amount = int(actual_amount * payout_rate) if won else 0
        total_payout = win_amount - actual_amount if won else actual_amount # difference used for log
        result_details['amount'] = total_payout if won else actual_amount # amount gained or lost 
        result_details['win_amount'] = win_amount
        
        if won:
            # Add win amount (return bet + profit) - note that bet was not deducted beforehand, so we just add profit
            u['balance'] += (win_amount - actual_amount)
        else:
            u['balance'] -= actual_amount
        
        # VIP & Stats
        if 'total_bet' not in u: u['total_bet'] = 0
        u['total_bet'] += actual_amount
        
        # Wager Reduction
        if 'required_wager' in u and u['required_wager'] > 0:
            u['required_wager'] -= actual_amount
            if u['required_wager'] < 0: u['required_wager'] = 0
        
        # VIP Check
        current_vip = u.get('vip_level', 0)
        new_vip = current_vip
        reward_msg = ""
        for level, (req, reward) in sorted(VIP_LEVELS.items()):
            if u['total_bet'] >= req and level > current_vip:
                u['balance'] += reward
                reward_msg += f"\n🏆 **LÊN VIP {level}!** +{reward:,}"
                new_vip = level 
        u['vip_level'] = new_vip
        result_details['vip_msg'] = reward_msg

        # History
        match_time = datetime.datetime.now().strftime("%H:%M")
        match_res = "THẮNG" if won else "THUA"
        sel_text = selection.upper() # "TAI", "XIU"...
        if game_type == "taixiu":
             sel_text = "Tài" if selection == "tai" else "Xỉu"
        elif game_type == "chanle":
             sel_text = "Chẵn" if selection == "chan" else "Lẻ"
        elif game_type == "xien":
             sel_text = f"Số {selection}"
             
        u['history'].append(f"⏰ {match_time} | {game_name}-{sel_text} | {match_res} {actual_amount:,}")
        if len(u['history']) > 15: u['history'].pop(0)

        if won and actual_amount >= 10000:
            try:
                uid_str = str(call.from_user.id)
                if len(uid_str) > 6:
                    masked_id = uid_str[:3] + "****" + uid_str[-3:]
                else:
                    masked_id = uid_str[:2] + "****" + uid_str[-1:]
                    
                msg_notify = (
                    f"🏆 **CHIẾN THẦN ĐỔ BỘ** 🏆\n"
                    f"➖➖➖➖➖➖➖➖➖➖\n"
                    f"👤 **Vua chơi:** `ID {masked_id}`\n"
                    f"🎮 **Bộ môn:** #{game_name}\n"
                    f"💰 **Húp trọn:** +{actual_amount:,} VND\n"
                    f"➖➖➖➖➖➖➖➖➖➖\n"
                    f"👉 _Vào Bot chiến ngay!_"
                )
                # Store message to send AFTER lock is released
                result_details['public_notification'] = msg_notify
            except Exception as e:
                print(f"Group notify prep error: {e}")

        u['current_bet'] = 0
        return True

    final_user = modify_user_data(chat_id, game_tx)
    
    # Process Public Notification (OUTSIDE LOCK)
    if 'public_notification' in result_details:
        try:
            bot.send_message(LIVE_GROUP_ID, result_details['public_notification'], parse_mode="Markdown")
        except Exception as e:
            print(f"Group notify send error: {e}")
    
    if 'amount' not in result_details:
         try:
             bot.answer_callback_query(call.id, "❌ Lỗi giao dịch hoặc số dư đã đổi!", show_alert=True)
         except telebot.apihelper.ApiTelegramException as e:
             if call.id != "dummy_id": # ignore dummy calls
                 print(f"Error answering callback: {e}")
         return

    # 4. Show Result
    
    # Format Result Variables
    tx_code = real_hash[-5:]
    session_id = block_num
    
    # Visual Icons
    icon_result = "🔴" if final_result % 2 != 0 else "🔵"
    if game_type == "taixiu":
         icon_result = "⚫" if outcome_key == "xiu" else "⚪"
    elif game_type == "xien":
         icon_result = "🎯"
    
    status_icon = "🏆" if won else "💀"
    status_text = "CHIẾN THẮNG" if won else "THẤT BẠI"
    pl_sign = "+" if won else "-"
    
    # Log Game
    log_game(chat_id, game_type, amount, selection, f"{final_result} ({outcome_key})", result_details['amount'] if won else 0, final_user['balance'])
    
    res_msg = (
        f"🎰 **KẾT QUẢ PHIÊN {session_id}** 🎰\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🧱 **Block:** `{block_num}`\n"
        f"🔗 **Hash:** `...{real_hash[-15:]}`\n"
        f"🎲 **Kết quả:** **{final_result}** | {icon_result} **{outcome_text.upper()}**\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"{status_icon} **{status_text}**: {pl_sign}{result_details['amount']:,} VND\n"
        f"{result_details.get('vip_msg', '')}"
        f"💰 **Số dư mới:** {final_user['balance']:,} VND\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👉 _Check kết quả xanh chín tại nút bên dưới_"
    )
    
    repl_markup = types.InlineKeyboardMarkup()
    
    # Actions Row
    check_url = f"https://tronscan.org/#/block/{block_num}"
    play_again_data = f"play_{game_type}"
    repl_markup.add(
        types.InlineKeyboardButton("🔗 Check K.Quả", url=check_url),
        types.InlineKeyboardButton("🔄 Chơi Lại", callback_data=play_again_data)
    )
    repl_markup.add(types.InlineKeyboardButton("🔙 Quay Về Sảnh", callback_data="games_list"))
    
    try: bot.delete_message(chat_id, call.message.message_id) 
    except: pass
    bot.send_message(chat_id, res_msg, parse_mode="Markdown", reply_markup=repl_markup)
