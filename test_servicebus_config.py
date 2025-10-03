#!/usr/bin/env python3
"""
Test script to verify Service Bus configuration and authentication
"""

import asyncio
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from config.azure_config import AzureConfig
from operations.service_bus_operations import ServiceBusOperations

async def test_servicebus_config():
    """Test Service Bus configuration and basic connectivity"""
    
    print("🔧 Testing Service Bus Configuration...")
    
    # Test Azure Config
    azure_config = AzureConfig()
    print(f"📍 Service Bus Namespace: {azure_config.get_servicebus_namespace()}")
    
    print("\n📋 Queue Configuration:")
    print(f"  - Inbound Email: {azure_config.get_servicebus_queue_inbound_email()}")
    print(f"  - Outbound Confirmations: {azure_config.get_servicebus_queue_outbound_confirmations()}")
    print(f"  - High Priority Exceptions: {azure_config.get_servicebus_queue_high_priority_exceptions()}")
    
    print("\n📋 Topic Configuration:")
    print(f"  - Loan Lifecycle: {azure_config.get_servicebus_topic_loan_lifecycle()}")
    print(f"  - Audit Events: {azure_config.get_servicebus_topic_audit_events()}")
    print(f"  - Compliance Events: {azure_config.get_servicebus_topic_compliance_events()}")
    print(f"  - Exception Alerts: {azure_config.get_servicebus_topic_exception_alerts()}")
    
    # Test Service Bus Operations
    print("\n🔌 Testing Service Bus Operations...")
    sb_ops = ServiceBusOperations()
    
    print(f"📡 Configured Topics: {list(sb_ops.topics.keys())}")
    print(f"📦 Configured Queues: {list(sb_ops.queues.keys())}")
    
    # Test authentication by checking queue messages
    print("\n🔐 Testing authentication...")
    try:
        messages = await sb_ops.receive_queue_messages('inbound_email', max_wait_time=1)
        print(f"✅ Successfully connected to queue! Found {len(messages)} messages")
        
        # Test topic connection by trying to receive from agent-workflow topic  
        print("\n📺 Testing topic subscription access...")
        # Test with logical name (should be mapped to actual topic name)
        topic_messages = await sb_ops.receive_messages('agent_workflow', 'email-intake-agent', max_wait_time=1)
        print(f"✅ Successfully connected to topic using logical name! Found {len(topic_messages)} messages")
        
    except Exception as e:
        print(f"❌ Authentication/Connection error: {e}")
        return False
    
    print("\n🎉 Service Bus configuration test completed successfully!")
    return True

if __name__ == "__main__":
    asyncio.run(test_servicebus_config())