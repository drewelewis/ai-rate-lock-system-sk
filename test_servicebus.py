#!/usr/bin/env python3
"""
Test script to check Service Bus queues for messages
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from operations.service_bus_operations import ServiceBusOperations

async def check_queues():
    """Check all queues for messages"""
    sb = ServiceBusOperations()
    
    print(f"Service Bus namespace: {sb.servicebus_namespace}")
    
    # Queue names from the infrastructure
    queues_to_check = [
        'inbound-email-queue',
        'outbound-confirmations', 
        'high-priority-exceptions'
    ]
    
    for queue_name in queues_to_check:
        print(f"\n=== Checking queue: {queue_name} ===")
        try:
            messages = await sb.receive_queue_messages(queue_name, max_wait_time=2)
            print(f"Found {len(messages)} messages in {queue_name}")
            
            for i, msg in enumerate(messages):
                print(f"  Message {i+1}:")
                print(f"    ID: {msg.get('message_id', 'N/A')}")
                print(f"    Correlation ID: {msg.get('correlation_id', 'N/A')}")
                print(f"    Delivery Count: {msg.get('delivery_count', 'N/A')}")
                print(f"    Body Preview: {str(msg.get('body', {}))[:100]}...")
                
        except Exception as e:
            print(f"Error checking queue {queue_name}: {e}")
    
    # No cleanup needed - each operation uses its own client with auto-cleanup

if __name__ == "__main__":
    asyncio.run(check_queues())