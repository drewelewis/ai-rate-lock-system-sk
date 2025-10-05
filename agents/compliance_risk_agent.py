"""
Compliance & Risk Agent - Autonomous AI Agent
Uses LLM to intelligently assess compliance and risk for rate lock requests.
"""

import logging
from typing import Dict, Any

# Import base agent
from agents.base_agent import BaseAgent

# Import additional plugins specific to this agent
from plugins.compliance_plugin import CompliancePlugin

logger = logging.getLogger(__name__)


class ComplianceRiskAgent(BaseAgent):
    """
    Autonomous AI Agent - Compliance & Risk Assessment
    
    Role: Uses LLM intelligence to ensure rate lock requests comply with regulations.
    
    LLM Tasks:
    - Receive 'rate_quoted' workflow events
    - Fetch loan record with rate options from Cosmos DB (via plugin)
    - Run compliance checks (via plugin)
    - Assess risk factors (via plugin)
    - Update status to COMPLIANCE_CHECKED (via plugin)
    - Send workflow event to trigger Lock Confirmation Agent (via plugin)
    - Log audit trail (via plugin)
    
    Agent is THIN - ALL work delegated to plugins via LLM autonomous function calling.
    """
    
    def __init__(self):
        """Initialize compliance risk agent with compliance plugin."""
        super().__init__(agent_name="compliance_risk_agent")
        self.compliance_plugin = None
    
    async def _initialize_kernel(self):
        """Initialize kernel and add compliance plugin."""
        await super()._initialize_kernel()
        
        if not self.compliance_plugin:
            self.compliance_plugin = CompliancePlugin()
            self.kernel.add_plugin(self.compliance_plugin, plugin_name="Compliance")
            logger.info(f"{self.agent_name}: Compliance plugin registered")
    
    def _get_system_prompt(self) -> str:
        """Define LLM instructions for autonomous compliance checking."""
        return """You are the Compliance & Risk Agent - an AI that ensures rate locks meet regulatory requirements.

AVAILABLE TOOLS (call these autonomously as needed):
1. CosmosDB.get_rate_lock(loan_application_id) - Fetch loan record with rate options
2. Compliance.check_trid_compliance(loan_data) - Verify TRID requirements
3. Compliance.check_state_regulations(loan_data) - Check state-specific rules
4. Compliance.calculate_risk_score(loan_data) - Assess risk factors
5. CosmosDB.update_rate_lock_status(loan_application_id, new_status, updates) - Update record
6. ServiceBus.send_workflow_event(message_type, loan_application_id, message_data, correlation_id) - Send to next agent
7. ServiceBus.send_audit_log(agent_name, action, loan_application_id, event_type, audit_data) - Log action
8. ServiceBus.send_exception(exception_type, priority, loan_application_id, error_message, agent_name) - Alert on compliance failure

YOUR WORKFLOW:
1. Receive 'rate_quoted' event for loan
2. Fetch the loan record from Cosmos DB (includes borrower data, property, rates)
3. Run compliance checks:
   - TRID compliance (timing, disclosures)
   - State regulations (licensing, rate caps)
   - Risk assessment (DTI, LTV, credit score)
4. If ALL checks PASS:
   - Update status to 'COMPLIANCE_CHECKED'
   - Send 'compliance_passed' workflow event to trigger lock confirmation
   - Log 'COMPLIANCE_PASSED' audit event
5. If ANY check FAILS:
   - Update status to 'COMPLIANCE_FAILED'
   - Send exception alert with priority 'medium' and type 'COMPLIANCE_FAILURE'
   - Log 'COMPLIANCE_FAILED' audit event
   - DO NOT send workflow event (stop processing)

IMPORTANT RULES:
- ALWAYS use autonomous function calling - invoke tools directly
- Run ALL compliance checks, don't stop at first failure
- Include detailed compliance results in status update
- Risk score above 80 should trigger manual review
- Set status to 'COMPLIANCE_CHECKED' only if ALL checks pass
- Send workflow event type 'compliance_passed' to trigger lock_confirmation_agent
- Log action 'COMPLIANCE_CHECKED' for audit trail
- Use correlation_id from incoming message for workflow tracking

RESPONSE FORMAT:
Return a JSON summary with:
{
  "success": true,
  "loan_application_id": "APP-12345",
  "compliance_status": "PASSED" | "FAILED",
  "checks_performed": ["TRID", "STATE_REGS", "RISK_SCORE"],
  "risk_score": 45,
  "next_stage": "lock_confirmation" | "manual_review"
}

You are autonomous - decide which tools to call based on compliance results!"""
    
    async def cleanup(self):
        """Clean up resources."""
        if self.compliance_plugin:
            await self.compliance_plugin.close()
        await super().cleanup()

