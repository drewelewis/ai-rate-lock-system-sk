"""
Audit & Logging Agent
Maintains comprehensive audit trail for compliance and traceability.
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

logger = logging.getLogger(__name__)

class AuditLoggingAgent:
    """
    Role: Maintains a comprehensive audit trail.
    
    Tasks:
    - Listens for 'audit_event' messages from any agent.
    - Parses the audit data.
    - Stores the audit data in the 'AuditLogs' container in Cosmos DB.
    - Handles storage errors gracefully.
    """
    
    def __init__(self):
        self.agent_name = "audit_logging_agent"
        self.session_id = f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.kernel = None
        self.cosmos_plugin = None
        self.servicebus_plugin = None

        self._initialized = False

    async def _initialize_kernel(self):
        """Initialize Semantic Kernel with Azure OpenAI and plugins."""
        if self._initialized:
            return

        try:
            self.kernel = Kernel()

            # The Audit agent doesn't need an LLM, but we initialize it for consistency
            # and potential future use (e.g., summarizing audit logs).
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

            self.kernel.add_plugin(self.cosmos_plugin, plugin_name="cosmos_db")
            self.kernel.add_plugin(self.servicebus_plugin, plugin_name="service_bus")

            self._initialized = True
            logger.info(f"{self.agent_name}: Semantic Kernel initialized successfully")

        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to initialize Semantic Kernel - {str(e)}")
            raise

    async def handle_message(self, message: Dict[str, Any]):
        """Handles a single audit message from the service bus."""
        await self._initialize_kernel()

        message_type = message.get('message_type')

        if message_type != 'audit_event':
            logger.warning(f"Received unexpected message type: {message_type}. Skipping.")
            return

        try:
            agent_name = message.get('agent_name')
            action = message.get('action')
            loan_application_id = message.get('loan_application_id')
            audit_data = message.get('audit_data', {})

            logger.info(f"Processing audit event from '{agent_name}' for action '{action}' on loan '{loan_application_id}'")

            # Prepare the audit record for Cosmos DB
            # The plugin function expects a single JSON string as its payload.
            audit_payload = {
                "agent_name": agent_name,
                "action": action,
                "loan_application_id": loan_application_id,
                "details": audit_data,
                "outcome": "SUCCESS" # Assume success unless an error occurs during logging
            }

            # Call the CosmosDB plugin to create the audit log
            result_str = await self.cosmos_plugin.create_audit_log(json.dumps(audit_payload))
            result = json.loads(result_str)

            if not result.get("success"):
                # If logging to Cosmos fails, we have a critical problem.
                # We'll log it to the console and send an exception alert.
                error_msg = f"CRITICAL: Failed to write audit log to Cosmos DB. Details: {result.get('error')}"
                logger.error(error_msg)
                # This could create a feedback loop if the exception bus is also down, but it's a risk worth taking.
                await self._send_exception_alert(
                    "LOGGING_FAILURE", 
                    "critical", 
                    error_msg, 
                    loan_application_id
                )

        except Exception as e:
            error_msg = f"Error processing audit message: {str(e)}"
            logger.error(error_msg)
            # Send an alert about the failure to process the audit message itself.
            await self._send_exception_alert(
                "TECHNICAL_ERROR", 
                "high", 
                error_msg, 
                message.get('loan_application_id', 'unknown')
            )

    async def _send_exception_alert(self, exception_type: str, priority: str, message: str, loan_application_id: str):
        """Sends an alert about a failure, in this case, a failure to log."""
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
            # If this fails, we can't do much else but log to console.
            logger.critical(f"FATAL: Could not send exception alert about logging failure. Error: {str(e)}")

    async def close(self):
        if self._initialized:
            if self.cosmos_plugin: await self.cosmos_plugin.close()
            if self.servicebus_plugin: await self.servicebus_plugin.close()
        logger.info(f"{self.agent_name}: Resources cleaned up.")