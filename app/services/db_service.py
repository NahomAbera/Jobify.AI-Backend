import logging
from datetime import datetime
from app import db
from app.models.models import User, Application, Rejection, Interview, Offer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_user(email, first_name=None, last_name=None, password=None):
    """
    Create a new user in the database.
    
    Args:
        email (str): User's email address
        first_name (str, optional): User's first name
        last_name (str, optional): User's last name
        password (str, optional): User's password
        
    Returns:
        User: The created user object or None if error
    """
    print(f"Creating new user with email: {email}")
    try:
        # Check if user already exists
        existing_user = User.query.filter_by(email_address=email).first()
        if existing_user:
            print(f"User with email {email} already exists")
            return existing_user
        
        # Create new user
        user = User(
            email_address=email,
            first_name=first_name,
            last_name=last_name,
            password=password,
            email_parse_start_date=datetime.now().date()
        )
        
        # Add to database
        db.session.add(user)
        db.session.commit()
        
        print(f"Successfully created new user with email: {email}")
        return user
    
    except Exception as e:
        print(f"Error creating user: {e}")
        logger.error(f"Error creating user: {e}")
        db.session.rollback()
        return None

def get_user(email):
    """
    Get a user from the database.
    
    Args:
        email (str): User's email address
        
    Returns:
        User: The user object or None if not found
    """
    print(f"Getting user with email: {email}")
    try:
        user = User.query.filter_by(email_address=email).first()
        if user:
            print(f"Found user with email: {email}")
        else:
            print(f"User with email {email} not found")
        return user
    
    except Exception as e:
        print(f"Error getting user: {e}")
        logger.error(f"Error getting user: {e}")
        return None

def create_application(user_email, company_name, position_title, application_date, location=None, job_id=None):
    """
    Create a new job application in the database.
    
    Args:
        user_email (str): User's email address
        company_name (str): Company name
        position_title (str): Position title
        application_date (date): Application date
        location (str, optional): Job location
        job_id (str, optional): Job ID
        
    Returns:
        Application: The created application object or None if error
    """
    print(f"Creating new application: {position_title} at {company_name} for user {user_email}")
    try:
        # Check if application already exists
        existing_application = Application.query.filter_by(
            user_email_id=user_email,
            company_name=company_name,
            position_title=position_title
        ).first()
        
        if existing_application:
            print(f"Application for {position_title} at {company_name} already exists with ID: {existing_application.application_id}")
            return existing_application
        
        # Create new application
        application = Application(
            user_email_id=user_email,
            company_name=company_name,
            position_title=position_title,
            application_date=application_date,
            location=location,
            job_id=job_id
        )
        
        # Add to database
        db.session.add(application)
        db.session.commit()
        
        print(f"Successfully created new application with ID: {application.application_id}")
        return application
    
    except Exception as e:
        print(f"Error creating application: {e}")
        logger.error(f"Error creating application: {e}")
        db.session.rollback()
        return None

def create_rejection(application_id, company_name, position_title, rejection_date):
    """
    Create a new rejection in the database.
    
    Args:
        application_id (int): Application ID
        company_name (str): Company name
        position_title (str): Position title
        rejection_date (date): Rejection date
        
    Returns:
        Rejection: The created rejection object or None if error
    """
    print(f"Creating new rejection for application ID: {application_id}")
    try:
        # Check if rejection already exists
        existing_rejection = Rejection.query.filter_by(application_id=application_id).first()
        
        if existing_rejection:
            print(f"Rejection for application ID {application_id} already exists")
            return existing_rejection
        
        # Create new rejection
        rejection = Rejection(
            application_id=application_id,
            company_name=company_name,
            position_title=position_title,
            rejection_date=rejection_date
        )
        
        # Add to database
        db.session.add(rejection)
        db.session.commit()
        
        print(f"Successfully created new rejection for application ID: {application_id}")
        return rejection
    
    except Exception as e:
        print(f"Error creating rejection: {e}")
        logger.error(f"Error creating rejection: {e}")
        db.session.rollback()
        return None

def create_interview(application_id, company_name, position_title, round_name, invitation_date, interview_link=None, deadline_date=None, completed=False):
    """
    Create a new interview in the database.
    
    Args:
        application_id (int): Application ID
        company_name (str): Company name
        position_title (str): Position title
        round_name (str): Interview round
        invitation_date (date): Invitation date
        interview_link (str, optional): Interview link
        deadline_date (date, optional): Deadline date
        completed (bool, optional): Whether the interview is completed
        
    Returns:
        Interview: The created interview object or None if error
    """
    print(f"Creating new interview for application ID: {application_id}, Round: {round_name}")
    try:
        # Check if interview already exists
        existing_interview = Interview.query.filter_by(
            application_id=application_id,
            round=round_name
        ).first()
        
        if existing_interview:
            print(f"Interview for application ID {application_id}, Round {round_name} already exists")
            return existing_interview
        
        # Create new interview
        interview = Interview(
            application_id=application_id,
            company_name=company_name,
            position_title=position_title,
            round=round_name,
            invitation_date=invitation_date,
            interview_link=interview_link,
            deadline_date=deadline_date,
            completed=completed
        )
        
        # Add to database
        db.session.add(interview)
        db.session.commit()
        
        print(f"Successfully created new interview for application ID: {application_id}, Round: {round_name}")
        return interview
    
    except Exception as e:
        print(f"Error creating interview: {e}")
        logger.error(f"Error creating interview: {e}")
        db.session.rollback()
        return None

def create_offer(application_id, company_name, position_title, offer_date, salary_comp=None, location=None, deadline_to_accept=None, accepted_or_declined=False):
    """
    Create a new offer in the database.
    
    Args:
        application_id (int): Application ID
        company_name (str): Company name
        position_title (str): Position title
        offer_date (date): Offer date
        salary_comp (str, optional): Salary compensation
        location (str, optional): Job location
        deadline_to_accept (date, optional): Deadline to accept
        accepted_or_declined (bool, optional): Whether the offer is accepted or declined
        
    Returns:
        Offer: The created offer object or None if error
    """
    print(f"Creating new offer for application ID: {application_id}")
    try:
        # Check if offer already exists
        existing_offer = Offer.query.filter_by(application_id=application_id).first()
        
        if existing_offer:
            print(f"Offer for application ID {application_id} already exists")
            return existing_offer
        
        # Create new offer
        offer = Offer(
            application_id=application_id,
            company_name=company_name,
            position_title=position_title,
            offer_date=offer_date,
            salary_comp=salary_comp,
            location=location,
            deadline_to_accept=deadline_to_accept,
            accepted_or_declined=accepted_or_declined
        )
        
        # Add to database
        db.session.add(offer)
        db.session.commit()
        
        print(f"Successfully created new offer for application ID: {application_id}")
        return offer
    
    except Exception as e:
        print(f"Error creating offer: {e}")
        logger.error(f"Error creating offer: {e}")
        db.session.rollback()
        return None

def get_application_by_id(application_id):
    """
    Get an application by ID.
    
    Args:
        application_id (int): Application ID
        
    Returns:
        Application: The application object or None if not found
    """
    print(f"Getting application with ID: {application_id}")
    try:
        application = Application.query.filter_by(application_id=application_id).first()
        if application:
            print(f"Found application with ID: {application_id}")
        else:
            print(f"Application with ID {application_id} not found")
        return application
    
    except Exception as e:
        print(f"Error getting application: {e}")
        logger.error(f"Error getting application: {e}")
        return None

def get_applications_by_user(user_email):
    """
    Get all applications for a user.
    
    Args:
        user_email (str): User's email address
        
    Returns:
        list: List of application objects
    """
    print(f"Getting applications for user: {user_email}")
    try:
        applications = Application.query.filter_by(user_email_id=user_email).all()
        print(f"Found {len(applications)} applications for user: {user_email}")
        return applications
    
    except Exception as e:
        print(f"Error getting applications for user: {e}")
        logger.error(f"Error getting applications for user: {e}")
        return []
