"""
Lock Confirmation Agent
Executes the rate lock and sends confirmation notifications via Service Bus.
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

# Import our plugins
from plugins.cosmos_db_plugin import CosmosDBPlugin
from plugins.service_bus_plugin import ServiceBusPlugin
from plugins.pricing_engine_plugin import PricingEnginePlugin
from plugins.los_plugin import LoanOriginationSystemPlugin
from plugins.document_plugin import DocumentPlugin

logger = logging.getLogger(__name__)

class LockConfirmationAgent:
    """
    Role: Executes the lock and sends confirmation notifications.
    
    Tasks:
    - Listens for 'compliance_passed' messages.
    - Fetches the loan record.
    - Submits the final lock request to the pricing engine/LOS.
    - Generates a lock confirmation document.
    - Sends messages to Service Bus to trigger confirmation emails.
    - Updates the rate lock record with the final 'Locked' status.
    """
    
    def __init__(self):
        self.agent_name = "lock_confirmation_agent"
        self.session_id = f"lock_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.kernel = None
        self.cosmos_plugin = None
        self.servicebus_plugin = None
        self.pricing_plugin = None
        self.los_plugin = None
        self.document_plugin = None
        
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
            
            if endpoint and api_key:
                self.kernel.add_service(AzureChatCompletion(
                    deployment_name=deployment_name,
                    endpoint=endpoint,
                    api_key=api_key
                ))
            
            self.cosmos_plugin = CosmosDBPlugin(debug=True, session_id=self.session_id)
            self.servicebus_plugin = ServiceBusPlugin(debug=True, session_id=self.session_id)
            self.pricing_plugin = PricingEnginePlugin(debug=True, session_id=self.session_id)
            self.los_plugin = LoanOriginationSystemPlugin(debug=True, session_id=self.session_id)
            self.document_plugin = DocumentPlugin(debug=True, session_id=self.session_id)
            
            self.kernel.add_plugin(self.cosmos_plugin, plugin_name="cosmos_db")
            self.kernel.add_plugin(self.servicebus_plugin, plugin_name="service_bus")
            self.kernel.add_plugin(self.pricing_plugin, plugin_name="pricing_engine")
            self.kernel.add_plugin(self.los_plugin, plugin_name="los")
            self.kernel.add_plugin(self.document_plugin, plugin_name="document")
            
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

        if message_type != 'compliance_passed':
            logger.warning(f"Received unexpected message type: {message_type}. Skipping.")
            return

        try:
            # 1. Fetch the full loan record from Cosmos DB
            rate_lock_record_str = await self.cosmos_plugin.get_rate_lock(loan_application_id)
            rate_lock_record = json.loads(rate_lock_record_str)

            if not rate_lock_record.get("success"):
                raise ValueError(f"Could not retrieve rate lock record for {loan_application_id}")

            loan_data = rate_lock_record.get("data", {})
            
            # Assume the borrower selected the first rate option for this simulation
            selected_rate = loan_data.get("rate_options", [{}])[0]
            if not selected_rate:
                raise ValueError("No rate options found in the record to lock.")

            # 2. Execute the rate lock with the pricing engine
            lock_result_str = await self.pricing_plugin.execute_rate_lock(json.dumps(selected_rate))
            lock_result = json.loads(lock_result_str)

            if not lock_result.get("success"):
                raise ValueError(f"Failed to execute rate lock: {lock_result.get('error')}")
            
            lock_details = lock_result.get("data", {})

            # 3. Generate the confirmation document
            doc_result_str = await self.document_plugin.generate_lock_confirmation(json.dumps(loan_data), json.dumps(lock_details))
            doc_result = json.loads(doc_result_str)
            if not doc_result.get("success"):
                logger.warning(f"Failed to generate confirmation document: {doc_result.get('error')}")
                confirmation_doc = None
            else:
                confirmation_doc = doc_result.get("data")

            # 4. Send confirmation email notifications via Service Bus
            borrower_info = loan_data.get("los_data", {}).get("borrower_info", {})
            loan_officer_info = loan_data.get("los_data", {}).get("loan_officer_info", {})
            
            await self._send_confirmation_notifications(borrower_info, loan_officer_info, loan_application_id, lock_details, confirmation_doc)

            # 5. Update the Cosmos DB record with the final status
            new_status = "Locked"
            update_payload = {
                "status": new_status,
                "lock_details": lock_details,
                "locked_at": datetime.utcnow().isoformat(),
                "confirmation_document_id": confirmation_doc.get("document_id") if confirmation_doc else None
            }
            await self.cosmos_plugin.update_rate_lock(loan_application_id, json.dumps(update_payload))
            
            # 6. Send final audit message
            await self._send_audit_message("RATE_LOCKED", loan_application_id, {
                "status": new_status,
                "lock_id": lock_details.get("confirmation_id")
            })
            
            logger.info(f"Rate lock successfully executed and confirmed for loan '{loan_application_id}'.")

        except Exception as e:
            error_msg = f"Failed to process lock confirmation for loan '{loan_application_id}': {str(e)}"
            logger.error(error_msg)
            await self._send_exception_alert("TECHNICAL_ERROR", "high", error_msg, loan_application_id)

    async def _send_confirmation_notifications(self, borrower_info, loan_officer_info, loan_id, lock_details, document):
        """Sends messages to Service Bus to trigger confirmation emails."""
        # Send to borrower
        if borrower_info.get("email"):
            subject = f"Rate Lock Confirmed for Loan {loan_id}"
            body = self._create_email_body(borrower_info.get("name", "Borrower"), loan_id, lock_details)
            
            # The attachment needs to be base64 encoded for the Logic App
            attachment_payload = None
            if document and document.get("content_base64"):
                 attachment_payload = [{
                    "Name": document.get("filename", "RateLockConfirmation.pdf"),
                    "ContentBytes": document.get("content_base64")
                }]

            await self._send_email_notification(
                recipient_email=borrower_info["email"],
                subject=subject,
                body=body,
                loan_id=loan_id,
                attachments=attachment_payload
            )
        
        # Send to loan officer
        if loan_officer_info.get("email"):
            subject = f"ACTION: Rate Lock Executed for {loan_id}"
            body = self._create_email_body(loan_officer_info.get("name", "Loan Officer"), loan_id, lock_details, is_lo=True)
            await self._send_email_notification(
                recipient_email=loan_officer_info["email"],
                subject=subject,
                body=body,
                loan_id=loan_id
            )

    async def _send_email_notification(self, recipient_email: str, subject: str, body: str, loan_id: str, attachments: list = None):
        """Constructs and sends an email notification message to the outbound Service Bus topic."""
        email_payload = {
            "recipient_email": recipient_email,
            "subject": subject,
            "body": body,
            "attachments": attachments or []
        }
        
        await self.servicebus_plugin.send_message_to_topic(
            topic_name="outbound_email",
            message_type="send_email_notification",
            loan_application_id=loan_id,
            message_data=email_payload
        )
        logger.info(f"Sent email notification request to Service Bus for '{recipient_email}'")


    def _create_email_body(self, recipient_name, loan_id, lock_details, is_lo=False):
        """Creates a formatted email body."""
        lock_expiration_str = lock_details.get('lock_expiration_date', 'N/A')
        try:
            # Format the date for readability
            lock_expiration_date = datetime.fromisoformat(lock_expiration_str).strftime('%B %d, %Y')
        except (ValueError, TypeError):
            lock_expiration_date = lock_expiration_str

        body = f"Dear {recipient_name},\n\n"
        if is_lo:
            body += f"A rate lock has been executed for loan application {loan_id}.\n\n"
        else:
            body += f"Great news! Your rate lock for loan application {loan_id} is confirmed.\n\n"
        
        body += "Here are the details:\n"
        body += f"- Interest Rate: {lock_details.get('interest_rate')}%\n"
        body += f"- Lock Period: {lock_details.get('lock_period_days')} days\n"
        body += f"- Lock Expiration Date: {lock_expiration_date}\n"
        body += f"- Confirmation ID: {lock_details.get('confirmation_id')}\n\n"
        
        if not is_lo:
            body += "Your rate is now protected from market changes until the expiration date. Please work with your loan officer to complete any outstanding items.\n\n"
        
        body += "Thank you,\nThe Rate Lock Team"
        return body

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
            if self.pricing_plugin: await self.pricing_plugin.close()
            if self.los_plugin: await self.los_plugin.close()
            if self.document_plugin: await self.document_plugin.close()
        logger.info(f"{self.agent_name}: Resources cleaned up.")