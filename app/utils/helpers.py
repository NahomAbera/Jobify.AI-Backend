import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_date(date_str):
    """
    Parse a date string into a datetime object.
    
    Args:
        date_str (str): Date string in format 'YYYY-MM-DD'
        
    Returns:
        datetime.date: Parsed date or None if parsing fails
    """
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing date {date_str}: {e}")
        return None

def create_summary_text(company_name, position_title, additional_info=None):
    """
    Create a summary text for embedding generation.
    
    Args:
        company_name (str): Company name
        position_title (str): Position title
        additional_info (str, optional): Additional information
        
    Returns:
        str: Summary text
    """
    summary = f"{company_name} | {position_title}"
    if additional_info:
        summary += f" | {additional_info}"
    return summary

def sanitize_vector_id(text):
    """
    Sanitize text for use as a vector ID.
    
    Args:
        text (str): Text to sanitize
        
    Returns:
        str: Sanitized text
    """
    # Replace spaces and special characters
    sanitized = text.replace(" ", "_").replace("/", "_").replace("\\", "_")
    sanitized = sanitized.replace("(", "").replace(")", "").replace(",", "")
    
    # Limit length
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    
    return sanitized
