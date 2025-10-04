"""
Utility module for generating unique identifiers for rate lock requests and related entities.
"""
import uuid
from datetime import datetime
from typing import Optional


def generate_rate_lock_request_id(loan_application_id: str, prefix: str = "RLR") -> str:
    """
    Generate a unique rate lock request ID.
    
    Format: {prefix}-{loan_id_suffix}-{timestamp}-{uuid_short}
    Example: RLR-LA12345-20251003-a7f3
    
    Args:
        loan_application_id (str): The loan application ID to associate with this request
        prefix (str): Prefix for the ID (default: "RLR" for Rate Lock Request)
        
    Returns:
        str: A unique rate lock request ID
    """
    # Extract last part of loan application ID for brevity
    loan_suffix = loan_application_id.split('-')[-1] if '-' in loan_application_id else loan_application_id
    
    # Generate timestamp in compact format (YYYYMMDD)
    timestamp = datetime.utcnow().strftime('%Y%m%d')
    
    # Generate short UUID (first 8 characters of UUID4)
    short_uuid = str(uuid.uuid4())[:8]
    
    # Combine into unique ID
    rate_lock_request_id = f"{prefix}-{loan_suffix}-{timestamp}-{short_uuid}"
    
    return rate_lock_request_id


def generate_audit_event_id(agent_name: str) -> str:
    """
    Generate a unique audit event ID.
    
    Format: AUD-{agent_abbrev}-{timestamp}-{uuid}
    Example: AUD-EI-20251003153045-a7f3b2c1
    
    Args:
        agent_name (str): Name of the agent generating the audit event
        
    Returns:
        str: A unique audit event ID
    """
    # Create agent abbreviation (first 2 chars or first letters)
    agent_abbrev = ''.join([c for c in agent_name if c.isupper()])[:2] or agent_name[:2].upper()
    
    # Generate timestamp in full format
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    
    # Generate short UUID
    short_uuid = str(uuid.uuid4())[:8]
    
    return f"AUD-{agent_abbrev}-{timestamp}-{short_uuid}"


def generate_exception_id(exception_type: str, loan_application_id: Optional[str] = None) -> str:
    """
    Generate a unique exception ID.
    
    Format: EXC-{type_abbrev}-{loan_suffix}-{uuid}
    Example: EXC-VAL-LA12345-a7f3b2c1
    
    Args:
        exception_type (str): Type of exception (e.g., "validation_error", "processing_failure")
        loan_application_id (str, optional): Associated loan application ID
        
    Returns:
        str: A unique exception ID
    """
    # Create exception type abbreviation (first 3 letters uppercase)
    type_abbrev = exception_type[:3].upper()
    
    # Extract loan suffix if provided
    loan_suffix = ""
    if loan_application_id:
        loan_suffix = loan_application_id.split('-')[-1] if '-' in loan_application_id else loan_application_id
        loan_suffix = f"-{loan_suffix}"
    
    # Generate short UUID
    short_uuid = str(uuid.uuid4())[:8]
    
    return f"EXC-{type_abbrev}{loan_suffix}-{short_uuid}"


def generate_document_id(document_type: str, loan_application_id: str) -> str:
    """
    Generate a unique document ID.
    
    Format: DOC-{type}-{loan_id}-{timestamp}
    Example: DOC-CONF-LA12345-20251003153045
    
    Args:
        document_type (str): Type of document (e.g., "confirmation", "disclosure")
        loan_application_id (str): Associated loan application ID
        
    Returns:
        str: A unique document ID
    """
    # Create document type abbreviation (first 4 letters uppercase)
    type_abbrev = document_type[:4].upper()
    
    # Extract loan suffix
    loan_suffix = loan_application_id.split('-')[-1] if '-' in loan_application_id else loan_application_id
    
    # Generate timestamp
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    
    return f"DOC-{type_abbrev}-{loan_suffix}-{timestamp}"


def is_valid_rate_lock_request_id(rate_lock_request_id: str) -> bool:
    """
    Validate if a string is a properly formatted rate lock request ID.
    
    Args:
        rate_lock_request_id (str): The ID to validate
        
    Returns:
        bool: True if valid format, False otherwise
    """
    if not rate_lock_request_id:
        return False
    
    parts = rate_lock_request_id.split('-')
    
    # Expected format: PREFIX-LOAN-YYYYMMDD-UUID
    if len(parts) < 4:
        return False
    
    # Check prefix is alphabetic
    if not parts[0].isalpha():
        return False
    
    # Check timestamp part (index -2) is 8 digits
    try:
        timestamp_part = parts[-2]
        if len(timestamp_part) != 8 or not timestamp_part.isdigit():
            return False
    except (IndexError, ValueError):
        return False
    
    # Check UUID part (index -1) is alphanumeric
    uuid_part = parts[-1]
    if not uuid_part.replace('-', '').isalnum():
        return False
    
    return True
