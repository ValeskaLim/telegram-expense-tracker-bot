# 💰 Expense Tracker Bot

A personal Telegram bot to track daily expenses. Log expenses against a **bank**
(`bca1`, `bca2`, `mandiri`, `cimb`) and query them by date or month. Months can be typed
in **Indonesian or English** (`Desember` or `December`).

**Features**
- ✅ **Button menu** — tap through every action (Add / Check / Audit / Change / Delete); no syntax to remember
- ✅ Quick add for today or any date this year
- ✅ Fixed bank/payment source (`bca1`, `bca2`, `mandiri`, `cimb`)
- ✅ Daily check and monthly audit (with per-bank breakdown)
- ✅ Edit and delete entries by ID
- ✅ Indonesian/English month names, Indonesian Rupiah formatting
- ✅ Dates use Asia/Jakarta time, independent of the server's timezone
- ✅ Input validation, error handling, and indexed SQLite storage

---

## 🖱️ Button menu (no typing required)
Send **/start** or **/menu** and tap a button. Each action is a short, guided
wizard that edits one message in place as you go:

- **➕ Add** — pick the day (or **📅 Today**), pick the month, type the note, type
  the amount, pick the bank, then **✅ Submit**.
- **📅 Check** — pick a date (or **Today**) and an optional bank filter.
- **📊 Audit** — pick a month (or **This month**) and a year.
- **✏️ Change** — send the entry **ID**, choose the field, enter the new value.
- **🗑️ Delete** — send the entry **ID** and confirm.

Cancel at any step with **❌ Cancel** or **/cancel**.

---

## 📖 Commands (typed fast path)
> Every typed command below still works. Sending a command with **no arguments**
> (e.g. just `/add`) opens its button wizard instead.

### ➕ `/add` — log an expense
The **last** word is the bank, the one before it is the amount, and everything
before that is the note.

```
/add <notes...> <amount> <bank>                 # today
/add <day> <month> <notes...> <amount> <bank>   # a date this year
```
Examples:
```
/add Makan siang 16000 bca1
/add 16 Desember Makan siang 20000 bca1
```
Bank must be one of: `bca1`, `bca2`, `mandiri`, `cimb`. Amounts may include thousands
separators (`16.000` or `16000`).

> ℹ️ If your note begins with a number followed by a month name (e.g.
> `16 Desember ...`), it is treated as the date form.

---

### 📅 `/check` — expenses on a date
```
/check <day> <month> <year> [bank]
```
Examples:
```
/check 16 Desember 2026
/check 16 December 2026 bca1
```

---

### 📊 `/audit` — monthly summary
```
/audit <month> <year>
```
Example:
```
/audit Desember 2026
```
Shows the total, entry count, and a per-bank breakdown.

---

### ✏️ `/change` — edit an entry by ID
```
/change <id> <field> <value...>
```
`field` is one of `amount`, `notes`, `bank`, or `date`:
```
/change 5 amount 25000
/change 5 notes Makan malam enak
/change 5 bank mandiri
/change 5 date 17 Desember 2026
```

---

### 🗑️ `/delete` — remove an entry by ID
```
/delete <id>
```

> 💡 IDs are shown as `ID:5` next to each entry in `/check` and `/audit`.

---

## 📅 Supported month names
**Indonesian:** Januari, Februari, Maret, April, Mei, Juni, Juli, Agustus,
September, Oktober, November, Desember
**English:** January … December
Common abbreviations also work (`Des`, `Dec`, `Sep`, …).

---

## 🗂️ Project layout
| File | Responsibility |
|------|----------------|
| `main.py` | Entry point — builds the app and registers handlers |
| `flows.py` | Button wizard — one `ConversationHandler` driving every action |
| `keyboards.py` | Inline-keyboard builders (pure, reused across flows) |
| `handlers.py` | Typed commands and the shared `render_*` response builders |
| `database.py` | SQLite access layer (`Database` class) |
| `utils.py` | Date/amount parsing & formatting helpers (pure, unit-tested) |
| `constant.py` | Banks, month maps, amount limits |
| `config.py` | Loads `BOT_TOKEN` from `.env` |

---

## 🚀 Setup on Ubuntu VPS

### 1. Transfer files (from Windows CMD, not SSH)
```cmd
scp main.py handlers.py database.py utils.py constant.py config.py requirements.txt .env root@your-vps-ip:/root/expense-tracker/
```
> Don't overwrite the server's `expenses.db` — it holds your real data. The
> schema migrates automatically on startup (a legacy `category` column is
> renamed to `bank`).

### 2. Install dependencies
```bash
cd /root/expense-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Create `.env` (if not transferred)
```bash
echo 'BOT_TOKEN=123456789:ABCdef...' > .env
```
Get the token from [@BotFather](https://t.me/BotFather).

### 4. Run
```bash
python3 main.py
```

### 5. (Optional) Run as a systemd service
```ini
# /etc/systemd/system/expense-bot.service
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
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now expense-bot
sudo systemctl status expense-bot
journalctl -u expense-bot -f   # logs
```

---

## 🗄️ Database
- **SQLite**, stored as `expenses.db` in the project folder.
- Columns: `id, date, amount, notes, bank, created_at`.
- Indexed on `date`, `bank`, and `(date, bank)`.
- Back up by copying `expenses.db`.

---

## ⚙️ Configuration
Edit `constant.py`:
- `BANKS` — accepted bank values (default `bca1`, `bca2`, `mandiri`, `cimb`).
- `MIN_AMOUNT` / `MAX_AMOUNT` — amount limits (default `1` … `1,000,000,000`).

---

## 📝 Version History
### v4.0 (Button UI)
- Full **inline-button menu** and a step-by-step wizard for every action.
- Each flow edits a single message in place (tap the day/month/bank, type only
  the note and amount).
- Typed commands kept as a fast path; rendering shared via `render_*` helpers.
- New `flows.py` (`ConversationHandler`) and `keyboards.py`.

### v3.0 (Refactored command set)
- New commands: `/add`, `/check`, `/audit`, `/change`, `/delete`.
- `category` replaced by a fixed `bank` field with validation.
- English + Indonesian month names; Indonesian display and Asia/Jakarta dates.
- Split into `handlers.py` / `utils.py` / `database.py` / `constant.py`.
- HTML-escaped output so notes can't break message formatting.

### v2.0
- Connection management, indexes, validation, `/edit`, error handling.

### v1.0
- Initial release.
