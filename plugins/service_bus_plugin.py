from datetime import datetime
import json
import logging
from typing import Annotated, Dict, Any
from semantic_kernel.functions import kernel_function
from operations.service_bus_operations import ServiceBusOperations

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize service bus operations
servicebus_operations = ServiceBusOperations()

class ServiceBusPlugin:
    @kernel_function(
        description="""
        Send a workflow event to trigger agent actions in the rate lock system.
        
        USE THIS WHEN:
        - Triggering the next agent in the workflow
        - Notifying agents of status changes
        - Coordinating multi-agent processing
        - Broadcasting workflow events
        
        CAPABILITIES:
        - Sends messages to workflow-events topic
        - Routes to appropriate agent subscriptions
        - Includes correlation tracking
        - Supports workflow coordination
        
        MESSAGE TYPES:
        - new_request: Triggers email intake processing
        - context_retrieved: Activates rate quote agent
        - rates_presented: Initiates compliance checking
        - compliance_passed: Triggers lock confirmation
        - exception_occurred: Activates exception handler
        
        COMMON USE CASES:
        - "Send new_request event for loan LA12345"
        - "Trigger context_retrieved for loan processing"
        - "Notify agents of rates_presented event"
        - "Send compliance_passed event to continue workflow"
        """
    )
    async def send_workflow_event(self, message_type: Annotated[str, "Type of workflow event (new_request, context_retrieved, rates_presented, compliance_passed, exception_occurred)"],
                                   loan_application_id: Annotated[str, "Loan application ID for the workflow"],
                                   message_data: Annotated[str, "Message payload as JSON string"],
                                   correlation_id: Annotated[str, "Optional correlation ID for tracking"] = None) -> Annotated[Dict[str, Any], "Returns message sending status and details."]:
        
        if not message_type or not loan_application_id or not message_data:
            raise ValueError("message_type, loan_application_id, and message_data are required")
        
        try:
            # Parse message data - must be valid JSON
            data_payload = json.loads(message_data)
            
            # Send message
            success = await servicebus_operations.send_workflow_message(
                message_type=message_type,
                loan_application_id=loan_application_id,
                message_data=data_payload,
                correlation_id=correlation_id
            )
            
            if success:
                return {
                    "success": True,
                    "message_type": message_type,
                    "loan_application_id": loan_application_id,
                    "correlation_id": correlation_id,
                    "sent_at": datetime.utcnow().isoformat(),
                    "message": f"Workflow message '{message_type}' sent for loan {loan_application_id}"
                }
            else:
                error_msg = "Failed to send workflow message"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in message_data: {str(e)}"
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Error sending workflow message: {str(e)}"
            logger.error(error_msg)
            raise

    @kernel_function(
        description="""
        Send an audit log to record agent actions and system events.
        
        USE THIS WHEN:
        - Recording agent actions for compliance
        - Logging system events and outcomes
        - Creating audit trails for regulatory compliance
        - Tracking agent performance metrics
        
        Actions: EMAIL_PROCESSED, CONTEXT_RETRIEVED, RATES_GENERATED, COMPLIANCE_CHECKED, LOCK_CONFIRMED, EXCEPTION_ESCALATED
        """
    )
    async def send_audit_log(self, agent_name: Annotated[str, "Name of the agent performing the action"],
                                action: Annotated[str, "Action being performed (EMAIL_PROCESSED, CONTEXT_RETRIEVED, RATES_GENERATED, COMPLIANCE_CHECKED, LOCK_CONFIRMED, EXCEPTION_ESCALATED)"],
                                loan_application_id: Annotated[str, "Loan application ID associated with the action"],
                                audit_data: Annotated[str, "Audit details as JSON string"]) -> Annotated[Dict[str, Any], "Returns audit log sending status."]:
        
        if not agent_name or not action or not loan_application_id or not audit_data:
            raise ValueError("agent_name, action, loan_application_id, and audit_data are required")
        
        try:
            # Parse audit data - must be valid JSON
            data_payload = json.loads(audit_data)
            
            # Send message
            success = await servicebus_operations.send_audit_message(
                agent_name=agent_name,
                action=action,
                loan_application_id=loan_application_id,
                audit_data=data_payload
            )
            
            if success:
                return {
                    "success": True,
                    "agent_name": agent_name,
                    "action": action,
                    "loan_application_id": loan_application_id,
                    "sent_at": datetime.utcnow().isoformat(),
                    "message": f"Audit log sent for {agent_name} - {action}"
                }
            else:
                error_msg = "Failed to send audit log"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in audit_data: {str(e)}"
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Error sending audit log: {str(e)}"
            logger.error(error_msg)
            raise

    @kernel_function(
        description="""
        Send an exception for issues requiring human intervention.
        
        USE THIS WHEN:
        - Agents encounter unresolvable errors
        - Compliance violations are detected
        - Technical failures need escalation
        - Manual review is required
        
        EXCEPTION TYPES:
        - COMPLIANCE_VIOLATION, TECHNICAL_ERROR, DATA_VALIDATION_FAILURE, SYSTEM_TIMEOUT, MISSING_DOCUMENTATION
        """
    )
    async def send_exception(self, exception_type: Annotated[str, "Type of exception (COMPLIANCE_VIOLATION, TECHNICAL_ERROR, DATA_VALIDATION_FAILURE, SYSTEM_TIMEOUT, MISSING_DOCUMENTATION)"],
                                  priority: Annotated[str, "Priority level (high, medium, low)"],
                                  loan_application_id: Annotated[str, "Loan application ID associated with the exception"],
                                  exception_data: Annotated[str, "Exception details as JSON string"]) -> Annotated[Dict[str, Any], "Returns exception sending status."]:
        
        if not exception_type or not priority or not loan_application_id or not exception_data:
            raise ValueError("exception_type, priority, loan_application_id, and exception_data are required")
        
        try:
            # Parse exception data - must be valid JSON
            data_payload = json.loads(exception_data)
            
            # Send message
            success = await servicebus_operations.send_exception_alert(
                exception_type=exception_type,
                priority=priority,
                loan_application_id=loan_application_id,
                exception_data=data_payload
            )
            
            if success:
                return {
                    "success": True,
                    "exception_type": exception_type,
                    "priority": priority,
                    "loan_application_id": loan_application_id,
                    "sent_at": datetime.utcnow().isoformat(),
                    "message": f"{priority.upper()} priority exception sent: {exception_type}"
                }
            else:
                error_msg = "Failed to send exception"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in exception_data: {str(e)}"
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Error sending exception: {str(e)}"
            logger.error(error_msg)
            raise

    @kernel_function(
        description="""
        Send a message to a borrower or user via the outbound communication queue.
        
        USE THIS WHEN:
        - Sending acknowledgment messages to borrowers
        - Requesting missing information from users
        - Sending rate lock confirmations
        - Notifying users of exceptions or issues
        - Sending status updates to borrowers
        
        CAPABILITIES:
        - Sends messages via outbound-email-queue (currently email via Logic Apps)
        - Future: Will support chat, SMS, and other channels
        - Supports custom subject and body
        - Can include attachments
        - Tracks via loan_application_id
        
        COMMON USE CASES:
        - "Send acknowledgment to borrower"
        - "Request missing loan ID from user"
        - "Send rate lock confirmation to john@example.com"
        - "Notify borrower about compliance issue"
        
        Returns success status and message tracking details.
        """
    )
    async def send_outbound_message(
        self,
        recipient: Annotated[str, "Recipient identifier (email, phone, chat ID, etc.)"],
        subject: Annotated[str, "Message subject line"],
        body: Annotated[str, "Message body content"],
        loan_application_id: Annotated[str, "Loan application ID or tracking reference"] = "SYSTEM",
        attachments: Annotated[str, "Optional attachments as JSON array string"] = "[]"
    ) -> Annotated[Dict[str, Any], "Returns message sending status and tracking details."]:
        """
        Send message via outbound communication queue (currently email, future: chat, SMS).
        """
        
        if not recipient or not subject or not body:
            raise ValueError("recipient, subject, and body are required")
        
        try:
            # Parse attachments if provided - must be valid JSON
            attachments_list = json.loads(attachments) if attachments else []
            
            # Create message payload (currently email format, future: multi-channel)
            message_payload = {
                "recipient": recipient,  # Could be email, phone, chat ID, etc.
                "subject": subject,
                "body": body,
                "attachments": attachments_list,
                "sent_at": datetime.utcnow().isoformat()
            }
            
            # Send to outbound confirmations queue
            success = await servicebus_operations.send_message(
                destination_name="outbound_confirmations",
                message_body=json.dumps(message_payload),
                correlation_id=loan_application_id,
                destination_type="queue"
            )
            
            if success:
                return {
                    "success": True,
                    "recipient": recipient,
                    "subject": subject,
                    "loan_application_id": loan_application_id,
                    "queued_at": datetime.utcnow().isoformat(),
                    "message": f"Message '{subject}' queued for delivery to {recipient}"
                }
            else:
                error_msg = "Failed to queue message for delivery"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in attachments: {str(e)}"
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Error sending outbound message: {str(e)}"
            logger.error(error_msg)
            raise

    async def send_message_to_topic(self, topic_name: str, message_body: str = None, correlation_id: str = None, 
                                   message_type: str = None, loan_application_id: str = None, message_data: dict = None,
                                   target_agent: str = None, priority: str = 'normal') -> bool:
        """
        Send a message to a specific Service Bus topic with routing metadata.
        
        Args:
            topic_name (str): Name of the topic to send to
            message_body (str, optional): Message content (if not provided, will be generated from other params)
            correlation_id (str, optional): Correlation ID for tracking
            message_type (str, optional): Type of message for SQL filter routing (e.g., 'email_parsed', 'context_retrieved')
            loan_application_id (str, optional): Loan application ID for tracking
            message_data (dict, optional): Additional message data
            target_agent (str, optional): Target agent name for routing (e.g., 'loan_context', 'rate_quote')
            priority (str): Message priority - 'normal', 'high', or 'critical' (default: 'normal')
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # If message_body is not provided, create it from other parameters
            if not message_body:
                message_content = {
                    "message_type": message_type or "workflow_event",
                    "loan_application_id": loan_application_id or "unknown",
                    "data": message_data or {},
                    "timestamp": datetime.utcnow().isoformat()
                }
                message_body = json.dumps(message_content)
            
            # Use loan_application_id as correlation_id if correlation_id not provided
            if not correlation_id and loan_application_id:
                correlation_id = loan_application_id
            
            # Pass routing metadata to operations layer for SQL filter routing
            success = await servicebus_operations.send_message_to_topic(
                topic_name=topic_name,
                message_body=message_body,
                correlation_id=correlation_id,
                message_type=message_type,        # ✅ Pass message type for SQL filters
                target_agent=target_agent,        # ✅ Pass target agent for routing
                priority=priority                  # ✅ Pass priority for exception filtering
            )
            
            if not success:
                raise RuntimeError("Failed to send message to topic")
            
            return success
                
        except Exception as e:
            error_msg = f"Error sending message to topic: {str(e)}"
            logger.error(error_msg)
            raise

    async def send_message_to_queue(self, queue_name: str, message_body: str = None, correlation_id: str = None, 
                                   message_type: str = None, loan_application_id: str = None, message_data: dict = None) -> bool:
        """
        Send a message to a specific Service Bus queue.
        
        Args:
            queue_name (str): Name of the queue to send to
            message_body (str, optional): Message content (if not provided, will be generated from other params)
            correlation_id (str, optional): Correlation ID for tracking
            message_type (str, optional): Type of message for workflow coordination
            loan_application_id (str, optional): Loan application ID for tracking
            message_data (dict, optional): Additional message data
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # If message_body is not provided, create it from other parameters
            if not message_body:
                message_content = {
                    "message_type": message_type or "queue_message",
                    "loan_application_id": loan_application_id or "unknown",
                    "data": message_data or {},
                    "timestamp": datetime.utcnow().isoformat()
                }
                message_body = json.dumps(message_content)
            
            # Use loan_application_id as correlation_id if correlation_id not provided
            if not correlation_id and loan_application_id:
                correlation_id = loan_application_id
            
            success = await servicebus_operations.send_message(
                destination_name=queue_name,
                message_body=message_body,
                correlation_id=correlation_id,
                destination_type='queue'
            )
            
            if not success:
                raise RuntimeError("Failed to send message to queue")
                
            return success
            
        except Exception as e:
            error_msg = f"Error sending message to queue: {str(e)}"
            logger.error(error_msg)
            raise
    
    # Convenience aliases for simplified agent usage
    
    async def send_audit_event(self, action: str, loan_application_id: str, data: Dict[str, Any]):
        """Convenience method for sending audit events."""
        return await self.send_audit_log(
            agent_name="system",
            action=action,
            loan_application_id=loan_application_id,
            audit_data=json.dumps(data)
        )
    
    async def send_exception_alert(self, exception_type: str, priority: str, message: str, loan_application_id: str):
        """Convenience method for sending exception alerts."""
        exception_data = {
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        return await self.send_exception(
            exception_type=exception_type,
            priority=priority,
            loan_application_id=loan_application_id,
            exception_data=json.dumps(exception_data)
        )

    async def close(self):
        """Clean up resources when the plugin is no longer needed."""
        pass
