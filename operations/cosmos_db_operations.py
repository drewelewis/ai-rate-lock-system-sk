import os
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
import asyncio
from azure.cosmos.aio import CosmosClient
from azure.cosmos import exceptions, PartitionKey
from azure.identity.aio import DefaultAzureCredential
from utils.logger import console_info, console_debug, console_warning, console_error, console_telemetry_event


class CosmosDBOperations:
    def __init__(self):
        """
        Initialize the CosmosDBOperations class.
        This class provides methods to interact with Azure Cosmos DB for the AI Rate Lock System.
        """
        
        # Configuration from environment variables
        self.cosmos_endpoint = os.getenv('AZURE_COSMOS_ENDPOINT')
        self.database_name = os.getenv('AZURE_COSMOS_DATABASE_NAME', 'RateLockSystem')
        self.credential = None
        self.cosmos_client = None
        self.database = None
        
        # Container names as defined in the Bicep template
        self.containers = {
            'rate_lock_records': 'RateLockRecords',
            'audit_logs': 'AuditLogs', 
            'configuration': 'Configuration',
            'exceptions': 'Exceptions'
        }
        
        # Cache for container references
        self._container_cache = {}
        
        console_info(f"Cosmos DB Operations initialized", "CosmosDBOps")
        console_info(f"Endpoint: {self.cosmos_endpoint}", "CosmosDBOps")
        console_info(f"Database: {self.database_name}", "CosmosDBOps")

    async def _get_cosmos_client(self):
        """
        Get or create Cosmos DB client with proper authentication.
        """
        if self.cosmos_client is None:
            try:
                if not self.cosmos_endpoint:
                    raise ValueError("AZURE_COSMOS_ENDPOINT environment variable is required")
                
                # Use DefaultAzureCredential for authentication
                self.credential = DefaultAzureCredential()
                self.cosmos_client = CosmosClient(self.cosmos_endpoint, self.credential)
                
                console_info("Cosmos DB client initialized successfully", "CosmosDBOps")
                
            except Exception as e:
                console_error(f"Failed to initialize Cosmos DB client: {e}", "CosmosDBOps")
                raise
        
        return self.cosmos_client

    async def _get_database(self):
        """
        Get or create database reference.
        """
        if self.database is None:
            try:
                client = await self._get_cosmos_client()
                self.database = client.get_database_client(self.database_name)
                console_debug(f"Database reference acquired: {self.database_name}", "CosmosDBOps")
                
            except Exception as e:
                console_error(f"Failed to get database reference: {e}", "CosmosDBOps")
                raise
        
        return self.database

    async def _get_container(self, container_name: str):
        """
        Get container reference with caching.
        """
        if container_name not in self._container_cache:
            try:
                database = await self._get_database()
                
                # Map logical names to actual container names
                actual_container_name = self.containers.get(container_name, container_name)
                container = database.get_container_client(actual_container_name)
                
                self._container_cache[container_name] = container
                console_debug(f"Container reference cached: {actual_container_name}", "CosmosDBOps")
                
            except Exception as e:
                console_error(f"Failed to get container reference for {container_name}: {e}", "CosmosDBOps")
                raise
        
        return self._container_cache[container_name]

    # Rate Lock Records Operations
    async def create_rate_lock_record(self, loan_application_id: str, rate_lock_data: Dict[str, Any]) -> bool:
        """
        Create a new rate lock record.
        
        Args:
            loan_application_id (str): The loan application ID (partition key)
            rate_lock_data (Dict[str, Any]): Rate lock data to store
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container = await self._get_container('rate_lock_records')
            
            # Ensure required fields
            record = {
                'id': rate_lock_data.get('id', f"rate_lock_{loan_application_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"),
                'loanApplicationId': loan_application_id,  # Partition key
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat(),
                'status': rate_lock_data.get('status', 'PendingRequest'),
                **rate_lock_data
            }
            
            await container.create_item(body=record)
            
            console_info(f"Rate lock record created: {record['id']}", "CosmosDBOps")
            console_telemetry_event("rate_lock_created", {
                "loan_application_id": loan_application_id,
                "record_id": record['id'],
                "status": record['status']
            }, "CosmosDBOps")
            
            return True
            
        except Exception as e:
            console_error(f"Failed to create rate lock record for {loan_application_id}: {e}", "CosmosDBOps")
            return False

    async def get_rate_lock_record(self, loan_application_id: str, record_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Get rate lock record by loan application ID.
        
        Args:
            loan_application_id (str): The loan application ID
            record_id (str, optional): Specific record ID to retrieve
            
        Returns:
            Optional[Dict[str, Any]]: Rate lock record or None if not found
        """
        try:
            container = await self._get_container('rate_lock_records')
            
            if record_id:
                # Get specific record
                response = await container.read_item(item=record_id, partition_key=loan_application_id)
                return dict(response)
            else:
                # Query for records by loan application ID
                query = "SELECT * FROM c WHERE c.loanApplicationId = @loan_app_id ORDER BY c.created_at DESC"
                items = container.query_items(
                    query=query,
                    parameters=[{"name": "@loan_app_id", "value": loan_application_id}],
                    partition_key=loan_application_id
                )
                
                records = [dict(item) async for item in items]
                return records[0] if records else None
                
        except exceptions.CosmosResourceNotFoundError:
            console_warning(f"Rate lock record not found for loan {loan_application_id}", "CosmosDBOps")
            return None
        except Exception as e:
            console_error(f"Failed to get rate lock record for {loan_application_id}: {e}", "CosmosDBOps")
            return None

    async def update_rate_lock_status(self, loan_application_id: str, record_id: str, status: str, updates: Dict[str, Any] = None) -> bool:
        """
        Update rate lock record status and other fields.
        
        Args:
            loan_application_id (str): The loan application ID
            record_id (str): The record ID to update
            status (str): New status
            updates (Dict[str, Any], optional): Additional fields to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container = await self._get_container('rate_lock_records')
            
            # Get current record
            current_record = await container.read_item(item=record_id, partition_key=loan_application_id)
            
            # Update fields
            current_record['status'] = status
            current_record['updated_at'] = datetime.utcnow().isoformat()
            
            if updates:
                current_record.update(updates)
            
            # Replace the item
            await container.replace_item(item=record_id, body=current_record)
            
            console_info(f"Rate lock record updated: {record_id} -> {status}", "CosmosDBOps")
            console_telemetry_event("rate_lock_updated", {
                "loan_application_id": loan_application_id,
                "record_id": record_id,
                "new_status": status,
                "updates": list(updates.keys()) if updates else []
            }, "CosmosDBOps")
            
            return True
            
        except Exception as e:
            console_error(f"Failed to update rate lock record {record_id}: {e}", "CosmosDBOps")
            return False

    # Audit Logs Operations
    async def create_audit_log(self, audit_data: Dict[str, Any]) -> bool:
        """
        Create an audit log entry.
        
        Args:
            audit_data (Dict[str, Any]): Audit log data
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container = await self._get_container('audit_logs')
            
            audit_date = datetime.utcnow().strftime('%Y-%m-%d')  # Partition key format
            
            # Ensure required fields
            log_entry = {
                'id': f"audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}",
                'auditDate': audit_date,  # Partition key
                'timestamp': datetime.utcnow().isoformat(),
                'agentName': audit_data.get('agent_name', 'Unknown'),
                'loanApplicationId': audit_data.get('loan_application_id'),
                'eventType': audit_data.get('event_type', 'UNKNOWN'),
                'action': audit_data.get('action'),
                'outcome': audit_data.get('outcome'),
                'details': audit_data.get('details', {}),
                'ttl': int((datetime.utcnow() + timedelta(days=30)).timestamp())  # Auto-delete after 30 days
            }
            
            await container.create_item(body=log_entry)
            
            console_debug(f"Audit log created: {log_entry['id']}", "CosmosDBOps")
            console_telemetry_event("audit_log_created", {
                "agent_name": log_entry['agentName'],
                "event_type": log_entry['eventType'],
                "loan_application_id": log_entry['loanApplicationId']
            }, "CosmosDBOps")
            
            return True
            
        except Exception as e:
            console_error(f"Failed to create audit log: {e}", "CosmosDBOps")
            return False

    async def get_audit_logs(self, loan_application_id: str = None, agent_name: str = None, 
                            start_date: str = None, end_date: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Query audit logs with various filters.
        
        Args:
            loan_application_id (str, optional): Filter by loan application ID
            agent_name (str, optional): Filter by agent name
            start_date (str, optional): Filter by start date (YYYY-MM-DD)
            end_date (str, optional): Filter by end date (YYYY-MM-DD)
            limit (int): Maximum number of records to return
            
        Returns:
            List[Dict[str, Any]]: List of audit log entries
        """
        try:
            container = await self._get_container('audit_logs')
            
            # Build query
            query_parts = ["SELECT * FROM c WHERE 1=1"]
            parameters = []
            
            if loan_application_id:
                query_parts.append("AND c.loanApplicationId = @loan_app_id")
                parameters.append({"name": "@loan_app_id", "value": loan_application_id})
            
            if agent_name:
                query_parts.append("AND c.agentName = @agent_name") 
                parameters.append({"name": "@agent_name", "value": agent_name})
            
            if start_date:
                query_parts.append("AND c.auditDate >= @start_date")
                parameters.append({"name": "@start_date", "value": start_date})
            
            if end_date:
                query_parts.append("AND c.auditDate <= @end_date")
                parameters.append({"name": "@end_date", "value": end_date})
            
            query_parts.append("ORDER BY c.timestamp DESC")
            query = " ".join(query_parts)
            
            items = container.query_items(query=query, parameters=parameters, max_item_count=limit)
            logs = [dict(item) async for item in items]
            
            console_info(f"Retrieved {len(logs)} audit log entries", "CosmosDBOps")
            return logs
            
        except Exception as e:
            console_error(f"Failed to query audit logs: {e}", "CosmosDBOps")
            return []

    # Exception Tracking Operations
    async def create_exception(self, priority: str, exception_data: Dict[str, Any]) -> str:
        """
        Create an exception record for human intervention.
        
        Args:
            priority (str): Exception priority (high, medium, low)
            exception_data (Dict[str, Any]): Exception details
            
        Returns:
            str: Exception ID if successful, None if failed
        """
        try:
            container = await self._get_container('exceptions')
            
            exception_id = f"exc_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
            
            # Ensure required fields
            exception_record = {
                'id': exception_id,
                'priority': priority.lower(),  # Partition key
                'status': 'open',
                'created': datetime.utcnow().isoformat(),
                'loanApplicationId': exception_data.get('loan_application_id'),
                'exceptionType': exception_data.get('exception_type'),
                'agentName': exception_data.get('agent_name'),
                'description': exception_data.get('description'),
                'context': exception_data.get('context', {}),
                'assignee': exception_data.get('assignee'),
                'estimatedResolutionTime': exception_data.get('estimated_resolution_time'),
                'ttl': int((datetime.utcnow() + timedelta(days=90)).timestamp())  # Auto-delete after 90 days
            }
            
            await container.create_item(body=exception_record)
            
            console_info(f"Exception created: {exception_id} (priority: {priority})", "CosmosDBOps")
            console_telemetry_event("exception_created", {
                "exception_id": exception_id,
                "priority": priority,
                "exception_type": exception_record['exceptionType'],
                "agent_name": exception_record['agentName']
            }, "CosmosDBOps")
            
            return exception_id
            
        except Exception as e:
            console_error(f"Failed to create exception: {e}", "CosmosDBOps")
            return None

    async def update_exception_status(self, exception_id: str, priority: str, status: str, 
                                    assignee: str = None, resolution_notes: str = None) -> bool:
        """
        Update exception status.
        
        Args:
            exception_id (str): Exception ID to update
            priority (str): Exception priority (for partition key)
            status (str): New status (open, in-progress, resolved)
            assignee (str, optional): Person assigned to handle
            resolution_notes (str, optional): Resolution details
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            container = await self._get_container('exceptions')
            
            # Get current record
            current_record = await container.read_item(item=exception_id, partition_key=priority)
            
            # Update fields
            current_record['status'] = status
            current_record['updated'] = datetime.utcnow().isoformat()
            
            if assignee:
                current_record['assignee'] = assignee
            
            if resolution_notes:
                current_record['resolutionNotes'] = resolution_notes
            
            if status == 'resolved':
                current_record['resolvedAt'] = datetime.utcnow().isoformat()
            
            # Replace the item
            await container.replace_item(item=exception_id, body=current_record)
            
            console_info(f"Exception updated: {exception_id} -> {status}", "CosmosDBOps")
            console_telemetry_event("exception_updated", {
                "exception_id": exception_id,
                "new_status": status,
                "assignee": assignee
            }, "CosmosDBOps")
            
            return True
            
        except Exception as e:
            console_error(f"Failed to update exception {exception_id}: {e}", "CosmosDBOps")
            return False

    async def get_exceptions_by_priority(self, priority: str, status: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get exceptions by priority and optionally status.
        
        Args:
            priority (str): Exception priority to filter by
            status (str, optional): Exception status to filter by
            limit (int): Maximum number of records to return
            
        Returns:
            List[Dict[str, Any]]: List of exception records
        """
        try:
            container = await self._get_container('exceptions')
            
            # Build query
            if status:
                query = "SELECT * FROM c WHERE c.priority = @priority AND c.status = @status ORDER BY c.created DESC"
                parameters = [
                    {"name": "@priority", "value": priority},
                    {"name": "@status", "value": status}
                ]
            else:
                query = "SELECT * FROM c WHERE c.priority = @priority ORDER BY c.created DESC"
                parameters = [{"name": "@priority", "value": priority}]
            
            items = container.query_items(
                query=query,
                parameters=parameters,
                partition_key=priority,
                max_item_count=limit
            )
            
            exceptions = [dict(item) async for item in items]
            
            console_info(f"Retrieved {len(exceptions)} exceptions (priority: {priority})", "CosmosDBOps")
            return exceptions
            
        except Exception as e:
            console_error(f"Failed to get exceptions by priority {priority}: {e}", "CosmosDBOps")
            return []

    async def close(self):
        """
        Clean up resources.
        """
        try:
            if self.cosmos_client:
                await self.cosmos_client.close()
                console_info("Cosmos DB client closed", "CosmosDBOps")
            
            if self.credential:
                await self.credential.close()
                console_info("Azure credential closed", "CosmosDBOps")
                
        except Exception as e:
            console_warning(f"Error closing Cosmos DB resources: {e}", "CosmosDBOps")
