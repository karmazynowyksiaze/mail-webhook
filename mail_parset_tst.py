import imapclient
import pyzmail
import requests
import time
import os
import traceback
import html2text
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ENVIRONMENT
EMAIL = "pawel.pawlowski@panowie.it"
PASSWORD = "!jiQ1[Fe9V+i4"
IMAP_SERVER = os.environ.get('IMAP_SERVER')
IMAP_PORT = int(os.environ.get('IMAP_PORT', 993))
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', 30))
#BUBBLE_API_ENDPOINT = os.environ.get('BUBBLE_ENDPOINT')
#BUBBLE_API_TOKEN = os.environ.get('BUBBLE_TOKEN')

def safe_get_attr(obj, attr_name, default=""):
    """Bezpiecznie pobiera atrybut obiektu"""
    return getattr(obj, attr_name, default) if hasattr(obj, attr_name) else default

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
            
            # PARSING
            subject = message.get_subject()
            from_email = message.get_addresses('from')
            to = message.get_addresses('to')
            cc = message.get_addresses('cc')
            bcc = message.get_addresses('bcc')
            
            # Obsługa treści wiadomości (text lub HTML)
            if message.text_part:
                body = message.text_part.get_payload().decode(message.text_part.charset)
            elif message.html_part:
                html_body = message.html_part.get_payload().decode(message.html_part.charset)
                body = html2text.html2text(html_body)
            else:
                body = "[Brak treści]"
                
            # Wykrywanie załączników
            attachments = []
            
            # Logujemy całą strukturę wiadomości do celów diagnostycznych
            print(f"\n[DEBUG] Struktura wiadomości (uid: {uid}):")
            for i, part in enumerate(message.mailparts):
                filename = safe_get_attr(part, 'filename', 'brak')
                print(f"nazwa pliku={filename}")
                
                # Sprawdźmy czy to nie jest główne ciało wiadomości
                if part == message.text_part or part == message.html_part:
                    continue
                    
                # Prosta i bezpośrednia identyfikacja załączników
                is_attachment = False
                
                # 1. Jeśli ma nazwę pliku - to jest załącznik
                if filename != 'brak':
                    is_attachment = True
                
                if is_attachment:
                    attachment_filename = filename if filename != 'brak' else f'załącznik_{i+1}'
                    attachments.append({
                        'filename': attachment_filename,
                    })
            
            # LOG ONLY – wyświetlanie dla weryfikacji
            print("=" * 60)
            print(f"Nowy e-mail (UID: {uid}):")
            print(f"Temat: {subject}")
            print(f"Od: {from_email}")
            print(f"Do: {to}")
            if cc:
                print(f"CC: {cc}")
            if bcc:
                print(f"BCC: {bcc}")
                
            # Wyświetlanie informacji o załącznikach
            if attachments:
                filenames = ', '.join([att['filename'] for att in attachments])
                print(f"Załączniki ({len(attachments)}): {filenames}")
            else:
                print("Brak załączników.")
                
            # Skrócona wersja treści
            body_preview = body[:500] + "..." if len(body) > 500 else body
            print(f"\nTreść (fragment):\n{body_preview}")
            print("=" * 60)

            # Przygotowanie danych dla Bubble API
            # Konwersja obiektów adresu email na format tekstowy
            from_email_str = f"{from_email[0][0]} <{from_email[0][1]}>" if from_email else ""
            to_str = [f"{name} <{email}>" for name, email in to] if to else []
            cc_str = [f"{name} <{email}>" for name, email in cc] if cc else []
            bcc_str = [f"{name} <{email}>" for name, email in bcc] if bcc else []
            
            """
            # SEND TO BUBBLE
            payload = {
                'subject': subject,
                'from': from_email_str,
                'to': to_str,
                'cc': cc_str,
                'bcc': bcc_str,
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

            """
if __name__ == '__main__':
    print("Start aplikacji EmailWebhook...")
    print(f"Konfiguracja:")
    print(f"  IMAP: {IMAP_SERVER}:{IMAP_PORT}")
    print(f"  E-mail: {EMAIL}")
    #print(f"  Bubble API: {'Skonfigurowane' if BUBBLE_API_ENDPOINT and BUBBLE_API_TOKEN else 'BRAK KONFIGURACJI'}")
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