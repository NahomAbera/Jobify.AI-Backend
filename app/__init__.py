import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# Load environment variables
load_dotenv()

# Initialize SQLAlchemy
db = SQLAlchemy()

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)
    
    # Configure the app
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-for-development-only')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    
    # Register blueprints
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    # Initialize and start the email parser scheduler
    if os.getenv('FLASK_ENV') != 'testing':
        from app.services.email_parser import start_email_parser
        scheduler = BackgroundScheduler()
        interval_minutes = int(os.getenv('EMAIL_PARSER_INTERVAL_MINUTES', 30))
        
        # Register the email parser job to run at the specified interval
        scheduler.add_job(
            func=start_email_parser,
            args=[None],  # Pass None to process emails for all users
            trigger='interval',
            minutes=interval_minutes,
            id='email_parser_job',
            replace_existing=True
        )
        
        # Start the scheduler
        scheduler.start()
    
    return app
