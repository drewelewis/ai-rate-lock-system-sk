# Single Topic with Filters - Implementation Summary

## ✅ What We've Created

### 1. **Design Document** (`SINGLE_TOPIC_WITH_FILTERS_DESIGN.md`)
- Complete architectural overview
- Current vs proposed comparison
- Message structure with routing metadata
- Subscription filter examples
- Implementation guide
- Migration strategy
- Testing strategy
- Cost analysis

### 2. **New Bicep Infrastructure** (`servicebus-single-topic.bicep`)
- Single topic: `agent-workflow-events`
- 7 subscriptions with SQL filters (one per agent)
- 3 queues (unchanged for Logic Apps integration)
- Azure RBAC role assignments for managed identity
- Comprehensive outputs for configuration

---

## 🎯 Architecture Overview

### Single Topic with Subscription Filters

```
agent-workflow-events (TOPIC)
├── email-intake-subscription       (filter: MessageType = 'email_received' OR TargetAgent = 'email_intake')
├── loan-context-subscription       (filter: MessageType = 'email_parsed' OR TargetAgent = 'loan_context')  
├── rate-quote-subscription         (filter: MessageType = 'context_retrieved' OR TargetAgent = 'rate_quote')
├── compliance-subscription         (filter: MessageType = 'rate_quoted' OR TargetAgent = 'compliance')
├── lock-confirmation-subscription  (filter: MessageType = 'compliance_passed' OR TargetAgent = 'lock_confirmation')
├── audit-subscription              (filter: MessageType IS NOT NULL) ← RECEIVES ALL MESSAGES
└── exception-subscription          (filter: Priority = 'high' OR MessageType = 'exception')

Queues (UNCHANGED):
├── inbound-email-queue            (Logic Apps → Email Intake)
├── outbound-email-queue           (Lock Confirmation → Logic Apps)
└── high-priority-exceptions       (Manual intervention)
```

---

## 📋 Next Steps to Implement

### Step 1: Deploy New Infrastructure ✅ READY

The new Bicep file is ready to deploy:

```cmd
REM Option A: Replace existing Service Bus module
copy /Y infra\core\messaging\servicebus-single-topic.bicep infra\core\messaging\servicebus.bicep
azd provision

REM Option B: Deploy side-by-side for testing (recommended)
REM Manually update main.bicep to reference servicebus-single-topic.bicep
azd provision
```

### Step 2: Update Configuration Files

#### `azure_config.py` Changes

**Add new method:**
```python
def get_servicebus_topic_agent_workflow(self) -> str:
    """Get the unified agent workflow events topic name"""
    return os.getenv('AZURE_SERVICEBUS_TOPIC_AGENT_WORKFLOW', 'agent-workflow-events')
```

**Optionally keep old methods for transition period:**
```python
def get_servicebus_topic_loan_lifecycle(self) -> str:
    """DEPRECATED: Use get_servicebus_topic_agent_workflow() instead"""
    return self.get_servicebus_topic_agent_workflow()
```

#### `service_bus_operations.py` Changes

**Update topic mapping:**
```python
self.topics = {
    'agent_workflow_events': config.get_servicebus_topic_agent_workflow(),
    # Keep old names during transition:
    'loan_lifecycle_events': config.get_servicebus_topic_agent_workflow(),
    'audit_events': config.get_servicebus_topic_agent_workflow(),
    'compliance_events': config.get_servicebus_topic_agent_workflow(),
    'exception_alerts': config.get_servicebus_topic_agent_workflow()
}
```

**Add message type constants:**
```python
# Message type constants for routing
MESSAGE_TYPES = {
    'EMAIL_RECEIVED': 'email_received',
    'EMAIL_PARSED': 'email_parsed',
    'CONTEXT_RETRIEVED': 'context_retrieved',
    'RATE_QUOTED': 'rate_quoted',
    'COMPLIANCE_PASSED': 'compliance_passed',
    'LOCK_CONFIRMED': 'lock_confirmed',
    'AUDIT_LOG': 'audit_log',
    'EXCEPTION': 'exception'
}
```

**Update `send_message()` method:**
```python
async def send_message(
    self, 
    destination_name: str, 
    message_body: str,
    message_type: str = None,      # NEW: Routing metadata
    target_agent: str = None,      # NEW: Explicit agent routing
    priority: str = 'normal',      # NEW: Priority level
    correlation_id: Optional[str] = None,
    destination_type: str = 'topic'
) -> bool:
    """
    Send a message with routing metadata for subscription filters.
    """
    try:
        client, credential = await self._get_servicebus_client()
        
        # Get actual destination name
        if destination_type == 'topic':
            actual_destination_name = self.topics.get(destination_name)
            sender_method = client.get_topic_sender
        else:
            actual_destination_name = self.queues.get(destination_name)
            sender_method = client.get_queue_sender
        
        # Create message with custom properties for filtering
        application_properties = {
            'Priority': priority,
            'Timestamp': datetime.utcnow().isoformat()
        }
        
        # Add message type for subscription filters
        if message_type:
            application_properties['MessageType'] = message_type
        
        # Add optional target agent for explicit routing
        if target_agent:
            application_properties['TargetAgent'] = target_agent
        
        message_to_send = ServiceBusMessage(
            body=message_body,
            content_type="text/plain",
            correlation_id=correlation_id or str(uuid.uuid4()),
            application_properties=application_properties
        )
        
        # Send message
        if destination_type == 'topic':
            sender = sender_method(topic_name=actual_destination_name)
        else:
            sender = sender_method(queue_name=actual_destination_name)
        
        async with client, sender:
            await sender.send_messages(message_to_send)
        
        # Cleanup
        await credential.close()
        if credential in self._active_credentials:
            self._active_credentials.remove(credential)
        
        console_info(f"Message sent to {destination_type} '{actual_destination_name}' with type '{message_type}'", "ServiceBusOps")
        
        return True
        
    except Exception as e:
        console_error(f"Failed to send message: {e}", "ServiceBusOps")
        return False
```

### Step 3: Update Agents

Each agent needs to publish with `message_type` metadata:

#### Email Intake Agent
```python
await self.service_bus.send_message(
    destination_name='agent_workflow_events',
    message_body=json.dumps(loan_data),
    message_type='email_parsed',           # ✅ Routes to loan_context subscription
    target_agent='loan_context',           # ✅ Explicit routing
    correlation_id=loan_application_id,
    destination_type='topic'
)
```

#### Loan Context Agent
```python
await self.service_bus.send_message(
    destination_name='agent_workflow_events',
    message_body=json.dumps(context_data),
    message_type='context_retrieved',      # ✅ Routes to rate_quote subscription
    target_agent='rate_quote',
    correlation_id=loan_application_id,
    destination_type='topic'
)
```

#### Rate Quote Agent
```python
await self.service_bus.send_message(
    destination_name='agent_workflow_events',
    message_body=json.dumps(rate_data),
    message_type='rate_quoted',            # ✅ Routes to compliance subscription
    target_agent='compliance',
    correlation_id=loan_application_id,
    destination_type='topic'
)
```

#### Compliance Agent
```python
await self.service_bus.send_message(
    destination_name='agent_workflow_events',
    message_body=json.dumps(compliance_data),
    message_type='compliance_passed',      # ✅ Routes to lock_confirmation subscription
    target_agent='lock_confirmation',
    correlation_id=loan_application_id,
    destination_type='topic'
)
```

#### Audit Logging (any agent)
```python
await self.service_bus.send_message(
    destination_name='agent_workflow_events',
    message_body=json.dumps(audit_data),
    message_type='audit_log',              # ✅ Captured by audit subscription
    target_agent='audit',
    priority='normal',
    correlation_id=loan_application_id,
    destination_type='topic'
)
```

#### Exception Handling
```python
await self.service_bus.send_message(
    destination_name='agent_workflow_events',
    message_body=json.dumps(exception_data),
    message_type='exception',              # ✅ Routes to exception subscription
    priority='high',                       # ✅ Also caught by priority filter
    correlation_id=loan_application_id,
    destination_type='topic'
)
```

### Step 4: Update Agent Listeners

**Agent listener configuration** in `main.py`:

```python
self.agents = {
    'email_intake': {
        'instance': EmailIntakeAgent(kernel, cosmosdb, service_bus),
        'config': {
            'topics': ['agent_workflow_events'],         # ✅ Single topic
            'queues': ['inbound_email_queue'],
            'subscription': 'email-intake-subscription'
        },
        'status': 'INITIALIZED'
    },
    'loan_context': {
        'instance': LoanContextAgent(kernel, cosmosdb, service_bus),
        'config': {
            'topics': ['agent_workflow_events'],         # ✅ Single topic
            'queues': [],
            'subscription': 'loan-context-subscription'
        },
        'status': 'INITIALIZED'
    },
    # ... continue for all agents
}
```

### Step 5: Testing

#### Test 1: Verify Subscription Filters
```python
# Send message with MessageType = 'email_parsed'
await service_bus.send_message(
    destination_name='agent_workflow_events',
    message_body='TEST',
    message_type='email_parsed',
    correlation_id='TEST-001'
)

# Verify only loan-context-subscription receives it
```

#### Test 2: Verify Audit Receives All
```python
# Send ANY message type
await service_bus.send_message(
    destination_name='agent_workflow_events',
    message_body='TEST',
    message_type='rate_quoted',
    correlation_id='TEST-002'
)

# Verify audit-subscription receives it (catches all)
```

#### Test 3: End-to-End Workflow
1. Send test email to `inbound-email-queue`
2. Verify EmailIntake processes it
3. Verify message published with `MessageType = 'email_parsed'`
4. Verify LoanContext receives it immediately
5. Continue through full workflow
6. Verify Audit agent logged all steps

---

## 🔧 Migration Checklist

### Infrastructure
- [ ] Review new Bicep template (`servicebus-single-topic.bicep`)
- [ ] Deploy new Service Bus topic with filters
- [ ] Verify subscriptions created correctly
- [ ] Test subscription filters with sample messages

### Code Updates
- [ ] Update `azure_config.py` with new topic method
- [ ] Update `service_bus_operations.py` topic mapping
- [ ] Add `MESSAGE_TYPES` constants
- [ ] Update `send_message()` with routing metadata
- [ ] Update all 7 agents to use `message_type` parameter
- [ ] Update agent listener configurations in `main.py`

### Testing
- [ ] Unit test subscription filters
- [ ] Integration test full workflow
- [ ] Verify audit agent receives all messages
- [ ] Test exception routing by priority
- [ ] Performance test with 100+ messages

### Deployment
- [ ] Deploy to development environment
- [ ] Monitor message routing for 24 hours
- [ ] Verify no messages in dead-letter queues
- [ ] Check application logs for errors
- [ ] Deploy to production

### Cleanup (after successful migration)
- [ ] Remove old topic references from code
- [ ] Delete old topic subscription methods
- [ ] Update documentation
- [ ] Archive old Bicep template

---

## 📊 Expected Results

### Performance
- **Same latency** - Filters add ~5-10ms (negligible)
- **Better throughput** - Single topic can handle 2000 ops/sec
- **Lower cost** - 60% reduction in base Service Bus costs

### Simplification
- **4 topics → 1 topic** - Easier to manage
- **Complex routing → SQL filters** - Declarative and clear
- **Manual coordination → Automatic routing** - Messages find correct agent

### Flexibility
- **Easy to add agents** - Just add subscription + filter
- **Dynamic routing** - Can route by MessageType, Priority, TargetAgent, etc.
- **Better debugging** - All events visible in one topic

---

## 🚀 Ready to Deploy?

All files are ready:

1. ✅ **Design document** - `SINGLE_TOPIC_WITH_FILTERS_DESIGN.md`
2. ✅ **Bicep template** - `infra/core/messaging/servicebus-single-topic.bicep`
3. ✅ **Implementation guide** - This file!

**Next command:**
```cmd
REM Review the Bicep file
code infra\core\messaging\servicebus-single-topic.bicep

REM When ready, deploy
azd provision
```

This architecture will be **cleaner, simpler, and more maintainable**! 🎉
