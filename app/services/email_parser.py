import os
import logging
from datetime import datetime
from flask import current_app
from app import db
from app.models.models import User, Application, Rejection, Interview, Offer
from app.services.gmail_service import get_gmail_service, fetch_new_emails
from app.services.openai_service import classify_and_extract_email, generate_embedding
from app.services.pinecone_service import init_pinecone, generate_and_upsert_application, find_matching_application, upsert_vector

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def start_email_parser(user_email=None):
    """
    Start the email parsing process. This function is called by the scheduler.
    
    Args:
        user_email (str, optional): The email address of the user to parse emails for.
                                   If None, parse for all users.
    """
    print(f"Starting email parser for user: {user_email if user_email else 'all users'}")
    with current_app.app_context():
        logger.info("Starting email parser job")
        
        try:
            # Initialize Gmail service
            print("Initializing Gmail service...")
            gmail_service = get_gmail_service()
            if not gmail_service:
                print("Failed to initialize Gmail service")
                logger.error("Failed to initialize Gmail service")
                return
            print("Gmail service initialized successfully")
            
            # Initialize Pinecone
            print("Initializing Pinecone...")
            pinecone_index = init_pinecone()
            if not pinecone_index:
                print("Failed to initialize Pinecone")
                logger.error("Failed to initialize Pinecone")
                return
            print("Pinecone initialized successfully")
            
            # If user_email is provided, process emails for that user only
            if user_email:
                print(f"Processing emails for specific user: {user_email}")
                process_user_emails(user_email, gmail_service, pinecone_index)
            else:
                print("Processing emails for all users...")
                # Process emails for all users
                users = User.query.all()
                print(f"Found {len(users)} users in the database")
                
                for user in users:
                    print(f"Processing emails for user: {user.email_address}")
                    process_user_emails(user.email_address, gmail_service, pinecone_index)
            
            logger.info("Email parser job completed successfully")
        
        except Exception as e:
            print(f"Error in email parser: {e}")
            logger.error(f"Error in email parser job: {e}")

def process_user_emails(user_email, gmail_service, pinecone_index):
    """
    Process emails for a specific user.
    
    Args:
        user_email (str): The email address of the user
        gmail_service: Gmail API service object
        pinecone_index: Pinecone index object
    """
    print(f"Processing emails for user: {user_email}")
    logger.info(f"Processing emails for user: {user_email}")
    
    # Get the user from the database
    user = User.query.filter_by(email_address=user_email).first()
    
    # If user doesn't exist, create them
    if not user:
        print(f"User {user_email} not found in database, creating new user")
        logger.info(f"User {user_email} not found, creating new user")
        user = User(email_address=user_email)
        db.session.add(user)
        db.session.commit()
        print(f"Created new user: {user_email}")
    else:
        print(f"Found existing user: {user_email}")
        logger.info(f"Found existing user: {user_email}")
    
    # Get the user's email parse start date
    start_date = user.email_parse_start_date
    print(f"Email parse start date for user {user_email}: {start_date}")
    logger.info(f"Email parse start date for user {user_email}: {start_date}")
    
    # Get current date to use as end date for this parsing session
    current_date = datetime.now().date()
    print(f"Current date (end date for parsing): {current_date}")
    
    # Fetch new emails from Gmail
    print(f"Fetching new emails for user {user_email} from {start_date} to {current_date}")
    logger.info(f"Fetching emails from {start_date} to {current_date} for user {user_email}")
    emails = fetch_new_emails(gmail_service, query=f"to:{user_email}", start_date=start_date)
    print(f"Fetched {len(emails)} new emails")
    logger.info(f"Fetched {len(emails)} new emails")
    
    # Process each email
    for email in emails:
        print(f"Processing email: {email['subject']}")
        logger.info(f"Processing email: {email['subject']}")
        process_email(email, pinecone_index, user_email)
    
    # Update the user's email parse start date to the current date
    # This ensures that the next time the parser runs, it will only fetch emails from this point forward
    if emails:  # Only update if we actually processed emails
        print(f"Updating email parse start date for user {user_email} from {start_date} to {current_date}")
        logger.info(f"Updating email parse start date for user {user_email} from {start_date} to {current_date}")
        user.email_parse_start_date = current_date
        db.session.commit()
        print(f"Updated email parse start date for user {user_email}")
    else:
        print(f"No emails processed, keeping email parse start date as {start_date}")
    
    logger.info(f"Email processing completed for user {user_email}")

def process_email(email, pinecone_index, user_email=None):
    """
    Process a single email.
    
    Args:
        email (dict): Email data including 'body', 'date', etc.
        pinecone_index: Pinecone index object
        user_email (str, optional): The email address of the user
    """
    try:
        print(f"Processing email: {email['subject']}")
        logger.info(f"Processing email: {email['subject']}")
        
        # Classify and extract information from the email
        print("Classifying and extracting information from email...")
        logger.info("Classifying and extracting information from email...")
        extracted_data = classify_and_extract_email(email['body'], email['date'])
        
        if not extracted_data:
            print("Email not classified as job-related")
            logger.info("Email not classified as job-related")
            return
        
        # Process the extracted data based on status
        status = extracted_data.get('status')
        
        if status == 'applied':
            print("Processing application...")
            logger.info("Processing application...")
            process_application(extracted_data, pinecone_index, user_email)
        elif status == 'rejected':
            print("Processing rejection...")
            logger.info("Processing rejection...")
            process_rejection(extracted_data, pinecone_index)
        elif status == 'interview':
            print("Processing interview...")
            logger.info("Processing interview...")
            process_interview(extracted_data, pinecone_index)
        elif status == 'offer':
            print("Processing offer...")
            logger.info("Processing offer...")
            process_offer(extracted_data, pinecone_index)
        else:
            print(f"Unknown status: {status}")
            logger.warning(f"Unknown status: {status}")
    
    except Exception as e:
        print(f"Error processing email: {e}")
        logger.error(f"Error processing email: {e}")

def process_application(data, pinecone_index, user_email=None):
    """
    Process an email classified as 'applied'.
    
    Args:
        data (dict): Extracted data from the email
        pinecone_index: Pinecone index object
        user_email (str, optional): The email address of the user
    """
    try:
        print("Processing application...")
        logger.info("Processing application...")
        # Extract required fields
        company_name = data.get('company_name')
        position_title = data.get('role')
        application_date_str = data.get('date')
        location = data.get('location')
        job_id = data.get('job_id')
        
        # Validate required fields
        if not company_name or not position_title or not application_date_str:
            print("Missing required fields for application")
            logger.error("Missing required fields for application")
            return
        
        # Parse application date
        try:
            application_date = datetime.strptime(application_date_str, '%Y-%m-%d').date()
        except ValueError:
            print(f"Invalid date format: {application_date_str}")
            logger.error(f"Invalid date format: {application_date_str}")
            application_date = datetime.now().date()
        
        # Use provided user_email or default
        email_to_use = user_email if user_email else "user@example.com"
        
        # Create a new Application record
        application = Application(
            user_email_id=email_to_use,
            company_name=company_name,
            position_title=position_title,
            application_date=application_date,
            location=location,
            job_id=job_id
        )
        
        # Add to database
        db.session.add(application)
        db.session.commit()
        
        print(f"Created new application record: {application.application_id}")
        logger.info(f"Created new application record: {application.application_id}")
        
        # Generate embedding and upsert into Pinecone
        success = generate_and_upsert_application(
            pinecone_index,
            application.application_id,
            company_name,
            position_title,
            application_date_str
        )
        
        if not success:
            print("Failed to upsert application vector")
            logger.error("Failed to upsert application vector")
    
    except Exception as e:
        db.session.rollback()
        print(f"Error processing application: {e}")
        logger.error(f"Error processing application: {e}")

def process_rejection(data, pinecone_index):
    """
    Process an email classified as 'rejected'.
    
    Args:
        data (dict): Extracted data from the email
        pinecone_index: Pinecone index object
    """
    try:
        print("Processing rejection...")
        logger.info("Processing rejection...")
        # Extract required fields
        company_name = data.get('company_name')
        position_title = data.get('role')
        rejection_date_str = data.get('date')
        
        # Validate required fields
        if not company_name or not position_title or not rejection_date_str:
            print("Missing required fields for rejection")
            logger.error("Missing required fields for rejection")
            return
        
        # Parse rejection date
        try:
            rejection_date = datetime.strptime(rejection_date_str, '%Y-%m-%d').date()
        except ValueError:
            print(f"Invalid date format: {rejection_date_str}")
            logger.error(f"Invalid date format: {rejection_date_str}")
            rejection_date = datetime.now().date()
        
        # Find matching application in Pinecone
        application_id = find_matching_application(pinecone_index, company_name, position_title, "rejected")
        
        if not application_id:
            print("No matching application found for rejection")
            logger.error("No matching application found for rejection")
            return
        
        # Check if rejection already exists
        existing_rejection = Rejection.query.filter_by(application_id=application_id).first()
        
        if existing_rejection:
            print(f"Rejection already exists for application {application_id}")
            logger.info(f"Rejection already exists for application {application_id}")
            return
        
        # Create a new Rejection record
        rejection = Rejection(
            application_id=application_id,
            company_name=company_name,
            position_title=position_title,
            rejection_date=rejection_date
        )
        
        # Add to database
        db.session.add(rejection)
        db.session.commit()
        
        print(f"Created new rejection record for application {application_id}")
        logger.info(f"Created new rejection record for application {application_id}")
    
    except Exception as e:
        db.session.rollback()
        print(f"Error processing rejection: {e}")
        logger.error(f"Error processing rejection: {e}")

def process_interview(data, pinecone_index):
    """
    Process an email classified as 'interview'.
    
    Args:
        data (dict): Extracted data from the email
        pinecone_index: Pinecone index object
    """
    try:
        print("Processing interview...")
        logger.info("Processing interview...")
        # Extract required fields
        company_name = data.get('company_name')
        position_title = data.get('role')
        invitation_date_str = data.get('date')
        interview_round = data.get('interview_round', 'Round 1')  # Default to Round 1 if not specified
        
        # Validate required fields
        if not company_name or not position_title or not invitation_date_str:
            print("Missing required fields for interview")
            logger.error("Missing required fields for interview")
            return
        
        # Parse invitation date
        try:
            invitation_date = datetime.strptime(invitation_date_str, '%Y-%m-%d').date()
        except ValueError:
            print(f"Invalid date format: {invitation_date_str}")
            logger.error(f"Invalid date format: {invitation_date_str}")
            invitation_date = datetime.now().date()
        
        # Find matching application in Pinecone
        application_id = find_matching_application(
            pinecone_index,
            company_name,
            position_title,
            "interview",
            interview_round
        )
        
        if not application_id:
            print("No matching application found for interview")
            logger.error("No matching application found for interview")
            return
        
        # Check if interview already exists
        existing_interview = Interview.query.filter_by(
            company_name=company_name,
            position_title=position_title,
            round=interview_round
        ).first()
        
        if existing_interview:
            # Update existing interview
            existing_interview.invitation_date = invitation_date
            # Update other fields if available in the data
            db.session.commit()
            print(f"Updated existing interview record for application {application_id}")
            logger.info(f"Updated existing interview record for application {application_id}")
        else:
            # Create a new Interview record
            interview = Interview(
                company_name=company_name,
                position_title=position_title,
                round=interview_round,
                invitation_date=invitation_date,
                application_id=application_id
            )
            
            # Add to database
            db.session.add(interview)
            db.session.commit()
            
            print(f"Created new interview record for application {application_id}")
            logger.info(f"Created new interview record for application {application_id}")
            
            # Generate embedding for the interview and upsert into Pinecone
            summary_text = f"{company_name} | {position_title} | {interview_round}"
            embedding = generate_embedding(summary_text)
            
            if embedding:
                metadata = {
                    "application_id": application_id,
                    "company_name": company_name,
                    "position_title": position_title,
                    "interview_round": interview_round,
                    "type": "interview"
                }
                
                vector_id = f"interview_{company_name}_{position_title}_{interview_round}".replace(" ", "_")
                
                upsert_vector(pinecone_index, embedding, metadata, vector_id)
    
    except Exception as e:
        print(f"Error processing interview: {e}")
        logger.error(f"Error processing interview: {e}")

def process_offer(data, pinecone_index):
    """
    Process an email classified as 'offer'.
    
    Args:
        data (dict): Extracted data from the email
        pinecone_index: Pinecone index object
    """
    try:
        print("Processing offer...")
        logger.info("Processing offer...")
        # Extract required fields
        company_name = data.get('company_name')
        position_title = data.get('role')
        offer_date_str = data.get('date')
        location = data.get('location')
        
        # Validate required fields
        if not company_name or not position_title or not offer_date_str:
            print("Missing required fields for offer")
            logger.error("Missing required fields for offer")
            return
        
        # Parse offer date
        try:
            offer_date = datetime.strptime(offer_date_str, '%Y-%m-%d').date()
        except ValueError:
            print(f"Invalid date format: {offer_date_str}")
            logger.error(f"Invalid date format: {offer_date_str}")
            offer_date = datetime.now().date()
        
        # Find matching application in Pinecone using hierarchical search
        application_id = find_matching_application(pinecone_index, company_name, position_title, "offer")
        
        if not application_id:
            print("No matching application found for offer")
            logger.error("No matching application found for offer")
            return
        
        # Check if offer already exists
        existing_offer = Offer.query.filter_by(
            company_name=company_name,
            position_title=position_title
        ).first()
        
        if existing_offer:
            # Update existing offer
            existing_offer.offer_date = offer_date
            existing_offer.location = location or existing_offer.location
            # Update other fields if available in the data
            db.session.commit()
            print(f"Updated existing offer record for application {application_id}")
            logger.info(f"Updated existing offer record for application {application_id}")
        else:
            # Create a new Offer record
            offer = Offer(
                company_name=company_name,
                position_title=position_title,
                offer_date=offer_date,
                location=location,
                application_id=application_id
            )
            
            # Add to database
            db.session.add(offer)
            db.session.commit()
            
            print(f"Created new offer record for application {application_id}")
            logger.info(f"Created new offer record for application {application_id}")
            
            # Generate embedding for the offer and upsert into Pinecone
            summary_text = f"{company_name} | {position_title} | offer"
            embedding = generate_embedding(summary_text)
            
            if embedding:
                metadata = {
                    "application_id": application_id,
                    "company_name": company_name,
                    "position_title": position_title,
                    "type": "offer"
                }
                
                vector_id = f"offer_{company_name}_{position_title}".replace(" ", "_")
                
                upsert_vector(pinecone_index, embedding, metadata, vector_id)
    
    except Exception as e:
        print(f"Error processing offer: {e}")
        logger.error(f"Error processing offer: {e}")
