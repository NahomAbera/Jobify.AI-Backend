import os
import json
import time
import random
import base64
import re
from datetime import datetime, timezone, date
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

import openai
import pinecone
import logging
from dateutil import parser as date_parser

from sqlalchemy import (create_engine, Column, String, Integer, Date, DateTime,
                        Boolean, ForeignKey, func)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# ============================================================
# 1. ENV & GLOBAL INITIALISATION
# ============================================================
# Try to locate .env relative to CWD; if not found, fall back to repo root.
dotenv_path = find_dotenv(filename=".env", usecwd=True)
if not dotenv_path:
    # fall back to parent of current file (repo root)
    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path, override=False)

# ---------------- Logging Setup ----------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
logger.debug("Loaded .env from %s", dotenv_path)

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENV = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = 1536  # text-embedding-3-small dimension

DATABASE_URL = os.getenv("DATABASE_URL")
DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "default@example.com")

GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH")
GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "token.json")

# Gmail OAuth scope – readonly is sufficient for parsing
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# ============================================================
# 2. DATABASE SET‑UP (SQLAlchemy)
# ============================================================
Base = declarative_base()


class User(Base):
    __tablename__ = "user"
    email_address = Column(String(255), primary_key=True)
    first_name = Column(String(255))
    last_name = Column(String(255))
    password = Column(String(255))  # hashed password expected
    email_parse_start_date = Column(
            DateTime(timezone=True),
            default=lambda: datetime.fromtimestamp(0, tz=timezone.utc),
        )
    # relationships
    applications = relationship("Application", back_populates="user")


class Application(Base):
    __tablename__ = "applications"
    application_id = Column(Integer, primary_key=True, autoincrement=True)
    user_email_id = Column(String(255), ForeignKey("user.email_address"))
    company_name = Column(String(255))
    position_title = Column(String(255))
    application_date = Column(Date)

    user = relationship("User", back_populates="applications")
    interviews = relationship("Interview", back_populates="application")
    offers = relationship("Offer", back_populates="application")
    rejection = relationship("Rejection", uselist=False, back_populates="application")


class Rejection(Base):
    __tablename__ = "rejections"
    application_id = Column(Integer, ForeignKey("applications.application_id"), primary_key=True)
    company_name = Column(String(255))
    position_title = Column(String(255))
    rejection_date = Column(Date)

    application = relationship("Application", back_populates="rejection")


class Interview(Base):
    __tablename__ = "interviews"
    id = Column(Integer, primary_key=True, autoincrement=True)  # surrogate key
    company_name = Column(String(255))
    position_title = Column(String(255))
    round = Column(String(100))
    invitation_date = Column(Date)
    interview_link = Column(String(255))
    deadline_date = Column(Date)
    completed = Column(Boolean, default=False)
    application_id = Column(Integer, ForeignKey("applications.application_id"))

    application = relationship("Application", back_populates="interviews")


class Offer(Base):
    __tablename__ = "offers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255))
    position_title = Column(String(255))
    offer_date = Column(Date)
    salary_comp = Column(String(255))
    location = Column(String(255))
    deadline_to_accept = Column(Date)
    accepted_or_declined = Column(Boolean)
    application_id = Column(Integer, ForeignKey("applications.application_id"))

    application = relationship("Application", back_populates="offers")


logger.info("Connecting to database ...")
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# Create tables if they do not exist (idempotent)
Base.metadata.create_all(bind=engine)
logger.debug("Database tables verified/created")

# ============================================================
# 3. GENERAL UTILS
# ============================================================

def exponential_backoff_retry(max_attempts: int = 5, base_delay: float = 1.0):
    """Decorator for retrying a function with exp back‑off + jitter."""

    def decorator(fn: Callable):
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    delay = base_delay * (2 ** (attempt - 1))
                    jitter = random.uniform(0, delay * 0.1)
                    time.sleep(delay + jitter)
        return wrapper
    return decorator


def sanitize_string(value: Optional[str]) -> str:
    return value.replace("/", "_").replace("\\", "_") if value else "Unknown"


def clean_html_content(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script", "img"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def clean_email_content(content: str) -> str:
    return content.strip()


def truncate_email_body(body: str, max_len: int = 3000) -> str:
    return body[:max_len]


# ---------------- Date Parsing Helper ----------------

def parse_date_safe(raw_date: Optional[str]) -> Optional[date]:
    """Parse a date string from arbitrary formats to a `date` object.

    1. Try `datetime.fromisoformat` (fast path for ISO strings).
    2. Fallback to `dateutil.parser.parse` for non‑standard formats (e.g. 'August 17, 2024').
    3. On failure, returns None and logs a warning.
    """
    if not raw_date:
        return None
    if isinstance(raw_date, (datetime, date)):
        return raw_date.date() if isinstance(raw_date, datetime) else raw_date
    try:
        return datetime.fromisoformat(raw_date).date()
    except (ValueError, TypeError):
        try:
            return date_parser.parse(raw_date).date()
        except (ValueError, TypeError) as e:
            logger.warning("Could not parse date '%s': %s", raw_date, e)
            return None

# ============================================================
# 4. GMAIL HELPERS
# ============================================================

def authenticate_gmail():
    logger.info("Authenticating Gmail ...")
    creds = None
    if os.path.exists(GMAIL_TOKEN_PATH):
        logger.debug("Found existing Gmail token file %s", GMAIL_TOKEN_PATH)
        import pickle
        with open(GMAIL_TOKEN_PATH, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS_PATH, GMAIL_SCOPES)
            # Attempt console-based flow; if unavailable, fallback to local_server without browser
            if hasattr(flow, "run_console"):
                logger.info("Running console OAuth flow – copy URL to browser if prompted")
                creds = flow.run_console()
            else:
                logger.info("Running local_server OAuth flow (no browser auto‑open)")
                creds = flow.run_local_server(port=0, open_browser=False)
        import pickle
        with open(GMAIL_TOKEN_PATH, "wb") as token:
            pickle.dump(creds, token)

    logger.info("Gmail authenticated successfully")
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return service


def get_last_update_timestamp(session, user_email: str) -> int:
    user = session.query(User).filter_by(email_address=user_email).one_or_none()
    if not user:
        # create user with epoch start
        user = User(email_address=user_email, email_parse_start_date=datetime.fromtimestamp(0, tz=timezone.utc))
        session.add(user)
        session.commit()
    return int(user.email_parse_start_date.replace(tzinfo=timezone.utc).timestamp())


def update_parse_timestamp(session, user_email: str, ts_epoch: int):
    iso = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
    session.query(User).filter_by(email_address=user_email).update({"email_parse_start_date": iso})
    session.commit()


@exponential_backoff_retry()
def list_gmail_messages(service, last_ts: int, current_ts: int) -> List[Dict[str, Any]]:
    logger.debug("Listing Gmail messages between %s and %s", last_ts, current_ts)
    query = f"after:{last_ts} before:{current_ts}"
    messages = []
    next_page_token = None
    page = 0
    while True:
        page += 1
        start_page = time.time()
        logger.info("[Gmail] Requesting page %d …", page)
        response = service.users().messages().list(
            userId="me",
            q=query,
            labelIds=["INBOX"],
            pageToken=next_page_token,
            maxResults=100,
        ).execute()
        batch = response.get("messages", [])
        messages.extend(batch)
        elapsed_page = time.time() - start_page
        logger.info("[Gmail] Page %d done – %d msgs (%.2fs) | running total %d", page, len(batch), elapsed_page, len(messages))
        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break
    # fetch metadata (internalDate) so we can sort
    full_messages: List[Dict[str, Any]] = []
    for msg_stub in messages:
        start_get = time.time()
        msg = service.users().messages().get(userId="me", id=msg_stub["id"], format="full").execute()
        logger.debug("[Gmail] get message id=%s (%.2fs)", msg_stub["id"], time.time() - start_get)
        full_messages.append(msg)
    # sort ascending by internalDate
    full_messages.sort(key=lambda m: int(m.get("internalDate", 0)))
    logger.info("Fetched %d messages", len(full_messages))
    return full_messages


def extract_email_body(payload: Dict[str, Any]) -> Optional[str]:
    if "parts" in payload:
        for part in payload["parts"]:
            mime_type = part.get("mimeType")
            data = part.get("body", {}).get("data")
            if data:
                decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                if mime_type == "text/plain":
                    return clean_email_content(decoded)
                elif mime_type == "text/html":
                    return clean_html_content(decoded)
            # recurse into nested parts
            if "parts" in part:
                nested = extract_email_body(part)
                if nested:
                    return nested
    else:
        data = payload.get("body", {}).get("data")
        if data:
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            return clean_email_content(decoded)
    return None

# ============================================================
# 5. OPENAI & PINECONE HELPERS
# ============================================================

@exponential_backoff_retry()
def create_embedding(text: str) -> List[float]:
    logger.debug("Requesting OpenAI embedding (length %d chars)", len(text))
    try:
        if openai.__version__.startswith("0."):
            # Legacy <= 0.x line
            resp = openai.Embedding.create(model=EMBEDDING_MODEL, input=text)
            emb = resp["data"][0]["embedding"]
        else:
            from openai import OpenAI  # type: ignore

            client = OpenAI()
            resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
            emb = resp.data[0].embedding  # type: ignore
    except Exception as e:
        logger.error("OpenAI embedding failed: %s", e)
        raise

    logger.debug("Received embedding of dim %d", len(emb))
    return emb


@exponential_backoff_retry()
def llm_classify_extract(text: str) -> Dict[str, Any]:
    logger.debug("Calling OpenAI chat completion for classification …")
    prompt = """
You are Jobify.AI, an expert recruiting assistant. Your task is to analyze the raw e‑mail (subject + body) provided by the user and decide whether it describes a stage of a job‑application life‑cycle.

If the e‑mail is unrelated to a job search (newsletters, personal, marketing, spam, social media, etc.) respond EXACTLY with:
{"status": "None of These"}

Otherwise respond with ONLY a valid, MINIFIED JSON object (no markdown, no line‑breaks) that conforms to the following schema. **Return all keys in the order shown**:

{
  "company_name": <string>,        # Proper‑case company (e.g. "Cisco")
  "role": <string>,                # Job title (e.g. "Software Engineer Intern")
  "date": <string>,                # Relevant date of the event in ISO‑8601 YYYY‑MM‑DD (convert long‑form dates if necessary)
  "status": <string>,              # One of: "applied", "interview", "rejected", "offer"
  "interview_round": <string|null>,# Only when status == "interview" else null
  "location": <string|null>,       # City/State/Country or "Remote" when clearly stated, else null
  "job_id": <string|null>          # Numeric or alphanumeric requisition / job id when present, else null
}

Strict rules:
1. Determine **status**:
   • "applied" – acknowledgements, confirmations, "Thank you for applying", etc.
   • "interview" – invitations, scheduling, confirmations or feedback for interviews/assessments.
   • "rejected" – denials, regret messages, "no longer being considered".
   • "offer" – offer letters, "we are pleased to", packages, acceptance instructions.
2. Extract entities from BOTH subject and body. Prefer explicit company names; do not guess.
3. Never hallucinate. If data is not available, output null for that field.
4. The output MUST be a single‑line JSON with no trailing commas, no additional keys, and double‑quotes around keys and string values.
5. Do NOT wrap the JSON in markdown fences or any prose.

### Examples:

Example 1 – Interview
Subject: Invitation – Technical Interview (Round 1) for Software Engineer @ ABC Corp
Body: Dear John, congratulations! You have been shortlisted for Round 1 of the technical interview for the Software Engineer position at ABC Corp scheduled on 2024‑03‑15.
JSON: {"company_name": "ABC Corp", "role": "Software Engineer", "date": "2024-03-15", "status": "interview", "interview_round": "Round 1", "location": null, "job_id": null}

Example 2 – Applied / Confirmation
Subject: Thank you for applying to Cisco – Job ID 1427387
Body: Hi Nahom, this email confirms we’ve received your application for Software Engineer Intern, Job ID 1427387, location San Jose, CA.
JSON: {"company_name": "Cisco", "role": "Software Engineer Intern", "date": null, "status": "applied", "interview_round": null, "location": "San Jose, CA", "job_id": "1427387"}

Example 3 – Rejection
Subject: Update on your application – Data Scientist (Remote) – DEF Inc.
Body: Dear candidate, after careful review, DEF Inc. has decided not to proceed with your application at this time.
JSON: {"company_name": "DEF Inc.", "role": "Data Scientist", "date": null, "status": "rejected", "interview_round": null, "location": "Remote", "job_id": null}

Example 4 – Offer
Subject: Offer Letter – Amazon – Data Engineer – Req 9981
Body: We are thrilled to offer you the position of Data Engineer at Amazon. Your start date is 2024‑06‑01 in Seattle, WA.
JSON: {"company_name": "Amazon", "role": "Data Engineer", "date": "2024-06-01", "status": "offer", "interview_round": null, "location": "Seattle, WA", "job_id": "9981"}

Example 5 – Irrelevant / Newsletter
Subject: Your Daily Digest from Reddit
Body: (news content)
JSON: {"status": "None of These"}

Tip: If the company name is not explicitly mentioned but the sender domain is clearly corporate (e.g., *@oracle.com*), you may use the organization part ("Oracle") as company_name.
 
"""
    if openai.__version__.startswith("0."):
        completion = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
        )
        usage = completion.get("usage", {})
        content = completion["choices"][0]["message"]["content"]
    else:
        from openai import OpenAI  # type: ignore

        client = OpenAI()
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
        )
        try:
            usage = completion.usage.model_dump() if completion.usage else {}
        except Exception:
            usage = {}
        content = completion.choices[0].message.content  # type: ignore

    logger.debug("OpenAI completion latency OK – usage: %s", usage)
    # extract JSON from assistant content
    try:
        first_brace = content.index("{")
        last_brace = content.rindex("}")
        json_str = content[first_brace : last_brace + 1]
        parsed = json.loads(json_str)
        logger.debug("Parsed LLM JSON: %s", parsed)
        return parsed
    except Exception:
        return {"status": "None of These"}


# Initialize Pinecone client with support for both v2 and v3 SDKs
def init_pinecone():
    """Return a Pinecone `Index` instance abstracting over SDK v2/v3 differences."""
    # -------- New / current SDK (>=6) or >=3 w/ Pinecone class --------
    # Path 1: SDK exposes `Pinecone` class (v3‑5)
    try:
        from pinecone import Pinecone as PineconeClient, ServerlessSpec  # type: ignore

        pc = PineconeClient(api_key=PINECONE_API_KEY)

        if PINECONE_INDEX_NAME not in pc.list_indexes():
            try:
                pc.create_index(
                    name=PINECONE_INDEX_NAME,
                    dimension=EMBEDDING_DIM,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                )
            except Exception as e:
                # Index may already exist (HTTP 409). Ignore and continue.
                logger.info("create_index failed (likely already exists): %s", e)

        logger.debug("Using Pinecone v3 client")
        return pc.Index(PINECONE_INDEX_NAME)
    except (ImportError, AttributeError):
        pass  # Either no Pinecone class or import failed

    # Path 2: SDK >=6 (no `Pinecone`, but provides global helpers and Index class)
    if hasattr(pinecone, "Index") and hasattr(pinecone, "list_indexes"):
        api_key = PINECONE_API_KEY
        if not api_key:
            raise ValueError("PINECONE_API_KEY env var is required for Pinecone")

        # v6 uses global config builder
        try:
            from pinecone import Config, ConfigBuilder  # type: ignore

            cfg = ConfigBuilder(api_key=api_key).build()
            pinecone.init(cfg) if hasattr(pinecone, "init") else None  # safe‑no‑op for v6
        except Exception:
            # If this fails just continue; most global ops work without explicit init in v6
            pass

        # Create index if needed
        try:
            if PINECONE_INDEX_NAME not in pinecone.list_indexes():
                pinecone.create_index(
                    name=PINECONE_INDEX_NAME,
                    dimension=EMBEDDING_DIM,
                    metric="cosine",
                    cloud="aws",
                    region="us-east-1",
                )
        except Exception as e:
            logger.warning("Could not create index (it may already exist or permissions issue): %s", e)

        # Connect to index (host auto‑resolved)
        try:
            return pinecone.Index(PINECONE_INDEX_NAME)
        except Exception as e:
            logger.error("Failed to instantiate Pinecone.Index: %s", e)

    # Path 3: legacy SDK (<=2) with init()
    # Fallback to v2.x style client (has `init`)
    if hasattr(pinecone, "init"):
        pinecone.init(api_key=PINECONE_API_KEY, environment=PINECONE_ENV)
        if PINECONE_INDEX_NAME not in pinecone.list_indexes():
            pinecone.create_index(name=PINECONE_INDEX_NAME, metric="cosine", dimension=EMBEDDING_DIM)

        logger.debug("Using Pinecone legacy client")
        return pinecone.Index(PINECONE_INDEX_NAME)

    # Neither API present -> instruct user to upgrade / install correct package
    raise ImportError(
        "Unsupported Pinecone package detected – please install supported SDK (`pip install -U pinecone` or `pip install pinecone-client`)."
    )

# ============================================================
# 6. STATUS‑BASED PROCESSING
# ============================================================

def insert_application(session, user_email: str, data: Dict[str, Any]) -> Application:
    app = Application(
        user_email_id=user_email,
        company_name=data["company_name"],
        position_title=data["role"],
        application_date=parse_date_safe(data.get("date")),
    )
    session.add(app)
    session.commit()
    logger.debug("Inserted Application id=%s", app.application_id)
    return app


def pinecone_upsert(index, namespace: str, vector: List[float], metadata: Dict[str, Any]):
    # Clean metadata – Pinecone does not allow null values.
    clean_meta: Dict[str, Any] = {}
    for k, v in metadata.items():
        if v is None:
            continue
        # Convert unsupported types to string
        if isinstance(v, (list, tuple)):
            clean_meta[k] = [str(x) for x in v]
        elif isinstance(v, (int, float, str, bool)):
            clean_meta[k] = v
        else:
            clean_meta[k] = str(v)

    vector_id = (
        f"{clean_meta.get('user_email', metadata.get('user_email'))}::"
        f"{clean_meta.get('application_id', metadata.get('application_id'))}::"
        f"{clean_meta.get('status', metadata.get('status'))}::"
        f"{random.randint(0, 1_000_000_000)}"
    )
    index.upsert(vectors=[(vector_id, vector, clean_meta)], namespace=namespace)
    logger.debug("Upserted vector to Pinecone ns=%s id=%s", namespace, vector_id)


def search_pinecone(index, namespace: str, vector: List[float], user_email: str, top_k: int = 3):
    logger.debug("Querying Pinecone ns=%s top_k=%d", namespace, top_k)
    return index.query(vector=vector, top_k=top_k, namespace=namespace, filter={"user_email": {"$eq": user_email}})

# ============================================================
# 7. MAIN PIPELINE
# ============================================================

def process_messages(messages: List[Dict[str, Any]], user_email: str):
    session = SessionLocal()
    index = init_pinecone()
    # trackers for summary
    counters = {
        "applications": 0,
        "interviews": 0,
        "rejections": 0,
        "offers": 0,
    }
    logger.info("Starting processing of %d messages", len(messages))
    for idx, msg in enumerate(messages, 1):
        if idx % 10 == 0:
            logger.debug("Processed %d / %d messages", idx, len(messages))
        logger.debug("Processing message id=%s", msg.get("id"))
        payload = msg.get("payload", {})
        # Log key headers for visibility
        headers_map = {h.get("name"): h.get("value") for h in payload.get("headers", [])}
        logger.info(
            "Email %d/%d - From: %s | Subject: %s | Date: %s",
            idx,
            len(messages),
            headers_map.get("From", "N/A"),
            headers_map.get("Subject", "N/A"),
            headers_map.get("Date", "N/A"),
        )
        body = extract_email_body(payload)
        subject = headers_map.get("Subject", "")
        if not body:
            continue
        combined_text = truncate_email_body(f"Subject: {subject}\n\n{body}")

        extraction = llm_classify_extract(combined_text)
        logger.debug("LLM extraction result: %s", extraction)
        
        # -------- Heuristic fallback for application confirmations --------
        subj_lower = headers_map.get("Subject", "").lower()
        if extraction.get("status") == "None of These" and any(
            kw in subj_lower for kw in [
                "thank you for applying",
                "thank you for your interest in",
                "application received",
                "thank you for your application",
            ]
        ):
            extraction["status"] = "applied"
            # Attempt simple company name inference from subject (word before first 'to' or 'in')
            if not extraction.get("company_name"):
                # e.g., "Thank you for applying to Cisco" -> company Cisco
                import re as _re

                m = _re.search(r"to ([A-Z][\w\s&.-]+)", headers_map.get("Subject", ""))
                if m:
                    extraction["company_name"] = m.group(1).strip()
            logger.info("Heuristic classified as applied – %s", extraction.get("company_name"))

        status = extraction.get("status")
        if status == "None of These":
            continue

        # ensure required fields present
        foreach_required = ["company_name", "role", "date", "status"]
        if not all(extraction.get(k) for k in foreach_required):
            continue  # skip ill‑formed

        # generate embedding once per email
        embedding = create_embedding(combined_text)

        # Processing logic per status
        if status == "applied":
            logger.info("Detected 'applied' email for %s - %s", extraction["company_name"], extraction["role"])
            app = insert_application(session, user_email, extraction)
            counters["applications"] += 1
            pinecone_upsert(index, "applications", embedding, {
                "user_email": user_email,
                "application_status": "applied",
                "application_id": app.application_id,
                "status": "applied",
                "company_name": extraction["company_name"],
                "role": extraction["role"],
                "location": extraction.get("location"),
                "job_id": extraction.get("job_id"),
            })

        elif status == "rejected":
            logger.info("Detected 'rejected' email")
            res = search_pinecone(index, "applications", embedding, user_email)
            match_id = res.matches[0].metadata.get("application_id") if res.matches and res.matches[0].metadata else None
            if match_id:
                app_id = match_id
            else:
                app = insert_application(session, user_email, extraction)
                counters["applications"] += 1
                app_id = app.application_id
            rej = Rejection(
                application_id=app_id,
                company_name=extraction["company_name"],
                position_title=extraction["role"],
                rejection_date=parse_date_safe(extraction.get("date")),
            )
            session.merge(rej)
            session.commit()
            logger.debug("Inserted Rejection for app_id=%s", app_id)
            counters["rejections"] += 1
            pinecone_upsert(index, "rejection", embedding, {
                "user_email": user_email,
                "application_id": app_id,
                "status": "rejected",
                "company_name": extraction["company_name"],
                "role": extraction["role"],
                "location": extraction.get("location"),
                "job_id": extraction.get("job_id"),
            })

        elif status == "interview":
            logger.info("Detected 'interview' email (round %s)", extraction.get("interview_round"))
            composite_key = f"{extraction['company_name']} {extraction['role']} {extraction.get('interview_round', '')}"
            res = search_pinecone(index, "interview", embedding, user_email)
            match_id = res.matches[0].metadata.get("application_id") if res.matches and res.matches[0].metadata else None
            if not match_id:
                res_apps = search_pinecone(index, "applications", embedding, user_email)
                match_id = res_apps.matches[0].metadata.get("application_id") if res_apps.matches and res_apps.matches[0].metadata else None
            if match_id:
                app_id = match_id
            else:
                app = insert_application(session, user_email, extraction)
                counters["applications"] += 1
                app_id = app.application_id
            interview = Interview(
                application_id=app_id,
                company_name=extraction["company_name"],
                position_title=extraction["role"],
                round=extraction.get("interview_round", "Unknown"),
                invitation_date=parse_date_safe(extraction.get("date")),
            )
            session.add(interview)
            session.commit()
            logger.debug("Inserted Interview for app_id=%s", app_id)
            counters["interviews"] += 1
            pinecone_upsert(index, "interview", embedding, {
                "user_email": user_email,
                "application_id": app_id,
                "status": "interview",
                "company_name": extraction["company_name"],
                "role": extraction["role"],
                "interview_round": extraction.get("interview_round"),
                "location": extraction.get("location"),
                "job_id": extraction.get("job_id"),
            })

        elif status == "offer":
            logger.info("Detected 'offer' email")
            # search hierarchy offer -> interview -> applications
            def search_chain(ns):
                res = search_pinecone(index, ns, embedding, user_email)
                return res.matches[0].metadata.get("application_id") if res.matches and res.matches[0].metadata else None
            match_id = search_chain("offer") or search_chain("interview") or search_chain("applications")
            if match_id:
                app_id = match_id
            else:
                app = insert_application(session, user_email, extraction)
                counters["applications"] += 1
                app_id = app.application_id
            offer = Offer(
                application_id=app_id,
                company_name=extraction["company_name"],
                position_title=extraction["role"],
                offer_date=parse_date_safe(extraction.get("date")),
                location=extraction.get("location"),
            )
            session.add(offer)
            session.commit()
            logger.debug("Inserted Offer for app_id=%s", app_id)
            counters["offers"] += 1
            pinecone_upsert(index, "offer", embedding, {
                "user_email": user_email,
                "application_id": app_id,
                "status": "offer",
                "company_name": extraction["company_name"],
                "role": extraction["role"],
                "location": extraction.get("location"),
                "job_id": extraction.get("job_id"),
            })

    session.close()
    logger.info(
        "Run summary – new Applications: %d | Interviews: %d | Rejections: %d | Offers: %d",
        counters["applications"],
        counters["interviews"],
        counters["rejections"],
        counters["offers"],
    )

# ============================================================
# 8. ENTRYPOINT
# ============================================================

def main():
    user_email = DEFAULT_USER_EMAIL
    service = authenticate_gmail()
    session = SessionLocal()

    logger.info("Retrieving timeframe cursor from DB …")
    last_ts = get_last_update_timestamp(session, user_email)
    # Custom bound: stop fetching emails after 31 Aug 2024 (inclusive)
    current_ts_default = int(datetime.now(tz=timezone.utc).timestamp())
    custom_end = datetime(2024, 8, 19, tzinfo=timezone.utc)
    current_ts = min(current_ts_default, int(custom_end.timestamp()))

    logger.info("Time window: %s – %s (%d days)", datetime.fromtimestamp(last_ts, tz=timezone.utc).date(), datetime.fromtimestamp(current_ts, tz=timezone.utc).date(), max((current_ts-last_ts)//86400,0))

    logger.info("Fetching messages from Gmail …")

    try:
        messages = list_gmail_messages(service, last_ts, current_ts)
        logger.info("Returned %d messages from Gmail list", len(messages))
        process_messages(messages, user_email)
        update_parse_timestamp(session, user_email, current_ts)
        logger.info("Processed %d messages for %s", len(messages), user_email)
    except HttpError as e:
        logger.error("Gmail API error: %s", e)
    finally:
        session.close()


if __name__ == "__main__":
    main()