import html2text
import aiohttp
import base64
import fitz  # PyMuPDF
import io
from PIL import Image
import pytesseract
from email import message_from_bytes

# EXTRACT BODY FROM EMAIL
def get_email_body(msg):
    """Extract the body from the raw email message."""
    if 'body' in msg:
        body_content = msg['body']
        content_type = body_content.get('contentType', 'text')
        content = body_content.get('content', '')

        if content_type == 'html':
            plain_text_content = html2text.html2text(content)
            return {'html': content, 'text': plain_text_content}
        elif content_type == 'text':
            return {'html': '', 'text': content}
        else:
            return {'html': '', 'text': ''}
        
    return {'html': '', 'text': ''}

# Function to extract text from PDF using PyMuPDF
async def extract_text_from_pdf(attachment_content):
    """Extract text from a PDF file."""
    try:
        # Decode base64 content
        pdf_bytes = base64.b64decode(attachment_content)
        
        # Open PDF from memory
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        text = ""
        for page in doc:
            text += page.get_text()
        
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {str(e)}")
        return ""

# Function to extract text from images using pytesseract
async def extract_text_from_image(attachment_content, image_format="jpeg"):
    """Extract text from an image file using OCR."""
    try:
        # Decode base64 content
        image_bytes = base64.b64decode(attachment_content)
        
        # Open image from memory
        image = Image.open(io.BytesIO(image_bytes))
        
        # Use pytesseract to extract text
        text = pytesseract.image_to_string(image)
        
        return text
    except Exception as e:
        print(f"Error extracting text from image: {str(e)}")
        return ""

# Process attachment based on its content type
async def process_attachment(attachment):
    """Process an attachment and extract text based on content type."""
    attachment_name = attachment.get('name', '')
    content_type = attachment.get('contentType', '').lower()
    attachment_content = attachment.get('contentBytes', '')
    extracted_text = ""
    
    # Process based on content type
    if 'pdf' in content_type:
        extracted_text = await extract_text_from_pdf(attachment_content)
    elif any(img_type in content_type for img_type in ['jpeg', 'jpg', 'png', 'gif', 'bmp', 'tiff']):
        image_format = content_type.split('/')[-1] if '/' in content_type else 'jpeg'
        extracted_text = await extract_text_from_image(attachment_content, image_format)
    
    return {
        'name': attachment_name,
        'content_type': content_type,
        'extracted_text': extracted_text
    }

# CREATE EMAIL OBJECT
async def create_email_details(access_token, user_id, msg):
    body_content = get_email_body(msg)

    # Get all the recipients and cc list
    to_recipients = [recipient.get('emailAddress', {}).get('address', '') for recipient in msg.get('toRecipients', [])]
    cc_recipients = [cc.get('emailAddress', {}).get('address', '') for cc in msg.get('ccRecipients', [])]
    
    to_recipients_str = ', '.join(to_recipients)
    cc_recipients_str = ', '.join(cc_recipients)

    # Fetch attachments
    raw_attachments = await fetch_attachments(access_token, user_id, msg.get('id', ''))
    
    # Process attachments to extract text
    processed_attachments = []
    for attachment in raw_attachments:
        processed_attachment = await process_attachment(attachment)
        processed_attachments.append(processed_attachment)

    email_details = {
        'email_id': msg.get('id', ''),
        'internet_message_id': msg.get('internetMessageId', ''),
        'to': to_recipients_str,
        'from': msg.get('from', {}).get('emailAddress', {}).get('address', ''),
        'date_received': msg.get('receivedDateTime', ''),
        'cc': cc_recipients_str,
        'subject': msg.get('subject', ''),
        'body_html': body_content.get('html', ''),
        'body_text': body_content.get('text', ''),
        'raw_attachments': raw_attachments,
        'processed_attachments': processed_attachments
    }
    
    return email_details

async def fetch_attachments(access_token, user_id, message_id):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }
    endpoint = f'https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}/attachments'
    
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                attachments = data.get('value', [])
                return attachments
            else:
                print(f"Failed to retrieve attachments for message {message_id}: {response.status}")
                print(await response.text())
                return []

# Generate a formatted LLM text with all email details and attachment content
def generate_llm_text(email_data):
    """Generate a formatted text string with all email details and attachment content."""
    llm_text = f"EMAIL_FROM: {email_data.get('from', '')}\n"
    llm_text += f"EMAIL_TO: {email_data.get('to', '')}\n"
    llm_text += f"EMAIL_CC: {email_data.get('cc', '')}\n"
    llm_text += f"EMAIL_SUBJECT: {email_data.get('subject', '')}\n"
    llm_text += f"EMAIL_DATE: {email_data.get('date_received', '')}\n"
    llm_text += f"EMAIL_BODY:\n{email_data.get('body_text', '')}\n\n"
    
    # Add attachment information
    attachments = email_data.get('processed_attachments', [])
    if attachments:
        for i, attachment in enumerate(attachments, 1):
            llm_text += f"ATTACHMENT_{i}_NAME: {attachment.get('name', '')}\n"
            llm_text += f"ATTACHMENT_{i}_TYPE: {attachment.get('content_type', '')}\n"
            llm_text += f"ATTACHMENT_{i}_TEXT:\n{attachment.get('extracted_text', '')}\n\n"
    
    return llm_text
