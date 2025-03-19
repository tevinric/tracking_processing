import html2text
import aiohttp
import base64
import os
import json
import tempfile
import asyncio
import re
from io import BytesIO
from pathlib import Path

# For Azure AI Document Intelligence
from azure.core.credentials import AzureKeyCredential
# Import the correct Document Intelligence client
from azure.core.credentials import AzureKeyCredential
try:
    # Try newer SDK structure
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.ai.formrecognizer import DocumentAnalysisClient
except ImportError:
    # Fall back to older SDK structure
    from azure.ai.formrecognizer import DocumentAnalysisClient
    # Define alias for compatibility
    DocumentIntelligenceClient = DocumentAnalysisClient
from azure.core.exceptions import HttpResponseError

# EXTRACT BODY FROM EMAIL
def get_email_body(msg):
    """Extract the body from the raw email message."""
    if 'body' in msg:
        body_content = msg['body']
        content_type = body_content.get('contentType', 'text')
        content = body_content.get('content', '')

        if content_type == 'html':
            plain_text_content = html2text.html2text(content)
            # Clean the text content to remove signatures and footers
            cleaned_text = clean_email_text(plain_text_content)
            return {'html': content, 'text': cleaned_text}
        elif content_type == 'text':
            # Clean the text content to remove signatures and footers
            cleaned_text = clean_email_text(content)
            return {'html': '', 'text': cleaned_text}
        else:
            return {'html': '', 'text': ''}
        
    return {'html': '', 'text': ''}

def clean_email_text(text):
    """
    Remove email signatures and footer text from the email body
    while preserving email trails and important content.
    """
    if not text:
        return ""
    
    # Split the email into lines
    lines = text.split('\n')
    cleaned_lines = []
    
    # Flags to track what we're processing
    in_signature = False
    in_legal_disclaimer = False
    in_confidentiality_notice = False
    
    # Common signature markers
    signature_markers = [
        r'^--

async def extract_text_with_document_intelligence(attachment_content, attachment_name):
    """
    Extract text from PDF or image using Azure Document Intelligence.
    
    Args:
        attachment_content: Base64 encoded content of the attachment
        attachment_name: Name of the attachment
    
    Returns:
        dict: Dictionary containing extracted text and error message if any
    """
    # Get configuration for Document Intelligence
    endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    api_key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY")
    
    if not endpoint or not api_key:
        return {
            "error": "Document Intelligence service not properly configured",
            "text": ""
        }
    
    # Initialize the Document Intelligence client
    try:
        document_client = DocumentAnalysisClient(
            endpoint=endpoint, 
            credential=AzureKeyCredential(api_key)
        )
    except Exception as e:
        return {
            "error": f"Error initializing Document Intelligence service: {str(e)}",
            "text": ""
        }
    
    # Check file extension to ensure it's supported
    file_extension = Path(attachment_name).suffix.lower()
    supported_extensions = ['.jpg', '.jpeg', '.jpe', '.jif', '.jfi', '.jfif', 
                           '.png', '.tif', '.tiff', '.pdf']
    
    if file_extension not in supported_extensions:
        return {
            "error": f"Unsupported file type. Only {', '.join(supported_extensions)} files are supported.",
            "text": ""
        }
    
    try:
        # Create a temporary file to store the attachment
        with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
            # Decode base64 content and write to temp file
            binary_content = base64.b64decode(attachment_content)
            temp_file.write(binary_content)
            temp_file_path = temp_file.name
        
        # Analyze the document
        with open(temp_file_path, "rb") as f:
            document_content = f.read()
            poller = document_client.begin_analyze_document(
                "prebuilt-read",
                document_content
            )
            
            # Wait for the operation to complete
            result = poller.result()
        
        # Remove temporary file
        os.unlink(temp_file_path)
        
        # Process results
        if not result or not result.pages:
            return {
                "error": "No text content detected in document",
                "text": ""
            }
        
        # Extract text from all pages
        full_text = ""
        page_texts = []
        
        for page in result.pages:
            # Group lines into paragraphs
            line_contents = [line.content for line in page.lines if line.content.strip()]
            paragraphs = group_lines_into_paragraphs(line_contents)
            
            # Combine paragraphs for this page
            page_text = "\n\n".join(paragraphs)
            page_texts.append({
                "page_number": page.page_number,
                "text": page_text
            })
            
            full_text += page_text + "\n\n"
        
        return {
            "full_text": full_text.strip(),
            "pages": page_texts,
            "page_count": len(result.pages),
            "has_handwritten_content": hasattr(result, 'styles') and any(
                style.is_handwritten for style in result.styles if hasattr(style, 'is_handwritten')
            )
        }
            
    except HttpResponseError as e:
        return {
            "error": f"Azure Document Intelligence service error: {str(e)}",
            "text": ""
        }
    except Exception as e:
        return {
            "error": f"Error analyzing document: {str(e)}",
            "text": ""
        }
    finally:
        # Ensure temp file is deleted if it exists
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except:
                pass

def group_lines_into_paragraphs(lines):
    """
    Group sequential lines into paragraphs.
    
    Args:
        lines (list): List of line content strings
        
    Returns:
        list: List of paragraph content strings
    """
    if not lines:
        return []
    
    paragraphs = []
    current_paragraph = []
    
    for line in lines:
        # Skip empty lines
        if not line.strip():
            if current_paragraph:
                # End of paragraph
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []
            continue
        
        # Check if this line is likely the start of a new paragraph
        if current_paragraph and (
            line.strip().startswith(('-', '•', '*', '>', '1.', '2.')) or  # List markers
            line.strip()[0:1].isupper() and ( # First char is uppercase AND
                # Previous line ends with sentence-ending punctuation
                (current_paragraph[-1].rstrip().endswith(('.', '!', '?')) and 
                 not current_paragraph[-1].rstrip().endswith('Fig.')) or  # Skip Fig. abbreviations
                # Previous line is very short (potential header)
                len(current_paragraph[-1].strip()) < 25
            )
        ):
            # End the current paragraph and start a new one
            paragraphs.append(" ".join(current_paragraph))
            current_paragraph = [line]
        else:
            # Continue current paragraph
            current_paragraph.append(line)
    
    # Add the last paragraph if there's any
    if current_paragraph:
        paragraphs.append(" ".join(current_paragraph))
    
    return paragraphs

# Process attachment based on its content type or file extension
async def process_attachment(attachment):
    """Process an attachment and extract text using Document Intelligence."""
    attachment_name = attachment.get('name', '').lower()
    content_type = attachment.get('contentType', '').lower()
    attachment_content = attachment.get('contentBytes', '')
    
    # Check file extension for common document formats
    is_supported_ext = any(attachment_name.endswith(ext) for ext in [
        '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif'
    ])
    
    # Check content type for supported formats
    is_supported_mime = any(mime_type in content_type for mime_type in [
        'pdf', 'jpeg', 'jpg', 'png', 'gif', 'bmp', 'tiff', 'octet-stream'
    ])
    
    # Process if either the extension or MIME type suggests a supported document
    if is_supported_ext or is_supported_mime:
        # If it's octet-stream, try to determine if it's actually a PDF or image
        if 'octet-stream' in content_type and is_supported_ext:
            print(f"Found octet-stream with supported extension: {attachment_name}")
        
        # Extract text using Document Intelligence
        extracted_data = await extract_text_with_document_intelligence(attachment_content, attachment_name)
        
        return {
            "name": attachment_name,
            "content_type": content_type,
            "analysis_result": extracted_data,
            # For backward compatibility
            "extracted_text": extracted_data.get("full_text", "") if "error" not in extracted_data else ""
        }
    else:
        # For other content types, we don't extract text
        return {
            "name": attachment_name,
            "content_type": content_type,
            "analysis_result": {"error": "Content type not supported for text extraction"},
            "extracted_text": ""
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

# Generate a formatted LLM text as JSON with all email details and attachment content
def generate_llm_text(email_data):
    """Generate a structured JSON with all email details and attachment content."""
    
    # Create the structured JSON object
    llm_data = {
        "email_metadata": {
            "from": email_data.get('from', ''),
            "to": email_data.get('to', ''),
            "cc": email_data.get('cc', ''),
            "subject": email_data.get('subject', ''),
            "date_received": email_data.get('date_received', '')
        },
        "email_body": email_data.get('body_text', ''),
        "attachments": []
    }
    
    # Add attachment information
    attachments = email_data.get('processed_attachments', [])
    if attachments:
        for i, attachment in enumerate(attachments, 1):
            attachment_data = {
                "name": attachment.get('name', ''),
                "type": attachment.get('content_type', ''),
                "index": i
            }
            
            # Add analysis results if available
            analysis_result = attachment.get('analysis_result', {})
            if analysis_result and "error" not in analysis_result:
                attachment_data["content"] = analysis_result.get("full_text", "")
                attachment_data["page_count"] = analysis_result.get("page_count", 1)
                attachment_data["has_handwritten_content"] = analysis_result.get("has_handwritten_content", False)
            else:
                attachment_data["content"] = ""
                attachment_data["error"] = analysis_result.get("error", "Unknown error during text extraction")
            
            llm_data["attachments"].append(attachment_data)
    
    # Convert to JSON string
    return json.dumps(llm_data, indent=2)
,  # Common signature delimiter
        r'^regards',
        r'^best regards',
        r'^kind regards',
        r'^thanks',
        r'^thank you',
        r'^cheers',
        r'^sincerely',
        r'^sent from my',
        r'^get outlook for',
    ]
    
    # Legal disclaimer and confidentiality markers
    legal_markers = [
        r'^disclaimer',
        r'^legal disclaimer',
        r'^confidentiality notice',
        r'^confidential:',
        r'^privacy notice',
        r'^this email and any files',
        r'^this message is confidential',
        r'^this email is confidential',
        r'^this communication is confidential',
        r'^this e-mail message may contain confidential',
        r'^the information contained in this',
    ]
    
    # Process each line
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        
        # Check for signature markers
        if not in_signature and not in_legal_disclaimer and not in_confidentiality_notice:
            # Check if this line starts a signature
            if any(re.match(marker, line_lower) for marker in signature_markers):
                in_signature = True
                continue
            
            # Check if this line starts a legal disclaimer
            if any(re.match(marker, line_lower) for marker in legal_markers):
                in_legal_disclaimer = True
                continue
            
            # Check for specific confidentiality notices
            if ('confidential' in line_lower and len(line_lower) > 50) or 'confidentiality notice' in line_lower:
                in_confidentiality_notice = True
                continue
            
            # Common email footer patterns
            if (line_lower.startswith('this email has been checked for viruses') or
                'virus' in line_lower and 'scan' in line_lower or
                'http://' in line_lower and len(line) > 40 or
                'https://' in line_lower and len(line) > 40):
                continue
        
        # Process the line
        if in_signature or in_legal_disclaimer or in_confidentiality_notice:
            # Check for email trail markers that might appear after a signature
            if (line.startswith('From:') or line.startswith('Sent:') or 
                line.startswith('To:') or line.startswith('Subject:') or
                '-----Original Message-----' in line or
                line.startswith('On ') and ' wrote:' in line):
                
                # Reset flags as we've found an email trail
                in_signature = False
                in_legal_disclaimer = False
                in_confidentiality_notice = False
                cleaned_lines.append(line)
            # Otherwise, skip this line as it's part of signature/disclaimer
        else:
            # Add normal content lines
            cleaned_lines.append(line)
    
    # Join the cleaned lines back into text
    return '\n'.join(cleaned_lines)

async def extract_text_with_document_intelligence(attachment_content, attachment_name):
    """
    Extract text from PDF or image using Azure Document Intelligence.
    
    Args:
        attachment_content: Base64 encoded content of the attachment
        attachment_name: Name of the attachment
    
    Returns:
        dict: Dictionary containing extracted text and error message if any
    """
    # Get configuration for Document Intelligence
    endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    api_key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY")
    
    if not endpoint or not api_key:
        return {
            "error": "Document Intelligence service not properly configured",
            "text": ""
        }
    
    # Initialize the Document Intelligence client
    try:
        document_client = DocumentAnalysisClient(
            endpoint=endpoint, 
            credential=AzureKeyCredential(api_key)
        )
    except Exception as e:
        return {
            "error": f"Error initializing Document Intelligence service: {str(e)}",
            "text": ""
        }
    
    # Check file extension to ensure it's supported
    file_extension = Path(attachment_name).suffix.lower()
    supported_extensions = ['.jpg', '.jpeg', '.jpe', '.jif', '.jfi', '.jfif', 
                           '.png', '.tif', '.tiff', '.pdf']
    
    if file_extension not in supported_extensions:
        return {
            "error": f"Unsupported file type. Only {', '.join(supported_extensions)} files are supported.",
            "text": ""
        }
    
    try:
        # Create a temporary file to store the attachment
        with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
            # Decode base64 content and write to temp file
            binary_content = base64.b64decode(attachment_content)
            temp_file.write(binary_content)
            temp_file_path = temp_file.name
        
        # Analyze the document
        with open(temp_file_path, "rb") as f:
            document_content = f.read()
            poller = document_client.begin_analyze_document(
                "prebuilt-read",
                document_content
            )
            
            # Wait for the operation to complete
            result = poller.result()
        
        # Remove temporary file
        os.unlink(temp_file_path)
        
        # Process results
        if not result or not result.pages:
            return {
                "error": "No text content detected in document",
                "text": ""
            }
        
        # Extract text from all pages
        full_text = ""
        page_texts = []
        
        for page in result.pages:
            # Group lines into paragraphs
            line_contents = [line.content for line in page.lines if line.content.strip()]
            paragraphs = group_lines_into_paragraphs(line_contents)
            
            # Combine paragraphs for this page
            page_text = "\n\n".join(paragraphs)
            page_texts.append({
                "page_number": page.page_number,
                "text": page_text
            })
            
            full_text += page_text + "\n\n"
        
        return {
            "full_text": full_text.strip(),
            "pages": page_texts,
            "page_count": len(result.pages),
            "has_handwritten_content": hasattr(result, 'styles') and any(
                style.is_handwritten for style in result.styles if hasattr(style, 'is_handwritten')
            )
        }
            
    except HttpResponseError as e:
        return {
            "error": f"Azure Document Intelligence service error: {str(e)}",
            "text": ""
        }
    except Exception as e:
        return {
            "error": f"Error analyzing document: {str(e)}",
            "text": ""
        }
    finally:
        # Ensure temp file is deleted if it exists
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except:
                pass

def group_lines_into_paragraphs(lines):
    """
    Group sequential lines into paragraphs.
    
    Args:
        lines (list): List of line content strings
        
    Returns:
        list: List of paragraph content strings
    """
    if not lines:
        return []
    
    paragraphs = []
    current_paragraph = []
    
    for line in lines:
        # Skip empty lines
        if not line.strip():
            if current_paragraph:
                # End of paragraph
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []
            continue
        
        # Check if this line is likely the start of a new paragraph
        if current_paragraph and (
            line.strip().startswith(('-', '•', '*', '>', '1.', '2.')) or  # List markers
            line.strip()[0:1].isupper() and ( # First char is uppercase AND
                # Previous line ends with sentence-ending punctuation
                (current_paragraph[-1].rstrip().endswith(('.', '!', '?')) and 
                 not current_paragraph[-1].rstrip().endswith('Fig.')) or  # Skip Fig. abbreviations
                # Previous line is very short (potential header)
                len(current_paragraph[-1].strip()) < 25
            )
        ):
            # End the current paragraph and start a new one
            paragraphs.append(" ".join(current_paragraph))
            current_paragraph = [line]
        else:
            # Continue current paragraph
            current_paragraph.append(line)
    
    # Add the last paragraph if there's any
    if current_paragraph:
        paragraphs.append(" ".join(current_paragraph))
    
    return paragraphs

# Process attachment based on its content type or file extension
async def process_attachment(attachment):
    """Process an attachment and extract text using Document Intelligence."""
    attachment_name = attachment.get('name', '').lower()
    content_type = attachment.get('contentType', '').lower()
    attachment_content = attachment.get('contentBytes', '')
    
    # Check file extension for common document formats
    is_supported_ext = any(attachment_name.endswith(ext) for ext in [
        '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif'
    ])
    
    # Check content type for supported formats
    is_supported_mime = any(mime_type in content_type for mime_type in [
        'pdf', 'jpeg', 'jpg', 'png', 'gif', 'bmp', 'tiff', 'octet-stream'
    ])
    
    # Process if either the extension or MIME type suggests a supported document
    if is_supported_ext or is_supported_mime:
        # If it's octet-stream, try to determine if it's actually a PDF or image
        if 'octet-stream' in content_type and is_supported_ext:
            print(f"Found octet-stream with supported extension: {attachment_name}")
        
        # Extract text using Document Intelligence
        extracted_data = await extract_text_with_document_intelligence(attachment_content, attachment_name)
        
        return {
            "name": attachment_name,
            "content_type": content_type,
            "analysis_result": extracted_data,
            # For backward compatibility
            "extracted_text": extracted_data.get("full_text", "") if "error" not in extracted_data else ""
        }
    else:
        # For other content types, we don't extract text
        return {
            "name": attachment_name,
            "content_type": content_type,
            "analysis_result": {"error": "Content type not supported for text extraction"},
            "extracted_text": ""
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

# Generate a formatted LLM text as JSON with all email details and attachment content
def generate_llm_text(email_data):
    """Generate a structured JSON with all email details and attachment content."""
    
    # Create the structured JSON object
    llm_data = {
        "email_metadata": {
            "from": email_data.get('from', ''),
            "to": email_data.get('to', ''),
            "cc": email_data.get('cc', ''),
            "subject": email_data.get('subject', ''),
            "date_received": email_data.get('date_received', '')
        },
        "email_body": email_data.get('body_text', ''),
        "attachments": []
    }
    
    # Add attachment information
    attachments = email_data.get('processed_attachments', [])
    if attachments:
        for i, attachment in enumerate(attachments, 1):
            attachment_data = {
                "name": attachment.get('name', ''),
                "type": attachment.get('content_type', ''),
                "index": i
            }
            
            # Add analysis results if available
            analysis_result = attachment.get('analysis_result', {})
            if analysis_result and "error" not in analysis_result:
                attachment_data["content"] = analysis_result.get("full_text", "")
                attachment_data["page_count"] = analysis_result.get("page_count", 1)
                attachment_data["has_handwritten_content"] = analysis_result.get("has_handwritten_content", False)
            else:
                attachment_data["content"] = ""
                attachment_data["error"] = analysis_result.get("error", "Unknown error during text extraction")
            
            llm_data["attachments"].append(attachment_data)
    
    # Convert to JSON string
    return json.dumps(llm_data, indent=2)
