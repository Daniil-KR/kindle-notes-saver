
import imaplib
import email
from email.policy import default
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
import re
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from functools import partial
from typing import Optional

# Email settings
IMAP_SERVER = "imap.gmail.com"
EMAIL_ACCOUNT = ""
EMAIL_PASSWORD = "" 
LABEL_NAME = ""
# Telegram settings
BOT_TOKEN = ""
TELEGRAM_ID = ""
INTERVAL_IN_MINUTES = 15

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

async def send_pdf(_: Optional[Update], context: ContextTypes.DEFAULT_TYPE):
    print("send_pdf processing")

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
            
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    scheduler = AsyncIOScheduler()
    
    application.add_handler(CommandHandler("update", send_pdf))
    scheduler.add_job(
        partial(send_pdf, None), 
        trigger=IntervalTrigger(minutes=INTERVAL_IN_MINUTES), 
        args=[application]
    )

    scheduler.start()
    application.run_polling()

if __name__ == '__main__':
    main()