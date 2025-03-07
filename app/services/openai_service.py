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
print(f"OpenAI API key: {'*****' + os.getenv('OPENAI_API_KEY')[-4:] if os.getenv('OPENAI_API_KEY') else 'Not set'}")

def classify_and_extract_email(email_content, email_date):
    """
    Use OpenAI's ChatGPT 4o-mini to classify and extract information from an email.
    
    Args:
        email_content (str): The content of the email to analyze
        email_date (datetime): The date the email was sent
        
    Returns:
        dict: A dictionary containing the classification and extracted information
    """
    try:
        print("Classifying and extracting information from email...")
        logger.info("Classifying and extracting information from email")
        
        # Format the date
        formatted_date = email_date.strftime("%Y-%m-%d")
        print(f"Email date: {formatted_date}")
        
        # Truncate email content for logging
        truncated_content = email_content[:100] + "..." if len(email_content) > 100 else email_content
        print(f"Email content (truncated): {truncated_content}")
        
        # Create the prompt
        prompt = f"""
        You are an AI assistant that analyzes job application emails. Your task is to classify the email as one of the following:
        1. "applied" - The user has applied for a job
        2. "rejected" - The user has been rejected for a job they applied for
        3. "interview" - The user has been invited for an interview
        4. "offer" - The user has received a job offer
        5. "other" - None of the above
        
        For each email, extract the following information based on its classification:
        
        For "applied" emails:
        - company_name: The name of the company the user applied to
        - position_name: The position the user applied for
        - application_date: The date of the application (use {formatted_date} if not specified)
        - job_description: A brief description of the job (if available)
        - application_method: How the application was submitted (e.g., "online portal", "email", "referral")
        
        For "rejected" emails:
        - company_name: The name of the company that rejected the user
        - position_name: The position the user was rejected for
        - rejection_date: The date of the rejection (use {formatted_date} if not specified)
        - reason: The reason for rejection (if available)
        
        For "interview" emails:
        - company_name: The name of the company inviting for an interview
        - position_name: The position the interview is for
        - interview_date: The date of the interview (if available)
        - interview_time: The time of the interview (if available)
        - interview_location: The location of the interview (if available)
        - interview_type: The type of interview (e.g., "phone", "video", "in-person")
        - interview_round: The round of the interview (e.g., "first", "second", "final")
        - interviewer_name: The name of the interviewer (if available)
        
        For "offer" emails:
        - company_name: The name of the company making the offer
        - position_name: The position the offer is for
        - offer_date: The date of the offer (use {formatted_date} if not specified)
        - salary: The offered salary (if available)
        - benefits: The offered benefits (if available)
        - start_date: The proposed start date (if available)
        - deadline: The deadline to accept the offer (if available)
        
        For "other" emails:
        - summary: A brief summary of what the email is about
        
        Analyze the following email and provide your classification and extracted information in JSON format:
        
        {email_content}
        """
        
        print("Calling OpenAI API for email classification...")
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes job application emails."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        
        # Extract the response
        result = json.loads(response.choices[0].message.content)
        
        print(f"OpenAI API response: {result}")
        
        # Check if the result contains a classification
        if 'classification' not in result:
            print("No classification found in OpenAI response")
            logger.warning("No classification found in OpenAI response")
            return None
        
        # Return the result
        return result
        
    except Exception as e:
        print(f"Error classifying and extracting email: {e}")
        logger.error(f"Error classifying and extracting email: {e}")
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
        print("Generating embedding for text...")
        
        # Truncate text for logging
        truncated_text = text[:100] + "..." if len(text) > 100 else text
        print(f"Text (truncated): {truncated_text}")
        
        # Call OpenAI API
        print("Calling OpenAI API for embedding generation...")
        response = client.embeddings.create(
            input=text,
            model="text-embedding-3-large"
        )
        
        # Extract the embedding
        embedding = response.data[0].embedding
        
        print(f"Generated embedding with {len(embedding)} dimensions")
        
        return embedding
        
    except Exception as e:
        print(f"Error generating embedding: {e}")
        logger.error(f"Error generating embedding: {e}")
        return None
