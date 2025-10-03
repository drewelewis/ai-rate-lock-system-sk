"""
Exception Handler Agent
Escalates complex cases and issues to human loan officers for review.
"""

import asyncio
import json
from typing import Dict, Any
from datetime import datetime, timedelta
import logging
import os

# Semantic Kernel imports
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.functions import kernel_function

# Import our plugins
from plugins.cosmos_db_plugin import CosmosDBPlugin
from plugins.service_bus_plugin import ServiceBusPlugin

logger = logging.getLogger(__name__)

class ExceptionHandlerAgent:
    """
    Role: Manages and escalates exceptions for human review.
    
    Tasks:
    - Listens for 'exception_alert' messages.
    - Uses an LLM to analyze, summarize, and categorize the exception.
    - Creates a detailed exception record in the 'Exceptions' container in Cosmos DB.
    - (Future) Assigns exceptions to the appropriate team/person based on rules.
    - (Future) Sends notifications about new high-priority exceptions.
    """
    
    def __init__(self):
        self.agent_name = "exception_handler_agent"
        self.session_id = f"exception_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

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
            
            endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
            api_key = os.environ.get("AZURE_OPENAI_API_KEY") 
            deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
            
            if not all([endpoint, api_key, deployment_name]):
                raise ValueError("Missing Azure OpenAI configuration for Exception Handler Agent.")

            self.kernel.add_service(AzureChatCompletion(
                deployment_name=deployment_name,
                endpoint=endpoint,
                api_key=api_key
            ))
            
            self.cosmos_plugin = CosmosDBPlugin(debug=True, session_id=self.session_id)
            self.servicebus_plugin = ServiceBusPlugin(debug=True, session_id=self.session_id)
            
            self.kernel.add_plugin(self.cosmos_plugin, plugin_name="cosmos_db")
            self.kernel.add_plugin(self.servicebus_plugin, plugin_name="service_bus")
            self.kernel.add_plugin(self, plugin_name="exception_analyzer")
            
            self._initialized = True
            logger.info(f"{self.agent_name}: Semantic Kernel initialized successfully")
            
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to initialize Semantic Kernel - {str(e)}")
            raise

    async def handle_message(self, message: Dict[str, Any]):
        """Handles a single exception message from the service bus."""
        await self._initialize_kernel()
        
        message_type = message.get('message_type')
        
        if message_type != 'exception_alert':
            logger.warning(f"Received unexpected message type: {message_type}. Skipping.")
            return

        try:
            priority = message.get('priority', 'medium')
            exception_type = message.get('exception_type', 'UNKNOWN')
            loan_application_id = message.get('loan_application_id')
            exception_data = message.get('exception_data', {})
            
            logger.info(f"Processing '{priority}' priority exception '{exception_type}' for loan '{loan_application_id}'")

            # Use the LLM to analyze the exception
            analysis_result_str = await self.kernel.invoke(
                self.kernel.plugins["exception_analyzer"]["analyze_exception"],
                exception_type=exception_type,
                error_message=exception_data.get("error_message", "No message provided."),
                context=json.dumps(exception_data)
            )
            analysis_result = json.loads(str(analysis_result_str))

            # Prepare the record for Cosmos DB
            exception_payload = {
                "loan_application_id": loan_application_id,
                "exception_type": exception_type,
                "agent_name": exception_data.get("agent", "Unknown"),
                "description": analysis_result.get("summary", "Analysis failed."),
                "context": exception_data,
                "assignee": analysis_result.get("suggested_assignee", "unassigned"),
                "estimated_resolution_time": analysis_result.get("estimated_resolution_time_hrs", 8)
            }

            # Call the CosmosDB plugin to create the exception record
            result_str = await self.cosmos_plugin.create_exception(priority, json.dumps(exception_payload))
            result = json.loads(result_str)

            if not result.get("success"):
                # This is a critical failure. If we can't log exceptions, the system is blind.
                error_msg = f"CRITICAL: Failed to create exception record in Cosmos DB. Details: {result.get('error')}"
                logger.error(error_msg)
                # We won't send another exception alert to avoid a loop. Just log it.
            else:
                logger.info(f"Successfully created exception record {result.get('data', {}).get('exception_id')} for loan '{loan_application_id}'")

        except Exception as e:
            # This is the 'meta-exception'. An exception occurred within the exception handler itself.
            error_msg = f"FATAL: Unhandled error in ExceptionHandlerAgent: {str(e)}"
            logger.critical(error_msg)
            # At this point, we can't trust our own exception bus. The best we can do is log to console.

    @kernel_function(
        description="Analyzes a technical or business exception and provides a summary, suggested assignee, and estimated resolution time.",
        name="analyze_exception"
    )
    def analyze_exception(
        self,
        exception_type: str,
        error_message: str,
        context: str
    ) -> str:
        """
        Uses an LLM to analyze an exception and return a structured JSON response.
        
        The prompt is designed to guide the LLM to provide a consistent, structured output
        that can be used to create a ticket or alert for human intervention.
        """
        
        prompt = f"""
        Analyze the following exception from our automated rate lock system and provide a structured JSON response.

        **Exception Details:**
        - Type: {exception_type}
        - Error Message: {error_message}
        - Full Context: {context}

        **Your Task:**
        Based on the information, generate a JSON object with the following keys:
        1. "summary": A concise, one-sentence summary of the problem for a human loan officer or IT support person.
        2. "suggested_assignee": Who should handle this? Your options are "Loan Officer", "IT Support", "Compliance Team", or "unassigned". Base this on the exception type and message.
        3. "estimated_resolution_time_hrs": An integer estimate of the hours needed to resolve this.

        **Assignee Guidelines:**
        - "COMPLIANCE_RISK": Assign to "Compliance Team".
        - "PRICING_UNAVAILABLE", "TECHNICAL_ERROR", "LOGGING_FAILURE": Assign to "IT Support".
        - "MISSING_DATA", "INVALID_LOAN_DATA": Assign to "Loan Officer".
        - If unsure, use "unassigned".

        **Example Response:**
        {{
            "summary": "The compliance check failed because the borrower's debt-to-income ratio exceeds the maximum allowed limit.",
            "suggested_assignee": "Compliance Team",
            "estimated_resolution_time_hrs": 2
        }}

        **JSON Response:**
        """
        # In a real scenario, you would invoke the LLM here.
        # For this simulation, we are returning a pre-canned response based on the type.
        
        if "COMPLIANCE" in exception_type.upper():
            assignee = "Compliance Team"
            summary = f"A compliance rule failed during processing. Details: {error_message}"
            hours = 4
        elif any(err in exception_type.upper() for err in ["TECHNICAL", "PRICING", "LOGGING"]):
            assignee = "IT Support"
            summary = f"A technical error occurred in the '{json.loads(context).get('agent', 'unknown')}' agent. Details: {error_message}"
            hours = 8
        else:
            assignee = "Loan Officer"
            summary = f"There is an issue with the loan data provided. Details: {error_message}"
            hours = 2

        return json.dumps({
            "summary": summary,
            "suggested_assignee": assignee,
            "estimated_resolution_time_hrs": hours
        })

    async def close(self):
        if self._initialized:
            if self.cosmos_plugin: await self.cosmos_plugin.close()
            if self.servicebus_plugin: await self.servicebus_plugin.close()
        logger.info(f"{self.agent_name}: Resources cleaned up.")