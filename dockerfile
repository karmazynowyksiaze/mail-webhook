FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
COPY mail_parser.py .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "mail_parser.py"]