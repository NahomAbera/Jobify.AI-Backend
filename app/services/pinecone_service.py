import os
import logging
from pinecone import Pinecone, ServerlessSpec
from app.services.openai_service import generate_embedding

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def similarity(str1, str2):
    """
    Calculate a simple similarity score between two strings.
    
    Args:
        str1 (str): First string
        str2 (str): Second string
        
    Returns:
        float: Similarity score between 0 and 1
    """
    # Convert to lowercase for comparison
    str1 = str1.lower()
    str2 = str2.lower()
    
    # Check if one string contains the other
    if str1 in str2 or str2 in str1:
        return 0.9
    
    # Check common words
    words1 = set(str1.split())
    words2 = set(str2.split())
    common_words = words1.intersection(words2)
    
    if not words1 or not words2:
        return 0.0
    
    # Calculate Jaccard similarity
    return len(common_words) / max(1, len(words1.union(words2)))

# Initialize Pinecone client
def init_pinecone():
    """
    Initialize the Pinecone client with API key and environment.
    """
    print("Initializing Pinecone...")
    print(f"PINECONE_API_KEY: {'*****' + os.getenv('PINECONE_API_KEY')[-4:] if os.getenv('PINECONE_API_KEY') else 'Not set'}")
    print(f"PINECONE_ENVIRONMENT: {os.getenv('PINECONE_ENVIRONMENT')}")
    print(f"PINECONE_INDEX_NAME: {os.getenv('PINECONE_INDEX_NAME', 'jobify-ai-index')}")
    print(f"PINECONE_HOST_URL: {os.getenv('PINECONE_HOST_URL')}")
    
    try:
        # Get configuration from environment variables
        api_key = os.getenv('PINECONE_API_KEY')
        index_name = os.getenv('PINECONE_INDEX_NAME', 'jobify-ai-index')
        
        if not api_key:
            print("Pinecone API key not set")
            logger.error("Pinecone API key not set")
            return None
            
        # Initialize Pinecone with v6.0.0 API
        print("Initializing Pinecone with new API format (v6.0.0)...")
        pc = Pinecone(api_key=api_key)
        print("Pinecone client initialized")
        
        # List indexes to check what's available
        try:
            indexes = pc.list_indexes()
            print(f"Available indexes: {indexes}")
        except Exception as e:
            print(f"Error listing indexes: {e}")
            logger.error(f"Error listing indexes: {e}")
        
        # Try different index name formats
        index_variants = [
            index_name,  # Original name from env
            index_name.replace('-', '_'),  # Replace hyphens with underscores
            index_name.split('-')[0]  # First part only
        ]
        
        # Extract from host URL if available
        host_url = os.getenv('PINECONE_HOST_URL')
        if host_url:
            try:
                extracted_name = host_url.split('//')[1].split('.')[0]
                if extracted_name not in index_variants:
                    index_variants.append(extracted_name)
                print(f"Extracted index name from host URL: {extracted_name}")
            except Exception as e:
                print(f"Couldn't extract index name from host URL: {e}")
        
        # Try each index variant
        for idx_name in index_variants:
            print(f"Trying to connect to index '{idx_name}'...")
            try:
                index = pc.Index(idx_name)
                try:
                    # Test the connection
                    stats = index.describe_index_stats()
                    print(f"Successfully connected to index '{idx_name}'")
                    print(f"Index stats: {stats}")
                    return index
                except Exception as e:
                    print(f"Error getting stats for '{idx_name}': {e}")
                    # Continue to next variant
            except Exception as e:
                print(f"Error connecting to index '{idx_name}': {e}")
        
        # If we get here, try one more approach - create the index
        try:
            print(f"Attempting to create index '{index_name}' with dimension 1536...")
            pc.create_index(
                name=index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
            print(f"Successfully created index '{index_name}'")
            # Connect to the new index
            index = pc.Index(index_name)
            return index
        except Exception as e:
            print(f"Error creating index: {e}")
            logger.error(f"Error creating index: {e}")
        
        print("Could not connect to any index. Email parsing will continue without vectorization.")
        return None
    
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
        # Format for v6.0.0 API
        response = index.upsert(
            vectors=[
                {
                    "id": id,
                    "values": vector,
                    "metadata": metadata
                }
            ]
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
        # Format for v6.0.0 API
        response = index.query(
            vector=vector,
            filter=filter,
            top_k=top_k,
            include_metadata=True
        )
        
        matches = response.get('matches', [])
        print(f"Query returned {len(matches)} matches")
        
        for i, match in enumerate(matches):
            print(f"Match {i+1}: ID={match.id}, Score={match.score}, Metadata={match.metadata}")
        
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
            metadata = match.metadata if hasattr(match, 'metadata') else match.get('metadata', {})
            match_company = metadata.get('company_name', '').lower()
            match_position = metadata.get('position_title', '').lower()
            match_id = metadata.get('application_id')
            match_score = match.score if hasattr(match, 'score') else match.get('score', 0)
            
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
