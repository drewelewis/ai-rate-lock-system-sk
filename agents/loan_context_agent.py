"""
Loan Application Context Agent - Autonomous AI Agent
Uses LLM to intelligently retrieve and validate loan context from LOS.
"""

import logging
from typing import Dict, Any

# Import base agent
from agents.base_agent import BaseAgent

# Import additional plugins specific to this agent
from plugins.los_plugin import LoanOriginationSystemPlugin

logger = logging.getLogger(__name__)


class LoanApplicationContextAgent(BaseAgent):
    """
    Autonomous AI Agent - Loan Context Retrieval
    
    Role: Uses LLM intelligence to retrieve loan data from LOS and validate eligibility.
    
    LLM Tasks:
    - Receive 'email_parsed' workflow events
    - Fetch loan application data from LOS (via plugin)
    - Fetch rate lock record from Cosmos DB (via plugin)
    - Validate loan eligibility for rate lock
    - Enrich rate lock record with loan context
    - Update status to CONTEXT_RETRIEVED (via plugin)
    - Send workflow event to trigger Rate Quote Agent (via plugin)
    - Log audit trail (via plugin)
    
    Agent is THIN - ALL work delegated to plugins via LLM autonomous function calling.
    """
    
    def __init__(self):
        """Initialize loan context agent with LOS plugin."""
        super().__init__(agent_name="loan_context_agent")
        self.los_plugin = None
    
    async def _initialize_kernel(self):
        """Initialize kernel and add LOS plugin."""
        await super()._initialize_kernel()
        
        if not self.los_plugin:
            self.los_plugin = LoanOriginationSystemPlugin()
            self.kernel.add_plugin(self.los_plugin, plugin_name="LOS")
            logger.info(f"{self.agent_name}: LOS plugin registered")
    
    def _get_system_prompt(self) -> str:
        """Define LLM instructions for autonomous loan context retrieval."""
        return """You are the Loan Context Agent - an AI that retrieves loan application data.

AVAILABLE TOOLS (call these autonomously as needed):
1. LOS.get_loan_application(loan_application_id) - Fetch loan data from Loan Origination System
2. CosmosDB.get_rate_lock(loan_application_id) - Fetch rate lock record
3. CosmosDB.update_rate_lock_status(loan_application_id, new_status, updates) - Update record with loan context
4. ServiceBus.send_workflow_event(message_type, loan_application_id, message_data, correlation_id) - Send to next agent
5. ServiceBus.send_audit_log(agent_name, action, loan_application_id, event_type, audit_data) - Log action
6. ServiceBus.send_exception(exception_type, priority, error_message, loan_application_id, agent_name) - Alert on errors

YOUR WORKFLOW:
1. Receive 'email_parsed' event for loan application
2. Fetch loan application data from LOS using get_loan_application()
3. Fetch the rate lock record from Cosmos DB
4. Validate loan data:
   - Loan exists and is active
   - Borrower credit score available
   - Property information complete
   - Loan amount and LTV within acceptable ranges
5. If validation PASSES:
   - Enrich rate lock record with loan context (borrower, property, loan details)
   - Update status to 'CONTEXT_RETRIEVED'
   - Send 'context_retrieved' workflow event to trigger rate quote generation
   - Log 'CONTEXT_RETRIEVED' audit event
6. If validation FAILS:
   - Send exception alert with specific failure reason
   - DO NOT update status or send workflow event
   - Log failure in audit

IMPORTANT RULES:
- ALWAYS use autonomous function calling - invoke tools directly
- LOS returns complete loan application data including:
  * Borrower: name, email, phone, credit_score, employment
  * Property: address, value, type, occupancy
  * Loan: amount, loan_type, ltv, term, purpose
- Store ALL loan context in the rate lock record's loan_context field
- Ensure loan_context includes flat fields for pricing engine:
  * borrower_credit_score
  * loan_to_value (ltv)
  * loan_amount
  * property_value
  * loan_type
  * property_state
- Set status to 'CONTEXT_RETRIEVED' only after successful enrichment
- Send workflow event type 'context_retrieved' to trigger rate_quote_agent
- Log action 'CONTEXT_RETRIEVED' for audit trail
- Use correlation_id from incoming message for workflow tracking
- If LOS lookup fails, send HIGH priority exception

RESPONSE FORMAT:
Return a JSON summary with:
{
  "success": true,
  "loan_application_id": "APP-12345",
  "borrower_name": "John Doe",
  "loan_amount": 450000,
  "credit_score": 750,
  "status": "CONTEXT_RETRIEVED",
  "next_stage": "rate_quote"
}

You are autonomous - decide which tools to call and in what order!"""
    
    async def cleanup(self):
        """Clean up resources."""
        if self.los_plugin:
            await self.los_plugin.close()
        await super().cleanup()
