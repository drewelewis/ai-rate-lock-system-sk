#!/usr/bin/env python3
"""
Test script to send messages to the Service Bus queue continuously
to validate the AI Rate Lock System is processing messages correctly.
Uses Faker to generate realistic test data every 10 seconds.
"""

import asyncio
import json
from datetime import datetime
from dotenv import load_dotenv
from faker import Faker
import signal
import sys

# Load environment variables from .env file
load_dotenv()

from operations.service_bus_operations import ServiceBusOperations

# Initialize Faker
fake = Faker('en_US')

# Global flag for graceful shutdown
running = True

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global running
    print("\n🛑 Stopping message generation...")
    running = False

async def send_single_test_message(service_bus, message_count=1):
    """Send a single test email message with realistic fake data."""
    
    try:
        # Generate realistic fake data
        borrower_name = fake.name()
        borrower_email = fake.email()
        phone_number = fake.phone_number()
        property_address = fake.address().replace('\n', ', ')
        loan_amount = fake.random_int(min=200000, max=800000, step=1000)
        application_id = f"APP-{fake.random_int(min=100000, max=999999)}"
        
        # Create a realistic email message as raw text (what the LLM should parse)
        email_content = f"""From: {borrower_email}
To: loans@mortgagecompany.com  
Subject: Rate Lock Request - Urgent Processing Needed
Date: {datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')}

Hello Loan Processing Team,

I would like to request a rate lock for my loan application.

Loan Application ID: {application_id}
Borrower Name: {borrower_name}
Property Address: {property_address}
Loan Amount: ${loan_amount:,}
Contact Phone: {phone_number}

Please process this request as soon as possible as rates are expected to change soon.

Best regards,
{borrower_name}
Email: {borrower_email}
Phone: {phone_number}
"""
        
        print(f"🚀 Sending message #{message_count}...")
        print(f"   👤 Borrower: {borrower_name}")
        print(f"   📧 Email: {borrower_email}")
        print(f"   🏠 Property: {property_address[:50]}...")
        print(f"   💰 Loan Amount: ${loan_amount:,}")
        print(f"   🆔 Application ID: {application_id}")
        
        # Send the raw email content directly - this is what the LLM should intelligently parse
        # No JSON wrapper - just the raw email text as it would come from an email server
        success = await service_bus.send_message(
            destination_name="inbound_email",
            message_body=email_content,  # Raw email text only
            destination_type="queue"
        )
        
        if success:
            message_id = f"test-{datetime.now().strftime('%Y%m%d_%H%M%S')}-{message_count}"
            print(f"✅ Message #{message_count} sent successfully! (ID: {message_id})")
        else:
            print(f"❌ Failed to send message #{message_count}")
            
        return success
        
    except Exception as e:
        print(f"❌ Error sending message #{message_count}: {str(e)}")
        return False

async def send_continuous_test_messages():
    """Send test messages continuously every 10 seconds."""
    
    global running
    message_count = 0
    
    try:
        # Initialize Service Bus operations
        service_bus = ServiceBusOperations()
        
        print("📨 AI Rate Lock System - Continuous Test Message Sender")
        print("=" * 60)
        print("� Sending realistic test messages every 10 seconds...")
        print("🛑 Press Ctrl+C to stop")
        print("=" * 60)
        
        while running:
            message_count += 1
            
            # Send a single message
            success = await send_single_test_message(service_bus, message_count)
            
            if not success:
                print("⚠️  Message sending failed, but continuing...")
            
            # Wait 10 seconds before next message (unless stopping)
            if running:
                print(f"⏱️  Waiting 10 seconds before next message... (Total sent: {message_count})")
                print("-" * 40)
                
                # Use asyncio.sleep with interruption check
                for i in range(10):
                    if not running:
                        break
                    await asyncio.sleep(1)
        
        print(f"\n🏁 Stopped. Total messages sent: {message_count}")
        
    except Exception as e:
        print(f"❌ Error in continuous message loop: {str(e)}")
        raise

async def send_test_email_message():
    """Send a single test email message (for backwards compatibility)."""
    service_bus = ServiceBusOperations()
    return await send_single_test_message(service_bus, 1)

if __name__ == "__main__":
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    # Check command line arguments for mode
    if len(sys.argv) > 1 and sys.argv[1] == "--single":
        print("📨 AI Rate Lock System - Single Test Message Sender")
        print("=" * 50)
        asyncio.run(send_test_email_message())
    else:
        # Default to continuous mode
        asyncio.run(send_continuous_test_messages())