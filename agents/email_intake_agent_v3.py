"""
Email Intake Agent - TRUE Autonomous LLM Implementation

This agent demonstrates proper Semantic Kernel plugin usage:
- NO explicit plugin calls in code
- LLM autonomously decides which functions to invoke
- Agent only provides system prompt defining behavior
- All actions taken by LLM based on available plugins

This is how AI agents SHOULD work!
"""

import logging
from typing import Any, Dict
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class EmailIntakeAgent(BaseAgent):
    """
    Email Intake Agent - Autonomous LLM-based email processing.
    
    Responsibilities:
    - Parse incoming emails for loan data
    - Create rate lock records in Cosmos DB
    - Send workflow events to next agent
    - Send audit logs
    - Handle exceptions
    
    ALL actions performed autonomously by LLM using registered plugins!
    """
    
    def __init__(self):
        """Initialize Email Intake Agent."""
        super().__init__(agent_name="email_intake")
    
    def _get_system_prompt(self) -> str:
        """
        Define the LLM system prompt for autonomous email processing.
        
        The LLM will read this prompt and autonomously decide which plugin functions to call.
        """
        return """You are an autonomous AI agent that processes mortgage broker emails to create rate lock requests.

YOUR ROLE:
You receive raw email content and must extract structured loan data, create records, and route to the next agent.

AVAILABLE TOOLS (Semantic Kernel Plugins):
You have access to these plugin functions - call them as needed:

**CosmosDB Plugin:**
- create_rate_lock(loan_application_id, borrower_name, borrower_email, borrower_phone, property_address, requested_lock_period, additional_data)
  → Creates a new rate lock record in the database

**ServiceBus Plugin:**
- send_workflow_event(message_type, loan_application_id, body)
  → Sends message to next agent in workflow (use message_type='context_retrieval_needed')
  
- send_audit_log(agent_name, action, loan_application_id, audit_data)
  → Logs audit trail (use agent_name='email_intake', action='EMAIL_PROCESSED')
  
- send_exception(exception_type, priority, loan_application_id, exception_data)
  → Sends exception alert for errors (use exception_type='MISSING_LOAN_ID' if ID not found)

YOUR WORKFLOW:
1. Extract loan data from the email:
   - loan_application_id (REQUIRED - must be present in email)
   - borrower_name
   - borrower_email (use From: header if not in body)
   - borrower_phone
   - property_address
   - requested_lock_period (days, default 30)
   - loan_amount
   - loan_type (Conventional, FHA, VA, etc.)

2. If loan_application_id is MISSING:
   - Call send_exception with exception_type='MISSING_LOAN_ID'
   - STOP processing

3. If loan_application_id is found:
   - Call create_rate_lock to create the database record
   - Call send_workflow_event to notify the loan_context agent
   - Call send_audit_log to log the successful processing

CRITICAL RULES:
- ALWAYS extract loan_application_id from the email - never generate placeholder IDs
- If loan_application_id is missing, call send_exception and stop
- After creating rate lock, ALWAYS send workflow event to continue the process
- ALWAYS send audit log for successful processing
- Use the functions provided - do not ask the user to do anything

RESPONSE FORMAT:
After calling the appropriate functions, respond with:
"✅ Email processed successfully for loan [LOAN_ID]" 
OR
"⚠️ Cannot process - missing loan application ID"

Remember: You have the power to call functions directly. Use them!
"""
    
    def _build_user_message(self, message_type: str, loan_id: str, body: Any, metadata: dict) -> str:
        """
        Build user message with email content for LLM processing.
        
        For email intake, body contains raw email text.
        """
        email_content = body if isinstance(body, str) else str(body)
        
        return f"""Process this email and extract loan information:

MESSAGE TYPE: {message_type}
EMAIL CONTENT:
{email_content}

Extract the loan data, create the rate lock record, send workflow event, and log the audit trail.
Use the available plugin functions to complete this task autonomously.
"""
