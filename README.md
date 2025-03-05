# Jobify.AI Backend

A Flask backend for a job application tracking system that automatically parses emails, classifies them using OpenAI's ChatGPT 4o-mini, and stores the data in PostgreSQL and Pinecone vector database.

## Features

- **Email Parsing Pipeline**: Automatically fetches and processes job-related emails from Gmail
- **AI-Powered Classification**: Uses OpenAI's ChatGPT 4o-mini to classify emails and extract relevant information
- **Vector Database Integration**: Uses Pinecone to store and search for similar job applications
- **PostgreSQL Database**: Stores all job application data in a structured format
- **RESTful API**: Provides endpoints to interact with the application data

## System Architecture

The system consists of the following components:

1. **Flask Web Server**: Handles HTTP requests and serves the API endpoints
2. **Email Parser**: Runs as a scheduled task to fetch and process new emails
3. **OpenAI Integration**: Classifies emails and extracts structured data
4. **Pinecone Vector Database**: Stores embeddings for semantic search
5. **PostgreSQL Database**: Stores structured data in relational tables

## Database Schema

- **User Table**: Stores user information
- **Applications Table**: Stores job application data
- **Rejections Table**: Stores rejection information
- **Interviews Table**: Stores interview information
- **Offers Table**: Stores job offer information

## Setup Instructions

### Prerequisites

- Python 3.9+
- PostgreSQL
- Pinecone account
- OpenAI API key
- Gmail API credentials

### Environment Variables

Create a `.env` file in the root directory with the following variables:

```
# Database Configuration
DATABASE_URL=postgresql://username:password@hostname:port/database_name

# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key

# Pinecone Configuration
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENVIRONMENT=your_pinecone_environment
PINECONE_INDEX_NAME=jobify-ai-index

# Gmail API Configuration
GMAIL_CREDENTIALS_PATH=path/to/credentials.json
GMAIL_TOKEN_PATH=path/to/token.json

# Flask Configuration
FLASK_APP=app
FLASK_ENV=development
SECRET_KEY=your_secret_key

# Email Parser Configuration
EMAIL_PARSER_INTERVAL_MINUTES=30
```

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/jobify-ai-backend.git
   cd jobify-ai-backend
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up Gmail API credentials:
   - Create a project in the Google Cloud Console
   - Enable the Gmail API
   - Create OAuth 2.0 credentials
   - Download the credentials JSON file and save it to the path specified in GMAIL_CREDENTIALS_PATH

4. Run the application:
   ```
   python run.py
   ```

### Docker Deployment

1. Build and run with Docker Compose:
   ```
   docker-compose up -d
   ```

## API Endpoints

- `GET /`: Welcome message
- `GET /health`: Health check
- `GET /applications`: Get all applications for a user
- `GET /rejections`: Get all rejections for a user
- `GET /interviews`: Get all interviews for a user
- `GET /offers`: Get all offers for a user
- `POST /users`: Create a new user
- `POST /parse-emails`: Manually trigger the email parsing process (optionally for a specific user)
- `PUT /user/email-parse-start-date`: Update a user's email parse start date

## Email Parser

The email parser runs as a scheduled task and performs the following steps:

1. Fetches new emails from Gmail
2. Cleans HTML content using BeautifulSoup
3. Sends the cleaned text to OpenAI for classification and extraction
4. Processes the extracted data based on the status:
   - For "applied" emails: Creates a new application record and stores its embedding in Pinecone
   - For "rejected" emails: Finds the matching application and creates a rejection record
   - For "interview" emails: Finds or creates an interview record and updates Pinecone
   - For "offer" emails: Finds or creates an offer record and updates Pinecone

## Email Parse Start Date Feature

Each user can set a custom start date for email parsing. This feature allows users to:

1. Specify the date from which the system should start parsing their emails
2. Update this date at any time through the API
3. Control which emails are processed by the system

The email parser will only fetch and process emails sent on or after the user's specified start date. This helps prevent processing old, irrelevant emails and allows users to focus on recent job applications.

### Using the Email Parse Start Date API

To update a user's email parse start date, send a PUT request to `/user/email-parse-start-date` with the following JSON payload:

```json
{
  "email_address": "user@example.com",
  "start_date": "2024-01-01"
}
```

The response will confirm the update:

```json
{
  "message": "Email parse start date updated successfully",
  "user": {
    "email_address": "user@example.com",
    "email_parse_start_date": "2024-01-01"
  }
}
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
