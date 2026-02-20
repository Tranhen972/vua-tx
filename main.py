# main.py
import time
import threading
import random
import string
import datetime
import os

from config import LIVE_GROUP_ID
from loader import bot
from utils import kill_previous_instances
from database import get_data_snapshot, save_data_snapshot

# Import handlers to register them with the bot
import handlers 
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return """
    <h1>Bot is Running!</h1>
    <p><a href="/admin/login">Go to Admin Panel</a></p>
    """
    
# --- ADMIN PANEL ROUTES ---
from flask import render_template, request, redirect, url_for, session
from database import get_system_stats, get_users_paginated, get_all_withdrawals

app.secret_key = 'super_secret_key_change_this' # For session

def is_logged_in():
    return session.get('admin_logged_in')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        # Hardcoded password for simplicity - Change this!
        if password == 'admin123': 
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return "Wrong password", 403
    return '''
    <form method="post" style="text-align:center; margin-top:50px;">
        <h2>Admin Login</h2>
        <input type="password" name="password" placeholder="Password" required>
        <button type="submit">Login</button>
    </form>
    '''

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_logged_in(): return redirect(url_for('admin_login'))
    
    stats = get_system_stats()
    # Get recent users (top balance for now or we can sort by id desc if we had created_at)
    # Using existing get_users_paginated
    recent_users, _ = get_users_paginated(page=1, per_page=5)
    
    # Get pending withdrawals
    pending_wd = get_all_withdrawals(status="pending")
    
    return render_template('dashboard.html', stats=stats, recent_users=recent_users, pending_withdrawals=pending_wd, pending_count=len(pending_wd))

@app.route('/admin/refresh_stats')
def refresh_stats():
    # Helper to just reload dashboard
    return redirect(url_for('admin_dashboard'))
    
# Placeholder routes for sidebar links
@app.route('/admin/users')
def admin_users():
    if not is_logged_in(): return redirect(url_for('admin_login'))
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '')
    users, total = get_users_paginated(page=page, per_page=20, search_query=search)
    total_pages = (total + 19) // 20
    return render_template('users.html', users=users, page=page, total_pages=total_pages, total=total)

@app.route('/admin/user/<user_id>/details')
def admin_user_details(user_id):
    if not is_logged_in(): return redirect(url_for('admin_login'))
    from database import get_user_context
    _, user = get_user_context(user_id)
    return render_template('user_details.html', user=user)

@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if not is_logged_in(): return redirect(url_for('admin_login'))
    
    # Get current settings
    from database import get_setting
    settings = {
        'global_win_rate': get_setting('global_win_rate', 30),
        'payout_rate': get_setting('payout_rate', 1.95), # Add Payout Rate
        'maintenance_mode': get_setting('maintenance_mode', '0'),
        'game_taixiu': get_setting('game_taixiu', '1'),
        'game_chanle': get_setting('game_chanle', '1'),
        'game_xocdia': get_setting('game_xocdia', '1'),
        'game_xien': get_setting('game_xien', '1'),
        'bank_name': get_setting('bank_name', 'MB Bank'),
        'bank_stk': get_setting('bank_stk', '0000123456789'),
        'bank_ctk': get_setting('bank_ctk', 'NGUYEN VAN A')
    }
    return render_template('settings.html', settings=settings)

@app.route('/admin/settings/update', methods=['POST'])
def update_settings_action():
    if not is_logged_in(): return redirect(url_for('admin_login'))
    
    from database import update_setting
    try:
        if 'global_win_rate' in request.form:
            update_setting('global_win_rate', int(request.form['global_win_rate']))
            
        if 'payout_rate' in request.form: # Update Payout Rate
             update_setting('payout_rate', float(request.form['payout_rate']))
        
        # Games logic removed as UI toggles are gone.
        # We don't want to accidentally turn them off because the form lacks the keys.
        
        # Save Bank Info
        
        # Save Bank Info
        if 'bank_name' in request.form: update_setting('bank_name', request.form['bank_name'])
        if 'bank_stk' in request.form: update_setting('bank_stk', request.form['bank_stk'])
        if 'bank_ctk' in request.form: update_setting('bank_ctk', request.form['bank_ctk'])
            
        return redirect(url_for('admin_settings'))
    except Exception as e:
        return f"Error: {e}"

@app.route('/admin/withdrawals')
def admin_withdrawals():
    if not is_logged_in(): return redirect(url_for('admin_login'))
    status = request.args.get('status', 'pending')
    wds = get_all_withdrawals(status=status)
    return render_template('withdrawals.html', withdrawals=wds, status=status)

# --- ACTION ROUTES ---

from database import modify_user_data, update_withdrawal_status, get_withdrawal_by_id, log_admin_action

@app.route('/admin/user/<user_id>/adjust_balance', methods=['POST'])
def adjust_balance(user_id):
    if not is_logged_in(): return redirect(url_for('admin_login'))
    try:
        amount = int(request.form.get('amount'))
        reason = request.form.get('reason')
        
        def adjust(u):
            u['balance'] += amount
            return True
            
        modify_user_data(user_id, adjust)
        log_admin_action("ADMIN", "ADJUST_BALANCE", user_id, f"Amount: {amount}, Reason: {reason}")
        return redirect(request.referrer)
    except Exception as e:
        return f"Error: {e}"

@app.route('/admin/user/<user_id>/ban', methods=['POST'])
def ban_user(user_id):
    if not is_logged_in(): return redirect(url_for('admin_login'))
    reason = request.form.get('reason')
    try:
        hours = int(request.form.get('hours', 87600))
    except: hours = 87600
    
    def ban_logic(u):
        u['banned_until'] = (datetime.datetime.now() + datetime.timedelta(hours=hours)).isoformat()
        u['ban_reason'] = reason
        return True
        
    modify_user_data(user_id, ban_logic)
    log_admin_action("ADMIN", "BAN", user_id, f"Reason: {reason}, Hours: {hours}")
    return redirect(request.referrer)

@app.route('/admin/user/<user_id>/unban', methods=['POST'])
def unban_user(user_id):
    if not is_logged_in(): return redirect(url_for('admin_login'))
    
    def unban_logic(u):
        u['banned_until'] = None
        u['ban_reason'] = None
        return True
        
    modify_user_data(user_id, unban_logic)
    log_admin_action("ADMIN", "UNBAN", user_id)
    return redirect(request.referrer)

@app.route('/admin/user/<user_id>/approve_withdrawal/<w_id>', methods=['POST'])
def approve_withdrawal(user_id, w_id): # Updated signature if needed, but wait, routes might be different. Let's stick to what we see.
    pass 
    
# Re-implementing routes cleanly based on file content

@app.route('/admin/withdrawal/<w_id>/approve', methods=['POST'])
def approve_withdrawal_route(w_id):
    if not is_logged_in(): return redirect(url_for('admin_login'))
    
    if update_withdrawal_status(w_id, 'approved'):
        try:
             w = get_withdrawal_by_id(w_id)
             if w:
                 bot.send_message(w['user_id'], f"✅ Yêu cầu rút tiền {w['amount']:,} VND đã được DUYỆT!")
        except: pass
    return redirect(request.referrer)

@app.route('/admin/withdrawal/<w_id>/reject', methods=['POST'])
def reject_withdrawal_route(w_id):
    if not is_logged_in(): return redirect(url_for('admin_login'))
    reason = request.form.get('reason')
    
    w = get_withdrawal_by_id(w_id)
    if not w or w['status'] != 'pending':
        return "Invalid withdrawal or already processed"

    if update_withdrawal_status(w_id, 'rejected'):
        # Refund
        def refund(u):
            u['balance'] += w['amount']
            return True
        modify_user_data(w['user_id'], refund)
        
        try:
             bot.send_message(w['user_id'], f"❌ Yêu cầu rút tiền {w['amount']:,} VND bị TỪ CHỐI.\nLý do: {reason}\nSố tiền đã được hoàn lại.")
        except: pass
        
    return redirect(request.referrer)

@app.route('/admin/user/<user_id>/edit_info', methods=['POST'])
def edit_user_info(user_id):
    if not is_logged_in(): return redirect(url_for('admin_login'))
    
    try:
        vip_level = int(request.form.get('vip_level', 0))
        win_rate = int(request.form.get('win_rate', -1))
        required_wager = int(request.form.get('required_wager', 0)) # Add Wager Req
        
        def update_info(u):
            u['vip_level'] = vip_level
            u['win_rate'] = win_rate
            u['required_wager'] = required_wager # Update Wager Req
            return True
        
        modify_user_data(user_id, update_info)
        log_admin_action("ADMIN", "EDIT_INFO", user_id, f"VIP: {vip_level}, Rate: {win_rate}, Wager: {required_wager}")
        return redirect(request.referrer)
    except Exception as e:
        return f"Error: {e}"

@app.route('/admin/analytics')
def admin_analytics():
    if not is_logged_in(): return redirect(url_for('admin_login'))
    from database import get_financial_stats
    stats = get_financial_stats()
    return render_template('analytics.html', stats=stats)

@app.route('/admin/user/<user_id>/message', methods=['POST'])
def message_user_route(user_id):
    if not is_logged_in(): return redirect(url_for('admin_login'))
    
    msg = request.form.get('message')
    if not msg: return "Empty message"
    
    try:
        bot.send_message(user_id, f"📩 **TIN NHẮN TỪ ADMIN**\n\n{msg}", parse_mode="Markdown")
        log_admin_action("ADMIN", "SEND_MSG", user_id, f"Content: {msg}")
    except Exception as e:
        return f"Failed to send: {e}"
        
    return redirect(request.referrer)

# --- SETTINGS & GIFTCODES ---

# ... (admin_settings and update_settings_action remain the same, hidden here) ...

@app.route('/admin/giftcodes/create', methods=['POST'])
def create_giftcode_route():
    if not is_logged_in(): return redirect(url_for('admin_login'))
    
    code = request.form.get('code')
    try:
        amount = int(request.form.get('amount'))
        quantity = int(request.form.get('quantity'))
        hours = int(request.form.get('hours'))
        wager = int(request.form.get('wager', 1)) # Wager Mult
    except:
        return "Invalid input"
        
    from database import create_giftcode
    
    import random, string
    if not code:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
    try:
        if create_giftcode(code, amount, quantity, hours, wager): # Pass Wager
             return redirect(url_for('admin_giftcodes'))
        else:
             return "Failed (Generic Error)"
    except Exception as e:
        return f"Failed: {e}"

# ... (create_giftcode_route restored above) ...

@app.route('/admin/giftcodes')
def admin_giftcodes():
    if not is_logged_in(): return redirect(url_for('admin_login'))
    from database import get_all_giftcodes
    gcs = get_all_giftcodes()
    return render_template('giftcodes.html', giftcodes=gcs)

@app.route('/admin/giftcode/<code>/delete', methods=['POST'])
def delete_giftcode_route(code):
    if not is_logged_in(): return redirect(url_for('admin_login'))
    from database import delete_giftcode
    delete_giftcode(code)
    return redirect(url_for('admin_giftcodes'))

@app.route('/admin/broadcast', methods=['POST'])
def broadcast_route():
    if not is_logged_in(): return redirect(url_for('admin_login'))
    
    msg = request.form.get('message')
    if not msg: return "Empty message"
    
    from database import get_all_user_ids
    users = get_all_user_ids()
    
    count = 0
    for uid in users:
        try:
            bot.send_message(uid, f"📢 **THÔNG BÁO TỪ ADMIN**\n\n{msg}", parse_mode="Markdown")
            count += 1
            time.sleep(0.05)
        except: pass
        
    return f"Broadcast sent to {count} users. <a href='/admin/settings'>Back</a>"

@app.route('/admin/logs')
def admin_logs():
    if not is_logged_in(): return redirect(url_for('admin_login'))
    log_type = request.args.get('type', 'game')
    filename = 'game_logs.txt'
    if log_type == 'transaction': filename = 'transaction_logs.txt'
    if log_type == 'admin': filename = 'admin_logs.txt'
    
    logs = []
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                logs = f.readlines()
            logs.reverse() # Newest first
    except: pass
    
    return render_template('logs.html', logs=logs, log_type=log_type)

# --- BACKGROUND TASKS ---

def fake_notification_loop():
    """Sends fake activity messages to the group."""
    while True:
        try:
            # Random sleep 1m to 60m
            sleep_time = random.randint(60, 3600)
            time.sleep(sleep_time)
            
            if LIVE_GROUP_ID == 0: continue
            
            fake_prefix = random.randint(100, 999) 
            fake_suffix = random.randint(100, 999)
            masked_id = f"{fake_prefix}****{fake_suffix}"
            
            event_type = random.choices(["win", "deposit", "withdraw"], weights=[50, 30, 20], k=1)[0]
            
            if event_type == "win":
                game = random.choice(["TÀI XỈU", "CHẴN LẺ"])
                # Random 500k - 1m5 (odd numbers)
                amount = random.randint(500000, 1500000)
                # Make it look random like 563,386
                # current amount is integer, formatting will handle commas.
                # To make last digits random:
                amount = (amount // 1000) * 1000 + random.randint(0, 999)
                
                msg = (
                    f"🏆 **CHIẾN THẦN ĐỔ BỘ** 🏆\n"
                    f"➖➖➖➖➖➖➖➖➖➖\n"
                    f"👤 **Vua chơi:** `ID {masked_id}`\n"
                    f"🎮 **Bộ môn:** #{game}\n"
                    f"💰 **Húp trọn:** +{amount:,} VND\n"
                    f"➖➖➖➖➖➖➖➖➖➖\n"
                    f"👉 _Vào Bot chiến ngay!_"
                )
            elif event_type == "deposit":
                # Specific list of amounts
                amounts = [10000, 20000, 40000, 50000, 60000, 80000, 100000, 120000, 250000, 380000, 560000, 500000, 820000, 630000, 600000]
                amount = random.choice(amounts)
                msg = (
                    f"💳 **TIN TINH**\n"
                    f"➖➖➖➖➖➖➖➖➖➖\n"
                    f"👤 **Thành viên:** `ID {masked_id}`\n"
                    f"💰 **Nạp vào:** +{amount:,} VND\n"
                    f"🚀 **Tốc độ:** _Siêu tốc 1s_"
                )
            elif event_type == "withdraw":
                # Random 50k - 1m
                amount = random.randint(50000, 1000000)
                # Round to thousands for cleaner look or keep odd? request implied range.
                # Let's keep it somewhat clean but random thousands
                amount = (amount // 10000) * 10000 
                
                msg = (
                    f"💸 **RÚT TIỀN THÀNH CÔNG**\n"
                    f"➖➖➖➖➖➖➖➖➖➖\n"
                    f"👤 **Thành viên:** `ID {masked_id}`\n"
                    f"💰 **Rút về:** -{amount:,} VND\n"
                    f"🏦 **Trạng thái:** ✅ Đã chuyển\n"
                    f"👉 _Uy tín - Xanh chín!_"
                )

            bot.send_message(LIVE_GROUP_ID, msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Fake notify error: {e}")
            time.sleep(60)

def auto_giftcode_loop():
    """Generates a random giftcode every 30 minutes."""
    while True:
        try:
            time.sleep(1800) # 30 minutes
            
            if LIVE_GROUP_ID == 0: continue
            
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            amount = random.randint(1000, 10000)
            quantity = 1
            wager = 0
            expires = datetime.datetime.now() + datetime.timedelta(minutes=5)
            
            data = get_data_snapshot()
            if "giftcodes" not in data: data["giftcodes"] = {}
            
            data["giftcodes"][code] = {
                "amount": amount,
                "quantity": quantity,
                "wager": wager,
                "expires": expires.isoformat(),
                "used": 0
            }
            save_data_snapshot(data)
            
            msg = (
                f"🧧 **GIFTCODE MAY MẮN** 🧧\n"
                f"🎫 Mã: `{code}`\n"
                f"💰 Giá trị: {amount:,} VND\n"
                f"🔢 Lượt dùng: {quantity}\n"
                f"⏳ Hết hạn: 5 phút\n"
                f"👉 Nhanh tay nhập mã!"
            )
            bot.send_message(LIVE_GROUP_ID, msg, parse_mode="Markdown")
            
        except Exception as e:
            print(f"Auto Giftcode Error: {e}")
            time.sleep(60)

def run():
  try:
      port = int(os.environ.get("PORT", 7860))
  except:
      port = 7860
  app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == "__main__":
    # Start web server FIRST to satisfy Hugging Face health check
    keep_alive()

    # Ensure only one instance runs
    # kill_previous_instances("main.py") # Commented out for Cloud/Docker environment
    
    # Start background threads
    threading.Thread(target=fake_notification_loop, daemon=True).start()
    threading.Thread(target=auto_giftcode_loop, daemon=True).start()
    
    print("Bot is starting... waiting for messages.")
    try:
        bot.remove_webhook()
    except Exception:
        pass

    while True:
        try:
            bot.polling(non_stop=True, interval=2, timeout=60, long_polling_timeout=60)
        except Exception as e:
            # Mask the huge error log
            err_str = str(e)
            if "NameResolutionError" in err_str or "ConnectionPool" in err_str:
                print(f"⚠️ Network Error: Unable to connect to Telegram. Retrying in 15s...")
                time.sleep(15)
            else:
                print(f"Bot polling error: {e}")
                time.sleep(5)
