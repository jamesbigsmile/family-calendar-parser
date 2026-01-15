# Family Calendar Parser v1.3

Lightweight family calendar from email. Free services only.

## Quick Start

```bash
cd family-calendar-parser
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env  # Fill Gmail credentials

python3 backend.py  # Starts polling
```

## Features

- Parses natural language emails → calendar events
- Relative dates ("tomorrow", "next Thursday")
- 24-hour time parsing ("6:30pm" → 1830)
- Gmail polling every 15min
- Daily HTML summaries with logo
- CSV storage (output_folder/calendar.csv)
- Ollama Qwen2.5 local AI (no internet)

## Test

Send email to GMAIL_USER:
```
Subject: Test
Body: I have yoga tomorrow at 9 AM
```

Check:
```bash
tail -f output_folder/logs/backend*.log
cat output_folder/calendar.csv
```

## Files

- `backend.py` - Core logic + polling
- `requirements.txt` - Dependencies
- `.env.example` - Copy to `.env`
- `output_folder/` - CSV + logs (auto-created)
 #family-calendar-parser
