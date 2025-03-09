import os
import base64
import pickle
import json
from datetime import datetime
import re
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from bs4 import BeautifulSoup
import logging
from email.utils import parsedate_to_datetime

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
    print("Initializing Gmail API service...")
    try:
        # Load credentials paths from environment variables
        credentials_path = os.getenv('GMAIL_CREDENTIALS_PATH')
        token_path = os.getenv('GMAIL_TOKEN_PATH')
        
        print(f"Credentials path: {credentials_path}")
        print(f"Token path: {token_path}")
        
        if not credentials_path or not token_path:
            print("Missing Gmail API credentials or token path")
            logger.error("Missing Gmail API credentials or token path")
            return None
        
        # Check if the credentials file exists
        if not os.path.exists(credentials_path):
            print(f"Credentials file not found at {credentials_path}")
            logger.error(f"Credentials file not found at {credentials_path}")
            return None
            
        # Create token directory if it doesn't exist
        token_dir = os.path.dirname(token_path)
        if not os.path.exists(token_dir):
            print(f"Creating token directory: {token_dir}")
            os.makedirs(token_dir)
            
        # The file token.json stores the user's access and refresh tokens
        creds = None
        if os.path.exists(token_path):
            print("Loading existing token...")
            creds = Credentials.from_authorized_user_info(json.load(open(token_path)))
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            print("Token not found or invalid, authenticating...")
            if creds and creds.expired and creds.refresh_token:
                print("Refreshing expired token...")
                creds.refresh(Request())
            else:
                print("Getting new token...")
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(token_path, 'w') as token:
                print("Saving token...")
                token.write(creds.to_json())
        
        # Build the Gmail API service
        print("Building Gmail API service...")
        service = build('gmail', 'v1', credentials=creds)
        print("Gmail API service initialized successfully")
        return service
        
    except Exception as e:
        print(f"Error initializing Gmail API service: {e}")
        logger.error(f"Error initializing Gmail API service: {e}")
        return None

def safe_print(text):
    """
    Safely print text that might contain Unicode characters
    that are not supported by the console.
    
    Args:
        text (str): Text to print
    """
    try:
        # Try to print normally
        print(text)
    except UnicodeEncodeError:
        # If that fails, replace problematic characters
        ascii_text = text.encode('ascii', 'replace').decode('ascii')
        print(ascii_text)

def sanitize_text(text):
    """
    Remove or replace problematic Unicode characters from text.
    
    Args:
        text (str): Text to sanitize
        
    Returns:
        str: Sanitized text
    """
    if not text:
        return ""
    
    # Replace emoji and other problematic Unicode characters with a placeholder
    sanitized = re.sub(r'[^\x00-\x7F]+', '[emoji]', text)
    return sanitized

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
    safe_print(f"Fetching emails with query: '{query}', start_date: {start_date}")
    try:
        # Add date filter to query if start_date is provided
        if start_date:
            formatted_date = start_date.strftime('%Y/%m/%d')
            date_query = f"after:{formatted_date}"
            
            if query:
                query = f"{query} {date_query}"
            else:
                query = date_query
                
            safe_print(f"Modified query with date filter: '{query}'")
        
        # Get list of messages
        safe_print("Executing Gmail API query...")
        results = service.users().messages().list(userId=user_id, q=query).execute()
        messages = results.get('messages', [])
        
        safe_print(f"Found {len(messages)} messages matching the query")
        
        emails = []
        for message in messages:
            try:
                safe_print(f"Fetching message details for message ID: {message['id']}")
                msg = service.users().messages().get(userId=user_id, id=message['id'], format='full').execute()
                
                # Extract headers
                headers = msg['payload']['headers']
                subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject')
                sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown Sender')
                date_str = next((header['value'] for header in headers if header['name'].lower() == 'date'), None)
                
                # Sanitize subject and sender for console output
                safe_subject = sanitize_text(subject)
                safe_sender = sanitize_text(sender)
                
                safe_print(f"Processing email: '{safe_subject}' from {safe_sender}")
                
                # Parse date
                date = None
                if date_str:
                    try:
                        # Try to parse the date string
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
                
                safe_print(f"Email body length: {len(body)} characters")
                    
                # Add email to list
                emails.append({
                    'id': message['id'],
                    'subject': subject,
                    'sender': sender,
                    'date': date,
                    'body': body
                })
            except UnicodeEncodeError as e:
                logger.error(f"Unicode encoding error processing message {message['id']}: {e}")
                # Continue to the next message
                continue
            except Exception as e:
                logger.error(f"Error processing message {message['id']}: {e}")
                # Continue to the next message
                continue
            
        safe_print(f"Successfully processed {len(emails)} emails")
        return emails
        
    except UnicodeEncodeError as e:
        logger.error(f"Unicode encoding error: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
        return []

def extract_email_body(message):
    """
    Extract the body of an email message.
    
    Args:
        message (dict): Gmail API message object
        
    Returns:
        str: Email body text
    """
    try:
        if 'parts' in message['payload']:
            for part in message['payload']['parts']:
                if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                    return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                elif part['mimeType'] == 'text/html' and 'data' in part['body']:
                    return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                elif 'parts' in part:
                    for subpart in part['parts']:
                        if subpart['mimeType'] == 'text/plain' and 'data' in subpart['body']:
                            return base64.urlsafe_b64decode(subpart['body']['data']).decode('utf-8', errors='replace')
                        elif subpart['mimeType'] == 'text/html' and 'data' in subpart['body']:
                            return base64.urlsafe_b64decode(subpart['body']['data']).decode('utf-8', errors='replace')
        elif 'body' in message['payload'] and 'data' in message['payload']['body']:
            return base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8', errors='replace')
        
        return "No body content found."
    except UnicodeDecodeError:
        # If UTF-8 fails, try with errors='replace' to handle problematic characters
        return "Email content contains characters that could not be decoded properly."
    except Exception as e:
        logger.error(f"Error extracting email body: {e}")
        return "Error extracting email body."

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
