
# database.py - PostgreSQL Implementation
import os
import json
import threading
import time
import datetime
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from config import DATABASE_URL

# Initialize Connection Pool
try:
    # ThreadedConnectionPool is suitable for multi-threaded applications like this bot
    db_pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=5,
        maxconn=20,
        dsn=DATABASE_URL
    )
    print("Database connection pool created successfully.")
except Exception as e:
    print(f"Error creating connection pool: {e}")
    db_pool = None

data_lock = threading.Lock()

@contextmanager
def get_db_cursor(commit=False):
    """
    Context manager to get a cursor from a pooled connection.
    Automatically handles connection retrieval, commit/rollback, and return to pool.
    """
    conn = None
    try:
        if db_pool:
            conn = db_pool.getconn()
            if conn:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                try:
                    yield cur
                    if commit:
                        conn.commit()
                except Exception as e:
                    conn.rollback()
                    raise e
                finally:
                    cur.close()
            else:
                raise Exception("Failed to get connection from pool")
        else:
             # Fallback if pool creation failed (mostly for debugging or strict environments)
             conn = psycopg2.connect(DATABASE_URL)
             cur = conn.cursor(cursor_factory=RealDictCursor)
             try:
                yield cur
                if commit:
                    conn.commit()
             except Exception as e:
                 conn.rollback()
                 raise e
             finally:
                 cur.close()
    except Exception as e:
        print(f"DB Operation Error: {e}")
        # If we yield nothing/error, the caller must handle it, 
        # but to keep existing code safe-ish we yield a dummy or re-raise.
        # Re-raising is better to catch bugs.
        raise e
    finally:
        if conn and db_pool:
            db_pool.putconn(conn)
        elif conn and not db_pool:
            conn.close()

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"DB Connection Error: {e}")
        return None

def init_db():
    """Initialize database tables if they don't exist"""
    print("Checking database tables...")
    try:
        with get_db_cursor(commit=True) as cur:
            # Users Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    balance BIGINT DEFAULT 0,
                    vip_level INTEGER DEFAULT 0,
                    total_deposit BIGINT DEFAULT 0,
                    total_withdraw BIGINT DEFAULT 0,
                    total_bet BIGINT DEFAULT 0,
                    current_bet BIGINT DEFAULT 0,
                    required_wager BIGINT DEFAULT 0,
                    win_rate INTEGER DEFAULT -1,
                    last_bonus DATE,
                    history JSONB DEFAULT '[]',
                    deposit_history JSONB DEFAULT '[]',
                    withdraw_history JSONB DEFAULT '[]',
                    used_giftcodes JSONB DEFAULT '[]',
                    completed_missions JSONB DEFAULT '[]',
                    banned_until TIMESTAMP,
                    ban_reason TEXT,
                    bank_info JSONB DEFAULT '{}'
                );
            """)
            
            # Withdrawals Table (Pending Requests)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id TEXT PRIMARY KEY,
                    user_id BIGINT,
                    amount BIGINT,
                    bank_name TEXT,
                    stk TEXT,
                    ctk TEXT,
                    time TEXT,
                    status TEXT
                );
            """)
            
            # Giftcodes Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS giftcodes (
                    code TEXT PRIMARY KEY,
                    amount BIGINT,
                    quantity INTEGER,
                    wager INTEGER DEFAULT 1,
                    expires TIMESTAMP,
                    used INTEGER DEFAULT 0
                );
            """)
            
            # Settings Table (Key-Value)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value JSONB
                );
            """)
            # Default Settings
            cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT DO NOTHING", 
                        ('global_win_rate', '30'))

        print("Database initialized successfully.")
    except Exception as e:
        print(f"Init DB Error: {e}")

# Run init on import
init_db()

# --- ADAPTER FUNCTIONS TO MATCH OLD API ---

def get_data_snapshot():
    """
    Simulates fetching all data. 
    WARNING: For PostgreSQL, fetching ALL users is bad practice.
    However, the bot code relies on 'data["users"][id]'. 
    We will modify this to return a PROXY object or minimal data.
    Actually, to support existing code with minimal changes, 
    we will implement 'get_user_context' to fetch ONLY the specific user.
    Calls to 'get_data_snapshot' should be minimized.
    """
    # Create a structure that looks like the old JSON but fetches from DB
    # We only fetch critical global lists. Users are fetched on demand.
    
    try:
        with get_db_cursor(commit=False) as cur:
            # Fetch Withdrawals (Only Pending to look like JSON list)
            cur.execute("SELECT * FROM withdrawals WHERE status = 'pending'")
            withdrawals = [dict(row) for row in cur.fetchall()]
            
            # Fetch Giftcodes
            cur.execute("SELECT * FROM giftcodes")
            giftcodes_list = cur.fetchall()
            giftcodes = {row['code']: dict(row) for row in giftcodes_list}
            # handling 'expires' timestamp to string if needed by old code
            for gc in giftcodes.values():
                if gc['expires']: gc['expires'] = gc['expires'].isoformat()

            # Fetch Settings
            cur.execute("SELECT * FROM settings")
            settings = {}
            for row in cur.fetchall():
                settings[row['key']] = row['value']
            
            # Return a dict where 'users' is empty initially. 
            return {
                "users": {}, # Metadata only, populating this is expensive
                "withdrawals": withdrawals,
                "giftcodes": giftcodes,
                "settings": settings
            }
    except Exception as e:
        print(f"Snapshot Error: {e}")
        return {"users": {}, "withdrawals": [], "giftcodes": {}, "settings": {"global_win_rate": 30}}

def save_data_snapshot(data):
    """
    Syncs 'settings' and 'giftcodes' back to DB.
    Users and Withdrawals are updated atomically via specific functions.
    """
    try:
        with get_db_cursor(commit=True) as cur:
            # Save Settings
            if "settings" in data:
                for k, v in data["settings"].items():
                    # v is already a value (int/str), not json string yet?
                    # get_data_snapshot loads it.
                    # data["settings"]["global_win_rate"] = rate (int)
                    # We should json dump it or store as text?
                    # The table schema says value is JSONB.
                    # So we should json.dumps it.
                    cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (k, json.dumps(v)))
            
            # Save Giftcodes (Upsert - mainly for creation)
            if "giftcodes" in data:
                for code, gc in data["giftcodes"].items():
                    # We upsert. Note: logic requiring atomic usage updates should NOT rely on this.
                    # usage updates use 'update_giftcode_usage'.
                    # This is mainly for 'process_create_giftcode'.
                    expires = gc.get('expires')
                    cur.execute("""
                        INSERT INTO giftcodes (code, amount, quantity, wager, expires, used)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (code) DO NOTHING
                    """, (code, gc['amount'], gc['quantity'], gc.get('wager', 1), expires, gc.get('used', 0)))
                    # changed to DO NOTHING on conflict to prevent overwriting 'used' count by accident
                    # if admin tries to recreate same code? 
                    # Actually if admin edits logic? process_create_giftcode overwrites.
                    # If we want to allow overwrite, we should allow it.
                    # But for now DO NOTHING is safer for concurrent usage. 
                    # If admin wants to delete, they use delete.
    except Exception as e:
        print(f"Save Snapshot Error: {e}")

def get_user_context(user_id):
    """
    Fetches specific user from DB and returns a format compatible with old code.
    """
    user_id = int(user_id)
    
    try:
        data = get_data_snapshot() # This now uses the pool too (nested pool usage is fine with threading pool)
        
        with get_db_cursor(commit=True) as cur: # commit=True because we might INSERT
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            
            if not row:
                # Create new user
                cur.execute("""
                    INSERT INTO users (user_id, balance, history, deposit_history, withdraw_history) 
                    VALUES (%s, 0, '[]', '[]', '[]')
                """, (user_id,))
                # Re-fetch is guaranteed if we are in same transaction/conn? 
                # Actually, with commit=True in context manager, we won't see it until next SELECT 
                # but commit happens at EXIT. 
                # So we must INSERT and then SELECT in same trans or just default construct.
                # To be safe:
                user = {
                    'user_id': user_id, 'balance': 0, 'history': [], 
                    'deposit_history': [], 'withdraw_history': [], 'used_giftcodes': [],
                    'completed_missions': [], 'bank_info': {}, 'vip_level': 0,
                    'total_deposit': 0, 'total_withdraw': 0, 'total_bet': 0, 
                    'current_bet': 0, 'required_wager': 0, 'win_rate': -1
                }
                # No need to re-fetch if we just inserted defaults.
            else:
                 # Convert row to dict
                user = dict(row)
                # Ensure JSON fields are lists
                if not user['history']: user['history'] = []
                if not user['deposit_history']: user['deposit_history'] = []
                if not user['withdraw_history']: user['withdraw_history'] = []
                if not user['used_giftcodes']: user['used_giftcodes'] = []
                if not user['completed_missions']: user['completed_missions'] = []
                if not user['bank_info']: user['bank_info'] = {}

        data["users"][str(user_id)] = user
        return data, user
    except Exception as e:
        print(f"Get User Error: {e}")
        return {}, {}

def modify_user_data(user_id, callback):
    """
    Transactional update for USER only.
    """
    with data_lock:
        # 1. Fetch latest (only user needed really, but maintaining API)
        data, user = get_user_context(user_id)
        
        # 2. Apply logic
        should_save = callback(user)
        
        if should_save:
            # 3. Write back to DB
            try:
                with get_db_cursor(commit=True) as cur:
                    cur.execute("""
                        UPDATE users SET
                            balance = %s,
                            vip_level = %s,
                            total_deposit = %s,
                            total_withdraw = %s,
                            total_bet = %s,
                            current_bet = %s,
                            required_wager = %s,
                            win_rate = %s,
                            last_bonus = %s,
                            history = %s,
                            deposit_history = %s,
                            withdraw_history = %s,
                            used_giftcodes = %s,
                            completed_missions = %s,
                            banned_until = %s,
                            ban_reason = %s,
                            bank_info = %s
                        WHERE user_id = %s
                    """, (
                        user['balance'], user['vip_level'], user['total_deposit'], user['total_withdraw'], 
                        user['total_bet'], user['current_bet'], user['required_wager'], user['win_rate'],
                        user['last_bonus'], 
                        json.dumps(user['history'], default=str),
                        json.dumps(user['deposit_history'], default=str),
                        json.dumps(user['withdraw_history'], default=str),
                        json.dumps(user['used_giftcodes'], default=str),
                        json.dumps(user['completed_missions'], default=str),
                        user.get('banned_until'), user.get('ban_reason'),
                        json.dumps(user['bank_info'], default=str),
                        int(user_id)
                    ))
                return user
            except Exception as e:
                print(f"Modify User Error: {e}")
                import traceback
                traceback.print_exc()
                return user
        return user

def add_withdrawal_request(w):
    try:
        with get_db_cursor(commit=True) as cur:
             cur.execute("""
                INSERT INTO withdrawals (id, user_id, amount, bank_name, stk, ctk, time, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status
             """, (w['id'], w['user_id'], w['amount'], w.get('bank_name'), w.get('stk'), w.get('ctk'), w['time'], w['status']))
    except Exception as e:
        print(f"Add Withdraw Error: {e}")

def update_giftcode_usage(code, used, quantity):
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("UPDATE giftcodes SET used = %s, quantity = %s WHERE code = %s", (used, quantity, code))
    except Exception as e:
         print(f"Update Giftcode Error: {e}")

def log_game(user_id, game_type, bet_amount, selection, outcome, win_amount, balance_after):
    # We can log to text file or DB. Text file is fine for logs.
    try:
        with open("game_logs.txt", "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sel_str = selection.upper() if selection else "UNKNOWN"
            log_entry = f"[{timestamp}] User: {user_id} | Game: {game_type} | Pick: {sel_str} | Bet: {bet_amount:,} | Result: {outcome} | Win: {win_amount:,} | Bal: {balance_after:,}\n"
            f.write(log_entry)
    except Exception as e:
        print(f"Log Error: {e}")

def log_transaction(user_id, trans_type, amount, method, status):
    try:
        with open("transaction_logs.txt", "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] User: {user_id} | Type: {trans_type} | Amount: {amount:,} | Method: {method} | Status: {status}\n"
            f.write(log_entry)
    except Exception as e:
        print(f"Log Error: {e}")

def log_admin_action(admin_id, action, target_id=None, details=""):
    try:
        with open("admin_logs.txt", "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] Admin: {admin_id} | Action: {action} | Target: {target_id} | Details: {details}\n"
            f.write(log_entry)
    except Exception as e:
        print(f"Log Error: {e}")

def get_system_stats():
    """Calculates system-wide statistics."""
    stats = {
        "total_users": 0,
        "total_balance": 0,
        "total_deposit": 0,
        "total_withdraw": 0,
        "total_bet": 0,
        "pending_withdrawals": 0,
        "system_profit": 0
    }
    
    try:
        data = get_data_snapshot()
        stats["pending_withdrawals"] = len(data.get("withdrawals", []))
        
        with get_db_cursor(commit=False) as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as cnt, 
                    SUM(balance) as bal, 
                    SUM(total_deposit) as dep, 
                    SUM(total_withdraw) as wd, 
                    SUM(total_bet) as bet 
                FROM users
            """)
            row = cur.fetchone()
            if row:
                stats["total_users"] = row['cnt'] or 0
                stats["total_balance"] = row['bal'] or 0
                stats["total_deposit"] = row['dep'] or 0
                stats["total_withdraw"] = row['wd'] or 0
                stats["total_bet"] = row['bet'] or 0
            
            # Simple Profit Calculation: (Total Deposit - Total Withdraw) - User Balances (Liability)
            # This represents "real money remaining" in the pot.
            stats["system_profit"] = stats["total_deposit"] - stats["total_withdraw"] - stats["total_balance"]

    except Exception as e:
        print(f"Stats Error: {e}")
    
    return stats

def delete_giftcode(code):
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM giftcodes WHERE code = %s", (code,))
    except Exception as e:
        print(f"Delete Giftcode Error: {e}")

def get_top_users(limit=10):
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT %s", (limit,))
            return [(row['user_id'], row['balance']) for row in cur.fetchall()]
    except Exception as e:
        print(f"Get Top Users Error: {e}")
        return []

def get_financial_stats(limit=10):
    try:
        with get_db_cursor(commit=False) as cur:
            # Top Depositors
            cur.execute("SELECT user_id, total_deposit FROM users ORDER BY total_deposit DESC LIMIT %s", (limit,))
            top_deposit = cur.fetchall()
            
            # Top Withdrawers
            cur.execute("SELECT user_id, total_withdraw FROM users ORDER BY total_withdraw DESC LIMIT %s", (limit,))
            top_withdraw = cur.fetchall()
            
            return {
                "top_deposit": top_deposit,
                "top_withdraw": top_withdraw
            }
    except Exception as e:
        print(f"Get Stats Error: {e}")
        return {"top_deposit": [], "top_withdraw": []}

def get_all_user_ids():
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT user_id FROM users")
            return [row['user_id'] for row in cur.fetchall()]
    except Exception as e:
        print(f"Get All Users Error: {e}")
        return []

def reset_all_users():
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE users 
                SET balance = 0, current_bet = 0, required_wager = 0
            """)
        return True
    except Exception as e:
        print(f"Reset All Error: {e}")
        return False

def get_users_paginated(page=1, per_page=20, search_query=None):
    """Fetches users with pagination and search."""
    try:
        offset = (page - 1) * per_page
        with get_db_cursor(commit=False) as cur:
            if search_query:
                # Optimized partial matching for ID (casted to text)
                cur.execute("""
                    SELECT user_id, balance, total_deposit, total_withdraw, vip_level, banned_until, current_bet, required_wager, bank_info, win_rate
                    FROM users 
                    WHERE CAST(user_id AS TEXT) LIKE %s 
                    ORDER BY balance DESC 
                    LIMIT %s OFFSET %s
                """, (f"%{search_query}%", per_page, offset))
                
                users = [dict(row) for row in cur.fetchall()]
                
                cur.execute("SELECT COUNT(*) as total FROM users WHERE CAST(user_id AS TEXT) LIKE %s", (f"%{search_query}%",))
                total = cur.fetchone()['total']
            else:
                cur.execute("""
                    SELECT user_id, balance, total_deposit, total_withdraw, vip_level, banned_until, current_bet, required_wager, bank_info, win_rate
                    FROM users 
                    ORDER BY balance DESC 
                    LIMIT %s OFFSET %s
                """, (per_page, offset))
                
                users = [dict(row) for row in cur.fetchall()]
                
                cur.execute("SELECT COUNT(*) as total FROM users")
                total = cur.fetchone()['total']
                
            return users, total
            
    except Exception as e:
        print(f"Get Users Error: {e}")
        return [], 0

def get_all_withdrawals(status="pending"):
    try:
        with get_db_cursor(commit=False) as cur:
            if status == "all":
                cur.execute("SELECT * FROM withdrawals ORDER BY time DESC LIMIT 100")
            else:
                 cur.execute("SELECT * FROM withdrawals WHERE status = %s ORDER BY time DESC", (status,))
            return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"Get Withdrawals Error: {e}")
        return []

def update_withdrawal_status(w_id, status):
    """Updates withdrawal status."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("UPDATE withdrawals SET status = %s WHERE id = %s", (status, w_id))
        return True
    except Exception as e:
        print(f"Update Withdraw Error: {e}")
        return False
        
def get_withdrawal_by_id(w_id):
    """Fetches a withdrawal by ID."""
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT * FROM withdrawals WHERE id = %s", (w_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"Get Withdraw Error: {e}")
        return None

def get_all_giftcodes():
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT * FROM giftcodes ORDER BY expires DESC")
            return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"Get Giftcodes Error: {e}")
        return []

def update_setting(key, value):
    try:
        with get_db_cursor(commit=True) as cur:
             cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, json.dumps(value)))
        return True
    except Exception as e:
        print(f"Update Setting Error: {e}")
        return False

def get_setting(key, default=None):
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
            row = cur.fetchone()
            return row['value'] if row else default
    except Exception as e:
        return default

def create_giftcode(code, amount, quantity, hours, wager=1):
    import datetime
    try:
        expires = datetime.datetime.now() + datetime.timedelta(hours=hours)
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO giftcodes (code, amount, quantity, wager, expires, used)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (code, amount, quantity, wager, expires, 0))
        return True
    except Exception as e:
        print(f"Create Giftcode Error: {e}")
        return False