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
        email_date (str or datetime): The date the email was sent
        
    Returns:
        dict: A dictionary containing the classification and extracted information
    """
    try:
        logger.info("Classifying and extracting information from email")
        
        # Format the date - handle both string and datetime objects
        if isinstance(email_date, str):
            # If it's already a string, use it directly
            formatted_date = email_date
        else:
            # Otherwise, it's a datetime object, so format it
            formatted_date = email_date.strftime("%Y-%m-%d")
            
        logger.info(f"Email date: {formatted_date}")
        
        # Truncate email content for logging
        truncated_content = email_content[:100] + "..." if len(email_content) > 100 else email_content
        logger.info(f"Email content (truncated): {truncated_content}")
        
        # Create the prompt with more specific guidelines
        prompt = f"""
        You are an AI assistant that accurately analyzes job application emails. Follow these precise guidelines:

        CLASSIFICATION CRITERIA:
        1. "applied" - ONLY if this email CONFIRMS that the user has SUBMITTED a job application, AND the email is from the company or their application system confirming receipt. DO NOT classify job posting notifications, invitations to apply, or general recruitment emails as "applied".

        2. "rejected" - ONLY if this email clearly states the user was not selected for a position they previously applied to.

        3. "interview" - ONLY if this email is a DIRECT invitation for an interview for a specific role. DO NOT classify scheduling confirmations, follow-ups, or general information about interview processes as "interview" unless they contain a specific invitation.

        4. "offer" - ONLY if this email contains a formal job offer with employment terms.

        5. "other" - If the email doesn't PRECISELY match any of the above categories.

        SPECIFIC EXTRACTION REQUIREMENTS:

        For "applied" emails:
        - company_name: Extract EXACT company name
        - role: Extract EXACT position title
        - date: Use application submission date, defaulting to {formatted_date} if not specified
        - location: Job location (if available)
        - job_id: Job ID/reference number (if available)
        - status: "applied"

        For "interview" emails:
        - company_name: Extract EXACT company name
        - role: Extract EXACT position title
        - date: Scheduled interview date
        - location: Interview location or link
        - interview_type: "phone", "video", "in-person", or other specific format
        - round: Use your knowledge to determine the interview round based on context:
          * "OA" - For online assessments, coding challenges
          * "behavioral" - For behavioral/HR interviews (e.g., HireVue at Goldman Sachs)
          * "round 1", "round 2", "round 3", etc. - For sequential interview rounds
          * "final" - For final round interviews, "superday" at banks, or on-site final interviews
        - status: "interview"

        Use common sense and your knowledge about company-specific interview terminology. For example:
        - HireVue interviews at Goldman Sachs are typically behavioral rounds
        - Superday at investment banks is typically the final round
        - Technical screens usually come before behavioral interviews

        For "rejected" and "offer" emails, extract information as previously specified.

        For "other" emails:
        - Return only a simple JSON with classification set to "other"

        BE EXTREMELY CONSERVATIVE with your classifications. If you're unsure, classify as "other".

        Analyze the following email and provide your classification and extracted information in JSON format with a consistent structure:
        
        {email_content}
        
        Your response should follow this exact format:
        
        For job-related emails (applied, interview, etc):
        {{{{
          "classification": "applied/rejected/interview/offer",
          "extracted_info": {{{{
            "company_name": "Company Name",
            "role": "Position Title",
            "date": "YYYY-MM-DD",
            "status": "applied/rejected/interview/offer"
            // Additional fields as appropriate for the classification
          }}}}
        }}}}
        
        For non-job-related emails:
        {{{{
          "classification": "other"
        }}}}
        """
        
        logger.info("Calling OpenAI API for email classification...")
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes job application emails with extremely high accuracy. You never misclassify emails."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Lower temperature for more consistent results
            response_format={"type": "json_object"}
        )
        
        # Get the response content
        result = response.choices[0].message.content
        logger.info(f"OpenAI API response: {result}")
        
        # Parse the JSON response
        parsed_result = json.loads(result)
        
        # Standardize the response format
        if "classification" in parsed_result:
            classification = parsed_result["classification"]
            
            # Return None for 'other' classification
            if classification == "other":
                return None
                
            # Extract information based on classification
            if "extracted_info" in parsed_result:
                extracted_info = parsed_result["extracted_info"]
            else:
                # Handle case where extracted_info isn't nested
                extracted_info = {k: v for k, v in parsed_result.items() if k != "classification"}
                
            # Ensure status is set correctly
            if "status" not in extracted_info:
                extracted_info["status"] = classification
                
            return extracted_info
        else:
            # For backward compatibility with responses that don't have classification field
            if "status" in parsed_result:
                status = parsed_result.get("status")
                if status == "other":
                    return None
                return parsed_result
            elif any(key in parsed_result for key in ["company_name", "role"]):
                # If it has job-related fields but no status/classification, infer from content
                if "interview_type" in parsed_result or "round" in parsed_result:
                    if "status" not in parsed_result:
                        parsed_result["status"] = "interview"
                return parsed_result
            else:
                # If we can't determine the classification, return None
                return None
    
    except Exception as e:
        logger.error(f"Error classifying and extracting email: {e}")
        return None

def generate_embedding(text):
    """
    Generate an embedding for the given text using OpenAI's text-embedding-3-small model.
    
    Args:
        text (str): The text to generate an embedding for
        
    Returns:
        list: The embedding vector
    """
    try:
        logger.info("Generating embedding for text...")
        
        # Truncate text for logging
        truncated_text = text[:100] + "..." if len(text) > 100 else text
        logger.info(f"Text (truncated): {truncated_text}")
        
        # Call OpenAI API
        logger.info("Calling OpenAI API for embedding generation...")
        response = client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        
        # Extract the embedding
        embedding = response.data[0].embedding
        
        logger.info(f"Generated embedding with {len(embedding)} dimensions")
        
        return embedding
        
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return None
