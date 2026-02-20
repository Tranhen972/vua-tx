# config.py
import os

API_TOKEN = os.environ.get("API_TOKEN", '8001320606:AAGooSMkQu-cwQAuJfCeaY4NEsbcmFVMsqo')
ADMIN_ID = int(os.environ.get("ADMIN_ID", 6928858477))
LIVE_GROUP_ID = int(os.environ.get("LIVE_GROUP_ID", -1003776966487))

# DATABASE
# Render will automatically inject DATABASE_URL if the service is linked
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://tx_srot_user:Hot898xuV6M8weuN5FtFPvho3YGnswJO@dpg-d6aovl3nv86c739r9qm0-a.singapore-postgres.render.com/tx_srot")


# Game Logic Configuration
WIN_RATE = 30 # User win rate percentage (0-100). 30% means user wins 30% of time.

# VIP System Configuration
# Level: (Required Total Bet, Reward Amount)
VIP_LEVELS = {
    1: (5_000_000, 23_456),
    2: (11_000_000, 59_999),
    3: (20_000_000, 99_999),
    4: (35_000_000, 158_888),
    5: (50_000_000, 222_222),
    6: (85_000_000, 333_333),
    7: (120_000_000, 444_444),
    8: (150_000_000, 555_555),
    9: (210_000_000, 888_888),
    10: (300_000_000, 1_234_567)
}
