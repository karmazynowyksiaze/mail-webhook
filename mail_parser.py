import imapclient
import pyzmail
import requests
import time
import os
import traceback

# ENVIORMENT
EMAIL = os.environ.get('EMAIL')
PASSWORD = os.environ.get('EMAIL_PASSWORD')
IMAP_SERVER = os.environ.get('IMAP_SERVER')
BUBBLE_API_ENDPOINT = os.environ.get('BUBBLE_ENDPOINT')
BUBBLE_API_TOKEN = os.environ.get('BUBBLE_TOKEN')

POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', 30))  # MAILBOX CHECK

def fetch_new_emails():
    with imapclient.IMAPClient(IMAP_SERVER, ssl=True) as client:
        client.login(EMAIL, PASSWORD)
        client.select_folder('INBOX', readonly=False)

        # SEARCH UNREAD MESSAGESS
        uids = client.search(['UNSEEN'])

        for uid in uids:
            raw_message = client.fetch([uid], ['BODY[]', 'FLAGS'])[uid][b'BODY[]']
            message = pyzmail.PyzMessage.factory(raw_message)

            # PARSING
            subject = message.get_subject()
            from_email = message.get_addresses('from')
            to = message.get_addresses('to')
            cc = message.get_addresses('cc')
            bcc = message.get_addresses('bcc')
            body = message.text_part.get_payload().decode(message.text_part.charset) if message.text_part else ''
            attachments = []

            for part in message.mailparts:
                if part.filename:
                    filename = part.filename
                    data = part.get_payload()
                    attachments.append({
                        'filename': filename,
                        'size': len(data)
                    })

            # SEND TO BUBBLE
            payload = {
                'subject': subject,
                'from': from_email,
                'to': to,
                'cc': cc,
                'bcc': bcc,
                'body': body,
                'attachments': attachments
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
    print("⏳ Start aplikacji EmailWebhook...")
    while True:
        try:
            fetch_new_emails()
        except Exception as e:
            print(f"[BŁĄD] podczas sprawdzania skrzynki: {e}")
            traceback.print_exc()

        print(f"⏸️ Odczekam {POLL_INTERVAL} sekund...")
        time.sleep(POLL_INTERVAL)