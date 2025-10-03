"""
Compliance & Risk Agent
Ensures rate lock requests comply with internal and regulatory guidelines.
"""

import asyncio
import json
from typing import Dict, Any
from datetime import datetime
import logging
import os

# Semantic Kernel imports
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

# Import our plugins
from plugins.cosmos_db_plugin import CosmosDBPlugin
from plugins.service_bus_plugin import ServiceBusPlugin
from plugins.compliance_plugin import CompliancePlugin

logger = logging.getLogger(__name__)

class ComplianceRiskAgent:
    """
    Role: Ensures the lock request complies with internal and regulatory guidelines.
    
    Tasks:
    - Listens for 'rates_presented' messages.
    - Fetches the loan record with rate options from Cosmos DB.
    - Runs a series of compliance checks (TRID, state laws, fee tolerance).
    - Updates the rate lock record with the compliance results and sets status.
    - Sends a 'compliance_checked' message to trigger the Lock Confirmation Agent.
    """
    
    def __init__(self):
        self.agent_name = "compliance_risk_agent"
        self.session_id = f"compliance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.kernel = None
        self.cosmos_plugin = None
        self.servicebus_plugin = None
        self.compliance_plugin = None

        self._initialized = False
        self._is_processing = False

    async def _initialize_kernel(self):
        """Initialize Semantic Kernel with Azure OpenAI and plugins."""
        if self._initialized:
            return
            
        try:
            self.kernel = Kernel()
            
            endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
            api_key = os.environ.get("AZURE_OPENAI_API_KEY") 
            deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
            
            if endpoint and api_key:
                self.kernel.add_service(AzureChatCompletion(
                    deployment_name=deployment_name,
                    endpoint=endpoint,
                    api_key=api_key
                ))
            
            self.cosmos_plugin = CosmosDBPlugin(debug=True, session_id=self.session_id)
            self.servicebus_plugin = ServiceBusPlugin(debug=True, session_id=self.session_id)
            self.compliance_plugin = CompliancePlugin(debug=True, session_id=self.session_id)
            
            self.kernel.add_plugin(self.cosmos_plugin, plugin_name="cosmos_db")
            self.kernel.add_plugin(self.servicebus_plugin, plugin_name="service_bus")
            self.kernel.add_plugin(self.compliance_plugin, plugin_name="compliance")
            
            self._initialized = True
            logger.info(f"{self.agent_name}: Semantic Kernel initialized successfully")
            
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to initialize Semantic Kernel - {str(e)}")
            raise

    async def handle_message(self, message: Dict[str, Any]):
        """Handles a single message from the service bus."""
        await self._initialize_kernel()
        
        message_type = message.get('message_type')
        loan_application_id = message.get('loan_application_id')
        
        logger.info(f"{self.agent_name}: Received message '{message_type}' for loan '{loan_application_id}'")

        if message_type != 'rates_presented':
            logger.warning(f"Received unexpected message type: {message_type}. Skipping.")
            return

        try:
            # 1. Fetch the full loan record from Cosmos DB
            rate_lock_record_str = await self.cosmos_plugin.get_rate_lock(loan_application_id)
            rate_lock_record = json.loads(rate_lock_record_str)

            if not rate_lock_record.get("success"):
                raise ValueError(f"Could not retrieve rate lock record for {loan_application_id}")

            loan_data = rate_lock_record.get("data", {})

            # 2. Run compliance assessment
            compliance_result_str = await self.compliance_plugin.run_compliance_assessment(json.dumps(loan_data))
            compliance_result = json.loads(compliance_result_str)

            if not compliance_result.get("success"):
                raise ValueError(f"Compliance assessment failed: {compliance_result.get('error')}")

            compliance_data = compliance_result.get("data", {})
            compliance_status = compliance_data.get("overall_status", "Failed")

            # 3. Determine new status and update Cosmos DB
            new_status = "Compliance" + compliance_status # e.g., "CompliancePassed" or "ComplianceFailed"
            update_payload = {
                "status": new_status,
                "compliance_check_results": compliance_data,
                "compliance_checked_at": datetime.utcnow().isoformat()
            }
            await self.cosmos_plugin.update_rate_lock(loan_application_id, json.dumps(update_payload))
            
            # 4. Send audit message
            await self._send_audit_message("COMPLIANCE_CHECKED", loan_application_id, {
                "status": new_status,
                "compliance_status": compliance_status
            })
            
            # 5. Send workflow message for the next agent
            if compliance_status == "Passed":
                await self._send_workflow_message("compliance_passed", loan_application_id, {
                    "loan_application_id": loan_application_id,
                    "next_action": "present_for_confirmation"
                })
                logger.info(f"Compliance check PASSED for loan '{loan_application_id}'.")
            else:
                # If compliance fails, we might send an alert or trigger a manual review
                await self._send_exception_alert("COMPLIANCE_FAILURE", "medium", 
                                                 f"Compliance check failed for loan {loan_application_id}", 
                                                 loan_application_id)
                logger.warning(f"Compliance check FAILED for loan '{loan_application_id}'.")


        except Exception as e:
            error_msg = f"Failed to process compliance check for loan '{loan_application_id}': {str(e)}"
            logger.error(error_msg)
            await self._send_exception_alert("TECHNICAL_ERROR", "high", error_msg, loan_application_id)

    async def _send_audit_message(self, action: str, loan_application_id: str, audit_data: Dict[str, Any]):
        try:
            await self.servicebus_plugin.send_audit_message(
                agent_name=self.agent_name,
                action=action,
                loan_application_id=loan_application_id,
                audit_data=json.dumps(audit_data)
            )
        except Exception as e:
            logger.error(f"Failed to send audit message: {str(e)}")

    async def _send_workflow_message(self, message_type: str, loan_application_id: str, message_data: Dict[str, Any]):
        try:
            await self.servicebus_plugin.send_workflow_message(
                message_type=message_type,
                loan_application_id=loan_application_id,
                message_data=json.dumps(message_data),
                correlation_id=self.session_id
            )
        except Exception as e:
            logger.error(f"Failed to send workflow message: {str(e)}")

    async def _send_exception_alert(self, exception_type: str, priority: str, message: str, loan_application_id: str):
        try:
            exception_data = {
                "agent": self.agent_name,
                "error_message": message,
                "timestamp": datetime.utcnow().isoformat()
            }
            await self.servicebus_plugin.send_exception_alert(
                exception_type=exception_type,
                priority=priority,
                loan_application_id=loan_application_id,
                exception_data=json.dumps(exception_data)
            )
        except Exception as e:
            logger.error(f"Failed to send exception alert: {str(e)}")

    async def close(self):
        if self._initialized:
            if self.cosmos_plugin: await self.cosmos_plugin.close()
            if self.servicebus_plugin: await self.servicebus_plugin.close()
            if self.compliance_plugin: await self.compliance_plugin.close()
        logger.info(f"{self.agent_name}: Resources cleaned up.")