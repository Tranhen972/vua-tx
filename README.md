---
title: Vibecode Bot
emoji: 🎲
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
app_port: 7860
---

# Telegram Bot Tài Xỉu (Refactored)

Đây là mã nguồn mẫu cho bot Telegram chơi game Tài Xỉu đơn giản (Đã tối ưu mã nguồn).

## Cấu trúc Project

- `main.py`: File chính để chạy Bot.
- `config.py`: Chứa cấu hình Token, Admin ID.
- `database.py`: Xử lý lưu trữ dữ liệu JSON.
- `handlers.py`: Chứa các lệnh và phản hồi của Bot.
- `games.py`: Logic xử lý game (Tài xỉu, Chẵn lẻ).
- `keyboards.py`: Các menu phím bấm.
- `utils.py`, `loader.py`: Các tiện ích hỗ trợ.

## Yêu cầu

- Python 3.x
- Bot Token từ BotFather trên Telegram

## Cài đặt

1. Cài đặt thư viện cần thiết:
   ```bash
   pip install -r requirements.txt
   ```

2. Cấu hình:
   - Mở file `config.py`
   - Thay đổi `API_TOKEN`, `ADMIN_ID`, `LIVE_GROUP_ID` phù hợp với bạn.

## Chạy Bot

Chạy lệnh sau trong terminal:
```bash
python main.py
```

## Chức năng
- **Menu chính**: Dễ dàng điều hướng tất cả các tính năng.
- **Game Tài Xỉu / Chẵn Lẻ (Blockchain System)**:
  - Kết quả minh bạch dựa trên Hash của TRON Blockchain.
  - Tự động cộng/trừ tiền và tính VIP.
- **Tài khoản**: Xem số dư, lịch sử (giả lập).
- **Nạp Tiền**: Hiển thị thông tin chuyển khoản.
- **Rút Tiền**: Rút tiền tự động tạo đơn chờ Admin duyệt.
- **Admin Panel**: Quản lý user, cộng trừ tiền, duyệt đơn rút, tạo giftcode.
- **Giftcode**: Hệ thống giftcode tự động.
- **Bot Notification**: Thông báo ảo tạo hiệu ứng đám đông.
