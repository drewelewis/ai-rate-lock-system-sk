"""
Rate Quote Agent - Autonomous AI Agent
Uses LLM to intelligently generate rate quotes and manage workflow progression.
"""

import asyncio
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

# Import base agent
from agents.base_agent import BaseAgent

# Import additional plugins specific to this agent
from plugins.pricing_engine_plugin import PricingEnginePlugin

logger = logging.getLogger(__name__)

class RateQuoteAgent(BaseAgent):
    """
    Role: Generates rate quotes using a pricing engine.
    
    Tasks:
    - Listens for 'context_retrieved' messages.
    - Fetches the enriched loan record from Cosmos DB.
    - Calls the pricing engine to get rate options.
    - Updates the rate lock record with the quotes and sets status to 'RateOptionsPresented'.
    - Sends a 'rates_presented' message to trigger the Compliance Agent.
    """
    
    def __init__(self):
        self.agent_name = "rate_quote_agent"
        self.session_id = f"quote_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.kernel = None
        self.cosmos_plugin = None
        self.servicebus_plugin = None
        self.pricing_plugin = None
        
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
            self.servicebus_plugin = ServiceBusPlugin()
            self.pricing_plugin = PricingEnginePlugin(debug=True, session_id=self.session_id)
            
            self.kernel.add_plugin(self.cosmos_plugin, plugin_name="cosmos_db")
            self.kernel.add_plugin(self.servicebus_plugin, plugin_name="service_bus")
            self.kernel.add_plugin(self.pricing_plugin, plugin_name="pricing_engine")
            
            self._initialized = True
            logger.info(f"{self.agent_name}: Semantic Kernel initialized successfully")
            
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to initialize Semantic Kernel - {str(e)}")
            raise

    async def handle_message(self, message: Dict[str, Any]):
        """Handles a single message from the service bus."""
        await self._initialize_kernel()
        
        # Message is already parsed and standardized by Service Bus operations
        message_type = message.get('message_type')
        loan_application_id = message.get('loan_application_id')
        
        logger.info(f"{self.agent_name}: Received message '{message_type}' for loan '{loan_application_id}'")

        if message_type != 'context_retrieved':
            logger.warning(f"Received unexpected message type: {message_type}. Skipping.")
            return

        try:
            # 1. Fetch the full loan record from Cosmos DB (returns dict directly, not JSON string)
            rate_lock_record = await self.cosmos_plugin.get_rate_lock(loan_application_id)

            if not rate_lock_record.get("found"):
                raise ValueError(f"Could not retrieve rate lock record for {loan_application_id}")

            # Extract loan_context (LOS data) from the record
            loan_context = rate_lock_record.get("loan_context", {})
            
            # The pricing engine needs the context from the LOS
            if not loan_context:
                raise ValueError(f"Loan context is missing from the rate lock record for {loan_application_id}")

            # 2. Get rate options from the pricing engine (returns JSON string)
            rate_options_str = await self.pricing_plugin.get_rate_options(json.dumps(loan_context))
            rate_options = json.loads(rate_options_str)

            if not rate_options.get("success"):
                raise ValueError(f"Failed to get rate options: {rate_options.get('error')}")

            # 3. Update the Cosmos DB record with the rate options
            record_id = rate_lock_record.get("record_id") or rate_lock_record.get("id")
            if not record_id:
                raise ValueError(f"No record_id found in rate lock record for {loan_application_id}")
            
            update_details = {
                "rate_options": rate_options.get("data"),
                "rates_presented_at": datetime.utcnow().isoformat()
            }
            
            await self.cosmos_plugin.update_rate_lock_status(
                loan_application_id=loan_application_id,
                record_id=record_id,
                new_status="RATES_QUOTED",
                agent_name="rate_quote_agent",
                update_details=json.dumps(update_details)
            )
            
            # 4. Send audit log (using BaseAgent helper method)
            await self._send_audit_log("RATES_GENERATED", loan_application_id, {
                "status": "RATES_QUOTED", 
                "quote_count": len(rate_options.get("data", []))
            })
            
            # 5. Send workflow event for the next agent (Compliance Agent) - using BaseAgent helper method
            # Using "rate_quoted" to match Service Bus subscription filter
            await self._send_workflow_event("rate_quoted", loan_application_id, {
                "loan_application_id": loan_application_id,
                "next_action": "compliance_check"
            })
            logger.info(f"Generated {len(rate_options.get('data', []))} rate options for loan '{loan_application_id}'.")

        except Exception as e:
            error_msg = f"Failed to process rate quote for loan '{loan_application_id}': {str(e)}"
            logger.error(error_msg)
            await self._send_exception_alert("TECHNICAL_ERROR", "high", error_msg, loan_application_id)

    async def process_rate_quote_request(self, rate_lock_id: str):
        """
        Demo method to process a rate quote request.
        Returns rate quote information for demo purposes.
        """
        # Try to initialize kernel, but continue in demo mode if it fails
        try:
            await self._initialize_kernel()
            ai_available = True
        except Exception as e:
            logger.warning(f"AI services unavailable for demo: {str(e)}")
            print(f"      ⚠️  Running in demo mode without AI services")
            ai_available = False
        
        try:
            print(f"      💰 Generating rate quotes for rate lock: {rate_lock_id}")
            
            # Simulate rate calculation process
            await asyncio.sleep(1)  # Simulate processing time
            
            # Generate mock rate quotes
            import random
            base_rate = 6.5 + random.uniform(-0.5, 0.5)
            
            rate_options = [
                {
                    "lock_period_days": 15,
                    "rate": round(base_rate - 0.125, 3),
                    "points": 0.5,
                    "monthly_payment": 2845.67
                },
                {
                    "lock_period_days": 30,
                    "rate": round(base_rate, 3),
                    "points": 0.0,
                    "monthly_payment": 2891.23
                },
                {
                    "lock_period_days": 45,
                    "rate": round(base_rate + 0.125, 3),
                    "points": -0.5,
                    "monthly_payment": 2936.89
                }
            ]
            
            result = {
                "rate_lock_id": rate_lock_id,
                "status": "RATES_PRESENTED",
                "rate_options": rate_options,
                "generated_timestamp": datetime.now().isoformat(),
                "expires_at": (datetime.now().timestamp() + 86400)  # 24 hours
            }
            
            print(f"      ✅ Generated {len(rate_options)} rate options")
            for option in rate_options:
                print(f"         📊 {option['lock_period_days']} days: {option['rate']}% rate, {option['points']} points")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in process_rate_quote_request demo: {str(e)}")
            print(f"      ❌ Error generating rate quotes: {str(e)}")
            return None

    def get_agent_status(self):
        """
        Returns the current status of the rate quote agent.
        """
        return {
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "initialized": self._initialized,
            "processing": self._is_processing,
            "status": "READY" if self._initialized else "INITIALIZING"
        }

    async def register_for_workflow_messages(self):
        """
        Demo method to simulate registering for workflow messages.
        Returns True to indicate successful registration.
        """
        try:
            print(f"      📡 Registering {self.agent_name} for workflow messages...")
            await asyncio.sleep(0.5)  # Simulate registration time
            print(f"      ✅ Successfully registered for Service Bus messages")
            return True
        except Exception as e:
            logger.error(f"Failed to register for workflow messages: {str(e)}")
            return False

    async def _send_audit_log(self, action: str, loan_application_id: str, audit_data: Dict[str, Any] = None):
        """Send audit log to Service Bus."""
        audit_payload = audit_data or {}
        
        try:
            await self.servicebus_plugin.send_audit_log(
                agent_name=self.agent_name,
                action=action,
                loan_application_id=loan_application_id,
                event_type="AGENT_ACTION",
                audit_data=json.dumps(audit_payload)
            )
        except Exception as e:
            logger.error(f"Failed to send audit log: {e}")

    async def _send_workflow_event(self, message_type: str, loan_application_id: str, message_data: Dict[str, Any]):
        """Send workflow event to Service Bus."""
        try:
            await self.servicebus_plugin.send_workflow_event(
                message_type=message_type,
                loan_application_id=loan_application_id,
                message_data=json.dumps(message_data),
                correlation_id=self.session_id
            )
        except Exception as e:
            logger.error(f"Failed to send workflow event: {e}")

    async def _send_exception_alert(self, exception_type: str, priority: str, error_message: str, loan_id: str):
        """Send exception alert to Service Bus."""
        try:
            await self.servicebus_plugin.send_exception(
                exception_type=exception_type,
                priority=priority,
                loan_application_id=loan_id,
                error_message=error_message,
                agent_name=self.agent_name
            )
        except Exception as e:
            logger.error(f"Failed to send exception alert: {e}")

    async def close(self):
        if self._initialized:
            if self.cosmos_plugin: await self.cosmos_plugin.close()
            if self.servicebus_plugin: await self.servicebus_plugin.close()
            if self.pricing_plugin: await self.pricing_plugin.close()
        logger.info(f"{self.agent_name}: Resources cleaned up.")