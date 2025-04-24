import imapclient
import pyzmail
import requests
import time
import os
import traceback
import html2text
import boto3
from botocore.exceptions import NoCredentialsError
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
BUBBLE_API_TOKEN = os.environ.get('BUBBLE_TOKEN')
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_S3_BUCKET = os.environ.get('AWS_S3_BUCKET')
AWS_S3_REGION = os.environ.get('AWS_S3_REGION')

s3_client = boto3.client(
    's3',
    region_name= AWS_S3_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

#GET ITEM ATRIBUTES
def safe_get_attr(obj, attr_name, default=""):
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
            
            # HTML MESSAGES(text or html)
            if message.text_part:
                body = message.text_part.get_payload().decode(message.text_part.charset)
            elif message.html_part:
                html_body = message.html_part.get_payload().decode(message.html_part.charset)
                body = html2text.html2text(html_body)
            else:
                body = "[Brak treści]"
                
            # SEARCHING ATACHMENTS
            attachments = []
            
            print(f"\n[DEBUG] Struktura wiadomości (uid: {uid}):")
            for i, part in enumerate(message.mailparts):
                filename = safe_get_attr(part, 'filename', 'brak')
                print(f"nazwa pliku={filename}")
                
                
                if part == message.text_part or part == message.html_part:
                    continue
                    
                
                is_attachment = False
                
                
                if filename != 'brak':
                    is_attachment = True
                
                if is_attachment:
                    attachment_filename = filename if filename != 'brak' else f'zalacznik_{i+1}'
                    file_content = part.get_payload()
                    content_type = part.get_content_type() if hasattr(part, 'get_content_type') else 'application/octet-stream'
    
                    date_prefix = datetime.now().strftime('%Y-%m-%d')
                    s3_path = f"{date_prefix}/{attachment_filename}"
                    full_s3_key = f"email_attachments/{s3_path}"
    
                    s3_url = upload_to_s3(file_content, full_s3_key, content_type)
    
                    attachments.append({
                        'filename': attachment_filename,
                        'url': s3_url
                    })
            
            # LOG ONLY
            print("=" * 60)
            print(f"Nowy e-mail (UID: {uid}):")
            print(f"Temat: {subject}")
            print(f"Od: {from_email}")
            print(f"Do: {to}")
            if cc:
                print(f"CC: {cc}")
            if bcc:
                print(f"BCC: {bcc}")
                
            # LOG ATTACHMENTS
            if attachments:
                filenames = ', '.join([att['filename'] for att in attachments])
                print(f"Załączniki ({len(attachments)}): {filenames}")
            else:
                print("Brak załączników.")
            
            attachments_filenames = [att['filename'] for att in attachments]
            attachments_urls = [att['url'] for att in attachments]
            print (f"URL: {attachments_urls}")
                
            body_preview = body[:500] + "..." if len(body) > 500 else body
            print(f"\nTreść (fragment):\n{body_preview}")
            print("=" * 60)

            # Przygotowanie danych dla Bubble API
            # Konwersja obiektów adresu email na format tekstowy
            from_name_str = f"{from_email[0][0]}" if from_email else ""
            from_email_str = f"{from_email[0][1]}" if from_email else ""
            to_str = [f"{name} <{email}>" for name, email in to] if to else []
            cc_str = [f"{name} <{email}>" for name, email in cc] if cc else []
            bcc_str = [f"{name} <{email}>" for name, email in bcc] if bcc else []

            # SEND TO BUBBLE
            payload = {
                'subject': subject,
                'from_name': from_name_str,
                'from_email': from_email_str,
                'to': to_str,
                'cc': cc_str,
                'bcc': bcc_str,
                'body': body,
                'attachments_filenames': attachments_filenames,
                'attachments_urls': attachments_urls
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
            

def upload_to_s3(file_content, s3_key, content_type='application/octet-stream'):
    try:
        s3_client.put_object(
            Bucket=AWS_S3_BUCKET,
            Key=s3_key,
            Body=file_content,
            ContentType=content_type,
            #ACL='public-read'
        )
        return f"https://{AWS_S3_BUCKET}.s3.{AWS_S3_REGION}.amazonaws.com/{s3_key}"
    except NoCredentialsError:
        print("[ERR] Błąd uwierzytelniania AWS")
        return None
    except Exception as e:
        print(f"[ERR] Upload do S3 nie powiódł się: {e}")
        return None

if __name__ == '__main__':
    print("Start aplikacji EmailWebhook...")
    print(f"Konfiguracja:")
    print(f"  IMAP: {IMAP_SERVER}:{IMAP_PORT}")
    print(f"  E-mail: {EMAIL}")
    print(f"  AWS S3: {'Skonfigurowane' if AWS_ACCESS_KEY and AWS_SECRET_ACCESS_KEY else 'BRAK KONFIGURACJI'}")
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