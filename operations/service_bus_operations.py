"""
Service Bus Operations
Handles all interactions with Azure Service Bus for messaging.
"""

import os
import json
import email
from email import policy
from datetime import datetime
from typing import Dict, Any, List, Optional
import asyncio
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from azure.identity.aio import DefaultAzureCredential
from utils.logger import console_info, console_debug, console_warning, console_error, console_telemetry_event
from config.azure_config import AzureConfig

class ServiceBusOperations:
    def __init__(self):
        """
        Initialize the ServiceBusOperations class.
        """
        self.azure_config = AzureConfig()
        self.servicebus_namespace = self.azure_config.get_servicebus_namespace()
        self.credential = None
        self.client = None
        self._active_credentials = []  # Track active credentials for cleanup
        
        # Load topic and queue names from Azure configuration
        self.queues = {
            'inbound_email': self.azure_config.get_servicebus_queue_inbound_email(),
            'outbound_confirmations': self.azure_config.get_servicebus_queue_outbound_confirmations(),
            'high_priority_exceptions': self.azure_config.get_servicebus_queue_high_priority_exceptions()
        }
        
        self.topics = {
            'agent-workflow-events': self.azure_config.get_servicebus_topic_workflow_events(),
            'loan_lifecycle': self.azure_config.get_servicebus_topic_loan_lifecycle(),
            'audit_events': self.azure_config.get_servicebus_topic_audit_events(),
            'compliance_events': self.azure_config.get_servicebus_topic_compliance_events(),
            'exception_alerts': self.azure_config.get_servicebus_topic_exception_alerts()
        }
        
        console_info(f"Service Bus Operations initialized for namespace: {self.servicebus_namespace}", "ServiceBusOps")

    def _parse_message_body(self, raw_body) -> Any:
        """
        Parse raw Service Bus message body into a clean Python object.
        
        Handles various body formats:
        - bytes: decode to string
        - iterable: join parts and decode
        - JSON string: parse to dict
        - plain string: return as-is
        
        Args:
            raw_body: Raw message body from Service Bus
            
        Returns:
            Parsed message body (dict for JSON, string for plain text)
        """
        # Handle None/empty body
        if not raw_body:
            return ""
        
        # Convert bytes/iterable to string
        if isinstance(raw_body, bytes):
            body_str = raw_body.decode('utf-8')
        elif isinstance(raw_body, str):
            body_str = raw_body
        elif hasattr(raw_body, '__iter__'):
            # Handle iterable body (multiple parts)
            body_parts = list(raw_body)
            body_str = ''.join(
                part.decode('utf-8') if isinstance(part, bytes) else str(part) 
                for part in body_parts
            )
        else:
            body_str = str(raw_body)
        
        # Try to parse as JSON, return dict if successful
        if body_str:
            try:
                return json.loads(body_str)
            except json.JSONDecodeError:
                # Not JSON, return as plain string
                return body_str
        
        return ""

    def _create_standard_message(self, msg) -> Dict[str, Any]:
        """
        Create a standardized message structure for agent consumption.
        
        This provides a clean, consistent interface regardless of whether
        the message came from a queue or topic subscription.
        
        Returns a dict with structure:
        {
            'message_type': 'workflow_event_type',  # Extracted from body for convenience
            'loan_application_id': 'APP-123',       # Extracted from body for convenience
            'body': {...},                          # Full parsed message body (dict or string)
            'metadata': {                           # All Service Bus metadata
                'correlation_id': '...',
                'message_id': '...',
                'content_type': '...',
                'properties': {...},
                'delivery_count': 1,
                'enqueued_time': '...'
            }
        }
        
        Args:
            msg: Azure Service Bus ReceivedMessage object
            
        Returns:
            Standardized message dictionary
        """
        # Parse the message body
        parsed_body = self._parse_message_body(msg.body)
        
        # Extract message_type - check multiple sources in order of preference:
        # 1. Application properties (MessageType set during send)
        # 2. Message body (message_type field)
        message_type = None
        loan_application_id = None
        
        # First, check application properties for routing metadata
        if hasattr(msg, 'application_properties') and msg.application_properties:
            message_type = msg.application_properties.get('MessageType')
            loan_application_id = msg.application_properties.get('LoanApplicationId')
        
        # Then check message body if it's a dict (can override if explicitly set in body)
        if isinstance(parsed_body, dict):
            message_type = parsed_body.get('message_type') or message_type
            loan_application_id = parsed_body.get('loan_application_id') or loan_application_id
        
        # Create standardized structure
        return {
            'message_type': message_type,
            'loan_application_id': loan_application_id,
            'body': parsed_body,
            'metadata': {
                'correlation_id': msg.correlation_id,
                'message_id': msg.message_id,
                'content_type': msg.content_type,
                'properties': dict(msg.application_properties) if msg.application_properties else {},
                'delivery_count': msg.delivery_count,
                'enqueued_time': msg.enqueued_time_utc.isoformat() if msg.enqueued_time_utc else None
            }
        }

    def _parse_email_content(self, raw_content: str) -> Dict[str, Any]:
        """
        Parse email content using Python's built-in email module.
        
        Args:
            raw_content (str): Raw email content
            
        Returns:
            Dict[str, Any]: Parsed email data
        """
        try:
            # Parse with modern EmailMessage API for unicode support
            msg = email.message_from_string(raw_content, policy=policy.default)
            
            parsed_email = {
                'subject': msg.get('Subject', ''),
                'from': msg.get('From', ''),
                'to': msg.get('To', ''),
                'cc': msg.get('Cc', ''),
                'date': msg.get('Date', ''),
                'message_id': msg.get('Message-ID', ''),
                'body_text': None,
                'body_html': None,
                'attachments': [],
                'headers': dict(msg.items())
            }
            
            # Extract body content and attachments
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = part.get_content_disposition()
                    
                    if content_type == 'text/plain' and not parsed_email['body_text']:
                        parsed_email['body_text'] = part.get_content()
                    elif content_type == 'text/html' and not parsed_email['body_html']:
                        parsed_email['body_html'] = part.get_content()
                    elif content_disposition == 'attachment':
                        parsed_email['attachments'].append({
                            'filename': part.get_filename(),
                            'content_type': content_type,
                            'size': len(part.get_payload(decode=True) or b''),
                            'content_id': part.get('Content-ID', '')
                        })
            else:
                # Single part message
                content_type = msg.get_content_type()
                if content_type == 'text/plain':
                    parsed_email['body_text'] = msg.get_content()
                elif content_type == 'text/html':
                    parsed_email['body_html'] = msg.get_content()
            
            console_info(f"Successfully parsed email with subject: {parsed_email['subject'][:50]}...", "ServiceBusOps")
            return parsed_email
            
        except Exception as e:
            console_warning(f"Failed to parse email content: {e}", "ServiceBusOps")
            return {
                'error': f'Failed to parse email: {e}',
                'raw_content': raw_content[:500],  # First 500 chars for debugging
                'parsed': False
            }

    def _looks_like_email(self, content: str) -> bool:
        """
        Simple heuristic to detect if content looks like an email message.
        
        Args:
            content (str): Content to check
            
        Returns:
            bool: True if content appears to be an email
        """
        if not content or len(content) < 50:
            return False
        
        # Check for common email headers
        email_indicators = [
            'From:', 'To:', 'Subject:', 'Date:',
            'Message-ID:', 'Return-Path:', 'Received:',
            'Content-Type:', 'MIME-Version:'
        ]
        
        # Convert to lowercase for case-insensitive matching
        content_lower = content.lower()
        
        # Count how many email indicators we find
        indicator_count = sum(1 for indicator in email_indicators 
                            if indicator.lower() in content_lower)
        
        # If we find at least 3 email headers, it's likely an email
        return indicator_count >= 3

    async def _get_servicebus_client(self):
        """
        Get or create Service Bus client with proper authentication.
        Creates a new client instance each time to avoid connection issues.
        Returns both the client and credential for proper cleanup.
        """
        try:
            if not self.servicebus_namespace:
                raise ValueError("AZURE_SERVICEBUS_NAMESPACE_NAME environment variable is required")
            
            # Always create a fresh credential and client for each operation
            # This avoids the connection handler issues we were seeing
            credential = DefaultAzureCredential()
            self._active_credentials.append(credential)  # Track for cleanup
            fully_qualified_namespace = f"{self.servicebus_namespace}.servicebus.windows.net"
            client = ServiceBusClient(fully_qualified_namespace, credential)
            
            console_debug("Service Bus client created successfully", "ServiceBusOps")
            return client, credential
            
        except Exception as e:
            console_error(f"Failed to create Service Bus client: {e}", "ServiceBusOps")
            raise

    async def send_message(
        self, 
        destination_name: str, 
        message_body: str, 
        correlation_id: Optional[str] = None, 
        destination_type: str = 'topic',
        message_type: Optional[str] = None,
        target_agent: Optional[str] = None,
        priority: str = 'normal'
    ) -> bool:
        """
        Send a message to a specific Service Bus topic or queue with routing metadata.
        
        For topics, adds application_properties for SQL subscription filter routing:
        - MessageType: Type of message for filter-based routing
        - TargetAgent: Intended agent recipient  
        - Priority: Message priority (normal, high, critical)
        - LoanApplicationId: Correlation tracking
        - Timestamp: Message creation time
        
        Args:
            destination_name (str): The logical name of the topic or queue to send the message to.
            message_body (str): The message payload as raw text or JSON.
            correlation_id (str, optional): A correlation ID for tracking.
            destination_type (str): Either 'topic' or 'queue'
            message_type (str, optional): Message type for routing (e.g., 'email_parsed', 'context_retrieved')
            target_agent (str, optional): Target agent name (e.g., 'loan_context', 'rate_quote')
            priority (str): Message priority - 'normal', 'high', or 'critical' (default: 'normal')
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            client, credential = await self._get_servicebus_client()
            
            if destination_type == 'topic':
                actual_destination_name = self.topics.get(destination_name)
                if not actual_destination_name:
                    raise ValueError(f"Topic '{destination_name}' not found in configuration.")
                sender_method = client.get_topic_sender
            elif destination_type == 'queue':
                actual_destination_name = self.queues.get(destination_name)
                if not actual_destination_name:
                    raise ValueError(f"Queue '{destination_name}' not found in configuration.")
                sender_method = client.get_queue_sender
            else:
                raise ValueError(f"Invalid destination_type: {destination_type}. Use 'topic' or 'queue'.")

            if destination_type == 'topic':
                sender = sender_method(topic_name=actual_destination_name)
            else:
                sender = sender_method(queue_name=actual_destination_name)
                
            async with client, sender:
                # Determine content type based on message body
                content_type = "application/json" if message_body.strip().startswith('{') else "text/plain"
                
                # Create message with routing metadata
                message_to_send = ServiceBusMessage(
                    body=message_body,
                    content_type=content_type,
                    correlation_id=correlation_id
                )
                
                # Add routing metadata for topics (enables SQL subscription filters)
                if destination_type == 'topic':
                    routing_properties = {
                        "MessageType": message_type or "unknown",
                        "TargetAgent": target_agent or "unknown",
                        "Priority": priority,
                        "Timestamp": datetime.utcnow().isoformat()
                    }
                    
                    # Add loan application ID if provided as correlation_id
                    if correlation_id:
                        routing_properties["LoanApplicationId"] = correlation_id
                    
                    message_to_send.application_properties = routing_properties
                    
                    console_debug(
                        f"📋 Routing metadata: MessageType={message_type}, TargetAgent={target_agent}, Priority={priority}", 
                        "ServiceBusOps"
                    )
                
                await sender.send_messages(message_to_send)
            
            # Explicitly close the credential to clean up HTTP sessions
            await credential.close()
            # Remove from active tracking
            if credential in self._active_credentials:
                self._active_credentials.remove(credential)
            
            console_info(f"Message sent to {destination_type} '{actual_destination_name}'", "ServiceBusOps")
            console_telemetry_event("message_sent", {
                "destination": actual_destination_name,
                "destination_type": destination_type,
                "correlation_id": correlation_id,
                "message_type": "raw_text"
            }, "ServiceBusOps")
            
            return True

        except Exception as e:
            console_error(f"Failed to send message to {destination_type} '{destination_name}': {e}", "ServiceBusOps")
            return False

    async def receive_messages(self, topic_name: str, subscription_name: str, max_wait_time: int = 5) -> List[Dict[str, Any]]:
        """
        Receive messages from a Service Bus topic subscription.
        
        DEPRECATED: Use listen_to_subscription() for event-driven message processing.
        This polling method is kept for backward compatibility only.
        
        Args:
            topic_name: Logical name of the topic or actual topic name
            subscription_name: Name of the subscription
            max_wait_time: Maximum time to wait for messages in seconds
            
        Returns:
            List of received messages as dictionaries
        """
        try:
            client, credential = await self._get_servicebus_client()
            
            # Check if topic_name is a logical name in our mapping, otherwise use as-is
            actual_topic_name = self.topics.get(topic_name, topic_name)
            
            # More visible polling indicator
            console_info(f"🔍 Polling {actual_topic_name}/{subscription_name} for messages (timeout: {max_wait_time}s)", "ServiceBusOps")
            
            receiver = client.get_subscription_receiver(
                topic_name=actual_topic_name,
                subscription_name=subscription_name
            )
            
            async with client, receiver:
                received_msgs = await receiver.receive_messages(max_wait_time=max_wait_time)
                
                if not received_msgs:
                    console_debug(f"📭 No messages found in {actual_topic_name}/{subscription_name}", "ServiceBusOps")
                    return []
                
                console_info(f"📨 Found {len(received_msgs)} message(s) in {actual_topic_name}/{subscription_name}", "ServiceBusOps")
                
                messages = []
                
                for msg in received_msgs:
                    try:
                        # Parse message body - FIXED: properly extract content from generator
                        if msg.body:
                            # Handle generator objects properly
                            if hasattr(msg.body, '__iter__') and not isinstance(msg.body, (str, bytes)):
                                try:
                                    # Convert generator to actual content
                                    body_parts = list(msg.body)
                                    body_str = ''.join(part.decode('utf-8') if isinstance(part, bytes) else str(part) for part in body_parts)
                                except Exception as e:
                                    console_warning(f"Failed to extract body from generator: {e}, falling back to str()", "ServiceBusOps")
                                    body_str = str(msg.body)
                            else:
                                body_str = msg.body.decode('utf-8') if isinstance(msg.body, bytes) else str(msg.body)
                        else:
                            body_str = ""
                        
                        if body_str:
                            try:
                                parsed_body = json.loads(body_str)
                            except json.JSONDecodeError:
                                # If not JSON, treat as plain text
                                console_warning(f"Message {msg.message_id} body is not JSON, treating as text", "ServiceBusOps")
                                parsed_body = {"raw_content": body_str}
                        else:
                            console_warning(f"Message {msg.message_id} has empty body", "ServiceBusOps")
                            parsed_body = {"raw_content": ""}
                        
                        # Parse message body
                        message_dict = {
                            'body': parsed_body,
                            'content_type': msg.content_type,
                            'correlation_id': msg.correlation_id,
                            'message_id': msg.message_id,
                            'properties': dict(msg.application_properties) if msg.application_properties else {},
                            'delivery_count': msg.delivery_count,
                            'enqueued_time': msg.enqueued_time_utc.isoformat() if msg.enqueued_time_utc else None
                        }
                        messages.append(message_dict)
                        
                        # Complete the message to remove it from the queue
                        await receiver.complete_message(msg)
                        console_info(f"Completed message {msg.message_id} from {topic_name}/{subscription_name}", "ServiceBusOps")
                        
                    except Exception as msg_error:
                        console_error(f"Error processing message {msg.message_id}: {msg_error}", "ServiceBusOps")
                        # Abandon the message so it can be retried
                        await receiver.abandon_message(msg)
                
                if messages:
                    console_info(f"Received {len(messages)} messages from {topic_name}/{subscription_name}", "ServiceBusOps")
                
                # Explicitly close the credential to clean up HTTP sessions
                await credential.close()
                # Remove from active tracking
                if credential in self._active_credentials:
                    self._active_credentials.remove(credential)
                return messages
            
        except Exception as e:
            console_warning(f"Error receiving messages from {topic_name}/{subscription_name}: {e}", "ServiceBusOps")
            # Clean up credential even on error
            try:
                await credential.close()
                if credential in self._active_credentials:
                    self._active_credentials.remove(credential)
            except:
                pass
            return []

    async def listen_to_subscription(self, topic_name: str, subscription_name: str, message_handler, stop_event: asyncio.Event):
        """
        Event-driven message listener for Service Bus topic subscriptions.
        Blocks until messages arrive (no polling delay) and processes them via callback.
        
        Args:
            topic_name: Logical name of the topic or actual topic name
            subscription_name: Name of the subscription
            message_handler: Async callback function to process each message (receives message dict)
            stop_event: asyncio.Event to signal when to stop listening
            
        Raises:
            Exception: If receiver setup or message processing fails critically
        """
        client = None
        credential = None
        receiver = None
        
        try:
            # Get Service Bus client and credential
            client, credential = await self._get_servicebus_client()
            
            # Resolve logical topic name to actual name
            actual_topic_name = self.topics.get(topic_name, topic_name)
            
            console_info(f"🎧 Starting event-driven listener for {actual_topic_name}/{subscription_name}", "ServiceBusOps")
            
            # Create receiver for the subscription
            receiver = client.get_subscription_receiver(
                topic_name=actual_topic_name,
                subscription_name=subscription_name,
                max_wait_time=60  # Wait up to 60 seconds per receive call
            )
            
            # Event-driven message processing loop
            async with receiver:
                while not stop_event.is_set():
                    try:
                        # Receive messages in smaller batches to prevent overwhelming OpenAI
                        # Reduced from 10 to 3 to align with MAX_CONCURRENT_OPENAI_CALLS
                        received_msgs = await receiver.receive_messages(max_wait_time=60, max_message_count=3)
                        
                        if not received_msgs:
                            # Timeout reached, check stop_event and continue
                            continue
                        
                        console_info(f"📨 Received {len(received_msgs)} message(s) from {actual_topic_name}/{subscription_name}", "ServiceBusOps")
                        
                        # Process each message
                        for msg in received_msgs:
                            if stop_event.is_set():
                                # Stop requested, abandon remaining messages
                                await receiver.abandon_message(msg)
                                continue
                            
                            try:
                                # Create standardized message structure
                                message_dict = self._create_standard_message(msg)
                                
                                # Call the message handler
                                await message_handler(message_dict)
                                
                                # Complete the message (removes from queue)
                                await receiver.complete_message(msg)
                                console_debug(f"✅ Completed message {msg.message_id}", "ServiceBusOps")
                                
                            except Exception as msg_error:
                                console_error(f"❌ Error processing message {msg.message_id}: {msg_error}", "ServiceBusOps")
                                # Abandon message so it can be retried
                                await receiver.abandon_message(msg)
                    
                    except asyncio.CancelledError:
                        console_info(f"🛑 Listener for {actual_topic_name}/{subscription_name} cancelled", "ServiceBusOps")
                        break
                    except Exception as receive_error:
                        console_error(f"❌ Error receiving messages from {actual_topic_name}/{subscription_name}: {receive_error}", "ServiceBusOps")
                        # Wait a bit before retrying to avoid tight error loops
                        await asyncio.sleep(5)
            
            console_info(f"🔚 Stopped listening to {actual_topic_name}/{subscription_name}", "ServiceBusOps")
            
        except Exception as e:
            console_error(f"❌ Fatal error in listener for {topic_name}/{subscription_name}: {e}", "ServiceBusOps")
            raise
        finally:
            # Clean up resources
            if credential:
                try:
                    await credential.close()
                    if credential in self._active_credentials:
                        self._active_credentials.remove(credential)
                except Exception as cleanup_error:
                    console_debug(f"Error during credential cleanup: {cleanup_error}", "ServiceBusOps")

    async def listen_to_queue(self, queue_name: str, message_handler, stop_event: asyncio.Event):
        """
        Event-driven message listener for Service Bus queues.
        Blocks until messages arrive (no polling delay) and processes them via callback.
        
        Args:
            queue_name: Logical name of the queue or actual queue name
            message_handler: Async callback function to process each message (receives message dict)
            stop_event: asyncio.Event to signal when to stop listening
            
        Raises:
            Exception: If receiver setup or message processing fails critically
        """
        client = None
        credential = None
        receiver = None
        
        try:
            # Get Service Bus client and credential
            client, credential = await self._get_servicebus_client()
            
            # Resolve logical queue name to actual name
            actual_queue_name = self.queues.get(queue_name, queue_name)
            
            console_info(f"🎧 Starting event-driven listener for queue {actual_queue_name}", "ServiceBusOps")
            
            # Create receiver for the queue
            receiver = client.get_queue_receiver(
                queue_name=actual_queue_name,
                max_wait_time=60  # Wait up to 60 seconds per receive call
            )
            
            # Event-driven message processing loop
            async with receiver:
                while not stop_event.is_set():
                    try:
                        # Receive messages in smaller batches to prevent overwhelming OpenAI
                        # Reduced from 10 to 3 to align with MAX_CONCURRENT_OPENAI_CALLS
                        received_msgs = await receiver.receive_messages(max_wait_time=60, max_message_count=3)
                        
                        if not received_msgs:
                            # Timeout reached, check stop_event and continue
                            continue
                        
                        console_info(f"📨 Received {len(received_msgs)} message(s) from queue {actual_queue_name}", "ServiceBusOps")
                        
                        # Process each message
                        for msg in received_msgs:
                            if stop_event.is_set():
                                # Stop requested, abandon remaining messages
                                await receiver.abandon_message(msg)
                                continue
                            
                            try:
                                # Create standardized message structure
                                message_dict = self._create_standard_message(msg)
                                
                                # Call the message handler
                                await message_handler(message_dict)
                                
                                # Complete the message (removes from queue)
                                await receiver.complete_message(msg)
                                console_debug(f"✅ Completed message {msg.message_id}", "ServiceBusOps")
                                
                            except Exception as msg_error:
                                console_error(f"❌ Error processing message {msg.message_id}: {msg_error}", "ServiceBusOps")
                                # Abandon message so it can be retried
                                await receiver.abandon_message(msg)
                    
                    except asyncio.CancelledError:
                        console_info(f"🛑 Listener for queue {actual_queue_name} cancelled", "ServiceBusOps")
                        break
                    except Exception as receive_error:
                        console_error(f"❌ Error receiving messages from queue {actual_queue_name}: {receive_error}", "ServiceBusOps")
                        # Wait a bit before retrying to avoid tight error loops
                        await asyncio.sleep(5)
            
            console_info(f"🔚 Stopped listening to queue {actual_queue_name}", "ServiceBusOps")
            
        except Exception as e:
            console_error(f"❌ Fatal error in listener for queue {queue_name}: {e}", "ServiceBusOps")
            raise
        finally:
            # Clean up resources
            if credential:
                try:
                    await credential.close()
                    if credential in self._active_credentials:
                        self._active_credentials.remove(credential)
                except Exception as cleanup_error:
                    console_debug(f"Error during credential cleanup: {cleanup_error}", "ServiceBusOps")

    async def receive_queue_messages(self, queue_name: str, max_wait_time: int = 5) -> List[Dict[str, Any]]:
        """
        Receive messages from a Service Bus queue.
        
        Args:
            queue_name (str): Logical name of the queue or actual queue name
            max_wait_time (int): Maximum time to wait for messages in seconds
            
        Returns:
            List of received messages as dictionaries
        """
        try:
            client, credential = await self._get_servicebus_client()
            
            # Check if queue_name is a logical name in our mapping, otherwise use as-is
            actual_queue_name = self.queues.get(queue_name, queue_name)
            
            # More visible polling indicator for queues
            console_info(f"🔍 Polling queue {actual_queue_name} for messages (timeout: {max_wait_time}s)", "ServiceBusOps")
            
            receiver = client.get_queue_receiver(queue_name=actual_queue_name)
            
            async with client, receiver:
                received_msgs = await receiver.receive_messages(max_wait_time=max_wait_time)
                
                if not received_msgs:
                    console_debug(f"📭 No messages found in queue {actual_queue_name}", "ServiceBusOps")
                    return []
                
                console_info(f"📨 Found {len(received_msgs)} message(s) in queue {actual_queue_name}", "ServiceBusOps")
                messages = []
                
                for msg in received_msgs:
                        try:
                            # Parse message body - FIXED: properly extract content from generator
                            if msg.body:
                                # Handle different body types - Service Bus SDK might return string, bytes, or generator
                                if isinstance(msg.body, bytes):
                                    body_str = msg.body.decode('utf-8')
                                    console_debug(f"Message {msg.message_id} decoded from bytes, length: {len(body_str)}", "ServiceBusOps")
                                elif isinstance(msg.body, str):
                                    body_str = msg.body
                                    console_debug(f"Message {msg.message_id} already string, length: {len(body_str)}", "ServiceBusOps")
                                elif hasattr(msg.body, '__iter__'):
                                    # Handle generator objects properly
                                    try:
                                        body_parts = list(msg.body)
                                        body_str = ''.join(part.decode('utf-8') if isinstance(part, bytes) else str(part) for part in body_parts)
                                        console_debug(f"Message {msg.message_id} extracted from generator, length: {len(body_str)}", "ServiceBusOps")
                                    except Exception as e:
                                        console_warning(f"Failed to extract body from generator: {e}, falling back to str()", "ServiceBusOps")
                                        body_str = str(msg.body)
                                else:
                                    body_str = str(msg.body)
                                    console_debug(f"Message {msg.message_id} converted to string from {type(msg.body)}, length: {len(body_str)}", "ServiceBusOps")
                            else:
                                body_str = ""
                                console_warning(f"Message {msg.message_id} has empty body", "ServiceBusOps")
                            
                            if body_str:
                                console_debug(f"Message {msg.message_id} body content: {body_str[:100]}...", "ServiceBusOps")
                                console_debug(f"Message {msg.message_id} content type: {msg.content_type}", "ServiceBusOps")
                                
                                # All messages are raw text for LLM processing
                                console_info(f"Message {msg.message_id} is raw text for LLM processing", "ServiceBusOps")
                                parsed_body = body_str
                            else:
                                console_warning(f"Message {msg.message_id} has empty body", "ServiceBusOps")
                                parsed_body = ""
                            
                            message_dict = {
                                'body': parsed_body,
                                'content_type': msg.content_type,
                                'correlation_id': msg.correlation_id,
                                'message_id': msg.message_id,
                                'properties': dict(msg.application_properties) if msg.application_properties else {},
                                'delivery_count': msg.delivery_count,
                                'enqueued_time': msg.enqueued_time_utc.isoformat() if msg.enqueued_time_utc else None
                            }
                            messages.append(message_dict)
                            
                            # Complete the message to remove it from the queue
                            await receiver.complete_message(msg)
                            console_info(f"Completed message {msg.message_id} from queue {queue_name}", "ServiceBusOps")
                            
                        except Exception as msg_error:
                            console_error(f"Error processing message {msg.message_id}: {msg_error}", "ServiceBusOps")
                            # Abandon the message so it can be retried
                            await receiver.abandon_message(msg)
                
                if messages:
                    console_info(f"Received {len(messages)} messages from queue {queue_name}", "ServiceBusOps")
                
                # Explicitly close the credential to clean up HTTP sessions
                await credential.close()
                # Remove from active tracking
                if credential in self._active_credentials:
                    self._active_credentials.remove(credential)
                return messages
        
        except Exception as e:
            console_error(f"Error receiving queue messages from {queue_name}: {e}", "ServiceBusOps")
            # Clean up credential even on error
            try:
                await credential.close()
                if credential in self._active_credentials:
                    self._active_credentials.remove(credential)
            except:
                pass
            return []

    async def cleanup_all_credentials(self):
        """
        Clean up any remaining active credentials to prevent unclosed session warnings.
        """
        if self._active_credentials:
            console_info(f"Cleaning up {len(self._active_credentials)} remaining credentials", "ServiceBusOps")
            for credential in self._active_credentials.copy():
                try:
                    await credential.close()
                    self._active_credentials.remove(credential)
                except Exception as e:
                    console_debug(f"Error closing credential: {e}", "ServiceBusOps")
            self._active_credentials.clear()

    async def send_exception_alert(self, exception_type: str, priority: str, loan_application_id: str, exception_data: str) -> bool:
        """
        Send an exception alert to the exception handling system.
        
        Args:
            exception_type (str): Type of exception
            priority (str): Priority level (high, medium, low)
            loan_application_id (str): Associated loan application ID
            exception_data (str): Exception details as JSON string
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Parse exception data if it's a JSON string
            if isinstance(exception_data, str):
                try:
                    exception_details = json.loads(exception_data)
                except json.JSONDecodeError:
                    exception_details = {"raw_data": exception_data}
            else:
                exception_details = exception_data
            
            # Create structured exception message body
            message_body = {
                "message_type": "exception_alert",
                "loan_application_id": loan_application_id,
                "exception_type": exception_type,
                "priority": priority,
                "exception_data": exception_details,
                "timestamp": datetime.utcnow().isoformat()
            }

            # High priority exceptions go to dedicated queue for immediate attention
            if priority == "high" or priority == "critical":
                destination = "high-priority-exceptions"
                destination_type = "queue"
            else:
                # Normal exceptions go to workflow events topic
                destination = "agent-workflow-events"
                destination_type = "topic"

            # Send message with proper routing metadata
            return await self.send_message(
                destination_name=destination,
                message_body=json.dumps(message_body),
                correlation_id=loan_application_id,
                destination_type=destination_type,
                message_type="exception_alert",
                target_agent="exception_handler",
                priority=priority
            )
            
        except Exception as e:
            console_error(f"Failed to send exception alert: {e}", "ServiceBusOps")
            return False

    async def send_message_to_topic(
        self, 
        topic_name: str, 
        message_body: str, 
        correlation_id: Optional[str] = None,
        message_type: Optional[str] = None,
        target_agent: Optional[str] = None,
        priority: str = 'normal'
    ) -> bool:
        """
        Send a message to a specific Service Bus topic with routing metadata.
        
        Args:
            topic_name (str): The logical name of the topic to send the message to
            message_body (str): The message payload as raw text or JSON
            correlation_id (str, optional): A correlation ID for tracking
            message_type (str, optional): Message type for SQL filter routing
            target_agent (str, optional): Target agent name for routing
            priority (str): Message priority (normal, high, critical)
            
        Returns:
            bool: True if successful, False otherwise
        """
        return await self.send_message(
            destination_name=topic_name,
            message_body=message_body,
            correlation_id=correlation_id,
            destination_type="topic",
            message_type=message_type,
            target_agent=target_agent,
            priority=priority
        )

    async def send_audit_message(self, agent_name: str, action: str, loan_application_id: str, audit_data: Dict[str, Any]) -> bool:
        """
        Send an audit message to the audit logging topic.
        
        Args:
            agent_name (str): Name of the agent performing the action
            action (str): Action being performed 
            loan_application_id (str): Associated loan application ID
            audit_data (Dict[str, Any]): Audit details as dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create audit message
            audit_message = {
                "agent_name": agent_name,
                "action": action,
                "loan_application_id": loan_application_id,
                "audit_data": audit_data,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Send to audit events topic with routing metadata
            return await self.send_message(
                destination_name="audit_events",
                message_body=json.dumps(audit_message),
                correlation_id=loan_application_id,
                destination_type="topic",
                message_type="audit_log",
                target_agent="audit_logging",
                priority="normal"
            )
            
        except Exception as e:
            console_error(f"Failed to send audit message: {e}", "ServiceBusOps")
            return False

    async def send_audit_log(self, agent_name: str, action: str, loan_application_id: str, audit_data: Dict[str, Any]) -> bool:
        """
        Send an audit log message to the audit logging topic (alias for send_audit_message).
        
        Args:
            agent_name (str): Name of the agent performing the action
            action (str): Action being performed 
            loan_application_id (str): Associated loan application ID
            audit_data (Dict[str, Any]): Audit details as dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        return await self.send_audit_message(agent_name, action, loan_application_id, audit_data)

    # OLD send_message_to_topic() deleted - duplicate of line 854 definition
    # The line 854 version has message_type, target_agent, priority parameters

    async def send_audit_message(self, agent_name: str, action: str, loan_application_id: str = None, audit_data: dict = None) -> bool:
        """
        Simplified audit message sending for backward compatibility.
        
        Args:
            agent_name (str): Name of the agent sending the audit
            action (str): Action being audited
            loan_application_id (str, optional): Associated loan application ID
            audit_data (dict, optional): Additional audit data
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Create audit message directly to avoid recursion
        try:
            # Create audit message with message_type included in body
            audit_message = {
                "message_type": "audit_event",  # Add message_type to body
                "agent_name": agent_name,
                "action": action,
                "loan_application_id": loan_application_id or "unknown",
                "audit_data": audit_data or {},
                "timestamp": datetime.utcnow().isoformat()
            }

            # Send to audit events topic (consolidated)
            return await self.send_message(
                destination_name="audit_events",
                message_body=json.dumps(audit_message),
                correlation_id=loan_application_id or "unknown",
                destination_type="topic",
                message_type="audit_event",  # Add to application properties for SQL filtering
                target_agent="audit_logging"
            )
            
        except Exception as e:
            console_error(f"Failed to send audit message: {e}", "ServiceBusOps")
            return False

    async def send_workflow_message(
        self, 
        message_type: str, 
        loan_application_id: str, 
        message_data: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> bool:
        """
        Send a workflow event message to the agent-workflow-events topic.
        
        This method sends workflow coordination messages that trigger agent actions
        in the multi-agent rate lock system.
        
        Args:
            message_type (str): Type of workflow event (e.g., context_retrieval_needed, 
                              context_retrieved, rates_presented, compliance_passed)
            loan_application_id (str): Loan application ID for tracking
            message_data (Dict[str, Any]): Message payload containing workflow data
            correlation_id (str, optional): Correlation ID for tracking (defaults to loan_application_id)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Use loan_application_id as correlation_id if not provided
            if not correlation_id:
                correlation_id = loan_application_id
            
            # Create workflow message with message_type in the body
            workflow_message = {
                "message_type": message_type,
                "loan_application_id": loan_application_id,
                **message_data  # Merge in the message data
            }
            
            # Send to agent-workflow-events topic
            return await self.send_message(
                destination_name="agent-workflow-events",
                message_body=json.dumps(workflow_message),
                correlation_id=correlation_id,
                destination_type="topic",
                message_type=message_type,  # Add to application properties for SQL filtering
                target_agent=None  # Workflow messages route to multiple agents via subscriptions
            )
            
        except Exception as e:
            console_error(f"Failed to send workflow message: {e}", "ServiceBusOps")
            return False

    # Note: No close() method needed since we use per-operation clients
    # Each method creates its own client and properly disposes it via async context managers
