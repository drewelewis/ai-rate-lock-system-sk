"""

AI Rate Lock System - Production Main Application

Runs all agents autonomously to process rate lock requests continuously.

"""

import os
import asyncio
import logging
import signal
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
import os
from datetime import datetime
from typing import Dict, Any, List

# Configure logging
from datetime import datetime

# Create a unique log file for each run in the logs directory
log_filename = f"logs/ai_rate_lock_system_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

# Remove any existing handlers to start fresh
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, mode='w', encoding='utf-8'),  # Fresh file each run
        logging.StreamHandler(sys.stdout)
    ],
    force=True  # Force reconfiguration
)

# Reduce Azure SDK noise while keeping important messages
azure_loggers = [
    'azure.servicebus._pyamqp',
    'azure.servicebus.aio._base_handler_async',
    'azure.servicebus._common.utils',
    'azure.servicebus.aio._servicebus_receiver_async',
    'azure.servicebus.aio._servicebus_sender_async',
    'azure.core.pipeline.policies.http_logging_policy',
    'azure.identity.aio._credentials',
    'azure.identity.aio._internal'
]

for azure_logger_name in azure_loggers:
    azure_logger = logging.getLogger(azure_logger_name)
    azure_logger.setLevel(logging.WARNING)  # Only show warnings and errors

# Keep important Azure Service Bus logs at INFO level
important_azure_loggers = [
    'azure.servicebus',
    'azure.identity'
]
for logger_name in important_azure_loggers:
    if not any(logger_name.startswith(noisy) for noisy in azure_loggers):
        logging.getLogger(logger_name).setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# Import agents
from agents.email_intake_agent import EmailIntakeAgent
from agents.rate_quote_agent import RateQuoteAgent
from agents.loan_context_agent import LoanApplicationContextAgent
from agents.compliance_risk_agent import ComplianceRiskAgent
from agents.lock_confirmation_agent import LockConfirmationAgent
from agents.audit_logging_agent import AuditLoggingAgent
from agents.exception_handler_agent import ExceptionHandlerAgent
from operations.service_bus_operations import ServiceBusOperations
from operations.service_bus_singleton import close_service_bus_connection
from config.azure_config import AzureConfig

class AIRateLockSystem:
    """
    Main orchestrator for the AI Rate Lock System.
    Manages all agents and coordinates their autonomous operation.
    """
    
    def __init__(self):
        self.system_name = "AI Rate Lock System"
        self.agents = {}
        self.service_bus = None
        self.running = False
        self.startup_time = datetime.now()
        
        # Initialize Azure config
        self.azure_config = AzureConfig()
        
        # Agent configurations - using consolidated Service Bus architecture
        self.agent_configs = {
            'email_intake': {
                'class': EmailIntakeAgent,
                'queues': [self.azure_config.get_servicebus_queue_inbound_email()],
                'topics': [self.azure_config.get_servicebus_topic_workflow_events()],
                'subscription': 'email-intake-subscription'
            },
            'loan_context': {
                'class': LoanApplicationContextAgent,
                'queues': [],
                'topics': [self.azure_config.get_servicebus_topic_workflow_events()],
                'subscription': 'loan-context-subscription'
            },
            'rate_quote': {
                'class': RateQuoteAgent,
                'queues': [],
                'topics': [self.azure_config.get_servicebus_topic_workflow_events()],
                'subscription': 'rate-quote-subscription'
            },
            'compliance_risk': {
                'class': ComplianceRiskAgent,
                'queues': [],
                'topics': [self.azure_config.get_servicebus_topic_workflow_events()],
                'subscription': 'compliance-subscription'
            },
            'lock_confirmation': {
                'class': LockConfirmationAgent,
                'queues': [self.azure_config.get_servicebus_queue_outbound_confirmations()],
                'topics': [self.azure_config.get_servicebus_topic_workflow_events()],
                'subscription': 'lock-confirmation-subscription'
            },
            'audit_logging': {
                'class': AuditLoggingAgent,
                'queues': [],
                'topics': [self.azure_config.get_servicebus_topic_workflow_events()],
                'subscription': 'audit-subscription'
            },
            'exception_handler': {
                'class': ExceptionHandlerAgent,
                'queues': [self.azure_config.get_servicebus_queue_high_priority_exceptions()],
                'topics': [self.azure_config.get_servicebus_topic_workflow_events()],
                'subscription': 'exception-subscription'
            }
        }

    async def initialize_system(self):
        """Initialize all system components."""
        try:
            logger.info(f"🚀 Initializing {self.system_name}...")
            logger.info(f"⏰ Startup time: {self.startup_time}")
            
            # Initialize Service Bus operations
            self.service_bus = ServiceBusOperations()
            logger.info("✅ Service Bus operations initialized")
            
            # Initialize all agents
            for agent_name, config in self.agent_configs.items():
                logger.info(f"🤖 Initializing {agent_name} agent...")
                agent_instance = config['class']()
                self.agents[agent_name] = {
                    'instance': agent_instance,
                    'config': config,
                    'status': 'INITIALIZING'
                }
                logger.info(f"✅ {agent_name} agent initialized")
            
            logger.info(f"🎉 {self.system_name} initialization complete!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize system: {str(e)}")
            return False

    async def start_agent_listeners(self):
        """Start all agent message listeners."""
        listener_tasks = []
        
        for agent_name, agent_data in self.agents.items():
            try:
                logger.info(f"📡 Starting event-driven listener for {agent_name}...")
                
                # Create stop event for graceful shutdown
                stop_event = asyncio.Event()
                agent_data['stop_event'] = stop_event
                
                # Create listener task for each agent
                task = asyncio.create_task(
                    self._agent_message_listener(agent_name, agent_data),
                    name=f"{agent_name}_listener"
                )
                listener_tasks.append(task)
                
                agent_data['status'] = 'LISTENING'
                agent_data['listener_task'] = task
                logger.info(f"✅ {agent_name} event-driven listener started")
                
            except Exception as e:
                logger.error(f"❌ Failed to start listener for {agent_name}: {str(e)}")
                agent_data['status'] = 'ERROR'
        
        return listener_tasks

    async def _agent_message_listener(self, agent_name: str, agent_data: Dict[str, Any]):
        """
        Generic event-driven message listener - NO agent-specific logic.
        Simply passes messages to agent's handle_message() method.
        """
        agent_instance = agent_data['instance']
        config = agent_data['config']
        stop_event = agent_data['stop_event']
        
        topics = config.get('topics', [])
        queues = config.get('queues', [])
        subscription = config.get('subscription', f"{agent_name}-subscription")
        
        logger.info(f"🎧 {agent_name} listener starting - topics: {topics}, queues: {queues}")
        
        # Generic message handler - same for ALL agents
        async def handle_message(message: Dict[str, Any]):
            """Generic message handler - delegates to agent."""
            await agent_instance.handle_message(message)
        
        # Start listeners for all topics and queues
        listener_tasks = []
        
        try:
            # Create listener for each topic subscription
            for topic in topics:
                listener_task = asyncio.create_task(
                    self.service_bus.listen_to_subscription(
                        topic_name=topic,
                        subscription_name=subscription,
                        message_handler=handle_message,
                        stop_event=stop_event
                    ),
                    name=f"{agent_name}_{topic}_listener"
                )
                listener_tasks.append(listener_task)
                logger.info(f"🎧 {agent_name} listening to topic {topic}/{subscription}")
            
            # Create listener for each queue
            for queue in queues:
                listener_task = asyncio.create_task(
                    self.service_bus.listen_to_queue(
                        queue_name=queue,
                        message_handler=handle_message,
                        stop_event=stop_event
                    ),
                    name=f"{agent_name}_{queue}_listener"
                )
                listener_tasks.append(listener_task)
                logger.info(f"🎧 {agent_name} listening to queue {queue}")
            
            # Wait for all listeners to complete (when stop_event is set)
            await asyncio.gather(*listener_tasks, return_exceptions=True)
            
            logger.info(f"🔚 {agent_name} all listeners stopped")
            
        except asyncio.CancelledError:
            logger.info(f"� {agent_name} listener cancelled")
            stop_event.set()
            # Wait for graceful shutdown of all listeners
            if listener_tasks:
                await asyncio.wait(listener_tasks, timeout=10)
        except Exception as e:
            logger.error(f"❌ {agent_name} listener error: {e}")
            agent_data['status'] = 'ERROR'
            raise
        finally:
            # Ensure stop event is set
            stop_event.set()

    # DEPRECATED: Old polling methods - kept for backward compatibility only
    # Use listen_to_subscription() and listen_to_queue() instead
    
    async def _check_for_messages(self, topic: str, subscription: str) -> List[Dict[str, Any]]:
        """
        DEPRECATED: Polling-based message check. Use event-driven listeners instead.
        Check for messages from Service Bus topic/subscription.
        """
        logger.warning("⚠️ DEPRECATED: _check_for_messages() uses polling. Use listen_to_subscription() instead.")
        try:
            messages = await self.service_bus.receive_messages(
                topic_name=topic,
                subscription_name=subscription,
                max_wait_time=1
            )
            return messages or []
            
        except Exception as e:
            logger.debug(f"No messages available from {topic}/{subscription}: {str(e)}")
            return []

    async def _check_for_queue_messages(self, queue: str) -> List[Dict[str, Any]]:
        """
        DEPRECATED: Polling-based message check. Use event-driven listeners instead.
        Check for messages from Service Bus queue.
        """
        logger.warning("⚠️ DEPRECATED: _check_for_queue_messages() uses polling. Use listen_to_queue() instead.")
        try:
            messages = await self.service_bus.receive_queue_messages(
                queue_name=queue,
                max_wait_time=1
            )
            return messages or []
            
        except Exception as e:
            logger.debug(f"No messages available from queue {queue}: {str(e)}")
            return []

    async def start_health_monitor(self):
        """Monitor system health and agent status."""
        logger.info("💓 Starting system health monitor...")
        
        while self.running:
            try:
                # Log system status every 5 minutes
                await asyncio.sleep(300)
                await self._log_system_status()
                
            except Exception as e:
                logger.error(f"❌ Error in health monitor: {str(e)}")
                await asyncio.sleep(60)

    async def _log_system_status(self):
        """Log current system status."""
        uptime = datetime.now() - self.startup_time
        
        logger.info("📊 === SYSTEM STATUS REPORT ===")
        logger.info(f"⏱️  System Uptime: {uptime}")
        logger.info(f"🔧 Active Agents: {len([a for a in self.agents.values() if a['status'] == 'LISTENING'])}")
        
        for agent_name, agent_data in self.agents.items():
            status = agent_data['status']
            logger.info(f"   🤖 {agent_name}: {status}")

    async def run_system(self):
        """Main system execution loop."""
        try:
            # Initialize system
            if not await self.initialize_system():
                logger.error("❌ System initialization failed. Exiting.")
                return
            
            self.running = True
            logger.info(f"🚀 {self.system_name} starting autonomous operation...")
            
            # Start all agent listeners
            listener_tasks = await self.start_agent_listeners()
            
            # Start health monitor
            health_task = asyncio.create_task(self.start_health_monitor(), name="health_monitor")
            
            # Combine all tasks
            all_tasks = listener_tasks + [health_task]
            
            logger.info(f"✅ All systems operational! Running {len(listener_tasks)} agent listeners.")
            logger.info("🔄 System is now running autonomously. Press Ctrl+C to shutdown.")
            
            # Wait for all tasks to complete (or be cancelled)
            await asyncio.gather(*all_tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            logger.info("⚠️  Shutdown signal received...")
        except Exception as e:
            logger.error(f"❌ Critical system error: {str(e)}")
        finally:
            await self.shutdown_system()

    async def shutdown_system(self):
        """Graceful system shutdown."""
        logger.info("🔄 Initiating graceful shutdown...")
        self.running = False
        
        # Signal all agent listeners to stop gracefully
        logger.info("🛑 Stopping all agent listeners...")
        for agent_name, agent_data in self.agents.items():
            if 'stop_event' in agent_data:
                agent_data['stop_event'].set()
                logger.debug(f"   Sent stop signal to {agent_name}")
        
        # Wait for listener tasks to complete gracefully
        listener_tasks = [agent_data.get('listener_task') for agent_data in self.agents.values() if 'listener_task' in agent_data]
        if listener_tasks:
            logger.info(f"⏳ Waiting for {len(listener_tasks)} listeners to stop...")
            await asyncio.wait(listener_tasks, timeout=30)
        
        # Cancel any remaining tasks
        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        if tasks:
            logger.info(f"🔄 Cancelling {len(tasks)} remaining tasks...")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Close all agent resources
        for agent_name, agent_data in self.agents.items():
            try:
                logger.info(f"🧹 Cleaning up {agent_name} agent...")
                await agent_data['instance'].close()
                logger.info(f"✅ {agent_name} cleaned up")
            except Exception as e:
                logger.error(f"❌ Error cleaning up {agent_name}: {str(e)}")
        
        # Give async tasks time to cleanup
        await asyncio.sleep(0.5)
        
        # Clean up any remaining Service Bus credentials to prevent session warnings
        if self.service_bus:
            try:
                await self.service_bus.cleanup_all_credentials()
            except Exception as e:
                logger.debug(f"Error during credential cleanup: {e}")
            logger.info("✅ Service Bus operations closed")
        
        shutdown_time = datetime.now()
        total_runtime = shutdown_time - self.startup_time
        
        logger.info(f"🏁 {self.system_name} shutdown complete")
        logger.info(f"⏱️  Total runtime: {total_runtime}")
        logger.info("👋 Goodbye!")

def setup_signal_handlers(system: AIRateLockSystem):
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        logger.info(f"📡 Received signal {signum}. Initiating shutdown...")
        # This will be handled by the KeyboardInterrupt in run_system
        raise KeyboardInterrupt()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """Main entry point for the AI Rate Lock System."""
    print("🏢 AI Rate Lock System - Production Mode")
    print("=" * 50)
    print("🤖 Autonomous mortgage rate lock processing")
    print("📨 Monitoring inbound email queue")
    print("💰 Generating intelligent rate quotes")
    print("🔄 Continuous operation mode")
    print("=" * 50)
    
    # Create and configure system
    system = AIRateLockSystem()
    setup_signal_handlers(system)
    
    # Run the system
    await system.run_system()

if __name__ == "__main__":
    try:
        # Environment variables are loaded from .env file by load_dotenv() above
        # Using real Azure OpenAI endpoint from environment configuration
        
        # Run the async main function
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n👋 Shutdown complete. Goodbye!")
    except Exception as e:
        print(f"❌ Critical error: {str(e)}")
        sys.exit(1)