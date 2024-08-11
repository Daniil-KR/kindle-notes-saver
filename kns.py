
import imaplib
import smtplib
import email
from email.policy import default
from email.message import EmailMessage
from telegram import Update, Document
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import requests
import re
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from functools import partial
from typing import Optional

# Email settings
IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ACCOUNT = ""
EMAIL_PASSWORD = ""
LABEL_NAME = ""
KINDLE_EMAIL = ""
# Telegram settings
BOT_TOKEN = ""
TELEGRAM_ID = ""
INTERVAL_IN_MINUTES = 10

SUPPORTED_FILE_TYPES = {
    'application/pdf': 'pdf',
    'application/msword': 'doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'text/plain': 'txt',
    'application/rtf': 'rtf',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/jpeg': 'jpg',
    'image/bmp': 'bmp',
    'application/epub+zip': 'epub',
}

def _extract_title(subject: str) -> Optional[str]:
    title_pattern = r'\"(.*?)\"'
    match = re.search(title_pattern, subject)
    if match:
        return match.group(1)
    return None

def _extract_first_url(text: str) -> Optional[str]:
    url_pattern = r'https?://[^\s)]+'
    match = re.search(url_pattern, text)
    if match:
        return match.group(0)
    return None

def fetch_unread_kindle_notes() -> dict:
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
    mail.select('inbox')

    status, search_data = mail.search(None, f'(UNSEEN X-GM-LABELS "{LABEL_NAME}")')
    
    pdf_links = {}
    for num in search_data[0].split():
        status, data = mail.fetch(num, '(RFC822)')
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email, policy=default)
        if msg.is_multipart():
            for part in msg.iter_parts():
                if part.get_content_type() == "text/plain":
                    email_body = part.get_payload(decode=True).decode(part.get_content_charset())
        else:
            email_body = msg.get_payload(decode=True).decode(msg.get_content_charset())
        
        pdf_url = _extract_first_url(email_body)
        title = _extract_title(msg['subject'])
        if title:
            pdf_links[title] = pdf_url

    mail.logout()

    return pdf_links

async def send_pdf_auto(context: ContextTypes.DEFAULT_TYPE):
    print("automatic update check")
    pdf_links = fetch_unread_kindle_notes()

    if pdf_links:
        for key in pdf_links:
            response = requests.get(pdf_links[key])
            response.raise_for_status()
            await context.bot.send_document(
                chat_id=TELEGRAM_ID, 
                document=response.content, 
                filename=f"{key}.pdf"
            )

async def send_pdf_manual(_: Update, context: ContextTypes.DEFAULT_TYPE):
    print("manual update check")
    pdf_links = fetch_unread_kindle_notes()

    if pdf_links:
        for key in pdf_links:
            response = requests.get(pdf_links[key])
            response.raise_for_status()
            await context.bot.send_document(
                chat_id=TELEGRAM_ID, 
                document=response.content, 
                filename=f"{key}.pdf"
            )
    else:
        await context.bot.send_message(chat_id=TELEGRAM_ID, text="Nothing new")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document: Document = update.message.document

    if document.mime_type in SUPPORTED_FILE_TYPES:
        file = await document.get_file()
        file_content = await file.download_as_bytearray()

        email_message = EmailMessage()
        email_message['From'] = EMAIL_ACCOUNT
        email_message['To'] = KINDLE_EMAIL
        email_message['Subject'] = 'New File from Telegram Bot'
        email_message.set_content(f'You have received a new {SUPPORTED_FILE_TYPES[document.mime_type].upper()} file.')

        email_message.add_attachment(
            file_content, 
            maintype=document.mime_type.split('/')[0], 
            subtype=document.mime_type.split('/')[1], 
            filename=document.file_name
        )

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            server.send_message(email_message)

        await update.message.reply_text(f"The file {document.file_name} has been sent successfully.")
    else:
        await update.message.reply_text("This file type is not supported.")
            
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    scheduler = AsyncIOScheduler()
    
    application.add_handler(CommandHandler("update", send_pdf_manual))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    scheduler.add_job(
        send_pdf_auto, 
        trigger=IntervalTrigger(minutes=INTERVAL_IN_MINUTES), 
        args=[application]
    )

    scheduler.start()
    application.run_polling()

if __name__ == '__main__':
    main()