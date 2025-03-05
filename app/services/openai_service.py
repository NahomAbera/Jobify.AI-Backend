import os
import json
import logging
from openai import OpenAI
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def classify_and_extract_email(email_content, email_date):
    """
    Use OpenAI's ChatGPT 4o-mini to classify and extract information from an email.
    
    Args:
        email_content (str): The content of the email to analyze
        email_date (datetime): The date the email was sent
        
    Returns:
        dict: Extracted information from the email or None if not job-related
    """
    try:
        # Format the date for the prompt
        formatted_date = email_date.strftime('%Y-%m-%d') if email_date else datetime.now().strftime('%Y-%m-%d')
        
        # Create the prompt for the LLM
        prompt = f"""
        You are a very careful email classifier and information extractor for a job application tracking system.
        
        Your task is to analyze the following email and determine if it's related to a job application process.
        Be very, very, very, very, very, very careful when classifying this email. If you have ANY doubt that 
        this is job-application related, output a status of "None of These".
        
        Only classify an email as job-related if it clearly falls into one of these categories:
        1. "applied" - A confirmation that the user has applied for a job
        2. "rejected" - A rejection notice for a job application
        3. "interview" - An invitation to an interview or information about an interview
        4. "offer" - A job offer
        
        For any other type of email, even if it mentions jobs or careers, output "None of These".
        
        If the email is job-related, extract the following information in JSON format:
        - company_name: The name of the company
        - role: The job title or role
        - date: {formatted_date} (use this date from the email)
        - location: The job location (if available, otherwise null)
        - status: One of "applied", "rejected", "interview", "offer", or "None of These"
        
        If status is "interview", also include:
        - interview_round: One of "OA" (Online Assessment), "Behavioral", "Round 1", "Round 2", "Round 3", "Round 4", "Final Round", etc.
        
        If available, also include:
        - job_id: The job ID or reference number
        
        Here's the email content:
        
        {email_content}
        
        Output ONLY valid JSON with no additional text.
        """
        
        # Call OpenAI API with ChatGPT 4o-mini
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts job application information from emails."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Low temperature for more deterministic outputs
            max_tokens=1000
        )
        
        # Extract the response content
        result_text = response.choices[0].message.content.strip()
        
        # Parse the JSON response
        try:
            result = json.loads(result_text)
            
            # Check if the email is job-related
            if result.get('status') == 'None of These':
                logger.info("Email classified as not job-related")
                return None
            
            return result
        
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}")
            logger.error(f"Response text: {result_text}")
            return None
    
    except Exception as e:
        logger.error(f"Error calling OpenAI API: {e}")
        return None

def generate_embedding(text):
    """
    Generate an embedding for the given text using OpenAI's text-embedding-3-large model.
    
    Args:
        text (str): The text to generate an embedding for
        
    Returns:
        list: The embedding vector
    """
    try:
        response = client.embeddings.create(
            model="text-embedding-3-large",
            input=text
        )
        
        return response.data[0].embedding
    
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return None
