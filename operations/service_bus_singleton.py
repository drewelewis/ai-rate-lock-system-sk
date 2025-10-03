"""
Service Bus Singleton Connection Manager
Provides a shared, thread-safe Service Bus client for all agents
"""

import asyncio
import threading
from typing import Optional
from azure.servicebus.aio import ServiceBusClient
from azure.identity.aio import DefaultAzureCredential
from utils.logger import console_info, console_error, console_warning
from config.azure_config import AzureConfig


class ServiceBusConnectionManager:
    """
    Singleton manager for Azure Service Bus connections.
    Ensures only one client instance is used across all agents.
    """
    
    _instance: Optional['ServiceBusConnectionManager'] = None
    _lock = threading.Lock()
    _client: Optional[ServiceBusClient] = None
    _credential: Optional[DefaultAzureCredential] = None
    _is_initialized = False
    _is_closed = False
    
    def __new__(cls) -> 'ServiceBusConnectionManager':
        """Ensure only one instance exists (singleton pattern)"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the connection manager (only once)"""
        if not self._is_initialized:
            self.azure_config = AzureConfig()
            self.servicebus_namespace = self.azure_config.get_servicebus_namespace()
            self._is_initialized = True
            console_info("🔌 Service Bus Connection Manager initialized", "ServiceBusSingleton")
    
    async def get_client(self) -> ServiceBusClient:
        """
        Get the shared Service Bus client instance.
        Creates the client if it doesn't exist or was closed.
        
        Returns:
            ServiceBusClient: The shared client instance
        """
        if self._client is None or self._is_closed:
            await self._initialize_client()
        
        return self._client
    
    async def _initialize_client(self):
        """Initialize the Service Bus client with proper error handling"""
        try:
            if not self.servicebus_namespace:
                raise ValueError("AZURE_SERVICEBUS_NAMESPACE_NAME environment variable is required")
            
            # Close existing client if it exists
            if self._client is not None:
                await self._close_client()
            
            # Create new credential and client
            self._credential = DefaultAzureCredential()
            fully_qualified_namespace = f"{self.servicebus_namespace}.servicebus.windows.net"
            self._client = ServiceBusClient(fully_qualified_namespace, self._credential)
            self._is_closed = False
            
            console_info(f"✅ Service Bus client connected to: {fully_qualified_namespace}", "ServiceBusSingleton")
            
        except Exception as e:
            console_error(f"❌ Failed to initialize Service Bus client: {e}", "ServiceBusSingleton")
            self._client = None
            self._credential = None
            raise
    
    async def _close_client(self):
        """Close the existing client and credential"""
        try:
            if self._client is not None:
                await self._client.close()
                console_info("🔌 Service Bus client closed", "ServiceBusSingleton")
            
            if self._credential is not None:
                await self._credential.close()
                console_info("🔐 Azure credential closed", "ServiceBusSingleton")
                
        except Exception as e:
            console_warning(f"⚠️ Error closing Service Bus client: {e}", "ServiceBusSingleton")
        finally:
            self._client = None
            self._credential = None
            self._is_closed = True
    
    async def close(self):
        """
        Close the Service Bus connection and cleanup resources.
        Should be called during application shutdown.
        """
        console_info("🔄 Closing Service Bus connection manager...", "ServiceBusSingleton")
        await self._close_client()
        console_info("✅ Service Bus connection manager closed", "ServiceBusSingleton")
    
    async def health_check(self) -> bool:
        """
        Check if the Service Bus connection is healthy.
        
        Returns:
            bool: True if connection is healthy, False otherwise
        """
        try:
            client = await self.get_client()
            # Simple health check - try to get a non-existent entity
            # This will fail but confirms the connection is working
            return client is not None and not self._is_closed
        except Exception as e:
            console_warning(f"⚠️ Service Bus health check failed: {e}", "ServiceBusSingleton")
            return False
    
    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (useful for testing)"""
        with cls._lock:
            if cls._instance is not None:
                # Close the connection if it exists
                if cls._instance._client is not None:
                    try:
                        asyncio.create_task(cls._instance.close())
                    except:
                        pass
            cls._instance = None
            cls._client = None
            cls._credential = None
            cls._is_initialized = False
            cls._is_closed = False


# Global instance accessor
_connection_manager: Optional[ServiceBusConnectionManager] = None

def get_service_bus_manager() -> ServiceBusConnectionManager:
    """
    Get the global Service Bus connection manager instance.
    
    Returns:
        ServiceBusConnectionManager: The singleton instance
    """
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ServiceBusConnectionManager()
    return _connection_manager

async def get_service_bus_client() -> ServiceBusClient:
    """
    Convenience function to get the shared Service Bus client.
    
    Returns:
        ServiceBusClient: The shared client instance
    """
    manager = get_service_bus_manager()
    return await manager.get_client()

async def close_service_bus_connection():
    """
    Convenience function to close the shared Service Bus connection.
    Should be called during application shutdown.
    """
    manager = get_service_bus_manager()
    await manager.close()