import os
import psutil
import requests
import random
import time

def kill_previous_instances(current_script_name):
    """Kills other running instances of the specified script."""
    current_pid = os.getpid()
    
    print(f"Checking for other instances of {current_script_name}...")
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                # Check if the script name is present in command line arguments
                if cmdline and any(current_script_name in arg for arg in cmdline):
                    if proc.info['pid'] != current_pid:
                        print(f"Stopping existing bot instance (PID: {proc.info['pid']})...")
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
                        except Exception:
                            pass
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

# Simple in-memory cache
_BLOCK_CACHE = {
    'last_update': 0,
    'data': []
}

def get_recent_blocks(limit=10):
    """Fetches a list of recent blocks from TronGrid with caching."""
    global _BLOCK_CACHE
    
    # Check cache (valid for 3 seconds)
    if time.time() - _BLOCK_CACHE['last_update'] < 3 and _BLOCK_CACHE['data']:
        return _BLOCK_CACHE['data'][:limit]
        
    try:
        r = requests.get("https://apilist.tronscan.org/api/block", params={"sort": "-number", "limit": limit}, timeout=5)
        data_api = r.json()
        candidates = []
        for blk in data_api.get('data', []):
            try:
                candidates.append((blk['number'], blk['hash']))
            except: continue
            
        # Update Cache
        if candidates:
            _BLOCK_CACHE['last_update'] = time.time()
            _BLOCK_CACHE['data'] = candidates
            
        return candidates
    except:
        # Fallback for demo/offline
        chars = "0123456789abcdef"
        candidates = []
        for i in range(limit):
             real_hash = "0000" + "".join(random.choice(chars) for _ in range(60))
             block_num = 12345 + i
             candidates.append((block_num, real_hash))
        return candidates

def get_blockchain_result():
    # Legacy wrapper
    blocks = get_recent_blocks(1)
    if blocks: return blocks[0]
    return 0, "0000"  
# Cooldown Cache
_USER_COOLDOWNS = {}

def check_cooldown(user_id, cooldown_time=2.0):
    """
    Checks if a user is in cooldown. 
    Returns True if allowed (not in cooldown), False if spamming.
    """
    global _USER_COOLDOWNS
    now = time.time()
    
    last_time = _USER_COOLDOWNS.get(user_id, 0)
    
    if now - last_time < cooldown_time:
        return False
    
    _USER_COOLDOWNS[user_id] = now
    
    # Cleanup old entries occasionally (simple check)
    if len(_USER_COOLDOWNS) > 1000:
        cleanup_threshold = now - 60
        _USER_COOLDOWNS = {k: v for k, v in _USER_COOLDOWNS.items() if v > cleanup_threshold}
        
    return True
