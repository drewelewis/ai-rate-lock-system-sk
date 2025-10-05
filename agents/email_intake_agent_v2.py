"""
Email Intake Agent - Simplified LLM-based implementation.

Responsibility: Parse incoming emails and create rate lock requests.

This agent is a THIN wrapper around an LLM call that:
1. Receives raw email content
2. Asks LLM to extract structured loan data
3. Uses plugins to store data and route to next agent

NO custom parsing logic - LLM handles all natural language understanding!
"""

import logging
import json
from typing import Dict, Any
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class EmailIntakeAgent(BaseAgent):
    """
    Email Intake Agent - extracts loan data from emails using LLM.
    
    Agent follows the clean architecture pattern:
    - Inherits from BaseAgent for standard message handling
    - Overrides _get_system_prompt() to define LLM instructions
    - Overrides _process_llm_response() to handle LLM output using plugins
    - NO custom business logic - everything delegated to LLM or plugins
    """
    
    def __init__(self):
        """Initialize Email Intake Agent."""
        super().__init__(agent_name="email_intake")
    
    def _get_system_prompt(self) -> str:
        """Define the LLM system prompt for email parsing."""
        return """You are an AI agent that extracts structured loan data from mortgage broker emails.

Your task is to parse incoming emails and extract the following information:
- loan_application_id: The loan application ID (required)
- borrower_name: Full name of the borrower
- borrower_email: Contact email address
- borrower_phone: Contact phone number
- property_address: Full property address
- requested_lock_period_days: Number of days to lock the rate (default: 30)
- loan_amount: Requested loan amount
- loan_type: Type of loan (Conventional, FHA, VA, etc.)
- credit_score: Borrower's credit score
- property_type: Type of property (Single Family, Condo, etc.)

CRITICAL RULES:
1. loan_application_id MUST be present in the email - extract it exactly as shown
2. If loan_application_id is missing or you cannot find it, return {"error": "MISSING_LOAN_ID"}
3. Do NOT generate placeholder IDs like "APP-XXXXXX" - extract the real ID
4. Extract borrower_email from the From: header if not in body
5. Return ONLY valid JSON with the extracted fields
6. Use null for missing optional fields

Return your response as a JSON object with the extracted fields."""
    
    async def _process_llm_response(self, llm_response: str, original_message: Dict[str, Any]):
        """
        Process LLM response and take action using plugins.
        
        NO custom logic here - just parse JSON and delegate to plugins!
        """
        try:
            # Parse LLM response as JSON
            extracted_data = json.loads(llm_response.strip())
            
            # Check for missing loan ID
            if "error" in extracted_data and extracted_data["error"] == "MISSING_LOAN_ID":
                logger.warning(f"{self.agent_name}: LLM could not extract loan ID - requesting from user")
                await self._request_loan_id_from_user(extracted_data, original_message)
                return
            
            loan_id = extracted_data.get('loan_application_id')
            
            if not loan_id:
                logger.error(f"{self.agent_name}: Missing loan_application_id in LLM response")
                await self.servicebus_plugin.send_exception_alert(
                    exception_type="MISSING_LOAN_ID",
                    priority="high",
                    message="Could not extract loan ID from email",
                    loan_application_id="unknown"
                )
                return
            
            logger.info(f"{self.agent_name}: Successfully extracted loan ID: {loan_id}")
            
            # Create rate lock record in Cosmos DB using plugin
            await self.cosmos_plugin.create_rate_lock(
                loan_application_id=loan_id,
                borrower_name=extracted_data.get('borrower_name'),
                borrower_email=extracted_data.get('borrower_email'),
                borrower_phone=extracted_data.get('borrower_phone'),
                property_address=extracted_data.get('property_address'),
                requested_lock_period=str(extracted_data.get('requested_lock_period_days', 30)),
                additional_data=json.dumps({
                    "status": "PENDING_CONTEXT",
                    "extracted_data": extracted_data,
                    "source": "email_intake"
                })
            )
            
            # Send to next agent in workflow using plugin
            await self.servicebus_plugin.send_workflow_event(
                message_type="context_retrieval_needed",
                loan_application_id=loan_id,
                body=extracted_data
            )
            
            # Send audit event using plugin
            await self.servicebus_plugin.send_audit_event(
                action="EMAIL_PROCESSED",
                loan_application_id=loan_id,
                data={"extracted_fields": list(extracted_data.keys())}
            )
            
            logger.info(f"{self.agent_name}: Successfully processed email for loan {loan_id}")
            
        except json.JSONDecodeError as e:
            logger.error(f"{self.agent_name}: LLM returned invalid JSON: {e}")
            logger.error(f"{self.agent_name}: LLM Response: {llm_response}")
            raise
        except Exception as e:
            logger.error(f"{self.agent_name}: Error processing LLM response: {e}")
            raise
    
    async def _request_loan_id_from_user(self, extracted_data: Dict[str, Any], original_message: Dict[str, Any]):
        """
        Request missing loan ID from user using Service Bus plugin.
        
        Sends message to exception handler queue for manual intervention.
        """
        await self.servicebus_plugin.send_exception_alert(
            exception_type="MISSING_LOAN_ID_REQUEST",
            priority="medium",
            message=f"Email received but missing loan application ID. Extracted data: {json.dumps(extracted_data)}",
            loan_application_id="unknown"
        )
        
        logger.info(f"{self.agent_name}: Sent loan ID request to exception handler")
    
    def _build_user_message(self, message_type: str, loan_id: str, body: Any, metadata: Dict) -> str:
        """
        Override to provide email-specific message format.
        
        For email queue, body contains raw email text.
        """
        # body is the raw email content
        email_content = body if isinstance(body, str) else str(body)
        
        return f"""Parse the following email and extract loan information as JSON:

{email_content}

Return ONLY a JSON object with the extracted fields."""
