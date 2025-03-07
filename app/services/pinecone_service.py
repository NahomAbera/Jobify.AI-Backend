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
    print("Initializing Pinecone...")
    print(f"PINECONE_API_KEY: {'*****' + os.getenv('PINECONE_API_KEY')[-4:] if os.getenv('PINECONE_API_KEY') else 'Not set'}")
    print(f"PINECONE_ENVIRONMENT: {os.getenv('PINECONE_ENVIRONMENT')}")
    print(f"PINECONE_INDEX_NAME: {os.getenv('PINECONE_INDEX_NAME', 'jobify-ai-index')}")
    
    try:
        pinecone.init(
            api_key=os.getenv('PINECONE_API_KEY'),
            environment=os.getenv('PINECONE_ENVIRONMENT')
        )
        print("Pinecone client initialized")
        
        # Get the index name from environment variables
        index_name = os.getenv('PINECONE_INDEX_NAME', 'jobify-ai-index')
        
        # Check if index exists, if not create it
        print(f"Checking if index '{index_name}' exists...")
        existing_indexes = pinecone.list_indexes()
        print(f"Existing indexes: {existing_indexes}")
        
        if index_name not in existing_indexes:
            print(f"Creating new index '{index_name}' with dimension 1536...")
            # Create index with dimension for text-embedding-3-large (1536)
            pinecone.create_index(
                name=index_name,
                dimension=1536,
                metric="cosine"
            )
            print(f"Created new Pinecone index: {index_name}")
            logger.info(f"Created new Pinecone index: {index_name}")
        else:
            print(f"Index '{index_name}' already exists")
        
        # Connect to the index
        print(f"Connecting to index '{index_name}'...")
        index = pinecone.Index(index_name)
        print(f"Successfully connected to index '{index_name}'")
        return index
    
    except Exception as e:
        print(f"Error initializing Pinecone: {e}")
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
    print(f"Upserting vector with ID: {id}")
    print(f"Vector metadata: {metadata}")
    
    try:
        index.upsert(
            vectors=[(id, vector, metadata)]
        )
        print(f"Successfully upserted vector with ID: {id}")
        logger.info(f"Successfully upserted vector with ID: {id}")
        return True
    
    except Exception as e:
        print(f"Error upserting vector: {e}")
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
    print(f"Querying Pinecone index with filter: {filter}, top_k: {top_k}")
    
    try:
        results = index.query(
            vector=vector,
            filter=filter,
            top_k=top_k,
            include_metadata=True
        )
        
        matches = results.get('matches', [])
        print(f"Query returned {len(matches)} matches")
        
        for i, match in enumerate(matches):
            print(f"Match {i+1}: ID={match['id']}, Score={match['score']}, Metadata={match['metadata']}")
        
        return matches
    
    except Exception as e:
        print(f"Error querying vector: {e}")
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
    print(f"Generating embedding for application: ID={application_id}, Company={company_name}, Position={position_title}")
    
    try:
        # Create a text representation of the application
        text = f"Application for {position_title} at {company_name} on {application_date}"
        
        # Generate embedding
        embedding = generate_embedding(text)
        
        if not embedding:
            print("Failed to generate embedding for application")
            logger.error("Failed to generate embedding for application")
            return False
        
        print(f"Successfully generated embedding for application (vector length: {len(embedding)})")
        
        # Create metadata
        metadata = {
            'type': 'application',
            'application_id': str(application_id),
            'company_name': company_name,
            'position_title': position_title,
            'application_date': str(application_date)
        }
        
        # Create a unique ID for the vector
        vector_id = f"application_{application_id}"
        
        # Upsert the vector
        print(f"Upserting application vector with ID: {vector_id}")
        return upsert_vector(index, embedding, metadata, vector_id)
    
    except Exception as e:
        print(f"Error generating and upserting application: {e}")
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
    print(f"Finding matching application: Company={company_name}, Position={position_title}, Status={status}")
    
    try:
        # Create a text representation for the query
        query_text = f"{position_title} at {company_name}"
        
        # Generate embedding for the query
        query_embedding = generate_embedding(query_text)
        
        if not query_embedding:
            print("Failed to generate embedding for query")
            logger.error("Failed to generate embedding for query")
            return None
        
        print(f"Successfully generated embedding for query (vector length: {len(query_embedding)})")
        
        # Filter for applications only
        filter_dict = {
            'type': 'application'
        }
        
        # Query Pinecone for similar vectors
        matches = query_vector(index, query_embedding, filter=filter_dict, top_k=5)
        
        if not matches:
            print("No matching applications found")
            return None
        
        # Find the best match based on company and position similarity
        best_match = None
        best_score = 0
        
        for match in matches:
            metadata = match.get('metadata', {})
            match_company = metadata.get('company_name', '').lower()
            match_position = metadata.get('position_title', '').lower()
            match_id = metadata.get('application_id')
            
            # Calculate a simple similarity score
            company_sim = similarity(company_name.lower(), match_company)
            position_sim = similarity(position_title.lower(), match_position)
            
            # Combined score with more weight on company name
            combined_score = (company_sim * 0.6) + (position_sim * 0.4)
            
            print(f"Potential match: ID={match_id}, Company={match_company} (sim={company_sim:.2f}), Position={match_position} (sim={position_sim:.2f}), Combined Score={combined_score:.2f}")
            
            if combined_score > best_score and combined_score > 0.7:  # Threshold for a good match
                best_score = combined_score
                best_match = match_id
        
        if best_match:
            print(f"Found best matching application with ID: {best_match}, Score: {best_score:.2f}")
            return int(best_match)
        else:
            print("No application met the similarity threshold")
            return None
    
    except Exception as e:
        print(f"Error finding matching application: {e}")
        logger.error(f"Error finding matching application: {e}")
        return None
