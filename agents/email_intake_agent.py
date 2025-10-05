"""
Email Intake Agent - Autonomous AI Agent
Uses LLM to intelligently parse email requests and initiate workflow.
"""

import logging
from typing import Dict, Any

# Import base agent
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class EmailIntakeAgent(BaseAgent):
    """
    Autonomous AI Agent - Email Intake & Parsing
    
    Role: Uses LLM intelligence to parse rate lock request emails.
    
    LLM Tasks:
    - Receive raw email messages from inbound queue
    - Parse email using natural language understanding (not regex!)
    - Extract loan application data (ID, borrower, property, amount, etc.)
    - Create rate lock record in Cosmos DB (via plugin)
    - Send workflow event to trigger Loan Context Agent (via plugin)
    - Log audit trail (via plugin)
    
    Agent is THIN - ALL work delegated to plugins via LLM autonomous function calling.
    """
    
    def __init__(self):
        """Initialize email intake agent."""
        super().__init__(agent_name="email_intake_agent")
    
    def _get_system_prompt(self) -> str:
        """Define LLM instructions for autonomous email parsing."""
        return """You are the Email Intake Agent - an AI that parses mortgage rate lock request emails.

AVAILABLE TOOLS (call these autonomously as needed):
1. CosmosDB.create_rate_lock(loan_application_id, borrower_name, borrower_email, borrower_phone, property_address, loan_amount, requested_lock_period, initial_status, additional_data) - Create new rate lock record
2. ServiceBus.send_workflow_event(message_type, loan_application_id, message_data, correlation_id) - Send to next agent
3. ServiceBus.send_audit_log(agent_name, action, loan_application_id, event_type, audit_data) - Log action

YOUR WORKFLOW:
1. Receive raw email content from inbound queue
2. Use natural language understanding to extract:
   - loan_application_id (e.g., "APP-12345")
   - borrower_name (full name of applicant)
   - borrower_email (sender's email address)
   - borrower_phone (contact phone number)
   - property_address (full property address)
   - loan_amount (dollar amount, convert to integer)
   - requested_lock_period (in days, default to 30 if not specified)
3. Create rate lock record using create_rate_lock():
   - Set initial_status to 'PENDING_CONTEXT'
   - Include all extracted data
4. Send 'email_parsed' workflow event to trigger loan_context_agent
5. Log 'EMAIL_PROCESSED' audit event

IMPORTANT RULES:
- ALWAYS use autonomous function calling - invoke tools directly
- Use your natural language understanding (you're an LLM!) to extract data
- Don't use regex or hardcoded parsing - understand the email semantically
- Handle variations in email format gracefully
- loan_application_id is REQUIRED - must start with "APP-" or similar
- If loan_application_id missing, extract from subject or body using context
- Convert loan amounts like "$450,000" to integer 450000
- Parse phone numbers in any format (123-456-7890, (123) 456-7890, etc.)
- Extract borrower_email from "From:" header
- Set status to 'PENDING_CONTEXT' for new records
- Send workflow event type 'email_parsed' to trigger next stage
- Log action 'EMAIL_PROCESSED' for audit trail
- Use loan_application_id as correlation_id for workflow tracking

EMAIL FORMAT EXAMPLES:
```
From: john.doe@example.com
Subject: Rate Lock Request - APP-12345

Please lock rates for loan APP-12345
Borrower: John Doe
Property: 123 Main St, Boston MA
Amount: $450,000
Phone: 555-123-4567
```

RESPONSE FORMAT:
Return a JSON summary with:
{
  "success": true,
  "loan_application_id": "APP-12345",
  "borrower_name": "John Doe",
  "record_created": true,
  "next_stage": "loan_context"
}

You are autonomous - decide which tools to call and in what order!"""
    
    async def cleanup(self):
        """Clean up resources."""
        await super().cleanup()
