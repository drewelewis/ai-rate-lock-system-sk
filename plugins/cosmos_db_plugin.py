from datetime import datetime
import os
import asyncio
import json
from typing import List, Optional, Annotated, Dict, Any
from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function

# Try to import the real CosmosDBOperations, fallback to mock if it fails
try:
    from operations.cosmos_db_operations import CosmosDBOperations
    print("✓ Using Cosmos DB Operations")
except Exception as e:
    print(f"⚠ Could not import CosmosDBOperations: {e}")
    raise

# Initialize cosmos operations
cosmos_operations = CosmosDBOperations()

class CosmosDBPlugin:
    def __init__(self, debug=False, session_id=None):
        self.debug = debug
        self.session_id = session_id

    def _log_function_call(self, function_name: str, **kwargs):
        """Log function calls for debugging"""
        if self.debug:
            print(f"🔧 [{self.session_id or 'CosmosDBPlugin'}] Calling {function_name} with args: {kwargs}")

    def _send_friendly_notification(self, message: str):
        """Send user-friendly notifications"""
        print(f"📢 {message}")

    ############################## KERNEL FUNCTION START #####################################
    @kernel_function(
        description="""
        Create a new rate lock record for a loan application.
        
        USE THIS WHEN:
        - Starting a new rate lock process for a borrower
        - Email intake agent needs to create initial loan record
        - User requests to "create rate lock" or "start loan process"
        
        CAPABILITIES:
        - Creates new rate lock record in Cosmos DB
        - Sets initial status to 'PendingRequest'
        - Stores borrower information and loan details
        - Assigns unique record ID and timestamps
        
        COMMON USE CASES:
        - "Create a rate lock for loan application LA12345"
        - "Start new rate lock process for borrower John Smith"
        - "Initialize loan record with borrower details"
        
        Returns success status and created record ID.
        """
    )
    async def create_rate_lock(self, loan_application_id: Annotated[str, "The loan application ID (partition key)"], 
                              borrower_name: Annotated[str, "Name of the borrower"],
                              borrower_email: Annotated[str, "Email address of the borrower"],
                              borrower_phone: Annotated[str, "Phone number of the borrower"] = "",
                              property_address: Annotated[str, "Property address for the loan"] = "",
                              requested_lock_period: Annotated[str, "Requested lock period in days"] = "30",
                              additional_data: Annotated[str, "Additional loan data as JSON string"] = None) -> Annotated[Dict[str, Any], "Returns creation status and record details."]:
        
        self._log_function_call("create_rate_lock", loan_application_id=loan_application_id, borrower_name=borrower_name)
        self._send_friendly_notification(f"🏠 Creating rate lock record for loan: {loan_application_id}...")
        
        if not loan_application_id or not borrower_name or not borrower_email:
            raise ValueError("loan_application_id, borrower_name, and borrower_email are required")
        
        try:
            # Parse additional data if provided
            extra_data = {}
            if additional_data:
                try:
                    extra_data = json.loads(additional_data)
                except json.JSONDecodeError:
                    print(f"⚠ Invalid JSON in additional_data, ignoring: {additional_data}")
            
            # Prepare rate lock data
            rate_lock_data = {
                'borrower_name': borrower_name,
                'borrower_email': borrower_email,
                'borrower_phone': borrower_phone,
                'property_address': property_address,
                'requested_lock_period': int(requested_lock_period) if requested_lock_period.isdigit() else 30,
                'status': 'PendingRequest',
                'request_source': 'email_intake',
                **extra_data
            }
            
            # Create record
            success = await cosmos_operations.create_rate_lock_record(loan_application_id, rate_lock_data)
            
            if success:
                self._send_friendly_notification(f"✅ Rate lock record created successfully for {borrower_name}")
                return {
                    "success": True,
                    "loan_application_id": loan_application_id,
                    "borrower_name": borrower_name,
                    "status": "PendingRequest",
                    "created_at": datetime.utcnow().isoformat(),
                    "message": f"Rate lock record created for {borrower_name}"
                }
            else:
                self._send_friendly_notification(f"❌ Failed to create rate lock record")
                return {
                    "success": False,
                    "error": "Failed to create rate lock record",
                    "loan_application_id": loan_application_id
                }
                
        except Exception as e:
            print(f"❌ Error creating rate lock record: {str(e)}")
            self._send_friendly_notification(f"❌ Error creating rate lock record")
            return {"success": False, "error": str(e), "loan_application_id": loan_application_id}

    @kernel_function(
        description="""
        Retrieve rate lock record information by loan application ID.
        
        USE THIS WHEN:
        - Agents need to check current loan status
        - User asks about specific loan application
        - Need to get borrower information for processing
        - Checking loan progression through workflow
        
        CAPABILITIES:
        - Returns complete rate lock record
        - Shows current status and progression
        - Provides borrower and loan details
        - Includes timestamps and audit trail
        
        COMMON USE CASES:
        - "Get information for loan LA12345"
        - "What's the status of loan application 67890?"
        - "Show me details for borrower John Smith's loan"
        - "Check loan record for property at 123 Main St"
        
        Returns complete rate lock record with all details.
        """
    )
    async def get_rate_lock(self, loan_application_id: Annotated[str, "The loan application ID to retrieve"]) -> Annotated[Dict[str, Any], "Returns complete rate lock record with borrower details, loan information, and current status."]:
        
        self._log_function_call("get_rate_lock", loan_application_id=loan_application_id)
        self._send_friendly_notification(f"🔍 Looking up rate lock record: {loan_application_id}...")
        
        if not loan_application_id:
            raise ValueError("loan_application_id is required")
        
        try:
            record = await cosmos_operations.get_rate_lock_record(loan_application_id)
            
            if record:
                self._send_friendly_notification(f"✅ Found rate lock record for {record.get('borrower_name', 'Unknown')}")
                return {
                    "found": True,
                    "loan_application_id": loan_application_id,
                    **record
                }
            else:
                self._send_friendly_notification(f"❌ No rate lock record found for {loan_application_id}")
                return {
                    "found": False,
                    "loan_application_id": loan_application_id,
                    "message": f"No rate lock record found for loan application {loan_application_id}"
                }
                
        except Exception as e:
            print(f"❌ Error retrieving rate lock record: {str(e)}")
            self._send_friendly_notification(f"❌ Error looking up loan record")
            return {"found": False, "error": str(e), "loan_application_id": loan_application_id}

    @kernel_function(
        description="""
        Update the status of a rate lock record and add progression details.
        
        USE THIS WHEN:
        - Agents complete their processing steps
        - Moving loan through workflow stages
        - Updating loan status after agent actions
        - Recording progression milestones
        
        CAPABILITIES:
        - Updates loan status in workflow
        - Records agent actions and outcomes
        - Adds timestamps for audit trail
        - Stores additional processing details
        
        COMMON USE CASES:
        - "Update loan LA12345 to 'UnderReview'"
        - "Set loan status to 'RateOptionsPresented'"
        - "Mark loan as 'CompliancePassed'"
        - "Update status to 'Locked' with confirmation details"
        
        Status options: PendingRequest, UnderReview, RateOptionsPresented, CompliancePassed, Locked, Exception
        """
    )
    async def update_rate_lock_status(self, loan_application_id: Annotated[str, "The loan application ID to update"], 
                                    record_id: Annotated[str, "The specific record ID to update"],
                                    new_status: Annotated[str, "New status for the rate lock (PendingRequest, UnderReview, RateOptionsPresented, CompliancePassed, Locked, Exception)"],
                                    agent_name: Annotated[str, "Name of the agent making the update"] = None,
                                    update_details: Annotated[str, "Additional update details as JSON string"] = None) -> Annotated[Dict[str, Any], "Returns update status and confirmation details."]:
        
        self._log_function_call("update_rate_lock_status", loan_application_id=loan_application_id, new_status=new_status)
        self._send_friendly_notification(f"📝 Updating loan {loan_application_id} to status: {new_status}...")
        
        if not loan_application_id or not record_id or not new_status:
            raise ValueError("loan_application_id, record_id, and new_status are required")
        
        try:
            # Parse update details if provided
            updates = {}
            if update_details:
                try:
                    updates = json.loads(update_details)
                except json.JSONDecodeError:
                    print(f"⚠ Invalid JSON in update_details, ignoring: {update_details}")
            
            # Add agent information
            if agent_name:
                updates['last_updated_by'] = agent_name
            
            updates['status_history'] = updates.get('status_history', [])
            updates['status_history'].append({
                'status': new_status,
                'updated_at': datetime.utcnow().isoformat(),
                'updated_by': agent_name or 'System'
            })
            
            # Update record
            success = await cosmos_operations.update_rate_lock_status(
                loan_application_id, record_id, new_status, updates
            )
            
            if success:
                self._send_friendly_notification(f"✅ Status updated to {new_status}")
                return {
                    "success": True,
                    "loan_application_id": loan_application_id,
                    "record_id": record_id,
                    "new_status": new_status,
                    "updated_by": agent_name,
                    "updated_at": datetime.utcnow().isoformat(),
                    "message": f"Loan status updated to {new_status}"
                }
            else:
                self._send_friendly_notification(f"❌ Failed to update loan status")
                return {
                    "success": False,
                    "error": "Failed to update rate lock status",
                    "loan_application_id": loan_application_id,
                    "record_id": record_id
                }
                
        except Exception as e:
            print(f"❌ Error updating rate lock status: {str(e)}")
            self._send_friendly_notification(f"❌ Error updating loan status")
            return {"success": False, "error": str(e), "loan_application_id": loan_application_id}

    @kernel_function(
        description="""
        Create an audit log entry for agent actions and system events.
        
        USE THIS WHEN:
        - Agents complete actions that need audit trail
        - Recording compliance-related activities
        - Logging system events and outcomes
        - Creating regulatory compliance records
        
        CAPABILITIES:
        - Creates detailed audit logs
        - Records agent actions and outcomes
        - Stores event context and details
        - Supports compliance reporting
        
        COMMON USE CASES:
        - "Log agent action: email processed"
        - "Record compliance check outcome"
        - "Audit rate quote generation"
        - "Log exception escalation"
        
        Event types: AGENT_ACTION, COMPLIANCE_CHECK, RATE_QUOTE, EXCEPTION, SYSTEM_EVENT
        """
    )
    async def create_audit_log(self, agent_name: Annotated[str, "Name of the agent performing the action"],
                              action: Annotated[str, "Action being performed"],
                              event_type: Annotated[str, "Type of event (AGENT_ACTION, COMPLIANCE_CHECK, RATE_QUOTE, EXCEPTION, SYSTEM_EVENT)"],
                              outcome: Annotated[str, "Outcome of the action (SUCCESS, FAILURE, WARNING)"],
                              loan_application_id: Annotated[str, "Associated loan application ID"] = None,
                              details: Annotated[str, "Additional details as JSON string"] = None) -> Annotated[Dict[str, Any], "Returns audit log creation status."]:
        
        self._log_function_call("create_audit_log", agent_name=agent_name, action=action, event_type=event_type)
        self._send_friendly_notification(f"📋 Creating audit log: {agent_name} - {action}...")
        
        if not agent_name or not action or not event_type or not outcome:
            raise ValueError("agent_name, action, event_type, and outcome are required")
        
        try:
            # Parse details if provided
            detail_data = {}
            if details:
                try:
                    detail_data = json.loads(details)
                except json.JSONDecodeError:
                    print(f"⚠ Invalid JSON in details, storing as string: {details}")
                    detail_data = {"raw_details": details}
            
            # Prepare audit data
            audit_data = {
                'agent_name': agent_name,
                'action': action,
                'event_type': event_type,
                'outcome': outcome,
                'loan_application_id': loan_application_id,
                'details': detail_data
            }
            
            # Create audit log
            success = await cosmos_operations.create_audit_log(audit_data)
            
            if success:
                self._send_friendly_notification(f"✅ Audit log created for {agent_name} action")
                return {
                    "success": True,
                    "agent_name": agent_name,
                    "action": action,
                    "event_type": event_type,
                    "outcome": outcome,
                    "logged_at": datetime.utcnow().isoformat(),
                    "message": f"Audit log created for {agent_name} - {action}"
                }
            else:
                self._send_friendly_notification(f"❌ Failed to create audit log")
                return {
                    "success": False,
                    "error": "Failed to create audit log",
                    "agent_name": agent_name,
                    "action": action
                }
                
        except Exception as e:
            print(f"❌ Error creating audit log: {str(e)}")
            self._send_friendly_notification(f"❌ Error creating audit log")
            return {"success": False, "error": str(e)}

    @kernel_function(
        description="""
        Retrieve audit logs for analysis and compliance reporting.
        
        USE THIS WHEN:
        - Need to review agent actions for a loan
        - Generating compliance reports
        - Investigating loan processing issues
        - Auditing system performance
        
        CAPABILITIES:
        - Queries audit logs by various filters
        - Returns detailed action history
        - Supports date range filtering
        - Provides compliance reporting data
        
        COMMON USE CASES:
        - "Get audit logs for loan LA12345"
        - "Show all actions by compliance agent"
        - "Retrieve audit trail for last week"
        - "Get logs for troubleshooting loan processing"
        
        Returns list of audit log entries matching criteria.
        """
    )
    async def get_audit_logs(self, loan_application_id: Annotated[str, "Loan application ID to filter by"] = None,
                            agent_name: Annotated[str, "Agent name to filter by"] = None,
                            start_date: Annotated[str, "Start date for filtering (YYYY-MM-DD)"] = None,
                            end_date: Annotated[str, "End date for filtering (YYYY-MM-DD)"] = None,
                            limit: Annotated[int, "Maximum number of logs to return"] = 50) -> Annotated[List[Dict[str, Any]], "Returns list of audit log entries matching the criteria."]:
        
        self._log_function_call("get_audit_logs", loan_application_id=loan_application_id, agent_name=agent_name)
        self._send_friendly_notification(f"📊 Retrieving audit logs...")
        
        try:
            logs = await cosmos_operations.get_audit_logs(
                loan_application_id=loan_application_id,
                agent_name=agent_name,
                start_date=start_date,
                end_date=end_date,
                limit=limit
            )
            
            log_count = len(logs)
            self._send_friendly_notification(f"✅ Retrieved {log_count} audit log entries")
            
            return {
                "success": True,
                "count": log_count,
                "filters": {
                    "loan_application_id": loan_application_id,
                    "agent_name": agent_name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": limit
                },
                "logs": logs
            }
                
        except Exception as e:
            print(f"❌ Error retrieving audit logs: {str(e)}")
            self._send_friendly_notification(f"❌ Error retrieving audit logs")
            return {"success": False, "error": str(e)}

    @kernel_function(
        description="""
        Create an exception record for issues requiring human intervention.
        
        USE THIS WHEN:
        - Agents encounter unresolvable issues
        - Compliance violations are detected
        - Technical errors require escalation
        - Manual review is needed
        
        CAPABILITIES:
        - Creates exception records for human review
        - Assigns priority levels for triage
        - Stores context for resolution
        - Tracks escalation details
        
        COMMON USE CASES:
        - "Create high priority exception for compliance failure"
        - "Escalate technical error to human review"
        - "Flag loan for manual underwriter review"
        - "Create exception for missing documentation"
        
        Priority levels: high, medium, low
        """
    )
    async def create_exception(self, priority: Annotated[str, "Exception priority (high, medium, low)"],
                              exception_type: Annotated[str, "Type of exception"],
                              description: Annotated[str, "Description of the exception"],
                              agent_name: Annotated[str, "Agent that identified the exception"],
                              loan_application_id: Annotated[str, "Associated loan application ID"] = None,
                              context: Annotated[str, "Additional context as JSON string"] = None,
                              assignee: Annotated[str, "Person assigned to handle the exception"] = None,
                              estimated_resolution_time: Annotated[str, "Estimated time to resolve"] = None) -> Annotated[Dict[str, Any], "Returns exception creation status and ID."]:
        
        self._log_function_call("create_exception", priority=priority, exception_type=exception_type)
        self._send_friendly_notification(f"🚨 Creating {priority} priority exception: {exception_type}...")
        
        if not priority or not exception_type or not description or not agent_name:
            raise ValueError("priority, exception_type, description, and agent_name are required")
        
        try:
            # Parse context if provided
            context_data = {}
            if context:
                try:
                    context_data = json.loads(context)
                except json.JSONDecodeError:
                    print(f"⚠ Invalid JSON in context, storing as string: {context}")
                    context_data = {"raw_context": context}
            
            # Prepare exception data
            exception_data = {
                'exception_type': exception_type,
                'description': description,
                'agent_name': agent_name,
                'loan_application_id': loan_application_id,
                'context': context_data,
                'assignee': assignee,
                'estimated_resolution_time': estimated_resolution_time
            }
            
            # Create exception
            exception_id = await cosmos_operations.create_exception(priority, exception_data)
            
            if exception_id:
                self._send_friendly_notification(f"✅ Exception created with ID: {exception_id}")
                return {
                    "success": True,
                    "exception_id": exception_id,
                    "priority": priority,
                    "exception_type": exception_type,
                    "status": "open",
                    "created_at": datetime.utcnow().isoformat(),
                    "message": f"Exception {exception_id} created with {priority} priority"
                }
            else:
                self._send_friendly_notification(f"❌ Failed to create exception")
                return {
                    "success": False,
                    "error": "Failed to create exception record",
                    "priority": priority,
                    "exception_type": exception_type
                }
                
        except Exception as e:
            print(f"❌ Error creating exception: {str(e)}")
            self._send_friendly_notification(f"❌ Error creating exception record")
            return {"success": False, "error": str(e)}

    async def close(self):
        """
        Clean up resources when the plugin is no longer needed.
        """
        try:
            await cosmos_operations.close()
            print("Cosmos DB plugin resources cleaned up")
        except Exception as e:
            print(f"Error during Cosmos DB plugin cleanup: {e}")
