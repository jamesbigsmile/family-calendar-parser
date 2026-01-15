
import os
import re
import json
import smtplib
import logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from pathlib import Path
import imaplib
import email
import requests
import threading
import time
from dotenv import load_dotenv
import csv
from dateparser import parse

load_dotenv()

log_dir = Path(__file__).parent / "output_folder" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"backend{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)-7s] %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ],
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).parent / "output_folder" / "calendar.csv"
CSV_COLUMNS = ["id", "date", "time", "title", "person", "location", "notes", "recurring", "created_at"]

EMAILTONAME = { //Comma seperated emails - //with names

}

def repairtruncatedjson(json_str):
    """Auto-repair truncated JSON by balancing braces."""
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')

    repairs = 0
    while open_brackets > close_brackets and repairs < 5:
        json_str += ']'
        repairs += 1

    while open_braces > close_braces and repairs < 5:
        json_str += '}'
        repairs += 1

    return json_str, repairs

def resolverelativedate(datestr):
    datestr = str(datestr).strip()
    today = datetime.now()

    try:
        parsed = parse(datestr, settings={'RELATIVE_BASE': today})
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    except:
        pass

    logger.warning(f"Could not resolve date '{datestr}', defaulting to today")
    return today.strftime("%Y-%m-%d")

def generateenhancedprompt(cleaned_body, sender_email, sender_name, today, tomorrow, today_name):
    """v1.3 Optimal prompt - 5 real examples, no hallucination"""

    today_obj = datetime.strptime(today, "%Y-%m-%d").date()
    today_weekday = today_obj.weekday()

    weekday_dates = {}
    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    for i, name in enumerate(weekday_names):
        days_ahead = (i - today_weekday) % 7
        if days_ahead == 0:
            days_ahead = 7  # Same day → next week
        weekday_dates[name.lower()] = (today_obj + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    prompt = f"""Extract calendar event from this email. Extract ONLY what is explicitly stated.

FROM: {sender_name} <{sender_email}>
EMAIL TEXT:
{cleaned_body}

TODAY: {today} ({today_name})

RULES (CRITICAL):
1. person = "{sender_name}" ALWAYS (never Ollama's guess)
2. Extract ONLY explicit information from email text
3. If not mentioned, use: date={today}, time=0900, location=""
4. Time format: 24-hour HHMM (6pm=1800, 6:30pm=1830, no time=0900)
5. Weekday dates TODAY={today}:
   - Monday={weekday_dates['monday']}, Tuesday={weekday_dates['tuesday']}, Wednesday={weekday_dates['wednesday']}
   - Thursday={weekday_dates['thursday']}, Friday={weekday_dates['friday']}, Saturday={weekday_dates['saturday']}, Sunday={weekday_dates['sunday']}

REAL EXAMPLES (from family emails):
1. "i have yoga this saturday the 17th at 9 AM" → {{"title":"Yoga","date":"2026-01-17","time":"0900","person":"{sender_name}","location":"","recurring":"none"}}
2. "Musical Parent Meeting on Jan 21 at 6:30pm" → {{"title":"Musical Parent Meeting","date":"2026-01-21","time":"1830","person":"{sender_name}","location":"","recurring":"none"}}
3. "Sarah hair appointment January 15 at 6 pm" → {{"title":"Hair appointment","date":"2026-01-15","time":"1800","person":"Sarah","location":"","recurring":"none"}}
4. "I have a meeting on Thursday at 2 with SOCI" → {{"title":"Meeting with SOCI","date":"{weekday_dates['thursday']}","time":"1400","person":"{sender_name}","location":"","recurring":"none"}}
5. "Middle School Showcase at RNS January 14 at 7 pm" → {{"title":"Middle School Showcase","date":"2026-01-14","time":"1900","person":"Simon and Sarah","location":"RNS","recurring":"none"}}

STEP-BY-STEP:
1. What is the event title? (extract from email)
2. What is the date? (use mappings above, or today={today} if none mentioned)
3. What is the time? (24-hour HHMM, 0900 if none mentioned)
4. What is the location? (only if explicitly named, else empty)
5. person = "{sender_name}" (ALWAYS)

OUTPUT JSON ONLY (no markdown, no backticks, start with {{):
"""

    return prompt

def resolverelativetime(timestr):
    timestr = str(timestr).strip().lower()

    if " to " in timestr or " - " in timestr:
        parts = re.split(r'\s+to\s+|\s+-\s+', timestr)
        timestr = parts[0].strip()

    match = re.search(r'(\d{{1,2}})(?::(\d{{2}}))?\s*(am|pm)?', timestr)
    if match:
        hour, minute, ampm = match.groups()
        hour = int(hour)
        minute = int(minute) if minute else 0

        if ampm:
            if ampm == 'pm' and hour != 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{{hour:02d}}{{minute:02d}}"

    if re.match(r'^\d{{4}}$', timestr.replace(':', '')):
        return timestr.replace(':', '')

    return "0900"

def create_csv_if_not_exists():
    if not CSV_PATH.exists():
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CSV_PATH, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
        logger.info(f"Created CSV: {{CSV_PATH}}")

def get_next_id():
    if not CSV_PATH.exists():
        return 1
    try:
        with open(CSV_PATH, 'r') as f:
            reader = csv.reader(f)
            next(reader)
            ids = [int(row[0]) for row in reader if row and row[0].isdigit()]
            return max(ids) + 1 if ids else 1
    except:
        return 1

def add_event(date, time, title, person, location="", notes="", recurring="none"):
    create_csv_if_not_exists()
    event_id = get_next_id()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(CSV_PATH, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([event_id, date, time, title, person, location, notes, recurring, created_at])

    logger.info(f"✓ Created event {{event_id}}: {{title}} on {{date}} at {{time}}")
    return event_id

def get_events():
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, 'r') as f:
        reader = csv.DictReader(f)
        return [row for row in reader if any(row.values())]

def get_events_for_date(target_date):
    return [e for e in get_events() if e.get('date') == target_date]

def edit_event(event_id, date, time, title, person, location="", notes="", recurring="none"):
    create_csv_if_not_exists()
    events = get_events()

    with open(CSV_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for e in events:
            if e.get('id') == str(event_id):
                writer.writerow({
                    'id': event_id, 'date': date, 'time': time, 'title': title,
                    'person': person, 'location': location, 'notes': notes,
                    'recurring': recurring, 'created_at': e.get('created_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                })
            else:
                writer.writerow(e)
    logger.info(f"✓ Edited event {{event_id}}: {{title}}")

def delete_event(event_id):
    create_csv_if_not_exists()
    events = get_events()

    with open(CSV_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for e in events:
            if e.get('id') != str(event_id):
                writer.writerow(e)
    logger.info(f"✓ Deleted event {{event_id}}")

def clean_email_body(body, subject=""):
    text = f"Subject: {{subject}}\n{{body}}" if subject else body
    text = text[:500]

    patterns = [r'--+', r'On .+? wrote:|Sent from .+', r'Best regards|Thanks|Regards', r'\d{{1,2}},\s*20\d{{2}}', r'\n\n+']

    for pat in patterns:
        text = re.sub(pat, '', text, flags=re.IGNORECASE | re.DOTALL)

    return text.strip()[:350]

def parse_email_to_event(email_body, sender_email):
    parsed_email = sender_email.strip()
    if '<' in parsed_email and '>' in parsed_email:
        parsed_email = parsed_email.split('<')[1].split('>')[0].strip()
    parsed_email = parsed_email.lower().strip()
    sender_name = EMAILTONAME.get(parsed_email, "Family")

    logger.info(f"📧 Sender email: {{parsed_email}} → Name: {{sender_name}}")

    simple_event = {}
    lines = email_body.split('\n')
    for line in lines:
        line_lower = line.lower()
        if 'event:' in line_lower:
            simple_event['title'] = line.split(':', 1)[1].strip()
        if 'date:' in line_lower:
            simple_event['date'] = line.split(':', 1)[1].strip()
        if 'time:' in line_lower:
            simple_event['time'] = line.split(':', 1)[1].strip()
        if 'person:' in line_lower:
            simple_event['person'] = line.split(':', 1)[1].strip()
        if 'location:' in line_lower:
            simple_event['location'] = line.split(':', 1)[1].strip()

    if 'title' in simple_event and 'date' in simple_event:
        simple_event['date'] = resolverelativedate(simple_event.get('date', ''))
        simple_event['time'] = resolverelativetime(simple_event.get('time', '0900'))
        simple_event['person'] = simple_event.get('person', sender_name)
        simple_event['location'] = simple_event.get('location', '')
        logger.info(f"✓ Parsed via simple rules: {{simple_event['title']}} on {{simple_event['date']}} at {{simple_event['time']}}")
        return simple_event

    cleaned_body = clean_email_body(email_body)
    logger.info(f"📤 Sending to Ollama: {{cleaned_body[:80]}}")

    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    today_name = datetime.now().strftime("%A")

    prompt = generateenhancedprompt(cleaned_body, parsed_email, sender_name, today, tomorrow, today_name)

    ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")

    try:
        response = requests.post(
            f"{{ollama_endpoint}}/api/generate",
            json={{
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",                    # v1.3 JSON mode
                "temperature": 0.0,                  # v1.3 Deterministic
                "top_p": 0.9,
                "top_k": 40,
                "num_predict": 150,
            }},
            timeout=300
        )

        if response.status_code == 200:
            result = response.json()
            text = result.get("response", "").strip()
            logger.info(f"📥 Ollama response ({{len(text)}} chars): {{text[:150]}}")

            json_start = text.find('{')
            json_end = text.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = text[json_start:json_end]

                try:
                    parsed = json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse error: {{e}}")
                    logger.warning(f"Attempting auto-repair of truncated JSON...")
                    repaired_json, repair_count = repairtruncatedjson(json_str)
                    logger.info(f"Repaired JSON: added {{repair_count}} closing symbols")
                    try:
                        parsed = json.loads(repaired_json)
                        logger.info(f"✓ JSON repair successful! {{repair_count}} symbols added")
                    except json.JSONDecodeError as e2:
                        logger.error(f"Repair failed: {{e2}}")
                        return {}

                parsed_date = resolverelativedate(parsed.get('date', today)) or today
                parsed_time = resolverelativetime(parsed.get('time', '0900')) or '0900'
                parsed_person = parsed.get('person', sender_name) or sender_name
                parsed_location = parsed.get('location', '') or ''

                logger.info(f"✓ Parsed via Ollama: {{parsed.get('title', 'Unknown')}} on {{parsed_date}} at {{parsed_time}}")

                return {{
                    'title': parsed.get('title', 'Unnamed Event'),
                    'date': parsed_date,
                    'time': parsed_time,
                    'person': parsed_person,
                    'location': parsed_location,
                }}
        else:
            logger.error(f"❌ Ollama error: {{response.status_code}}")
    except requests.exceptions.Timeout:
        logger.error("❌ Ollama timeout (300s)")
    except Exception as e:
        logger.error(f"❌ Ollama request failed: {{e}}")

    return {}

def send_daily_summary():
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_PASSWORD")
    family_emails = os.getenv("FAMILY_EMAILS", "").split(',')

    if not gmail_user or not gmail_password or not family_emails:
        logger.warning("Gmail credentials not configured")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    events = get_events_for_date(today)

    if not events:
        logger.info("No events for today")
        return

    today_name = datetime.now().strftime("%A, %B %d, %Y")
    body = f"Family Calendar - {{today_name}}\n\nEVENTS TODAY ({{len(events)}}):\n"
    for i, e in enumerate(events, 1):
        body += f"{{i}}. {{e.get('time', '0000')}} {{e.get('title', 'Unnamed')}}\n"
        body += f"   Person: {{e.get('person', 'Family')}}\n"
        if e.get('location'):
            body += f"   Location: {{e.get('location')}}\n"

    msg = MIMEMultipart('related')
    msg['Subject'] = f"Family Calendar - {{today_name}}"
    msg['From'] = gmail_user
    msg['To'] = ', '.join(family_emails)

    msg.attach(MIMEText(body, 'plain'))

    logo_path = Path(__file__).parent / "mcintyrelogo.jpeg"
    if logo_path.exists():
        with open(logo_path, 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-ID', '<mcintyrelogo>')
            img.add_header('Content-Disposition', 'inline', filename='mcintyrelogo.jpeg')
            msg.attach(img)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, family_emails, msg.as_string())
        server.quit()
        logger.info(f"✓ Daily summary sent to {{len(family_emails)}} recipients")
    except Exception as e:
        logger.error(f"❌ Email send failed: {{e}}")

def poll_gmail():
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_PASSWORD")

    if not gmail_user or not gmail_password:
        logger.warning("Gmail credentials not configured")
        return

    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(gmail_user, gmail_password)
        mail.select('INBOX')

        _, data = mail.search(None, 'UNSEEN')
        email_ids = data[0].split()

        logger.info(f"📧 Polling Gmail for new emails...")
        logger.info(f"Found {{len(email_ids)}} unseen emails")

        for email_id in email_ids:
            _, msg_data = mail.fetch(email_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])

            sender_email = msg.get('From', '')
            subject = msg.get('Subject', '')

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
            else:
                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

            event = parse_email_to_event(body, sender_email)
            if event and event.get('date') and event.get('title'):
                add_event(
                    event['date'],
                    event['time'],
                    event['title'],
                    event.get('person', 'Family'),
                    event.get('location', '')
                )

            mail.store(email_id, '+FLAGS', '\\Seen')

        mail.close()
        mail.logout()
    except Exception as e:
        logger.error(f"❌ Gmail polling failed: {{e}}")

def start_email_polling():
    def poll_loop():
        while True:
            poll_gmail()
            time.sleep(900)  # 15 minutes

    thread = threading.Thread(target=poll_loop, daemon=True)
    thread.start()
    logger.info("📬 Email polling thread started (checking every 15 minutes)")

if __name__ == "__main__":
    import sys

    logger.info("=" * 70)
    logger.info("Family Calendar Backend v1.3")
    logger.info("=" * 70)

    logger.info(f"GMAIL_USER: {{os.getenv('GMAIL_USER')}}")
    logger.info(f"GMAIL_PASSWORD: {{'*' * 16 if os.getenv('GMAIL_PASSWORD') else 'Not set'}}")
    logger.info(f"FAMILY_EMAILS: {{len(os.getenv('FAMILY_EMAILS', '').split(','))}} recipients")
    logger.info(f"OLLAMA_ENDPOINT: {{os.getenv('OLLAMA_ENDPOINT', 'http://localhost:11434')}}")
    logger.info(f"OLLAMA_MODEL: {{os.getenv('OLLAMA_MODEL', 'qwen2.5:0.5b')}}")

    if "--send-summary" in sys.argv:
        send_daily_summary()
    else:
        create_csv_if_not_exists()
        start_email_polling()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
