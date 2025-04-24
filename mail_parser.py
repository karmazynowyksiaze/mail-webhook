import imapclient
import pyzmail
import requests
import time
import os
import traceback
import html2text
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv

# ENVIRONMENT
load_dotenv()

EMAIL = os.environ.get('EMAIL')
PASSWORD = os.environ.get('EMAIL_PASSWORD')
IMAP_SERVER = os.environ.get('IMAP_SERVER')
IMAP_PORT = int(os.environ.get('IMAP_PORT', 993))
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', 30))
BUBBLE_API_ENDPOINT = os.environ.get('BUBBLE_ENDPOINT')
BUBBLE_FILE_UPLOAD_ENDPOINT = os.environ.get('BUBBLE_FILE_UPLOAD_ENDPOINT')
BUBBLE_API_TOKEN = os.environ.get('BUBBLE_TOKEN')

#GET ITEM ATTRIBUTES
def safe_get_attr(obj, attr_name, default=""):
    return getattr(obj, attr_name, default) if hasattr(obj, attr_name) else default

def upload_file_to_bubble(file_bytes, filename):
    files = {
        "file": (filename, BytesIO(file_bytes), "application/octet-stream")
    }

    headers = {
        "Authorization": f"Bearer {BUBBLE_API_TOKEN}"
    }

    try:
        response = requests.post(BUBBLE_FILE_UPLOAD_ENDPOINT, files=files, headers=headers)
        if response.status_code == 200:
            return response.json().get("file_url")
        else:
            print(f"[ERR] Bubble file upload: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"[ERR] Upload do Bubble nie powiódł się: {e}")
        return None

def fetch_new_emails():
    with imapclient.IMAPClient(IMAP_SERVER, ssl=True) as client:
        client.login(EMAIL, PASSWORD)
        client.select_folder('INBOX', readonly=False)

        # SEARCH UNREAD MESSAGES
        uids = client.search(['UNSEEN'])

        if not uids:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Brak nowych wiadomości")
            return

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Znaleziono {len(uids)} nowych wiadomości")

        for uid in uids:
            raw_message = client.fetch([uid], ['BODY[]', 'FLAGS'])[uid][b'BODY[]']
            message = pyzmail.PyzMessage.factory(raw_message)

            subject = message.get_subject()
            from_email = message.get_addresses('from')
            to = message.get_addresses('to')
            cc = message.get_addresses('cc')
            bcc = message.get_addresses('bcc')

            if message.text_part:
                body = message.text_part.get_payload().decode(message.text_part.charset)
            elif message.html_part:
                html_body = message.html_part.get_payload().decode(message.html_part.charset)
                body = html2text.html2text(html_body)
            else:
                body = "[Brak treści]"

            attachments = []

            for i, part in enumerate(message.mailparts):
                if part == message.text_part or part == message.html_part:
                    continue

                # Poprawka błędu: get_content_disposition nie istnieje w pyzmail
                if part.filename:
                    filename = part.filename or f"attachment_{i}"
                    file_content = part.get_payload()
                    file_url = upload_file_to_bubble(file_content, filename)

                    if file_url:
                        attachments.append({
                            'filename': filename,
                            'url': file_url
                        })

            print("=" * 60)
            print(f"Nowy e-mail (UID: {uid}):")
            print(f"Temat: {subject}")
            print(f"Od: {from_email}")
            print(f"Do: {to}")
            if cc:
                print(f"CC: {cc}")
            if bcc:
                print(f"BCC: {bcc}")

            if attachments:
                filenames = ', '.join([att['filename'] for att in attachments])
                print(f"Załączniki ({len(attachments)}): {filenames}")
            else:
                print("Brak załączników.")

            attachments_filenames = [att['filename'] for att in attachments]
            attachments_urls = [att['url'] for att in attachments]

            body_preview = body[:500] + "..." if len(body) > 500 else body
            print(f"\nTreść (fragment):\n{body_preview}")
            print("=" * 60)

            from_name_str = f"{from_email[0][0]}" if from_email else ""
            from_email_str = f"{from_email[0][1]}" if from_email else ""
            to_str = [f"{name} <{email}>" for name, email in to] if to else []
            cc_str = [f"{name} <{email}>" for name, email in cc] if cc else []
            bcc_str = [f"{name} <{email}>" for name, email in bcc] if bcc else []

            payload = {
                'subject': subject,
                'from_name': from_name_str,
                'from_email': from_email_str,
                'to': to_str,
                'cc': cc_str,
                'bcc': bcc_str,
                'body': body,
                'attachments_filenames': attachments_filenames,
                'attachments_urls': attachments_urls,
            }

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {BUBBLE_API_TOKEN}'
            }
            try:
                response = requests.post(BUBBLE_API_ENDPOINT, json=payload, headers=headers)
                if response.status_code == 200:
                    print(f"[OK] E-mail '{subject}' wysłany do aplikacji Panowie.IT")
                else:
                    print(f"[ERR] Panowie.IT API: {response.status_code} - {response.text}")
            except Exception as e:
                print(f"[ERR] Nie udało się wysłać do Bubble: {e}")
                traceback.print_exc()

if __name__ == '__main__':
    print("Start aplikacji EmailWebhook...")
    print(f"Konfiguracja:")
    print(f"  IMAP: {IMAP_SERVER}:{IMAP_PORT}")
    print(f"  E-mail: {EMAIL}")
    print(f"  Bubble API: {'Skonfigurowane' if BUBBLE_API_ENDPOINT and BUBBLE_API_TOKEN else 'BRAK KONFIGURACJI'}")
    print(f"  Interwał sprawdzania: {POLL_INTERVAL} sekund")
    print("=" * 60)

    while True:
        try:
            fetch_new_emails()
        except Exception as e:
            print(f"[BŁĄD] podczas sprawdzania skrzynki: {e}")
            traceback.print_exc()

        print(f"Odczekam {POLL_INTERVAL} sekund...")
        time.sleep(POLL_INTERVAL)
