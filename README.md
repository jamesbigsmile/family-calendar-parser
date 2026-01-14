
# Family Calendar Parser

Lightweight self-hosted email-to-calendar system for Mac mini. Parses natural language emails into CSV events using local Ollama (Qwen2.5). No cloud, no paid services.

## Features
- Gmail IMAP polling (15min interval)
- Dual parsing: structured rules + Ollama NL
- Flask web UI for event management
- CSV storage (human-readable)
- Daily summary emails
- Relative date/time handling

## Architecture
```
Gmail → IMAP → Python/Flask → CSV events → Web UI
                           ↓
                      Ollama Qwen2.5 (optional NL parsing)
```

## Quick Start
```bash
# 1. Clone repo
git clone <repo-url>
cd family-calendar

# 2. Setup (Mac mini)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure .env
cp .env.example .env
# Edit with your Gmail app password

# 4. Start Ollama (separate terminal)
OLLAMA_KEEP_ALIVE=24h ollama serve
ollama pull qwen2.5:0.5b

# 5. Start app
python3 app.py

# 6. Open browser
http://localhost:5000
```

## Email Examples
```
"Duty day Tuesday from 6am to 10pm" → 2026-01-14 0600 Duty day
"Meeting Thursday at 2pm" → 2026-01-16 1400 Meeting
"Yoga Saturday the 17th at 9am" → 2026-01-17 0900 Yoga
```

## Files
- `app.py` - Flask web UI
- `backend.py` - Email polling, parsing, CSV ops
- `requirements.txt` - Dependencies
- `.env.example` - Config template
- `docs/` - Build notes, fixes, improvements

## Credits
Built for hobby use on Mac mini 8GB RAM. Free services only.
