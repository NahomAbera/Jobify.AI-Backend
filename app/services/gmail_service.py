import os
import base64
import pickle
from datetime import datetime
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from bs4 import BeautifulSoup
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    """
    Authenticate with the Gmail API and return the service object.
    
    Returns:
        googleapiclient.discovery.Resource: Gmail API service object
    """
    creds = None
    credentials_path = os.getenv('GMAIL_CREDENTIALS_PATH')
    token_path = os.getenv('GMAIL_TOKEN_PATH')
    
    # Check if token.json exists
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)
    
    # If credentials don't exist or are invalid, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
    
    # Build the Gmail service
    service = build('gmail', 'v1', credentials=creds)
    return service

def fetch_new_emails(service, user_id='me', query='', start_date=None):
    """
    Fetch new emails from Gmail.
    
    Args:
        service (googleapiclient.discovery.Resource): Gmail API service object
        user_id (str): User ID, default is 'me'
        query (str): Gmail search query
        start_date (datetime.date, optional): Start date for fetching emails
        
    Returns:
        list: List of email dictionaries with 'id', 'subject', 'sender', 'date', and 'body'
    """
    try:
        # If start_date is provided, add it to the query
        if start_date:
            # Format date as YYYY/MM/DD for Gmail query
            formatted_date = start_date.strftime('%Y/%m/%d')
            date_query = f"after:{formatted_date}"
            
            # Combine with existing query if any
            if query:
                query = f"{query} {date_query}"
            else:
                query = date_query
            
            logger.info(f"Fetching emails with query: {query}")
        
        # Get list of messages
        results = service.users().messages().list(userId=user_id, q=query).execute()
        messages = results.get('messages', [])
        
        if not messages:
            logger.info("No new emails found.")
            return []
        
        emails = []
        
        for message in messages:
            msg_id = message['id']
            msg = service.users().messages().get(userId=user_id, id=msg_id, format='full').execute()
            
            # Extract headers
            headers = msg['payload']['headers']
            subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject')
            sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown Sender')
            date_str = next((header['value'] for header in headers if header['name'].lower() == 'date'), None)
            
            # Parse date
            date = None
            if date_str:
                try:
                    # Try to parse the date in various formats
                    from email.utils import parsedate_to_datetime
                    date = parsedate_to_datetime(date_str)
                except Exception as e:
                    logger.error(f"Error parsing date: {e}")
                    date = datetime.now()
            else:
                date = datetime.now()
            
            # Extract body
            body = extract_email_body(msg)
            
            # Clean HTML if body is in HTML format
            if body and '<html' in body.lower():
                body = clean_html_content(body)
            
            emails.append({
                'id': msg_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body
            })
        
        return emails
    
    except Exception as e:
        logger.error(f"An error occurred while fetching emails: {e}")
        return []

def extract_email_body(message):
    """
    Extract the body of an email message.
    
    Args:
        message (dict): Gmail API message object
        
    Returns:
        str: Email body text
    """
    if 'parts' in message['payload']:
        for part in message['payload']['parts']:
            if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            elif part['mimeType'] == 'text/html' and 'data' in part['body']:
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            elif 'parts' in part:
                for subpart in part['parts']:
                    if subpart['mimeType'] == 'text/plain' and 'data' in subpart['body']:
                        return base64.urlsafe_b64decode(subpart['body']['data']).decode('utf-8')
                    elif subpart['mimeType'] == 'text/html' and 'data' in subpart['body']:
                        return base64.urlsafe_b64decode(subpart['body']['data']).decode('utf-8')
    elif 'body' in message['payload'] and 'data' in message['payload']['body']:
        return base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8')
    
    return "No body content found."

def clean_html_content(html_content):
    """
    Clean HTML content using BeautifulSoup to extract text.
    
    Args:
        html_content (str): HTML content to clean
        
    Returns:
        str: Cleaned text content
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
        
        # Get text
        text = soup.get_text()
        
        # Break into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        
        # Remove blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
    
    except Exception as e:
        logger.error(f"Error cleaning HTML content: {e}")
        return html_content  # Return original content if cleaning fails
