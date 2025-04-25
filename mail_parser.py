import imapclient
import pyzmail
import requests
import time
import os
import traceback
import html2text
import base64
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ENVIRONMENT

EMAIL = os.environ.get('EMAIL')
PASSWORD = os.environ.get('EMAIL_PASSWORD')
IMAP_SERVER = os.environ.get('IMAP_SERVER')
IMAP_PORT = int(os.environ.get('IMAP_PORT', 993))
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', 30))
BUBBLE_API_ENDPOINT = os.environ.get('BUBBLE_ENDPOINT')
BUBBLE_API_TOKEN = os.environ.get('BUBBLE_TOKEN')
BUBBLE_FILE_UPLOAD_ENDPOINT = os.environ.get('BUBBLE_FILE_UPLOAD_ENDPOINT')

ATTACHMENTS_DIR = "email_attachments"
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

def safe_get_attr(part, attr_name, default=None):
    try:
        return getattr(part, attr_name) or default
    except:
        return default

def fetch_new_emails():
    with imapclient.IMAPClient(IMAP_SERVER, ssl=True) as client:
        client.login(EMAIL, PASSWORD)
        client.select_folder('INBOX', readonly=False)

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
            attachments_urls = []

            for i, part in enumerate(message.mailparts):
                filename = safe_get_attr(part, 'filename', None)

                if part == message.text_part or part == message.html_part:
                    continue

                if filename:
                    file_data = part.get_payload()
                    safe_folder = "email_załączniki"
                    os.makedirs(safe_folder, exist_ok=True)
                    file_path = os.path.join(safe_folder, filename)

                    with open(file_path, "wb") as f:
                        f.write(file_data)

                try:
                    with open(file_path, "rb") as f:
                        encoded_content = base64.b64encode(f.read()).decode('utf-8')

                # Logowanie danych przed wysłaniem
                    print(f"Sending file: {filename}, encoded_content (first 50 chars): {encoded_content[:50]}...")

                    upload_payload = {
                    "plik": {
                        "private": False,
                        "filename": filename, 
                        "contents": encoded_content
                        }
                    }
                    headers = {
                        "Authorization": f"Bearer {BUBBLE_API_TOKEN}",
                    }
                    response_file = requests.post(
                        BUBBLE_FILE_UPLOAD_ENDPOINT,
                        json=upload_payload,
                        headers=headers,
                        timeout=30
                    )
                    if response_file.status_code == 200:
                        response_data = response_file.json()
                        if "response" in response_data and "url_zwrotny" in response_data["response"]:
                            url_zwrotny = response_data["response"]["url_zwrotny"]
                            attachments_urls.append(f"https:{url_zwrotny}")
                            print(f"[OK] Załącznik '{filename}' wysłany. {response_file.status_code} - {response_data}")
                        else:
                            print("Błąd: Nie można znaleźć pola url_zwrotny w odpowiedzi.")
                            
                        if "resources" in response_data and response_data["resources"]:
                            print(f"Plik zapisany w Bubble.io: {response_data['resources']}")
                        else:
                            print("Plik nie został zapisany - pole 'resources' jest puste.")
                    else:
                        print(f"[ERR] Błąd przy wysyłce '{filename}': {response_file.status_code} - {response_file.text}")
                except requests.exceptions.Timeout:
                    print(f"[ERR] Timeout podczas wysyłki załącznika '{filename}'.")
                except Exception as e:
                    print(f"[ERR] Błąd podczas wysyłki załącznika '{filename}': {e}")
                finally:
                    if os.path.exists(file_path):
                        os.remove(file_path)

            attachments.append({'filename': filename})

            from_name_str = f"{from_email[0][0]}" if from_email else ""
            from_email_str = f"{from_email[0][1]}" if from_email else ""
            to_str = [f"{name} <{email}>" for name, email in to] if to else []
            cc_str = [f"{name} <{email}>" for name, email in cc] if cc else []
            bcc_str = [f"{name} <{email}>" for name, email in bcc] if bcc else []

            body_preview = body[:500] + "..." if len(body) > 500 else body
            print("=" * 60)
            print(f"Temat: {subject}")
            print(f"Od: {from_email}")
            print(f"Do: {to}")
            print(f"Załączniki: {[att['filename'] for att in attachments]}")
            print(f"Załącznik URL: {attachments_urls} ")
            print(f"Treść:\n{body_preview}")
            print("=" * 60)

            payload = {
                'subject': subject,
                'from_name': from_name_str,
                'from_email': from_email_str,
                'to': to_str,
                'cc': cc_str,
                'bcc': bcc_str,
                'body': body,
                'attachments_filenames': [att['filename'] for att in attachments],
                'attachments_urls': attachments_urls
            }

            try:
                response_email = requests.post(BUBBLE_API_ENDPOINT, json=payload, headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {BUBBLE_API_TOKEN}'
                })
                if response_email.status_code == 200:
                    print(f"[OK] E-mail '{subject}' wysłany do Bubble.")
                else:
                    print(f"[ERR] Panowie.IT API: {response_email.status_code} - {response_email.text}")
            except Exception as e:
                print(f"[ERR] Nie udało się wysłać e-maila do Bubble: {e}")
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