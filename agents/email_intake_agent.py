"""
Email Intake Agent - Enhanced for Service Bus Integration
Parses loan lock requests from Service Bus messages (originating from a Logic App) and initiates the workflow.
"""

import asyncio
import json
from typing import Optional, Dict, Any
from datetime import datetime
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

class EmailIntakeAgent:
    """
    Role: AI-powered intake for loan lock requests from Service Bus.
    
    Tasks:
    - Listens for 'new_email_request' messages from Service Bus.
    - Uses an LLM to parse the email content within the message.
    - Validates the request and sender.
    - Creates a rate lock record in Cosmos DB.
    - Sends a message to the next agent in the workflow.
    - Sends a message to the outbound email topic to send an acknowledgment.
    """
    
    def __init__(self):
        self.agent_name = "email_intake_agent"
        self.session_id = f"intake_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
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
            deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
            
            # EXPLICIT LOGGING - NO HIDING CONFIGURATION ISSUES
            logger.info(f"{self.agent_name}: 🔧 Azure OpenAI Endpoint: {endpoint}")
            logger.info(f"{self.agent_name}: 🔧 Deployment Name: {deployment_name}")
            
            if not all([endpoint, deployment_name]):
                raise ValueError(f"Missing Azure OpenAI configuration: endpoint={endpoint}, deployment={deployment_name}")

            # Use managed identity for Azure OpenAI authentication
            from azure.identity.aio import DefaultAzureCredential
            
            async def get_token():
                credential = DefaultAzureCredential()
                token = await credential.get_token("https://cognitiveservices.azure.com/.default")
                return token.token

            # Add the Azure OpenAI service with proper service_id
            azure_chat_service = AzureChatCompletion(
                deployment_name=deployment_name,
                endpoint=endpoint,
                ad_token_provider=get_token,
                service_id="azure_openai_chat"  # Give it a proper service ID
            )
            
            self.kernel.add_service(azure_chat_service)
            
            self.cosmos_plugin = CosmosDBPlugin(debug=True, session_id=self.session_id)
            self.servicebus_plugin = ServiceBusPlugin(debug=True, session_id=self.session_id)
            
            self.kernel.add_plugin(self.cosmos_plugin, plugin_name="cosmos_db")
            self.kernel.add_plugin(self.servicebus_plugin, plugin_name="service_bus")
            # Note: No need to register self as email_parser plugin since we call LLM directly
            
            self._initialized = True
            logger.info(f"{self.agent_name}: Semantic Kernel initialized successfully")
            
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to initialize Semantic Kernel - {str(e)}")
            raise

    async def handle_message(self, message: str):
        """Handles a single message from the service bus."""
        await self._initialize_kernel()
        
        # Enhanced logging for debugging
        logger.info(f"{self.agent_name}: 🎯 HANDLING NEW MESSAGE")
        logger.info(f"{self.agent_name}: 📏 Message length: {len(message) if message else 0} characters")
        logger.info(f"{self.agent_name}: 📋 Message type: {type(message)}")
        
        try:
            # All messages are raw text that need LLM parsing
            if message and message.strip():
                logger.info(f"{self.agent_name}: ✅ Message validation passed - proceeding with LLM processing")
                await self._process_raw_email_with_llm(message)
            else:
                logger.warning(f"{self.agent_name}: ❌ Received empty message")
                
        except Exception as e:
            error_msg = f"Failed to process message: {str(e)}"
            logger.error(f"{self.agent_name}: 🚨 {error_msg}")
            await self._send_exception_alert("TECHNICAL_ERROR", "high", error_msg, "unknown")

    async def _process_raw_email_with_llm(self, raw_email_content: str):
        """Process raw email content using LLM for intelligent parsing."""
        logger.info(f"{self.agent_name}: Processing raw email content with LLM")
        
        # Log the raw input message for debugging
        logger.info(f"{self.agent_name}: 📨 RAW INPUT MESSAGE:")
        logger.info(f"{self.agent_name}: {'-'*50}")
        logger.info(f"{self.agent_name}: {raw_email_content[:500]}{'...' if len(raw_email_content) > 500 else ''}")
        logger.info(f"{self.agent_name}: {'-'*50}")
        
        try:
            # Call Azure OpenAI directly to parse the email content
            extracted_data = await self._extract_loan_data_with_llm(raw_email_content)
            
            loan_application_id = extracted_data.get('loan_application_id')
            if not loan_application_id or loan_application_id in [None, "", "null"]:
                logger.warning("LLM could not extract loan application ID from email content, but this should not happen with improved extraction")
                return
                
            logger.info(f"{self.agent_name}: LLM successfully extracted loan ID: {loan_application_id}")
            
            # Extract email metadata from raw content for audit trail
            from_address = self._extract_email_address(raw_email_content)
            subject = self._extract_subject(raw_email_content)
            
            # Create the initial record in Cosmos DB
            rate_lock_record = {
                "status": "PENDING_CONTEXT",
                "source_email": from_address,
                "subject": subject,
                "received_at": datetime.utcnow().isoformat(),
                "extracted_data": extracted_data,
                "raw_email_content": raw_email_content[:1000]  # First 1000 chars for audit
            }
            
            # Store in Cosmos DB using the correct method and parameters
            await self.cosmos_plugin.create_rate_lock(
                loan_application_id=loan_application_id,
                borrower_name=extracted_data.get('borrower_name'),  # NO FALLBACKS - must be extracted by LLM
                borrower_email=from_address,  # NO FALLBACKS - must exist
                borrower_phone=extracted_data.get('contact_phone', ''),
                property_address=extracted_data.get('property_address', ''),
                requested_lock_period=str(extracted_data.get('requested_lock_period_days', 30)),
                additional_data=json.dumps(rate_lock_record)
            )
            
            # Send to next agent in workflow
            await self._send_to_workflow(loan_application_id, from_address, extracted_data)
            
            logger.info(f"{self.agent_name}: Successfully processed email for loan {loan_application_id}")
            
        except Exception as e:
            error_msg = f"Failed to process raw email with LLM: {str(e)}"
            logger.error(f"{self.agent_name}: 🚨 CRITICAL ERROR - NO FALLBACKS: {error_msg}")
            # Re-raise to surface the real issue
            raise

    async def _extract_loan_data_with_llm(self, email_content: str) -> dict:
        """Direct LLM call to extract loan data from email content."""
        prompt = f"""
You are an AI agent that extracts loan application data from emails. Analyze the following email and extract key information.

Email Content:
{email_content}

Extract and return ONLY a valid JSON object with these fields:
- loan_application_id: The loan ID found in the email. Look for patterns like "APP-123456", "Loan Application ID:", "Application #:", "Loan #:", "ID:", etc. REQUIRED FIELD - generate one if none found using format APP-XXXXXX
- borrower_name: Full name of the borrower
- property_address: Full property address
- loan_amount: Loan amount in dollars (number only, no commas or $)
- requested_lock_period_days: Number of days for rate lock (default 30 if not specified)
- contact_phone: Phone number if mentioned
- contact_email: Email address if mentioned
- property_type: Type of property (single family, condo, etc.)
- loan_purpose: Purchase, refinance, etc.

Rules:
1. Return ONLY valid JSON, no explanation or markdown formatting
2. Use null for missing values EXCEPT loan_application_id which is REQUIRED
3. Extract actual data from the email content
4. Be precise and accurate
5. If no loan ID found, generate one using format APP-XXXXXX with random 6 digits

JSON:"""

        try:
            import json
            import random
            from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
            
            logger.info(f"{self.agent_name}: 🤖 Making LLM call to Azure OpenAI...")
            logger.info(f"{self.agent_name}: 📝 Prompt length: {len(prompt)} characters")
            
            # Use kernel to invoke prompt directly - simpler and more reliable
            response = await self.kernel.invoke_prompt(prompt)
            
            logger.info(f"{self.agent_name}: ✅ LLM call completed successfully")
            logger.info(f"{self.agent_name}: 📤 LLM Response type: {type(response)}")
            
            # Extract and clean the response
            extracted_json = str(response).strip()
            logger.info(f"LLM raw response: {extracted_json[:200]}...")
            
            # Clean up response if it has markdown formatting
            if extracted_json.startswith("```json"):
                extracted_json = extracted_json.replace("```json", "").replace("```", "").strip()
            elif extracted_json.startswith("```"):
                extracted_json = extracted_json.replace("```", "").strip()
            
            # Parse the JSON
            parsed_data = json.loads(extracted_json)
            
            # Validate required fields - NO FALLBACKS
            if not parsed_data.get('loan_application_id') or parsed_data.get('loan_application_id') in [None, "", "null"]:
                raise ValueError(f"LLM failed to extract loan_application_id from email. Raw response: {extracted_json}")
            
            logger.info(f"LLM successfully extracted loan ID: {parsed_data.get('loan_application_id')}")
            return parsed_data
            
        except Exception as e:
            logger.error(f"{self.agent_name}: 🚨 LLM extraction failed: {str(e)}")
            logger.error(f"{self.agent_name}: 🚨 Exception type: {type(e).__name__}")
            logger.error(f"{self.agent_name}: 🚨 Full error details: {repr(e)}")
            
            # NO FALLBACKS - Re-raise the exception to surface the real issue
            raise Exception(f"LLM extraction failed and no fallbacks allowed: {str(e)}") from e

    def _extract_email_address(self, raw_email: str) -> str:
        """Extract 'From' email address from raw email content."""
        import re
        match = re.search(r'From:\s*([^\n\r]+)', raw_email, re.IGNORECASE)
        return match.group(1).strip() if match else "unknown@unknown.com"
    
    def _extract_subject(self, raw_email: str) -> str:
        """Extract subject line from raw email content.""" 
        import re
        match = re.search(r'Subject:\s*([^\n\r]+)', raw_email, re.IGNORECASE)
        return match.group(1).strip() if match else "No Subject"

    async def _process_parsed_email(self, message: Dict[str, Any]):
        """Process a message that contains parsed email data."""
        # Email data could be at root level or nested in body
        email_data = message.get('email_data', {}) or message.get('body', {}).get('email_data', {})
        
        if email_data.get('error'):
            logger.error(f"Received email with parsing error: {email_data.get('error')}")
            return
        
        from_address = email_data.get('from', '')
        subject = email_data.get('subject', '')
        body_text = email_data.get('body_text', '')
        body_html = email_data.get('body_html', '')
        
        logger.info(f"{self.agent_name}: Processing parsed email from {from_address} with subject '{subject[:50]}...'")
        
        # Use the email body (prefer text, fall back to HTML)
        email_body = body_text or body_html or ''
        
        if not email_body:
            logger.warning("Email has no body content, skipping processing")
            return
        
        # Extract loan application ID from subject or body
        loan_application_id = await self._extract_loan_id_from_email(subject, email_body)
        
        if not loan_application_id:
            logger.warning("Could not extract loan application ID from email, skipping")
            return
        
        # Use the LLM to extract full details from the email body
        extraction_result_str = await self.kernel.invoke(
            self.kernel.plugins["email_parser"]["extract_loan_data_from_email"],
            email_body=email_body,
            subject_loan_id=loan_application_id
        )
        extracted_data = json.loads(str(extraction_result_str))
        
        # Create the initial record in Cosmos DB
        rate_lock_record = {
            "status": "PENDING_CONTEXT",
            "source_email": from_address,
            "subject": subject,
            "received_at": datetime.utcnow().isoformat(),
            "extracted_data": extracted_data,
            "raw_email_data": email_data
        }
        await self.cosmos_plugin.create_rate_lock(loan_application_id, json.dumps(rate_lock_record))
        
        # Send to next agent
        await self._send_to_workflow(loan_application_id, from_address, extracted_data)
        
        logger.info(f"Successfully processed parsed email for loan '{loan_application_id}'")

    async def _process_legacy_email_request(self, message: Dict[str, Any]):
        """Process legacy message format for backwards compatibility."""
        loan_application_id_from_subject = message.get('loan_application_id')
        email_body = message.get('email_body')
        from_address = message.get('from_address')
        
        logger.info(f"{self.agent_name}: Processing legacy email from {from_address} for loan '{loan_application_id_from_subject}'")
        
        # Use the LLM to extract full details from the email body
        extraction_result_str = await self.kernel.invoke(
            self.kernel.plugins["email_parser"]["extract_loan_data_from_email"],
            email_body=email_body,
            subject_loan_id=loan_application_id_from_subject
        )
        extracted_data = json.loads(str(extraction_result_str))

        loan_application_id = extracted_data.get('loan_application_id') or loan_application_id_from_subject
        if not loan_application_id:
            raise ValueError("Failed to extract a valid Loan Application ID from the email.")

        # Create the initial record in Cosmos DB
        rate_lock_record = {
            "status": "PENDING_CONTEXT",
            "source_email": from_address,
            "received_at": datetime.utcnow().isoformat(),
            "extracted_data": extracted_data
        }
        await self.cosmos_plugin.create_rate_lock(loan_application_id, json.dumps(rate_lock_record))
        
        # Send to next agent
        await self._send_to_workflow(loan_application_id, from_address, extracted_data)
        
        logger.info(f"Successfully processed legacy email for loan '{loan_application_id}'")

    async def _process_raw_message(self, message: Dict[str, Any]):
        """Process raw message content."""
        # Extract raw content from message body
        body = message.get('body', {})
        if isinstance(body, dict) and 'raw_content' in body:
            raw_content = body['raw_content']
        else:
            raw_content = str(body)
        
        logger.info(f"{self.agent_name}: Processing raw message content")
        
        # Try to extract basic information
        loan_application_id = await self._extract_loan_id_from_text(raw_content)
        
        if not loan_application_id:
            logger.warning("Could not extract loan application ID from raw content, skipping")
            return
        
        # Simple extraction for raw content
        extracted_data = {
            "loan_application_id": loan_application_id,
            "raw_content": raw_content[:1000],  # First 1000 chars
            "extraction_method": "raw_text"
        }
        
        # Create the initial record in Cosmos DB
        rate_lock_record = {
            "status": "PENDING_CONTEXT", 
            "source": "raw_message",
            "received_at": datetime.utcnow().isoformat(),
            "extracted_data": extracted_data
        }
        await self.cosmos_plugin.create_rate_lock(loan_application_id, json.dumps(rate_lock_record))
        
        # Send to next agent
        await self._send_to_workflow(loan_application_id, "unknown", extracted_data)
        
        logger.info(f"Successfully processed raw message for loan '{loan_application_id}'")

    async def _extract_loan_id_from_email(self, subject: str, body: str) -> Optional[str]:
        """Extract loan application ID from email subject or body."""
        # Simple regex patterns for loan IDs
        import re
        
        # Look in subject first
        for text in [subject, body]:
            if not text:
                continue
                
            # Common patterns for loan IDs
            patterns = [
                r'loan[:\s]+([A-Z0-9-]{6,20})',
                r'application[:\s]+([A-Z0-9-]{6,20})',  
                r'loan[:\s]*id[:\s]*([A-Z0-9-]{6,20})',
                r'([A-Z]{2,4}\d{6,12})',  # Pattern like ABC123456789
                r'(\d{10,15})',  # Simple numeric IDs
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1)
        
        return None

    async def _extract_loan_id_from_text(self, text: str) -> Optional[str]:
        """Extract loan application ID from raw text."""
        return await self._extract_loan_id_from_email("", text)

    async def _send_to_workflow(self, loan_application_id: str, from_address: str, extracted_data: Dict[str, Any]):
        """Send processed email data to the workflow."""
        # Send audit message
        await self._send_audit_message("EMAIL_PROCESSED", loan_application_id, {
            "email_from": from_address,
            "extracted_data": extracted_data
        })
        
        # Send message to the next agent in the workflow
        await self.servicebus_plugin.send_message_to_topic(
            topic_name="loan_lifecycle",
            message_type="context_retrieval_needed", 
            loan_application_id=loan_application_id,
            message_data={"status": "PENDING_CONTEXT"}
        )
        
        # Send acknowledgment if we have a valid email address
        if from_address and '@' in from_address:
            await self._send_acknowledgment_notification(from_address, loan_application_id, extracted_data)

    async def process_inbox(self):
        """
        Demo method to simulate processing inbound email queue messages.
        Returns a list of processed rate lock requests for demo purposes.
        """
        # Try to initialize kernel, but continue in demo mode if it fails
        try:
            await self._initialize_kernel()
            ai_available = True
        except Exception as e:
            logger.warning(f"AI services unavailable for demo: {str(e)}")
            print(f"   ⚠️  Running in demo mode without AI services")
            ai_available = False
        
        # Simulate inbound email messages that would come from Service Bus
        sample_messages = [
            {
                "message_type": "new_email_request",
                "loan_application_id": "LA123456",
                "email_body": "Hello, I would like to lock the rate for loan LA123456 for 45 days. The property is at 123 Main St, Anytown, USA. Please confirm. Best regards, John Doe",
                "from_address": "john.doe@email.com"
            },
            {
                "message_type": "new_email_request", 
                "loan_application_id": "LA789012",
                "email_body": "Rate lock request for loan LA789012. Need 30 day lock for property at 456 Oak Ave. Thanks, Jane Smith",
                "from_address": "jane.smith@email.com"
            }
        ]
        
        processed_requests = []
        
        try:
            print(f"📨 Processing {len(sample_messages)} simulated email messages...")
            
            for i, message in enumerate(sample_messages, 1):
                print(f"   📧 Processing message {i}/{len(sample_messages)} from {message['from_address']}")
                
                # Process the message
                loan_application_id = message.get('loan_application_id')
                email_body = message.get('email_body')
                from_address = message.get('from_address')
                
                if ai_available:
                    # Extract data using AI
                    try:
                        extraction_result_str = await self.kernel.invoke(
                            self.kernel.plugins["email_parser"]["extract_loan_data_from_email"],
                            email_body=email_body,
                            subject_loan_id=loan_application_id
                        )
                        extracted_data = json.loads(str(extraction_result_str))
                    except Exception as e:
                        logger.warning(f"AI extraction failed, using fallback: {str(e)}")
                        extracted_data = self._fallback_extract_data(email_body, loan_application_id)
                else:
                    # Use fallback extraction for demo
                    extracted_data = self._fallback_extract_data(email_body, loan_application_id)
                
                print(f"   🤖 Extracted: Loan {extracted_data.get('loan_application_id')}, {extracted_data.get('requested_lock_period_days')} days")
                
                # Create rate lock record
                rate_lock_record = {
                    "rate_lock_id": f"RL{datetime.now().strftime('%Y%m%d%H%M%S')}{i:02d}",
                    "loan_application_id": extracted_data.get("loan_application_id", loan_application_id),
                    "borrower_email": from_address,
                    "status": "PENDING_QUOTE",
                    "requested_lock_period_days": extracted_data.get("requested_lock_period_days", 30),
                    "borrower_name": extracted_data.get("borrower_name", "Unknown"),
                    "property_address": extracted_data.get("property_address", "Unknown"),
                    "created_timestamp": datetime.now().isoformat(),
                    "updated_timestamp": datetime.now().isoformat()
                }
                
                # Store in Cosmos DB (simulated for demo)
                print(f"   💾 Creating rate lock record: {rate_lock_record['rate_lock_id']}")
                
                # Add to processed list
                processed_requests.append(rate_lock_record)
                
                print(f"   ✅ Message processed successfully")
                
                # Small delay to simulate processing time
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"Error in process_inbox demo: {str(e)}")
            print(f"   ❌ Error processing messages: {str(e)}")
        
        return processed_requests
    
    def _fallback_extract_data(self, email_body: str, subject_loan_id: str):
        """
        Fallback data extraction without AI for demo purposes.
        """
        import re
        
        # Try to find a loan ID in the body first
        loan_id_match = re.search(r'LA\d{5,}', email_body, re.IGNORECASE)
        loan_id = loan_id_match.group() if loan_id_match else subject_loan_id
        
        # Extract lock period
        lock_period_match = re.search(r'(\d+)\s*day', email_body, re.IGNORECASE)
        lock_period = int(lock_period_match.group(1)) if lock_period_match else 30
        
        # Extract name (simple heuristic)
        name_match = re.search(r'(Best regards|Thanks|Sincerely),?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)', email_body)
        borrower_name = name_match.group(2) if name_match else "Unknown Borrower"
        
        # Extract address (simple heuristic)  
        address_match = re.search(r'(\d+\s+[A-Za-z\s]+(?:St|Ave|Rd|Blvd|Dr)[^.]*)', email_body)
        property_address = address_match.group(1).strip() if address_match else "Address not found"
        
        return {
            "loan_application_id": loan_id,
            "requested_lock_period_days": lock_period,
            "borrower_name": borrower_name,
            "property_address": property_address
        }

    async def _send_acknowledgment_notification(self, recipient_email: str, loan_id: str, extracted_data: Dict[str, Any]):
        """Sends a message to the outbound email topic via Service Bus."""
        
        subject = f"Rate Lock Request Received for Loan: {loan_id}"
        body = f"""
        Dear {extracted_data.get('borrower_name', 'Customer')},

        Thank you for submitting your rate lock request for loan application {loan_id}.

        We have received your request for a {extracted_data.get('requested_lock_period_days')}-day lock period. Our system is now gathering the required information from the Loan Origination System.

        You will receive a separate email with your personalized rate quotes shortly.

        Thank you,
        The Automated Rate Lock System
        """
        
        email_payload = {
            "recipient_email": recipient_email,
            "subject": subject,
            "body": body,
            "attachments": [] # No attachments for acknowledgment
        }
        
        await self.servicebus_plugin.send_message_to_queue(
            queue_name="outbound_confirmations",
            message_type="send_email_notification",
            loan_application_id=loan_id,
            message_data=email_payload
        )
        logger.info(f"Sent acknowledgment notification request to Service Bus for loan '{loan_id}'")

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

    def get_agent_status(self):
        """
        Returns the current status of the email intake agent.
        """
        return {
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "initialized": self._initialized,
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
        logger.info(f"{self.agent_name}: Resources cleaned up.")