"""
Rate Quote Agent - Autonomous AI Agent
Uses LLM to intelligently generate rate quotes and manage workflow progression.
"""

import logging
from typing import Dict, Any

# Import base agent
from agents.base_agent import BaseAgent

# Import additional plugins specific to this agent
from plugins.pricing_engine_plugin import PricingEnginePlugin

logger = logging.getLogger(__name__)


class RateQuoteAgent(BaseAgent):
    """
    Autonomous AI Agent - Rate Quote Generation
    
    Role: Uses LLM intelligence to generate rate quotes using pricing engine.
    
    LLM Tasks:
    - Receive 'context_retrieved' workflow events
    - Fetch loan record from Cosmos DB (via plugin)
    - Generate rate options using pricing engine (via plugin)
    - Update status to RATES_QUOTED (via plugin)
    - Send workflow event to trigger Compliance Agent (via plugin)
    - Log audit trail (via plugin)
    
    Agent is THIN - ALL work delegated to plugins via LLM autonomous function calling.
    """
    
    def __init__(self):
        """Initialize rate quote agent with pricing engine plugin."""
        super().__init__(agent_name="rate_quote_agent")
        self.pricing_plugin = None
    
    async def _initialize_kernel(self):
        """Initialize kernel and add pricing engine plugin."""
        await super()._initialize_kernel()
        
        if not self.pricing_plugin:
            self.pricing_plugin = PricingEnginePlugin(debug=True, session_id=self.agent_name)
            self.kernel.add_plugin(self.pricing_plugin, plugin_name="PricingEngine")
            logger.info(f"{self.agent_name}: Pricing Engine plugin registered")
    
    def _get_system_prompt(self) -> str:
        """Define LLM instructions for autonomous rate quote generation."""
        return """You are the Rate Quote Agent - an AI that generates mortgage rate quotes.

AVAILABLE TOOLS (call these autonomously as needed):
1. CosmosDB.get_rate_lock(loan_application_id) - Fetch loan record
2. PricingEngine.get_rate_options(loan_context) - Generate rate quotes  
3. CosmosDB.update_rate_lock_status(loan_application_id, new_status, updates) - Update record
4. ServiceBus.send_workflow_event(message_type, loan_application_id, message_data, correlation_id) - Send to next agent
5. ServiceBus.send_audit_log(agent_name, action, loan_application_id, event_type, audit_data) - Log action

YOUR WORKFLOW:
1. Receive 'context_retrieved' event for loan
2. Fetch the loan record from Cosmos DB using get_rate_lock()
3. Extract loan_context from the fetched record
4. Call PricingEngine.get_rate_options() with loan_context to generate rate quotes
5. Update loan status to 'RATES_QUOTED' with the generated rate options
6. Send 'rate_quoted' workflow event to trigger the next agent (compliance check)
7. Log audit event 'RATES_GENERATED' for audit trail

IMPORTANT RULES:
- ALWAYS use autonomous function calling - invoke tools directly
- Pricing engine needs loan_context with: loan_amount, credit_score, ltv, loan_type, property_state
- Rate options should include: rate, points, apr, monthly_payment, lock_period
- Set status to 'RATES_QUOTED' after successful generation
- Send workflow event type 'rate_quoted' to trigger compliance_risk_agent
- Log action 'RATES_GENERATED' for audit trail
- Use correlation_id from incoming message for workflow tracking

RESPONSE FORMAT:
Return a JSON summary with:
{
  "success": true,
  "loan_application_id": "APP-12345",
  "rate_options_count": 3,
  "status": "RATES_QUOTED",
  "next_stage": "compliance_check"
}

You are autonomous - decide which tools to call and in what order!"""
    
    async def cleanup(self):
        """Clean up resources."""
        if self.pricing_plugin:
            await self.pricing_plugin.close()
        await super().cleanup()

