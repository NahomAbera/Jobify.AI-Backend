from flask import Blueprint, jsonify, request
from app import db
from app.models.models import User, Application, Rejection, Interview, Offer
from app.services.email_parser import start_email_parser
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Root endpoint"""
    return jsonify({"message": "Welcome to Jobify.AI API"})

@main_bp.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})

@main_bp.route('/applications', methods=['GET'])
def get_applications():
    """Get all applications for a user"""
    try:
        user_email = request.args.get('user_email', 'user@example.com')  # Default for testing
        
        applications = Application.query.filter_by(user_email_id=user_email).all()
        
        result = []
        for app in applications:
            app_data = {
                "application_id": app.application_id,
                "company_name": app.company_name,
                "position_title": app.position_title,
                "application_date": app.application_date.strftime('%Y-%m-%d'),
                "location": app.location,
                "job_id": app.job_id
            }
            result.append(app_data)
        
        return jsonify({"applications": result})
    
    except Exception as e:
        logger.error(f"Error getting applications: {e}")
        return jsonify({"error": str(e)}), 500

@main_bp.route('/rejections', methods=['GET'])
def get_rejections():
    """Get all rejections for a user"""
    try:
        user_email = request.args.get('user_email', 'user@example.com')  # Default for testing
        
        # Join with applications to filter by user_email
        rejections = db.session.query(Rejection).join(
            Application, Rejection.application_id == Application.application_id
        ).filter(
            Application.user_email_id == user_email
        ).all()
        
        result = []
        for rej in rejections:
            rej_data = {
                "application_id": rej.application_id,
                "company_name": rej.company_name,
                "position_title": rej.position_title,
                "rejection_date": rej.rejection_date.strftime('%Y-%m-%d')
            }
            result.append(rej_data)
        
        return jsonify({"rejections": result})
    
    except Exception as e:
        logger.error(f"Error getting rejections: {e}")
        return jsonify({"error": str(e)}), 500

@main_bp.route('/interviews', methods=['GET'])
def get_interviews():
    """Get all interviews for a user"""
    try:
        user_email = request.args.get('user_email', 'user@example.com')  # Default for testing
        
        # Join with applications to filter by user_email
        interviews = db.session.query(Interview).join(
            Application, Interview.application_id == Application.application_id
        ).filter(
            Application.user_email_id == user_email
        ).all()
        
        result = []
        for interview in interviews:
            interview_data = {
                "company_name": interview.company_name,
                "position_title": interview.position_title,
                "round": interview.round,
                "invitation_date": interview.invitation_date.strftime('%Y-%m-%d'),
                "interview_link": interview.interview_link,
                "deadline_date": interview.deadline_date.strftime('%Y-%m-%d') if interview.deadline_date else None,
                "completed": interview.completed,
                "application_id": interview.application_id
            }
            result.append(interview_data)
        
        return jsonify({"interviews": result})
    
    except Exception as e:
        logger.error(f"Error getting interviews: {e}")
        return jsonify({"error": str(e)}), 500

@main_bp.route('/offers', methods=['GET'])
def get_offers():
    """Get all offers for a user"""
    try:
        user_email = request.args.get('user_email', 'user@example.com')  # Default for testing
        
        # Join with applications to filter by user_email
        offers = db.session.query(Offer).join(
            Application, Offer.application_id == Application.application_id
        ).filter(
            Application.user_email_id == user_email
        ).all()
        
        result = []
        for offer in offers:
            offer_data = {
                "company_name": offer.company_name,
                "position_title": offer.position_title,
                "offer_date": offer.offer_date.strftime('%Y-%m-%d'),
                "salary_comp": offer.salary_comp,
                "location": offer.location,
                "deadline_to_accept": offer.deadline_to_accept.strftime('%Y-%m-%d') if offer.deadline_to_accept else None,
                "accepted_or_declined": offer.accepted_or_declined,
                "application_id": offer.application_id
            }
            result.append(offer_data)
        
        return jsonify({"offers": result})
    
    except Exception as e:
        logger.error(f"Error getting offers: {e}")
        return jsonify({"error": str(e)}), 500

@main_bp.route('/users', methods=['POST'])
def create_user():
    """Create a new user"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['email_address', 'first_name', 'last_name', 'password']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Check if user already exists
        existing_user = User.query.filter_by(email_address=data['email_address']).first()
        if existing_user:
            return jsonify({"error": "User already exists"}), 409
        
        # Create new user
        new_user = User(
            email_address=data['email_address'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            password=data['password']  # In a real app, this should be hashed
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({
            "message": "User created successfully",
            "user": {
                "email_address": new_user.email_address,
                "first_name": new_user.first_name,
                "last_name": new_user.last_name
            }
        }), 201
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating user: {e}")
        return jsonify({"error": str(e)}), 500

@main_bp.route('/parse-emails', methods=['POST'])
def parse_emails():
    """Manually trigger the email parsing process"""
    try:
        # Get user email from request
        data = request.get_json() or {}
        user_email = data.get('user_email')
        
        # Start the email parser for the specified user or all users
        start_email_parser(user_email)
        
        return jsonify({"message": "Email parsing process started"}), 202
    
    except Exception as e:
        logger.error(f"Error starting email parser: {e}")
        return jsonify({"error": str(e)}), 500

@main_bp.route('/user/email-parse-start-date', methods=['PUT'])
def update_email_parse_start_date():
    """Update a user's email parse start date"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or 'email_address' not in data or 'start_date' not in data:
            return jsonify({"error": "Missing required fields: email_address and start_date"}), 400
        
        email_address = data['email_address']
        start_date_str = data['start_date']
        
        # Parse the start date
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        # Find the user
        user = User.query.filter_by(email_address=email_address).first()
        if not user:
            return jsonify({"error": f"User not found: {email_address}"}), 404
        
        # Update the user's email_parse_start_date
        user.email_parse_start_date = start_date
        db.session.commit()
        
        return jsonify({
            "message": "Email parse start date updated successfully",
            "user": {
                "email_address": user.email_address,
                "email_parse_start_date": start_date.strftime('%Y-%m-%d')
            }
        })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating email parse start date: {e}")
        return jsonify({"error": str(e)}), 500
