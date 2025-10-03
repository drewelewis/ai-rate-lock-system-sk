"""
Azure Configuration Management
Handles environment-specific Azure service connections
Compatible with Azure Developer CLI (azd) outputs
"""
import os
from typing import Tuple


class AzureConfig:
    """Manages Azure service configurations based on environment"""
    
    def __init__(self):
        self.environment = os.getenv('ENVIRONMENT', 'development').lower()
        
    def get_openai_endpoint(self) -> str:
        """Get Azure OpenAI endpoint"""
        return os.getenv('AZURE_OPENAI_ENDPOINT', os.getenv('OPENAI_BASE'))
    
    def get_openai_service_name(self) -> str:
        """Get Azure OpenAI service name"""
        return os.getenv('AZURE_OPENAI_SERVICE', 'openai-service')
    
    def get_cosmosdb_endpoint(self) -> str:
        """Get Cosmos DB endpoint"""
        return os.getenv('AZURE_COSMOS_ENDPOINT')
    
    def get_cosmosdb_database(self) -> str:
        """Get Cosmos DB database name"""
        return os.getenv('AZURE_COSMOS_DATABASE_NAME', 'RateLockSystem')
    
    def get_servicebus_endpoint(self) -> str:
        """Get Service Bus endpoint"""
        return os.getenv('AZURE_SERVICEBUS_ENDPOINT', os.getenv('AZURE_SERVICE_BUS_ENDPOINT'))
        
    def get_servicebus_namespace(self) -> str:
        """Get Service Bus namespace"""
        return os.getenv('AZURE_SERVICEBUS_NAMESPACE_NAME', os.getenv('AZURE_SERVICE_BUS_NAMESPACE'))
    
    def get_servicebus_queue_inbound_email(self) -> str:
        """Get inbound email queue name"""
        return os.getenv('AZURE_SERVICEBUS_QUEUE_INBOUND_EMAIL', 'inbound-email-queue')
    
    def get_servicebus_queue_outbound_confirmations(self) -> str:
        """Get outbound confirmations queue name"""
        return os.getenv('AZURE_SERVICEBUS_QUEUE_OUTBOUND_CONFIRMATIONS', 'outbound-email-queue')
    
    def get_servicebus_queue_high_priority_exceptions(self) -> str:
        """Get high priority exceptions queue name"""
        return os.getenv('AZURE_SERVICEBUS_QUEUE_HIGH_PRIORITY_EXCEPTIONS', 'high-priority-exceptions')
    
    def get_servicebus_topic_loan_lifecycle(self) -> str:
        """Get loan lifecycle events topic name (main workflow coordination)"""
        return os.getenv('AZURE_SERVICEBUS_TOPIC_LOAN_LIFECYCLE', 'loan-lifecycle-events')
    
    def get_servicebus_topic_audit_events(self) -> str:
        """Get audit events topic name (all audit logging)"""
        return os.getenv('AZURE_SERVICEBUS_TOPIC_AUDIT_EVENTS', 'audit-events')
    
    def get_servicebus_topic_compliance_events(self) -> str:
        """Get compliance events topic name (regulatory notifications)"""
        return os.getenv('AZURE_SERVICEBUS_TOPIC_COMPLIANCE_EVENTS', 'compliance-events')
    
    def get_servicebus_topic_exception_alerts(self) -> str:
        """Get exception alerts topic name (error handling)"""
        return os.getenv('AZURE_SERVICEBUS_TOPIC_EXCEPTION_ALERTS', 'exception-alerts')
    
    def get_container_registry(self) -> str:
        """Get Container Registry endpoint"""
        return os.getenv('AZURE_CONTAINER_REGISTRY_ENDPOINT')
    

    
    def get_azure_location(self) -> str:
        """Get Azure region"""
        return os.getenv('AZURE_LOCATION', 'eastus')
    
    def get_azure_subscription_id(self) -> str:
        """Get Azure subscription ID"""
        return os.getenv('AZURE_SUBSCRIPTION_ID')
    
    def get_azure_tenant_id(self) -> str:
        """Get Azure tenant ID"""
        return os.getenv('AZURE_TENANT_ID')
    
    # Legacy methods for backward compatibility
    def get_servicebus_connection(self) -> str:
        """Legacy method - returns Service Bus endpoint"""
        return self.get_servicebus_endpoint()
        
    def get_cosmosdb_connection(self) -> str:
        """Legacy method - returns Cosmos DB endpoint"""
        return self.get_cosmosdb_endpoint()
    
    def get_redis_config(self) -> Tuple[str, int, int]:
        """Get Redis configuration (host, port, db) - Optional component"""
        host = os.getenv('REDIS_HOST', 'localhost')
        port = int(os.getenv('REDIS_PORT', 6379))
        db = int(os.getenv('REDIS_DB', 0))
        return host, port, db
    
    def is_redis_enabled(self) -> bool:
        """Check if Redis is configured and should be used"""
        return bool(os.getenv('REDIS_HOST'))
    
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.environment == 'development'
    
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment == 'production'
    
    def validate_configuration(self) -> dict:
        """Validate that all required configuration is present"""
        validation = {
            'openai_endpoint': bool(self.get_openai_endpoint()),
            'cosmos_endpoint': bool(self.get_cosmosdb_endpoint()),
            'servicebus_endpoint': bool(self.get_servicebus_endpoint()),
            'database_name': bool(self.get_cosmosdb_database()),
            'namespace': bool(self.get_servicebus_namespace()),
            'environment': bool(self.environment)
        }
        return validation
    
    def get_configuration_summary(self) -> str:
        """Get a summary of current configuration"""
        validation = self.validate_configuration()
        missing = [k for k, v in validation.items() if not v]
        
        summary = f"Environment: {self.environment}\n"
        summary += f"OpenAI: {'✅' if validation['openai_endpoint'] else '❌'}\n"
        summary += f"Cosmos DB: {'✅' if validation['cosmos_endpoint'] else '❌'}\n" 
        summary += f"Service Bus: {'✅' if validation['servicebus_endpoint'] else '❌'}\n"
        summary += f"Redis: {'✅' if self.is_redis_enabled() else '⚪ (optional)'}\n"
        
        if missing:
            summary += f"\n⚠️  Missing: {', '.join(missing)}"
            summary += "\n💡 Run 'azd up' to deploy infrastructure"
        else:
            summary += "\n🎯 All required configuration present!"
            
        return summary


# Global instance
azure_config = AzureConfig()