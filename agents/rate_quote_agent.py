"""
Rate Quote Agent
Connects to a pricing engine to generate rate options based on the loan context.
"""

import asyncio
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import os

# Semantic Kernel imports
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

# Import our plugins
from plugins.cosmos_db_plugin import CosmosDBPlugin
from plugins.service_bus_plugin import ServiceBusPlugin
from plugins.pricing_engine_plugin import PricingEnginePlugin

logger = logging.getLogger(__name__)

class RateQuoteAgent:
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
            self.servicebus_plugin = ServiceBusPlugin(debug=True, session_id=self.session_id)
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
        
        message_type = message.get('message_type')
        loan_application_id = message.get('loan_application_id')
        
        logger.info(f"{self.agent_name}: Received message '{message_type}' for loan '{loan_application_id}'")

        if message_type != 'context_retrieved':
            logger.warning(f"Received unexpected message type: {message_type}. Skipping.")
            return

        try:
            # 1. Fetch the full loan record from Cosmos DB
            rate_lock_record_str = await self.cosmos_plugin.get_rate_lock(loan_application_id)
            rate_lock_record = json.loads(rate_lock_record_str)

            if not rate_lock_record.get("success"):
                raise ValueError(f"Could not retrieve rate lock record for {loan_application_id}")

            loan_data = rate_lock_record.get("data", {})
            los_data = loan_data.get("los_data", {})
            
            # The pricing engine needs the context from the LOS
            if not los_data:
                raise ValueError(f"LOS data is missing from the rate lock record for {loan_application_id}")

            # 2. Get rate options from the pricing engine
            rate_options_str = await self.pricing_plugin.get_rate_options(json.dumps(los_data))
            rate_options = json.loads(rate_options_str)

            if not rate_options.get("success"):
                raise ValueError(f"Failed to get rate options: {rate_options.get('error')}")

            # 3. Update the Cosmos DB record with the rate options
            new_status = "RateOptionsPresented"
            update_payload = {
                "status": new_status,
                "rate_options": rate_options.get("data"),
                "rates_presented_at": datetime.utcnow().isoformat()
            }
            await self.cosmos_plugin.update_rate_lock(loan_application_id, json.dumps(update_payload))
            
            # 4. Send audit message
            await self._send_audit_message("RATES_GENERATED", loan_application_id, {
                "status": new_status, 
                "quote_count": len(rate_options.get("data", []))
            })
            
            # 5. Send workflow message for the next agent
            await self._send_workflow_message("rates_presented", loan_application_id, {
                "loan_application_id": loan_application_id,
                "next_action": "compliance_check"
            })
            logger.info(f"Generated {len(rate_options.get('data', []))} rate options for loan '{loan_application_id}'.")

        except Exception as e:
            error_msg = f"Failed to process rate quote for loan '{loan_application_id}': {str(e)}"
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

    async def close(self):
        if self._initialized:
            if self.cosmos_plugin: await self.cosmos_plugin.close()
            if self.servicebus_plugin: await self.servicebus_plugin.close()
            if self.pricing_plugin: await self.pricing_plugin.close()
        logger.info(f"{self.agent_name}: Resources cleaned up.")