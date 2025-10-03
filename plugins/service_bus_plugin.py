from datetime import datetime
import os
import asyncio
import json
from typing import List, Optional, Annotated, Dict, Any
from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function

# Try to import the real ServiceBusOperations, fallback to mock if it fails
try:
    from operations.service_bus_operations import ServiceBusOperations
    print("✓ Using Service Bus Operations")
except Exception as e:
    print(f"⚠ Could not import ServiceBusOperations: {e}")
    raise

# Initialize service bus operations
servicebus_operations = ServiceBusOperations()

class ServiceBusPlugin:
    def __init__(self, debug=False, session_id=None):
        self.debug = debug
        self.session_id = session_id

    def _log_function_call(self, function_name: str, **kwargs):
        """Log function calls for debugging"""
        if self.debug:
            print(f"🔧 [{self.session_id or 'ServiceBusPlugin'}] Calling {function_name} with args: {kwargs}")

    def _send_friendly_notification(self, message: str):
        """Send user-friendly notifications"""
        print(f"📢 {message}")

    ############################## KERNEL FUNCTION START #####################################
    @kernel_function(
        description="""
        Send a workflow message to trigger agent actions in the rate lock system.
        
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
        - "Send new_request message for loan LA12345"
        - "Trigger context_retrieved for loan processing"
        - "Notify agents of rates_presented event"
        - "Send compliance_passed message to continue workflow"
        """
    )
    async def send_workflow_message(self, message_type: Annotated[str, "Type of workflow message (new_request, context_retrieved, rates_presented, compliance_passed, exception_occurred)"],
                                   loan_application_id: Annotated[str, "Loan application ID for the workflow"],
                                   message_data: Annotated[str, "Message payload as JSON string"],
                                   correlation_id: Annotated[str, "Optional correlation ID for tracking"] = None) -> Annotated[Dict[str, Any], "Returns message sending status and details."]:
        
        self._log_function_call("send_workflow_message", message_type=message_type, loan_application_id=loan_application_id)
        self._send_friendly_notification(f"📨 Sending workflow message: {message_type} for loan {loan_application_id}...")
        
        if not message_type or not loan_application_id or not message_data:
            raise ValueError("message_type, loan_application_id, and message_data are required")
        
        try:
            # Parse message data
            try:
                data_payload = json.loads(message_data)
            except json.JSONDecodeError:
                print(f"⚠ Invalid JSON in message_data, wrapping as string: {message_data}")
                data_payload = {"raw_data": message_data}
            
            # Send message
            success = await servicebus_operations.send_workflow_message(
                message_type=message_type,
                loan_application_id=loan_application_id,
                message_data=data_payload,
                correlation_id=correlation_id
            )
            
            if success:
                self._send_friendly_notification(f"✅ Workflow message sent successfully")
                return {
                    "success": True,
                    "message_type": message_type,
                    "loan_application_id": loan_application_id,
                    "correlation_id": correlation_id,
                    "sent_at": datetime.utcnow().isoformat(),
                    "message": f"Workflow message '{message_type}' sent for loan {loan_application_id}"
                }
            else:
                self._send_friendly_notification(f"❌ Failed to send workflow message")
                return {
                    "success": False,
                    "error": "Failed to send workflow message",
                    "message_type": message_type,
                    "loan_application_id": loan_application_id
                }
                
        except Exception as e:
            print(f"❌ Error sending workflow message: {str(e)}")
            self._send_friendly_notification(f"❌ Error sending workflow message")
            return {"success": False, "error": str(e)}

    @kernel_function(
        description="""
        Send an audit message to record agent actions and system events.
        
        USE THIS WHEN:
        - Recording agent actions for compliance
        - Logging system events and outcomes
        - Creating audit trails for regulatory compliance
        - Tracking agent performance metrics
        
        Actions: EMAIL_PROCESSED, CONTEXT_RETRIEVED, RATES_GENERATED, COMPLIANCE_CHECKED, LOCK_CONFIRMED, EXCEPTION_ESCALATED
        """
    )
    async def send_audit_message(self, agent_name: Annotated[str, "Name of the agent performing the action"],
                                action: Annotated[str, "Action being performed (EMAIL_PROCESSED, CONTEXT_RETRIEVED, RATES_GENERATED, COMPLIANCE_CHECKED, LOCK_CONFIRMED, EXCEPTION_ESCALATED)"],
                                loan_application_id: Annotated[str, "Loan application ID associated with the action"],
                                audit_data: Annotated[str, "Audit details as JSON string"]) -> Annotated[Dict[str, Any], "Returns audit message sending status."]:
        
        self._log_function_call("send_audit_message", agent_name=agent_name, action=action)
        self._send_friendly_notification(f"📋 Sending audit message: {agent_name} - {action}...")
        
        if not agent_name or not action or not loan_application_id or not audit_data:
            raise ValueError("agent_name, action, loan_application_id, and audit_data are required")
        
        try:
            # Parse audit data
            try:
                data_payload = json.loads(audit_data)
            except json.JSONDecodeError:
                print(f"⚠ Invalid JSON in audit_data, wrapping as string: {audit_data}")
                data_payload = {"raw_data": audit_data}
            
            # Send message
            success = await servicebus_operations.send_audit_message(
                agent_name=agent_name,
                action=action,
                loan_application_id=loan_application_id,
                audit_data=data_payload
            )
            
            if success:
                self._send_friendly_notification(f"✅ Audit message sent successfully")
                return {
                    "success": True,
                    "agent_name": agent_name,
                    "action": action,
                    "loan_application_id": loan_application_id,
                    "sent_at": datetime.utcnow().isoformat(),
                    "message": f"Audit message sent for {agent_name} - {action}"
                }
            else:
                self._send_friendly_notification(f"❌ Failed to send audit message")
                return {
                    "success": False,
                    "error": "Failed to send audit message",
                    "agent_name": agent_name,
                    "action": action
                }
                
        except Exception as e:
            print(f"❌ Error sending audit message: {str(e)}")
            self._send_friendly_notification(f"❌ Error sending audit message")
            return {"success": False, "error": str(e)}

    @kernel_function(
        description="""
        Send an exception alert for issues requiring human intervention.
        
        USE THIS WHEN:
        - Agents encounter unresolvable errors
        - Compliance violations are detected
        - Technical failures need escalation
        - Manual review is required
        
        EXCEPTION TYPES:
        - COMPLIANCE_VIOLATION, TECHNICAL_ERROR, DATA_VALIDATION_FAILURE, SYSTEM_TIMEOUT, MISSING_DOCUMENTATION
        """
    )
    async def send_exception_alert(self, exception_type: Annotated[str, "Type of exception (COMPLIANCE_VIOLATION, TECHNICAL_ERROR, DATA_VALIDATION_FAILURE, SYSTEM_TIMEOUT, MISSING_DOCUMENTATION)"],
                                  priority: Annotated[str, "Priority level (high, medium, low)"],
                                  loan_application_id: Annotated[str, "Loan application ID associated with the exception"],
                                  exception_data: Annotated[str, "Exception details as JSON string"]) -> Annotated[Dict[str, Any], "Returns exception alert sending status."]:
        
        self._log_function_call("send_exception_alert", exception_type=exception_type, priority=priority)
        self._send_friendly_notification(f"🚨 Sending {priority} priority exception alert: {exception_type}...")
        
        if not exception_type or not priority or not loan_application_id or not exception_data:
            raise ValueError("exception_type, priority, loan_application_id, and exception_data are required")
        
        try:
            # Parse exception data
            try:
                data_payload = json.loads(exception_data)
            except json.JSONDecodeError:
                print(f"⚠ Invalid JSON in exception_data, wrapping as string: {exception_data}")
                data_payload = {"raw_data": exception_data}
            
            # Send message
            success = await servicebus_operations.send_exception_alert(
                exception_type=exception_type,
                priority=priority,
                loan_application_id=loan_application_id,
                exception_data=data_payload
            )
            
            if success:
                self._send_friendly_notification(f"✅ Exception alert sent successfully")
                return {
                    "success": True,
                    "exception_type": exception_type,
                    "priority": priority,
                    "loan_application_id": loan_application_id,
                    "sent_at": datetime.utcnow().isoformat(),
                    "message": f"{priority.upper()} priority exception alert sent: {exception_type}"
                }
            else:
                self._send_friendly_notification(f"❌ Failed to send exception alert")
                return {
                    "success": False,
                    "error": "Failed to send exception alert",
                    "exception_type": exception_type,
                    "priority": priority
                }
                
        except Exception as e:
            print(f"❌ Error sending exception alert: {str(e)}")
            self._send_friendly_notification(f"❌ Error sending exception alert")
            return {"success": False, "error": str(e)}

    async def send_message_to_topic(self, topic_name: str, message_body: str = None, correlation_id: str = None, 
                                   message_type: str = None, loan_application_id: str = None, message_data: dict = None) -> bool:
        """
        Send a message to a specific Service Bus topic.
        
        Args:
            topic_name (str): Name of the topic to send to
            message_body (str, optional): Message content (if not provided, will be generated from other params)
            correlation_id (str, optional): Correlation ID for tracking
            message_type (str, optional): Type of message for workflow coordination
            loan_application_id (str, optional): Loan application ID for tracking
            message_data (dict, optional): Additional message data
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self._log_function_call("send_message_to_topic", topic_name=topic_name, message_type=message_type, loan_application_id=loan_application_id)
            self._send_friendly_notification(f"📨 Sending message to topic: {topic_name}...")
            
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
            
            success = await servicebus_operations.send_message_to_topic(
                topic_name=topic_name,
                message_body=message_body,
                correlation_id=correlation_id
            )
            
            if success:
                self._send_friendly_notification(f"✅ Message sent to topic successfully")
            else:
                self._send_friendly_notification(f"❌ Failed to send message to topic")
                
            return success
            
        except Exception as e:
            print(f"❌ Error sending message to topic: {str(e)}")
            self._send_friendly_notification(f"❌ Error sending message to topic")
            return False

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
            self._log_function_call("send_message_to_queue", queue_name=queue_name, message_type=message_type, loan_application_id=loan_application_id)
            self._send_friendly_notification(f"📨 Sending message to queue: {queue_name}...")
            
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
            
            if success:
                self._send_friendly_notification(f"✅ Message sent to queue successfully")
            else:
                self._send_friendly_notification(f"❌ Failed to send message to queue")
                
            return success
            
        except Exception as e:
            print(f"❌ Error sending message to queue: {str(e)}")
            self._send_friendly_notification(f"❌ Error sending message to queue")
            return False

    async def close(self):
        """
        Clean up resources when the plugin is no longer needed.
        Note: ServiceBusOperations uses per-operation clients, so no cleanup needed.
        """
        print("Service Bus plugin resources cleaned up")
