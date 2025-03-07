import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
import datetime

# Load environment variables
load_dotenv()
print("Environment variables loaded from .env file")
print(f"DATABASE_URL: {os.getenv('DATABASE_URL')}")
print(f"FLASK_APP: {os.getenv('FLASK_APP')}")
print(f"FLASK_ENV: {os.getenv('FLASK_ENV')}")
print(f"DEFAULT_USER_EMAIL: {os.getenv('DEFAULT_USER_EMAIL')}")

# Initialize SQLAlchemy
db = SQLAlchemy()
print("SQLAlchemy initialized")

def create_app():
    """
    Create and configure the Flask application.
    """
    print("Creating Flask application...")
    app = Flask(__name__)
    
    # Load environment variables from .env file
    load_dotenv()
    print("Environment variables loaded from .env file")
    
    # Print environment variables for debugging
    print(f"DATABASE_URL: {os.getenv('DATABASE_URL')}")
    print(f"FLASK_APP: {os.getenv('FLASK_APP')}")
    print(f"FLASK_ENV: {os.getenv('FLASK_ENV')}")
    print(f"SECRET_KEY: {'*****' if os.getenv('SECRET_KEY') else 'Not set'}")
    print(f"DEFAULT_USER_EMAIL: {os.getenv('DEFAULT_USER_EMAIL')}")
    print(f"EMAIL_PARSER_INTERVAL_MINUTES: {os.getenv('EMAIL_PARSER_INTERVAL_MINUTES')}")
    
    # Configure the application
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    print(f"App configured with DATABASE_URL: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    # Initialize extensions
    print("Initializing database...")
    db.init_app(app)
    print("Database initialized with app")
    
    # Register blueprints
    print("Registering blueprints...")
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)
    print("Blueprints registered")
    
    # Create database tables
    with app.app_context():
        print("Creating database tables if they don't exist...")
        try:
            db.create_all()
            print("Database tables created successfully")
            
            # Create default user if DEFAULT_USER_EMAIL is set
            default_email = os.environ.get('DEFAULT_USER_EMAIL')
            if default_email:
                print(f"Default user email found: {default_email}")
                
                # Check if user already exists
                from app.models.models import User
                user = User.query.filter_by(email_address=default_email).first()
                
                if not user:
                    print(f"Creating default user with email: {default_email}")
                    # Create new user with default email
                    user = User(
                        email_address=default_email,
                        email_parse_start_date=datetime.now().date()
                    )
                    db.session.add(user)
                    db.session.commit()
                    print(f"Default user created successfully with email: {default_email}")
                else:
                    print(f"Default user already exists with email: {default_email}")
            
        except Exception as e:
            print(f"Error creating database tables: {e}")
            print("WARNING: Application will run with limited functionality due to database connection issues")
            
            # Add a route to show database connection error
            @app.route('/db-status')
            def db_status():
                return """
                <html>
                    <head>
                        <title>Database Connection Status</title>
                        <style>
                            body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
                            h1 { color: #333; }
                            .container { max-width: 800px; margin: 0 auto; }
                            .card { border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
                            .error { color: #e74c3c; }
                            .success { color: #2ecc71; }
                            pre { background: #f8f8f8; padding: 10px; border-radius: 5px; overflow-x: auto; }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>Database Connection Status</h1>
                            <div class="card">
                                <h2>Status</h2>
                                <p class="error">Database connection error: {}</p>
                                <p>The application is running with limited functionality.</p>
                            </div>
                            
                            <div class="card">
                                <h2>Connection Details</h2>
                                <pre>
DATABASE_URL: {}
                                </pre>
                            </div>
                            
                            <div class="card">
                                <h2>Troubleshooting Steps</h2>
                                <ol>
                                    <li>Check that your database credentials are correct in the .env file</li>
                                    <li>Verify that your Supabase database is running and accessible</li>
                                    <li>Check your network connection to the database server</li>
                                </ol>
                            </div>
                        </div>
                    </body>
                </html>
                """.format(str(e), os.getenv('DATABASE_URL', 'Not set'))
    
    # Initialize scheduler
    print("Initializing scheduler...")
    if os.environ.get('FLASK_ENV') != 'testing':
        print("Initializing email parser scheduler...")
        from app.services.email_parser import start_email_parser
        
        # Schedule email parser to run at regular intervals
        interval_minutes = int(os.getenv('EMAIL_PARSER_INTERVAL_MINUTES', '30'))
        print(f"Email parser will run every {interval_minutes} minutes for user: {os.getenv('DEFAULT_USER_EMAIL')}")
        
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': ThreadPoolExecutor(20),
            'processpool': ProcessPoolExecutor(5)
        }
        job_defaults = {
            'coalesce': False,
            'max_instances': 3
        }
        scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults)
        scheduler.start()
        
        @scheduler.scheduled_job('interval', minutes=interval_minutes)
        def parse_emails():
            print(f"Running scheduled email parser at {datetime.now()}")
            with app.app_context():
                try:
                    start_email_parser(os.getenv('DEFAULT_USER_EMAIL'))
                    print("Email parser completed successfully")
                except Exception as e:
                    print(f"Error running email parser: {e}")
        
        print("Email parser scheduler started")
    
    # Add a home route that works without database
    @app.route('/')
    def home():
        return """
        <html>
            <head>
                <title>Jobify.AI Backend</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
                    h1 { color: #333; }
                    .container { max-width: 800px; margin: 0 auto; }
                    .card { border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
                    .button { 
                        display: inline-block; 
                        background-color: #4CAF50; 
                        color: white; 
                        padding: 10px 20px; 
                        text-align: center; 
                        text-decoration: none; 
                        font-size: 16px; 
                        border-radius: 5px; 
                        margin: 10px 0; 
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Jobify.AI Backend</h1>
                    <div class="card">
                        <h2>Status</h2>
                        <p>The Jobify.AI backend is running.</p>
                        <a href="/db-status" class="button">Check Database Status</a>
                    </div>
                </div>
            </body>
        </html>
        """
    
    print("Flask application created successfully")
    return app
