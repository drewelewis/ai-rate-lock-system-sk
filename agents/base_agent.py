"""
Base Agent - Thin LLM wrapper for autonomous AI agents.

All agents inherit from this base class and simply override:
1. agent_name - Unique identifier
2. _get_system_prompt() - LLM instruction set
3. _process_llm_response() - Handle LLM output

NO business logic in agents - delegate everything to plugins!
"""

import logging
import os
import asyncio
import random
from typing import Dict, Any, Optional
from datetime import datetime
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.contents.chat_history import ChatHistory
from plugins.cosmos_db_plugin import CosmosDBPlugin
from plugins.service_bus_plugin import ServiceBusPlugin

logger = logging.getLogger(__name__)

# Global rate limiter: Semaphore to limit concurrent OpenAI calls
# This prevents too many simultaneous requests when processing multiple messages
# CONSERVATIVE: Target 50% of quota (50K TPM out of 100K available)
# With 2 concurrent calls @ 3s delay = ~13 calls/min × 3.5K tokens = 45.5K TPM (45%)
MAX_CONCURRENT_OPENAI_CALLS = 2  # Conservative setting for 50% quota safety margin
_openai_semaphore = asyncio.Semaphore(MAX_CONCURRENT_OPENAI_CALLS)


class BaseAgent:
    """
    Base class for all AI agents in the rate lock system.
    
    Design Principles:
    - Agents are THIN wrappers around LLM calls
    - ALL business logic delegated to plugins
    - Agents only contain: name, system prompt, and response handling
    - NO custom logic, NO parsing, NO validation - plugins handle everything
    """
    
    def __init__(self, agent_name: str):
        """Initialize base agent with standard components."""
        self.agent_name = agent_name
        self.kernel = None
        self.chat_service = None
        self._initialized = False
        
        # Standard plugins available to all agents
        self.cosmos_plugin = None
        self.servicebus_plugin = None
        
        logger.info(f"🤖 {agent_name} agent created")
    
    async def _initialize_kernel(self):
        """Initialize Semantic Kernel with Azure OpenAI - standard for all agents."""
        if self._initialized:
            return
        
        logger.info(f"{self.agent_name}: Initializing Semantic Kernel...")
        
        try:
            self.kernel = Kernel()
            
            # Get Azure OpenAI configuration
            endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
            deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
            
            if not all([endpoint, deployment_name]):
                raise ValueError(f"Missing Azure OpenAI configuration")
            
            # Use managed identity for Azure OpenAI authentication
            from azure.identity.aio import DefaultAzureCredential
            
            async def get_token():
                credential = DefaultAzureCredential()
                token = await credential.get_token("https://cognitiveservices.azure.com/.default")
                return token.token
            
            # Add Azure OpenAI service
            # Note: Built-in retry is handled by OpenAI SDK, but our semaphore + exponential backoff provides additional control
            self.chat_service = AzureChatCompletion(
                deployment_name=deployment_name,
                endpoint=endpoint,
                ad_token_provider=get_token,
                service_id="azure_openai_chat"
            )
            
            self.kernel.add_service(self.chat_service)
            
            # Initialize and register plugins with kernel for autonomous function calling
            self.cosmos_plugin = CosmosDBPlugin()
            self.servicebus_plugin = ServiceBusPlugin()
            
            # Import plugins into kernel so LLM can autonomously invoke them
            self.kernel.add_plugin(self.cosmos_plugin, plugin_name="CosmosDB")
            self.kernel.add_plugin(self.servicebus_plugin, plugin_name="ServiceBus")
            
            self._initialized = True
            logger.info(f"{self.agent_name}: Semantic Kernel initialized successfully")
            
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to initialize Semantic Kernel - {str(e)}")
            raise
    
    async def handle_message(self, message: Dict[str, Any]):
        """
        Generic message handler - same for ALL agents.
        
        This is the ONLY method that should be called by main.py.
        
        Flow:
        1. Extract and validate message data
        2. Check if message type is expected (optional override)
        3. Build prompt with agent's system instructions
        4. Call LLM with automatic function calling enabled
        5. LLM autonomously invokes plugins as needed
        6. Return LLM's final response
        
        NO explicit plugin calls - LLM decides everything!
        """
        await self._initialize_kernel()
        
        # Extract message data using helper method
        message_type = message.get('message_type')
        loan_id = message.get('loan_application_id', 'unknown')
        
        logger.info(f"{self.agent_name}: Received message '{message_type}' for loan '{loan_id}'")
        
        # Optional: Check if this agent should handle this message type
        if hasattr(self, '_get_expected_message_types'):
            expected_types = self._get_expected_message_types()
            if expected_types and message_type not in expected_types:
                logger.warning(f"{self.agent_name}: Received unexpected message type: {message_type}. Skipping.")
                return
        
        try:
            body = message.get('body', {})
            metadata = message.get('metadata', {})
            
            # Get agent-specific system prompt
            system_prompt = self._get_system_prompt()
            
            # Build user message from standardized message structure
            user_message = self._build_user_message(message_type, loan_id, body, metadata)
            
            # Call LLM with automatic function calling
            # The LLM will autonomously decide which plugin functions to invoke
            logger.info(f"{self.agent_name}: Calling Azure OpenAI with automatic function calling...")
            llm_response = await self._call_llm(system_prompt, user_message)
            
            logger.info(f"{self.agent_name}: ✅ Completed processing")
            logger.debug(f"{self.agent_name}: LLM Response: {llm_response}")
            
        except Exception as e:
            error_msg = f"Failed to process message: {str(e)}"
            logger.error(f"{self.agent_name}: ❌ {error_msg}")
            # Use helper method to send exception alert
            await self._send_exception_alert("TECHNICAL_ERROR", "high", error_msg, loan_id)
            raise
    
    def _build_user_message(self, message_type: str, loan_id: str, body: Any, metadata: Dict) -> str:
        """Build user message from standardized message structure."""
        return f"""
Message Type: {message_type}
Loan Application ID: {loan_id}
Message Body: {body}
Metadata: {metadata}

Process this message according to your instructions.
"""
    
    async def _call_llm(self, system_prompt: str, user_message: str, max_retries: int = 5) -> str:
        """
        Call Azure OpenAI with automatic function calling enabled.
        
        Includes:
        - Rate limiting via semaphore (max concurrent calls)
        - Exponential backoff retry for 429 errors
        - Jitter to prevent thundering herd
        
        The LLM will autonomously invoke plugin functions as needed to complete the task.
        
        Args:
            system_prompt: Agent's system instructions
            user_message: User's request message
            max_retries: Maximum number of retry attempts for 429 errors
        """
        from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
        from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
        from openai import RateLimitError
        
        chat_history = ChatHistory()
        chat_history.add_system_message(system_prompt)
        chat_history.add_user_message(user_message)
        
        # Enable automatic function calling - LLM can autonomously invoke any registered plugin
        execution_settings = OpenAIChatPromptExecutionSettings(
            max_tokens=2000,
            temperature=0.1,  # Low temperature for consistent, factual responses
            function_choice_behavior=FunctionChoiceBehavior.Auto()  # LLM decides which functions to call
        )
        
        # Implement exponential backoff retry with rate limiting
        retry_count = 0
        base_delay = 1  # Start with 1 second
        
        while retry_count <= max_retries:
            try:
                # Use semaphore to limit concurrent OpenAI calls
                async with _openai_semaphore:
                    logger.debug(f"{self.agent_name}: Acquiring OpenAI call slot ({_openai_semaphore._value} available)")
                    
                    # Get completion with automatic function calling
                    response = await self.chat_service.get_chat_message_content(
                        chat_history=chat_history,
                        settings=execution_settings,
                        kernel=self.kernel  # Required for function calling
                    )
                    
                    # CRITICAL TPM rate limiting: Stay 50% below quota for safety
                    # Azure quota: 100K TPM, targeting 50K TPM max (50% safety margin)
                    # Average call: ~3,500 tokens
                    # With 2 concurrent + 3s delay:
                    #   Each call ~5s API + 3s delay = 8s total
                    #   2 concurrent = (60s ÷ 8s) × 2 = 15 calls/min
                    #   15 calls/min × 3.5K tokens = 52.5K TPM (52% - close to target)
                    # More conservative estimate: ~13 calls/min = 45.5K TPM (45% ✅)
                    await asyncio.sleep(3)  # 3-second delay for 50% quota safety margin
                    logger.debug(f"{self.agent_name}: TPM rate limit delay completed (3s)")
                    
                    return str(response)
                    
            except RateLimitError as e:
                retry_count += 1
                
                if retry_count > max_retries:
                    logger.error(f"{self.agent_name}: ❌ Rate limit exceeded after {max_retries} retries")
                    raise
                
                # Exponential backoff: 2^retry_count * base_delay
                delay = (2 ** retry_count) * base_delay
                
                # Add jitter (random 0-25% of delay) to prevent thundering herd
                jitter = delay * random.uniform(0, 0.25)
                total_delay = delay + jitter
                
                logger.warning(
                    f"{self.agent_name}: ⚠️  Rate limit hit (429). "
                    f"Retry {retry_count}/{max_retries} in {total_delay:.1f}s"
                )
                
                await asyncio.sleep(total_delay)
                
            except Exception as e:
                logger.error(f"{self.agent_name}: ❌ LLM call failed: {str(e)}")
                raise
    
    # ABSTRACT METHOD - Must be overridden by each agent
    
    def _get_system_prompt(self) -> str:
        """
        Get the LLM system prompt for this agent.
        
        MUST BE OVERRIDDEN by each agent subclass.
        
        This defines:
        - Agent's role and responsibilities
        - Available plugin functions  
        - When and how to use each function
        - Expected workflow and outputs
        
        The LLM will use this prompt to autonomously decide which plugin functions to call.
        """
        raise NotImplementedError(f"{self.agent_name} must implement _get_system_prompt()")
    
    # OPTIONAL OVERRIDE - Message type filtering
    
    def _get_expected_message_types(self) -> Optional[list]:
        """
        Return list of message types this agent should process.
        
        If None (default), agent processes all message types.
        If list provided, agent will skip messages not in the list.
        
        Example:
            return ['email_parsed', 'context_retrieval_needed']
        """
        return None
    
    # HELPER METHODS - Common Service Bus operations (non-LLM)
    
    async def _send_workflow_event(self, message_type: str, loan_application_id: str, message_data: Dict[str, Any], correlation_id: str = None):
        """
        Send workflow event to Service Bus.
        
        This is a non-LLM helper method for workflow progression.
        All agents can use this to send messages to the next stage in the workflow.
        
        Args:
            message_type: Type of workflow event (e.g., 'context_retrieved', 'rates_quoted', 'compliance_passed')
            loan_application_id: Loan application ID
            message_data: Dictionary containing the message payload
            correlation_id: Optional correlation ID for tracking (defaults to agent's session_id)
        """
        try:
            import json
            session_id = correlation_id or getattr(self, 'session_id', None)
            await self.servicebus_plugin.send_workflow_event(
                message_type=message_type,
                loan_application_id=loan_application_id,
                message_data=json.dumps(message_data),
                correlation_id=session_id
            )
            logger.debug(f"{self.agent_name}: Sent workflow event '{message_type}' for loan {loan_application_id}")
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to send workflow event: {e}")
    
    async def _send_audit_log(self, action: str, loan_application_id: str, audit_data: Dict[str, Any] = None):
        """
        Send audit log to Service Bus.
        
        This is a non-LLM helper method for audit trail creation.
        All agents can use this for consistent audit logging.
        
        Args:
            action: Action being audited (e.g., 'EMAIL_PROCESSED', 'CONTEXT_RETRIEVED', 'RATES_GENERATED')
            loan_application_id: Loan application ID
            audit_data: Optional dictionary containing additional audit information
        """
        try:
            import json
            audit_payload = audit_data or {}
            await self.servicebus_plugin.send_audit_log(
                agent_name=self.agent_name,
                action=action,
                loan_application_id=loan_application_id,
                event_type="AGENT_ACTION",
                audit_data=json.dumps(audit_payload)
            )
            logger.debug(f"{self.agent_name}: Sent audit log for action '{action}' on loan {loan_application_id}")
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to send audit log: {e}")
    
    async def _send_exception_alert(self, exception_type: str, priority: str, error_message: str, loan_id: str):
        """
        Send exception alert to Service Bus.
        
        This is a non-LLM helper method for error handling.
        All agents can use this for consistent exception reporting.
        """
        try:
            import json
            await self.servicebus_plugin.send_exception(
                exception_type=exception_type,
                priority=priority,
                error_message=error_message,
                loan_application_id=loan_id,
                agent_name=self.agent_name,
                additional_data=json.dumps({"timestamp": datetime.utcnow().isoformat()})
            )
        except Exception as e:
            logger.error(f"{self.agent_name}: Failed to send exception alert: {e}")
    
    async def cleanup(self):
        """Cleanup resources when agent shuts down."""
        logger.info(f"{self.agent_name}: Resources cleaned up.")
    
    async def close(self):
        """Alias for cleanup() to maintain compatibility with main.py."""
        await self.cleanup()
