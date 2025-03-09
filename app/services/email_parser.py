import os
import logging
import re
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

def start_email_parser(user_email=None):
    """
    Start the email parsing process. This function is called by the scheduler.
    
    Args:
        user_email (str, optional): The email address of the user to parse emails for.
                                   If None, parse for all users.
    """
    safe_print(f"Starting email parser for user: {user_email if user_email else 'all users'}")
    with current_app.app_context():
        logger.info("Starting email parser job")
        
        try:
            # Initialize Gmail service
            safe_print("Initializing Gmail service...")
            gmail_service = get_gmail_service()
            if not gmail_service:
                safe_print("Failed to initialize Gmail service")
                logger.error("Failed to initialize Gmail service")
                return
            safe_print("Gmail service initialized successfully")
            
            # Initialize Pinecone
            safe_print("Initializing Pinecone...")
            pinecone_index = None
            try:
                pinecone_index = init_pinecone()
                if not pinecone_index:
                    safe_print("Failed to initialize Pinecone, continuing without vectorization")
                    logger.warning("Failed to initialize Pinecone, continuing without vectorization")
                else:
                    safe_print("Pinecone initialized successfully")
            except Exception as e:
                safe_print(f"Pinecone initialization error: {str(e)}, continuing without vectorization")
                logger.warning(f"Pinecone initialization error: {e}, continuing without vectorization")
            
            # If user_email is provided, process emails for that user only
            if user_email:
                safe_print(f"Processing emails for specific user: {user_email}")
                process_user_emails(user_email, gmail_service, pinecone_index)
            else:
                safe_print("Processing emails for all users...")
                # Process emails for all users
                users = User.query.all()
                safe_print(f"Found {len(users)} users in the database")
                
                for user in users:
                    safe_print(f"Processing emails for user: {user.email_address}")
                    process_user_emails(user.email_address, gmail_service, pinecone_index)
            
            logger.info("Email parser job completed successfully")
        
        except Exception as e:
            safe_print(f"Error in email parser: {str(e)}")
            logger.error(f"Error in email parser job: {e}")

def process_user_emails(user_email, gmail_service, pinecone_index):
    """
    Process emails for a specific user.
    
    Args:
        user_email (str): The email address of the user
        gmail_service: Gmail API service object
        pinecone_index: Pinecone index object
    """
    # Capture the system start time when the function begins running
    system_start_time = datetime.now()
    system_start_time_str = system_start_time.isoformat()
    
    safe_print(f"Processing emails for user: {user_email}")
    logger.info(f"Processing emails for user: {user_email}")
    
    # Get the user from the database
    user = User.query.filter_by(email_address=user_email).first()
    
    # If user doesn't exist, create them
    if not user:
        safe_print(f"User {user_email} not found in database, creating new user")
        logger.info(f"User {user_email} not found, creating new user")
        user = User(email_address=user_email)
        db.session.add(user)
        db.session.commit()
        safe_print(f"Created new user: {user_email}")
    else:
        safe_print(f"Found existing user: {user_email}")
        logger.info(f"Found existing user: {user_email}")
    
    # Get the user's email parse start date
    start_date = user.email_parse_start_date
    safe_print(f"Email parse start date for user {user_email}: {start_date}")
    logger.info(f"Email parse start date for user {user_email}: {start_date}")
    
    # Get system start time to use as end date for this parsing session
    safe_print(f"System start time (end date for parsing): {system_start_time}")
    
    # Check if this is the first time we're processing emails for this user
    if not user.emails_parsed:
        safe_print(f"First-time email parsing for user {user_email} - processing all emails from {start_date} to {system_start_time}")
        logger.info(f"First-time email parsing for user {user_email} - processing all emails from {start_date} to {system_start_time}")
        
        # Fetch emails from start_date to system_start_time
        emails = fetch_new_emails(gmail_service, query=f"to:{user_email}", start_date=start_date)
        safe_print(f"Fetched {len(emails)} emails for first-time processing")
        logger.info(f"Fetched {len(emails)} emails for first-time processing")
        
        # Sort emails by date (oldest first)
        emails.sort(key=lambda x: x['date'])
        safe_print(f"Sorted {len(emails)} emails by date (oldest first)")
        logger.info(f"Sorted {len(emails)} emails by date (oldest first)")
        
        # Process each email
        for email in emails:
            try:
                subject = sanitize_text(email['subject'])
                safe_print(f"Processing email: {subject}")
                logger.info(f"Processing email: {subject}")
                process_email(email, pinecone_index, user_email)
            except UnicodeEncodeError as e:
                logger.error(f"Unicode error processing email: {e}")
                continue
            except Exception as e:
                logger.error(f"Error processing email: {e}")
                continue
        
        # Mark the user as having their emails parsed and update the parse date
        user.emails_parsed = True
        
        # Store the system start time with full precision
        # NOTE: If the database schema is still using Date instead of DateTime,
        # this will only store the date part. Consider adding a separate field for storing
        # the exact time if this precision is critical.
        user.email_parse_start_date = system_start_time
        
        # Additionally log the exact datetime for reference
        logger.info(f"Exact system start time (ISO format): {system_start_time_str}")
        
        db.session.commit()
        safe_print(f"Marked user {user_email} as having emails parsed, and updated start date to {system_start_time}")
        logger.info(f"Marked user {user_email} as having emails parsed, and updated start date to {system_start_time}")
    else:
        # Regular incremental processing - just get new emails since the last parse date
        safe_print(f"Incremental email parsing for user {user_email} - processing new emails from {start_date} to {system_start_time}")
        logger.info(f"Incremental email parsing for user {user_email} - processing new emails from {start_date} to {system_start_time}")
        
        # Fetch new emails from Gmail
        emails = fetch_new_emails(gmail_service, query=f"to:{user_email}", start_date=start_date)
        safe_print(f"Fetched {len(emails)} new emails for incremental processing")
        logger.info(f"Fetched {len(emails)} new emails for incremental processing")
        
        # Sort emails by date (oldest first)
        emails.sort(key=lambda x: x['date'])
        safe_print(f"Sorted {len(emails)} emails by date (oldest first)")
        logger.info(f"Sorted {len(emails)} emails by date (oldest first)")
        
        # Process each email
        for email in emails:
            try:
                subject = sanitize_text(email['subject'])
                safe_print(f"Processing email: {subject}")
                logger.info(f"Processing email: {subject}")
                process_email(email, pinecone_index, user_email)
            except UnicodeEncodeError as e:
                logger.error(f"Unicode error processing email: {e}")
                continue
            except Exception as e:
                logger.error(f"Error processing email: {e}")
                continue
        
        # Update the user's email parse start date to the system start time
        # This ensures that the next time the parser runs, it will only fetch emails from this point forward
        if emails:  # Only update if we actually processed emails
            safe_print(f"Updating email parse start date for user {user_email} from {start_date} to {system_start_time}")
            logger.info(f"Updating email parse start date for user {user_email} from {start_date} to {system_start_time}")
            
            # Store the system start time with full precision
            # NOTE: If the database schema is still using Date instead of DateTime,
            # this will only store the date part. Consider adding a separate field for storing
            # the exact time if this precision is critical.
            user.email_parse_start_date = system_start_time
            
            # Additionally log the exact datetime for reference
            logger.info(f"Exact system start time (ISO format): {system_start_time_str}")
            
            db.session.commit()
            safe_print(f"Updated email parse start date for user {user_email}")
        else:
            safe_print(f"No emails processed, keeping email parse start date as {start_date}")
    
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
        subject = sanitize_text(email['subject'])
        safe_print(f"Processing email: {subject}")
        logger.info(f"Processing email: {subject}")
        
        # Classify and extract information from the email
        safe_print("Classifying and extracting information from email...")
        logger.info("Classifying and extracting information from email...")
        extracted_data = classify_and_extract_email(email['body'], email['date'])
        
        if not extracted_data:
            safe_print("Email not classified as job-related")
            logger.info("Email not classified as job-related")
            return
        
        # Process the extracted data based on status
        status = extracted_data.get('status')
        
        if status == 'applied':
            safe_print("Processing job application...")
            logger.info("Processing job application...")
            process_application(extracted_data, pinecone_index, user_email)
        elif status == 'rejected':
            safe_print("Processing rejection...")
            logger.info("Processing rejection...")
            process_rejection(extracted_data, pinecone_index)
        elif status == 'interview':
            safe_print("Processing interview...")
            logger.info("Processing interview...")
            process_interview(extracted_data, pinecone_index)
        elif status == 'offer':
            safe_print("Processing offer...")
            logger.info("Processing offer...")
            process_offer(extracted_data, pinecone_index)
        else:
            safe_print(f"Unknown status: {status}")
            logger.warning(f"Unknown status: {status}")
    
    except UnicodeEncodeError as e:
        logger.error(f"Unicode error processing email: {e}")
    except Exception as e:
        safe_print(f"Error processing email: {str(e)}")
        logger.error(f"Error processing email: {e}")

def process_application(data, pinecone_index, user_email=None):
    """
    Process an application email, extracting relevant data and updating the database.
    
    Args:
        data (dict): Extracted data from the email
        pinecone_index: Pinecone index object (or None if unavailable)
        user_email (str, optional): The email of the user (defaults to None/environment variable)
    """
    try:
        safe_print("Processing job application...")
        logger.info("Processing job application...")
        
        # Verify this is actually a job application confirmation
        if not data.get('company_name') or not data.get('role'):
            safe_print("Missing company name or role, this may not be a valid application confirmation")
            logger.warning("Missing company name or role, this may not be a valid application confirmation")
            return
            
        # Double-check the status
        if data.get('status') != 'applied':
            safe_print(f"Unexpected status: {data.get('status')}, expected 'applied'")
            logger.warning(f"Unexpected status: {data.get('status')}, expected 'applied'")
            return
        
        # Extract required fields
        company_name = data.get('company_name')
        position_title = data.get('role')
        application_date_str = data.get('date')
        location = data.get('location')
        job_id = data.get('job_id')
        
        safe_print(f"Application details: {company_name} - {position_title}")
        
        # Get user email (use provided one or default)
        if not user_email:
            user_email = os.environ.get('DEFAULT_USER_EMAIL')
            if not user_email:
                safe_print("No user email provided and DEFAULT_USER_EMAIL not set")
                logger.error("No user email provided and DEFAULT_USER_EMAIL not set")
                return
        
        # Convert date string to date object
        if application_date_str:
            try:
                application_date = datetime.strptime(application_date_str, '%Y-%m-%d').date()
            except ValueError:
                try:
                    application_date = datetime.strptime(application_date_str, '%m/%d/%Y').date()
                except ValueError:
                    logger.error(f"Invalid date format: {application_date_str}")
                    application_date = datetime.now().date()
        else:
            application_date = datetime.now().date()
        
        # Create application record in database
        application = Application(
            user_email_id=user_email,
            company_name=company_name,
            position_title=position_title,
            application_date=application_date,
            location=location if location else None,
            job_id=job_id if job_id else None
        )
        
        # Add application to database
        db.session.add(application)
        db.session.commit()
        
        # Get the application ID after commit
        application_id = application.application_id
        
        safe_print(f"Created application record with ID: {application_id}")
        logger.info(f"Created application record with ID: {application_id}")
        
        # Generate embedding and upsert to Pinecone
        if pinecone_index:
            try:
                success = generate_and_upsert_application(
                    pinecone_index, 
                    application_id,
                    company_name, 
                    position_title, 
                    application_date
                )
                if not success:
                    safe_print("Failed to upsert application vector")
                    logger.error("Failed to upsert application vector")
            except Exception as e:
                safe_print(f"Failed to upsert application vector: {str(e)}")
                logger.error(f"Failed to upsert application vector: {e}")
    
    except Exception as e:
        db.session.rollback()
        safe_print(f"Error processing application: {str(e)}")
        logger.error(f"Error processing application: {e}")

def process_rejection(data, pinecone_index):
    """
    Process an email classified as 'rejected'.
    
    Args:
        data (dict): Extracted data from the email
        pinecone_index: Pinecone index object
    """
    try:
        safe_print("Processing rejection...")
        logger.info("Processing rejection...")
        # Extract required fields
        company_name = data.get('company_name')
        position_title = data.get('role')
        rejection_date_str = data.get('date')
        reason = data.get('reason')
        
        # Convert date string to date object
        if rejection_date_str:
            try:
                rejection_date = datetime.strptime(rejection_date_str, '%Y-%m-%d').date()
            except ValueError:
                try:
                    rejection_date = datetime.strptime(rejection_date_str, '%m/%d/%Y').date()
                except ValueError:
                    logger.error(f"Invalid date format: {rejection_date_str}")
                    rejection_date = datetime.now().date()
        else:
            rejection_date = datetime.now().date()
        
        # Find the matching application
        if pinecone_index:
            try:
                # Find the matching application in Pinecone
                from app.services.pinecone_service import find_matching_application
                application_id = find_matching_application(
                    pinecone_index, 
                    company_name, 
                    position_title, 
                    'rejected'
                )
                
                if application_id:
                    safe_print(f"Found matching application: {application_id}")
                    logger.info(f"Found matching application: {application_id}")
                    
                    # Update the application status
                    application = Application.query.filter_by(application_id=application_id).first()
                    if application:
                        application.status = 'rejected'
                        application.rejection_date = rejection_date
                        application.rejection_reason = reason
                        
                        db.session.commit()
                        safe_print(f"Updated application {application_id} status to 'rejected'")
                        logger.info(f"Updated application {application_id} status to 'rejected'")
                    else:
                        safe_print(f"Application {application_id} not found in database")
                        logger.error(f"Application {application_id} not found in database")
                else:
                    safe_print("No matching application found for rejection")
                    logger.warning("No matching application found for rejection")
            except Exception as e:
                safe_print(f"Error finding matching application: {str(e)}")
                logger.error(f"Error finding matching application: {e}")
        else:
            safe_print("Pinecone index not available, can't find matching application")
            logger.warning("Pinecone index not available, can't find matching application")
    
    except Exception as e:
        safe_print(f"Error processing rejection: {str(e)}")
        logger.error(f"Error processing rejection: {e}")

def process_interview(data, pinecone_index):
    """
    Process an email classified as 'interview'.
    
    Args:
        data (dict): Extracted data from the email
        pinecone_index: Pinecone index object
    """
    try:
        safe_print("Processing interview invitation...")
        logger.info("Processing interview invitation...")
        
        # Extract required fields
        company_name = data.get('company_name')
        position_title = data.get('role')
        interview_date_str = data.get('date')
        location = data.get('location')
        interview_type = data.get('interview_type')
        interview_round = data.get('round')
        
        # Standardize interview round format
        if interview_round:
            # Convert to lowercase for standardization
            round_lower = interview_round.lower()
            
            # Map to standard round values
            if 'oa' in round_lower or 'assessment' in round_lower or 'coding challenge' in round_lower:
                interview_round = 'OA'
            elif 'behavioral' in round_lower or 'hirevue' in round_lower or 'hr screen' in round_lower:
                interview_round = 'behavioral'
            elif 'superday' in round_lower or 'final' in round_lower or 'onsite' in round_lower or 'on-site' in round_lower:
                interview_round = 'final round'
            elif 'first' in round_lower or '1' in round_lower:
                interview_round = 'round 1'
            elif 'second' in round_lower or '2' in round_lower:
                interview_round = 'round 2'
            elif 'third' in round_lower or '3' in round_lower:
                interview_round = 'round 3'
            elif '4' in round_lower:
                interview_round = 'round 4'
            elif '5' in round_lower:
                interview_round = 'round 5'
            
            safe_print(f"Standardized interview round: {interview_round}")
            logger.info(f"Standardized interview round: {interview_round}")
        else:
            # Default to round 1 if not specified
            interview_round = 'round 1'
            safe_print(f"No round specified, defaulting to: {interview_round}")
            logger.info(f"No round specified, defaulting to: {interview_round}")
        
        # Convert date string to date object
        if interview_date_str:
            try:
                interview_date = datetime.strptime(interview_date_str, '%Y-%m-%d').date()
            except ValueError:
                try:
                    interview_date = datetime.strptime(interview_date_str, '%m/%d/%Y').date()
                except ValueError:
                    logger.error(f"Invalid date format: {interview_date_str}")
                    interview_date = datetime.now().date()
        else:
            interview_date = datetime.now().date()
        
        # Find the matching application
        if pinecone_index:
            try:
                # Find the matching application in Pinecone
                from app.services.pinecone_service import find_matching_application
                application_id = find_matching_application(
                    pinecone_index, 
                    company_name, 
                    position_title, 
                    'interview', 
                    interview_round
                )
                
                if application_id:
                    safe_print(f"Found matching application: {application_id}")
                    logger.info(f"Found matching application: {application_id}")
                    
                    # Update the application status
                    application = Application.query.filter_by(application_id=application_id).first()
                    if application:
                        # Update status
                        application.status = 'interview'
                        
                        # Create a new interview record
                        interview = Interview(
                            application_id=application_id,
                            interview_date=interview_date,
                            interview_type=interview_type,
                            interview_round=interview_round,
                            location=location
                        )
                        
                        db.session.add(interview)
                        db.session.commit()
                        
                        safe_print(f"Added interview for application {application_id}")
                        logger.info(f"Added interview for application {application_id}")
                    else:
                        safe_print(f"Application {application_id} not found in database")
                        logger.error(f"Application {application_id} not found in database")
                else:
                    safe_print("No matching application found for interview")
                    logger.warning("No matching application found for interview")
            except Exception as e:
                safe_print(f"Error finding matching application: {str(e)}")
                logger.error(f"Error finding matching application: {e}")
        else:
            safe_print("Pinecone index not available, can't find matching application")
            logger.warning("Pinecone index not available, can't find matching application")
    
    except Exception as e:
        safe_print(f"Error processing interview: {str(e)}")
        logger.error(f"Error processing interview: {e}")

def process_offer(data, pinecone_index):
    """
    Process an email classified as 'offer'.
    
    Args:
        data (dict): Extracted data from the email
        pinecone_index: Pinecone index object
    """
    try:
        safe_print("Processing job offer...")
        logger.info("Processing job offer...")
        
        # Extract required fields
        company_name = data.get('company_name')
        position_title = data.get('role')
        offer_date_str = data.get('date')
        salary = data.get('salary')
        location = data.get('location')
        deadline_str = data.get('deadline')
        
        # Convert date strings to date objects
        if offer_date_str:
            try:
                offer_date = datetime.strptime(offer_date_str, '%Y-%m-%d').date()
            except ValueError:
                try:
                    offer_date = datetime.strptime(offer_date_str, '%m/%d/%Y').date()
                except ValueError:
                    logger.error(f"Invalid date format: {offer_date_str}")
                    offer_date = datetime.now().date()
        else:
            offer_date = datetime.now().date()
        
        deadline = None
        if deadline_str:
            try:
                deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
            except ValueError:
                try:
                    deadline = datetime.strptime(deadline_str, '%m/%d/%Y').date()
                except ValueError:
                    logger.error(f"Invalid deadline format: {deadline_str}")
        
        # Find the matching application
        if pinecone_index:
            try:
                # Find the matching application in Pinecone
                from app.services.pinecone_service import find_matching_application
                application_id = find_matching_application(
                    pinecone_index, 
                    company_name, 
                    position_title, 
                    'offer'
                )
                
                if application_id:
                    safe_print(f"Found matching application: {application_id}")
                    logger.info(f"Found matching application: {application_id}")
                    
                    # Update the application
                    application = Application.query.filter_by(application_id=application_id).first()
                    if application:
                        # Update status and location if provided
                        application.status = 'offer'
                        if location:
                            application.location = location
                        
                        # Create a new offer record
                        offer = Offer(
                            application_id=application_id,
                            offer_date=offer_date,
                            salary=salary,
                            deadline=deadline
                        )
                        
                        db.session.add(offer)
                        db.session.commit()
                        
                        safe_print(f"Added offer for application {application_id}")
                        logger.info(f"Added offer for application {application_id}")
                    else:
                        safe_print(f"Application {application_id} not found in database")
                        logger.error(f"Application {application_id} not found in database")
                else:
                    safe_print("No matching application found for offer")
                    logger.warning("No matching application found for offer")
            except Exception as e:
                safe_print(f"Error finding matching application: {str(e)}")
                logger.error(f"Error finding matching application: {e}")
        else:
            safe_print("Pinecone index not available, can't find matching application")
            logger.warning("Pinecone index not available, can't find matching application")
    
    except Exception as e:
        safe_print(f"Error processing offer: {str(e)}")
        logger.error(f"Error processing offer: {e}")