import os
import logging
import pinecone
from app.services.openai_service import generate_embedding

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Pinecone client
def init_pinecone():
    """
    Initialize the Pinecone client with API key and environment.
    """
    try:
        pinecone.init(
            api_key=os.getenv('PINECONE_API_KEY'),
            environment=os.getenv('PINECONE_ENVIRONMENT')
        )
        
        # Get the index name from environment variables
        index_name = os.getenv('PINECONE_INDEX_NAME', 'jobify-ai-index')
        
        # Check if index exists, if not create it
        if index_name not in pinecone.list_indexes():
            # Create index with dimension for text-embedding-3-large (1536)
            pinecone.create_index(
                name=index_name,
                dimension=1536,
                metric="cosine"
            )
            logger.info(f"Created new Pinecone index: {index_name}")
        
        # Connect to the index
        index = pinecone.Index(index_name)
        return index
    
    except Exception as e:
        logger.error(f"Error initializing Pinecone: {e}")
        return None

def upsert_vector(index, vector, metadata, id):
    """
    Upsert a vector into the Pinecone index.
    
    Args:
        index: Pinecone index object
        vector (list): The embedding vector
        metadata (dict): Metadata to store with the vector
        id (str): Unique identifier for the vector
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        index.upsert(vectors=[(id, vector, metadata)])
        logger.info(f"Upserted vector with ID: {id}")
        return True
    
    except Exception as e:
        logger.error(f"Error upserting vector: {e}")
        return False

def query_vector(index, vector, filter=None, top_k=1):
    """
    Query the Pinecone index for similar vectors.
    
    Args:
        index: Pinecone index object
        vector (list): The query embedding vector
        filter (dict, optional): Filter for the query
        top_k (int): Number of results to return
        
    Returns:
        list: List of matches
    """
    try:
        results = index.query(
            vector=vector,
            filter=filter,
            top_k=top_k,
            include_metadata=True
        )
        
        return results.matches
    
    except Exception as e:
        logger.error(f"Error querying vector: {e}")
        return []

def generate_and_upsert_application(index, application_id, company_name, position_title, application_date):
    """
    Generate an embedding for an application and upsert it into Pinecone.
    
    Args:
        index: Pinecone index object
        application_id (int): The application ID
        company_name (str): The company name
        position_title (str): The position title
        application_date (str): The application date
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Generate a summary text for the application
        summary_text = f"{company_name} | {position_title} | {application_date}"
        
        # Generate embedding for the summary text
        embedding = generate_embedding(summary_text)
        
        if not embedding:
            logger.error("Failed to generate embedding")
            return False
        
        # Prepare metadata
        metadata = {
            "application_id": application_id,
            "company_name": company_name,
            "position_title": position_title,
            "application_date": application_date,
            "type": "application"
        }
        
        # Generate a unique ID for the vector
        vector_id = f"application_{application_id}"
        
        # Upsert the vector
        return upsert_vector(index, embedding, metadata, vector_id)
    
    except Exception as e:
        logger.error(f"Error generating and upserting application: {e}")
        return False

def find_matching_application(index, company_name, position_title, status, interview_round=None):
    """
    Find a matching application in Pinecone based on the email data.
    
    Args:
        index: Pinecone index object
        company_name (str): The company name
        position_title (str): The position title
        status (str): The status of the email (rejected, interview, offer)
        interview_round (str, optional): The interview round (for interview status)
        
    Returns:
        int or None: The matching application ID or None if no match found
    """
    try:
        # Generate a query text based on the email data
        query_text = f"{company_name} | {position_title}"
        if status == "interview" and interview_round:
            query_text += f" | {interview_round}"
        
        # Generate embedding for the query text
        query_embedding = generate_embedding(query_text)
        
        if not query_embedding:
            logger.error("Failed to generate query embedding")
            return None
        
        # Define filters based on status
        if status == "offer":
            # Hierarchical search for offers
            # First, try to find in offers
            offer_filter = {"type": "offer"}
            offer_matches = query_vector(index, query_embedding, filter=offer_filter)
            
            if offer_matches and len(offer_matches) > 0 and offer_matches[0].score > 0.7:
                return offer_matches[0].metadata.get("application_id")
            
            # If no match in offers, try interviews
            interview_filter = {"type": "interview"}
            interview_matches = query_vector(index, query_embedding, filter=interview_filter)
            
            if interview_matches and len(interview_matches) > 0 and interview_matches[0].score > 0.7:
                return interview_matches[0].metadata.get("application_id")
            
            # If still no match, try applications
            application_filter = {"type": "application"}
            application_matches = query_vector(index, query_embedding, filter=application_filter)
            
            if application_matches and len(application_matches) > 0 and application_matches[0].score > 0.7:
                return application_matches[0].metadata.get("application_id")
        
        elif status == "interview":
            # For interviews, first check if there's a match with the same round
            if interview_round:
                interview_filter = {
                    "type": "interview",
                    "company_name": company_name,
                    "position_title": position_title,
                    "interview_round": interview_round
                }
                interview_matches = query_vector(index, query_embedding, filter=interview_filter)
                
                if interview_matches and len(interview_matches) > 0 and interview_matches[0].score > 0.7:
                    return interview_matches[0].metadata.get("application_id")
            
            # If no match with the same round, search in applications
            application_filter = {"type": "application"}
            application_matches = query_vector(index, query_embedding, filter=application_filter)
            
            if application_matches and len(application_matches) > 0 and application_matches[0].score > 0.7:
                return application_matches[0].metadata.get("application_id")
        
        elif status == "rejected":
            # For rejections, search in applications
            application_filter = {"type": "application"}
            application_matches = query_vector(index, query_embedding, filter=application_filter)
            
            if application_matches and len(application_matches) > 0 and application_matches[0].score > 0.7:
                return application_matches[0].metadata.get("application_id")
        
        return None
    
    except Exception as e:
        logger.error(f"Error finding matching application: {e}")
        return None
