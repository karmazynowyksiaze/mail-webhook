FROM python 3.11-slim

WORKDIR /app

COPY requirements.txt .
COPY mail_parser.py .

RUN pip install --no-cashe-dir -r requirements.txt

CMD ["python", "fetch_emails.py"]