"""
Lock Confirmation Agent - Autonomous AI Agent
Uses LLM to intelligently execute rate locks and send confirmations.
"""

import logging
from typing import Dict, Any

# Import base agent
from agents.base_agent import BaseAgent

# Import additional plugins specific to this agent
from plugins.document_plugin import DocumentPlugin

logger = logging.getLogger(__name__)


class LockConfirmationAgent(BaseAgent):
    """
    Autonomous AI Agent - Rate Lock Confirmation
    
    Role: Uses LLM intelligence to execute rate locks and send confirmations.
    
    LLM Tasks:
    - Receive 'compliance_passed' workflow events
    - Fetch loan record with approved rate from Cosmos DB (via plugin)
    - Generate lock confirmation document (via plugin)
    - Update status to LOCKED with lock details (via plugin)
    - Send confirmation email notification (via plugin)
    - Send workflow event to complete workflow (via plugin)
    - Log audit trail (via plugin)
    
    Agent is THIN - ALL work delegated to plugins via LLM autonomous function calling.
    """
    
    def __init__(self):
        """Initialize lock confirmation agent with document plugin."""
        super().__init__(agent_name="lock_confirmation_agent")
        self.document_plugin = None
    
    async def _initialize_kernel(self):
        """Initialize kernel and add Document plugin."""
        await super()._initialize_kernel()
        
        if not self.document_plugin:
            self.document_plugin = DocumentPlugin(debug=True, session_id=self.agent_name)
            self.kernel.add_plugin(self.document_plugin, plugin_name="Document")
            logger.info(f"{self.agent_name}: Document plugin registered")
    
    def _get_system_prompt(self) -> str:
        """Define LLM instructions for autonomous lock confirmation."""
        return """You are the Lock Confirmation Agent - an AI that executes mortgage rate locks and sends confirmations.

AVAILABLE TOOLS (call these autonomously as needed):
1. CosmosDB.get_rate_lock(loan_application_id) - Fetch loan record with approved rate
2. Document.generate_lock_confirmation(loan_data, rate_data, lock_details) - Generate confirmation document
3. CosmosDB.update_rate_lock_status(loan_application_id, new_status, update_data) - Update to LOCKED status
4. ServiceBus.send_workflow_event(message_type, loan_application_id, message_data, correlation_id) - Send workflow event
5. ServiceBus.send_audit_log(agent_name, action, loan_application_id, event_type, audit_data) - Log action
6. ServiceBus.send_message_to_queue(queue_name, message_data) - Send email notification

YOUR WORKFLOW:
1. Receive 'compliance_passed' workflow event for loan
2. Fetch loan record from Cosmos DB using get_rate_lock()
3. Extract loan data, selected rate option, and compliance results
4. Generate lock confirmation document using generate_lock_confirmation()
5. Update loan status to 'LOCKED' with:
   - locked_rate (from selected option)
   - lock_period (from request)
   - lock_expiry_date (calculated from lock_period)
   - confirmation_document_id (from generated document)
   - locked_at (current timestamp)
6. Send email notification to 'outbound-email-queue' with:
   - recipient: borrower_email
   - subject: "Rate Lock Confirmation - {loan_application_id}"
   - body: Include loan details, locked rate, expiry date, confirmation document
7. Send 'rate_locked' workflow event to complete workflow
8. Log 'RATE_LOCKED' audit event

IMPORTANT RULES:
- ALWAYS use autonomous function calling - invoke tools directly
- Lock expiry date = current date + lock_period days
- Confirmation document must include: borrower name, property address, loan amount, locked rate, lock period, expiry date
- Email notification MUST go to 'outbound-email-queue' queue
- Include confirmation_document_id in the email
- Update status to 'LOCKED' (all caps)
- Log action 'RATE_LOCKED' for audit trail
- Use loan_application_id as correlation_id

RESPONSE FORMAT:
Return a JSON summary with:
{
  "success": true,
  "loan_application_id": "APP-12345",
  "locked_rate": 6.75,
  "lock_period": 30,
  "lock_expiry_date": "2025-11-04",
  "confirmation_sent": true,
  "workflow_completed": true
}

You are autonomous - decide which tools to call and in what order!"""
    
    async def cleanup(self):
        """Clean up resources."""
        if self.document_plugin:
            await self.document_plugin.close()
        await super().cleanup()
