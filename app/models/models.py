from datetime import datetime
from app import db

class User(db.Model):
    """User table for storing user information"""
    __tablename__ = 'user'
    
    email_address = db.Column(db.String(255), primary_key=True)
    first_name = db.Column(db.String(255))
    last_name = db.Column(db.String(255))
    password = db.Column(db.String(255))
    email_parse_start_date = db.Column(db.TIMESTAMP(timezone=True), default=datetime.now)
    emails_parsed = db.Column(db.Boolean, default=False)
    
    # Relationships
    applications = db.relationship('Application', backref='user', lazy=True)
    
    def __repr__(self):
        return f"<User {self.email_address}>"


class Application(db.Model):
    """Applications table for storing job application information"""
    __tablename__ = 'applications'
    
    application_id = db.Column(db.Integer, primary_key=True)
    user_email_id = db.Column(db.String(255), db.ForeignKey('user.email_address'), nullable=False)
    company_name = db.Column(db.String(255), nullable=False)
    position_title = db.Column(db.String(255), nullable=False)
    application_date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(255))
    job_id = db.Column(db.String(255))
    
    # Relationships
    rejection = db.relationship('Rejection', backref='application', uselist=False, lazy=True)
    interviews = db.relationship('Interview', backref='application', lazy=True)
    offer = db.relationship('Offer', backref='application', uselist=False, lazy=True)
    
    def __repr__(self):
        return f"<Application {self.application_id}: {self.company_name} - {self.position_title}>"


class Rejection(db.Model):
    """Rejections table for storing job rejection information"""
    __tablename__ = 'rejections'
    
    application_id = db.Column(db.Integer, db.ForeignKey('applications.application_id'), primary_key=True)
    company_name = db.Column(db.String(255), nullable=False)
    position_title = db.Column(db.String(255), nullable=False)
    rejection_date = db.Column(db.Date, nullable=False)
    
    def __repr__(self):
        return f"<Rejection for Application {self.application_id}>"


class Interview(db.Model):
    """Interviews table for storing job interview information"""
    __tablename__ = 'interviews'
    
    company_name = db.Column(db.String(255), primary_key=True)
    position_title = db.Column(db.String(255), primary_key=True)
    round = db.Column(db.String(100), primary_key=True)  # OA, Behavioral, Round 1, Round 2, etc.
    invitation_date = db.Column(db.Date, nullable=False)
    interview_link = db.Column(db.String(255))
    deadline_date = db.Column(db.Date)  # Interview scheduling deadline or interview date
    completed = db.Column(db.Boolean, default=False)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.application_id'), nullable=False)
    
    def __repr__(self):
        return f"<Interview {self.company_name} - {self.position_title} - {self.round}>"


class Offer(db.Model):
    """Offers table for storing job offer information"""
    __tablename__ = 'offers'
    
    company_name = db.Column(db.String(255), primary_key=True)
    position_title = db.Column(db.String(255), primary_key=True)
    offer_date = db.Column(db.Date, nullable=False)
    salary_comp = db.Column(db.String(255))
    location = db.Column(db.String(255))
    deadline_to_accept = db.Column(db.Date)
    accepted_or_declined = db.Column(db.Boolean, default=False)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.application_id'), nullable=False)
    
    def __repr__(self):
        return f"<Offer {self.company_name} - {self.position_title}>"
