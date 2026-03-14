import hashlib
import json
import os
import smtplib
import difflib
import re
from pathlib import Path
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

URLS_FILE = "urls.txt"
SNAPSHOTS_FILE = "snapshots.json"
EMAIL_FROM = os.environ["GMAIL_FROM"]
EMAIL_TO = os.environ["GMAIL_TO"]
APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

NOISE_PATTERNS = [
    r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}',   # תאריכים
    r'\d{1,2}:\d{2}(:\d{2})?',              # שעות
    r'עודכן בתאריך[^\n]*',                  # "עודכן בתאריך..."
    r'Last updated[^\n]*',
    r'copyright[^\n]*',
    r'©[^\n]*',
]


def clean_text(text):
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return ' '.join(text.split())


def get_text(url):
    try:
        if url.lower().endswith('.pdf'):
            r = requests.get(url, timeout=20, headers=HEADERS)
            return hashlib.md5(r.content).hexdigest()
        r = requests.get(url, timeout=15, headers=HEADERS)
        r.encoding = r.apparent_encoding or 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'meta', 'noscript']):
            tag.decompose()
        raw = soup.get_text(separator=' ')
        return clean_text(raw)
    except Exception as e:
        return f"ERROR: {e}"


def send_alert(url, old_text, new_text):
    is_pdf = url.lower().endswith('.pdf')

    if is_pdf:
        diff_str = "קובץ ה-PDF השתנה (תוכן בינארי – לא ניתן להשוות טקסט)."
    else:
        old_lines = [s.strip() for s in old_text.split('.') if s.strip()]
        new_lines = [s.strip() for s in new_text.split('.') if s.strip()]
        diff = list(difflib.unified_diff(old_lines, new_lines, lineterm='', n=2))
        if diff:
            diff_str = '\n'.join(diff[:50])
        else:
            diff_str = "השינוי קטן מדי לתיאור מדויק – כנסי לאתר לבדיקה."

    body = f"""שלום זיו,

זוהה שינוי בדף הבא:
{url}

{'─' * 60}
השוואה (שורות שהוסרו מסומנות ב- , שורות חדשות ב-+):

{diff_str}
{'─' * 60}

הודעה אוטומטית ממערכת ניטור האתרים שלך.
"""

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = f"🔔 שינוי זוהה: {url[:60]}"
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(EMAIL_FROM, APP_PASSWORD)
        s.send_message(msg)
    print(f"  ✉️  התראה נשלחה על: {url}")


def main():
    urls = [
        u.strip()
        for u in Path(URLS_FILE).read_text(encoding='utf-8').splitlines()
        if u.strip() and not u.startswith('#')
    ]

    snapshots = {}
    if Path(SNAPSHOTS_FILE).exists():
        snapshots = json.loads(Path(SNAPSHOTS_FILE).read_text(encoding='utf-8'))

    for url in urls:
        print(f"בודק: {url}")
        new_text = get_text(url)
        new_hash = hashlib.md5(new_text.encode()).hexdigest()

        if url in snapshots:
            if snapshots[url]['hash'] != new_hash:
                print(f"  ⚠️  שינוי זוהה!")
                send_alert(url, snapshots[url].get('text', ''), new_text)
            else:
                print(f"  ✅ ללא שינוי")
        else:
            print(f"  📸 snapshot ראשון נשמר")

        snapshots[url] = {'hash': new_hash, 'text': new_text}

    Path(SNAPSHOTS_FILE).write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    print("\nסיום. snapshots עודכנו.")


if __name__ == '__main__':
    main()
