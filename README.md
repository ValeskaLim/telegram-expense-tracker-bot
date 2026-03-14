# 💰 Expense Tracker Bot

A Telegram bot to track your daily expenses. Log expenses in natural Indonesian date format and query them by date, range, or monthly summary.

---

## 🚀 Setup on Ubuntu VPS

### 1. Transfer files from Windows to VPS
Run this on your **Windows CMD** (not SSH):
```cmd
scp main.py database.py config.py requirements.txt .env expenses.db root@your-vps-ip:/root/expense-tracker/
```

### 2. SSH into your VPS and go to the project folder
```bash
cd /root/expense-tracker
```

### 3. Install Python dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Create your `.env` file (if not transferred)
```bash
nano .env
```

Fill in your Telegram bot token (get it from [@BotFather](https://t.me/BotFather)):
```
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
```

### 5. Run the bot
```bash
python3 main.py
```

### 6. (Optional) Run as a background service with systemd
Create the service file:
```bash
sudo nano /etc/systemd/system/expense-bot.service
```

Paste this:
```ini
[Unit]
Description=Expense Tracker Telegram Bot
After=network.target

[Service]
WorkingDirectory=/root/expense-tracker
ExecStart=/root/expense-tracker/venv/bin/python3 main.py
Restart=always
User=root
EnvironmentFile=/root/expense-tracker/.env

[Install]
WantedBy=multi-user.target
```

Then enable it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable expense-bot
sudo systemctl start expense-bot
```

To check if it's running:
```bash
sudo systemctl status expense-bot
```

To view logs:
```bash
journalctl -u expense-bot -f
```

---

## 📖 Usage

### Log an expense
Just send a message (no command needed):
```
<day> <month> <year> <amount> <notes>
```
Example:
```
8 Maret 2026 25000 Makan siang
15 April 2026 50000 Transportasi ojek
```

---

### Commands

#### `/tanggal` — Get expenses on a specific date
```
/tanggal <day> <month> <year>
```
Example:
```
/tanggal 8 Maret 2026
```

---

#### `/range` — Get expenses in a date range
```
/range <start_day> <start_month> <start_year> <end_day> <end_month> <end_year> [detail]
```
Examples:
```
/range 1 Maret 2026 31 Maret 2026
/range 1 Maret 2026 31 Maret 2026 detail
```
Add `detail` at the end to see all individual entries with their IDs.

---

#### `/summary` — Monthly summary
```
/summary <month>
/summary <month1> <month2>
```
Examples:
```
/summary Maret
/summary Maret April
```
Multi-month summary shows total per month + grand total.

---

#### `/edit` — Edit an expense
```
/edit <id> <amount> <notes>
```
Example:
```
/edit 5 30000 Makan malam
```

---

#### `/delete` — Delete an expense
```
/delete <id>
```
Example:
```
/delete 5
```

> 💡 To find an ID, use `/tanggal` or `/range ... detail` — IDs appear as `[ID:5]` next to each entry.

---

## 📅 Supported Month Names (Indonesian)
`Januari, Februari, Maret, April, Mei, Juni, Juli, Agustus, September, Oktober, November, Desember`

---

## 🗄️ Database
- Uses **SQLite** — stored as `expenses.db` in the project folder
- No extra database setup needed
- To back up: just copy `expenses.db`
- To migrate existing data from Windows: transfer `expenses.db` along with the other files