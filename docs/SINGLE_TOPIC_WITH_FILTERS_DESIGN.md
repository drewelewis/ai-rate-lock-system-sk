# Single Topic with Subscription Filters - Architecture Design

## 🎯 Goal
Consolidate **4 topics** → **1 topic** with **subscription filters** to route messages to specific agents.

## Current Architecture (4 Topics) ❌

```
Topics (4):
├── loan-lifecycle-events (7 subscriptions - one per agent)
├── audit-events (1 subscription - audit agent)
├── compliance-events (1 subscription - compliance agent)
└── exception-alerts (1 subscription - exception handler)

Queues (3):
├── inbound-email-queue (Logic Apps → Email Intake)
├── outbound-email-queue (Lock Confirmation → Email sender)
└── high-priority-exceptions (Manual intervention)
```

**Issues:**
- 🔄 **Message duplication** - Same agents subscribed to multiple topics
- 🧩 **Complex routing** - Hard to trace message flow
- 📊 **Management overhead** - 4 topics + 10+ subscriptions to maintain
- 💰 **Cost inefficiency** - More resources than needed

---

## Proposed Architecture (1 Topic) ✅

```
Topic (1):
└── agent-workflow-events
    ├── email-intake-sub (filter: MessageType = 'email_received' OR TargetAgent = 'email_intake')
    ├── loan-context-sub (filter: MessageType = 'email_parsed' OR TargetAgent = 'loan_context')
    ├── rate-quote-sub (filter: MessageType = 'context_retrieved' OR TargetAgent = 'rate_quote')
    ├── compliance-sub (filter: MessageType = 'rate_quoted' OR TargetAgent = 'compliance')
    ├── lock-confirmation-sub (filter: MessageType = 'compliance_passed' OR TargetAgent = 'lock_confirmation')
    ├── audit-sub (filter: MessageType = 'audit_log' OR TargetAgent = 'audit')
    └── exception-sub (filter: Priority = 'high' OR MessageType = 'exception')

Queues (3): UNCHANGED
├── inbound-email-queue (Logic Apps → Email Intake)
├── outbound-email-queue (Lock Confirmation → Email sender)
└── high-priority-exceptions (Manual intervention)
```

**Benefits:**
- ✅ **Single source of truth** - All workflow events in one topic
- ✅ **Flexible routing** - Filters can route by MessageType, TargetAgent, Priority, etc.
- ✅ **Easy debugging** - All events visible in one topic
- ✅ **Cost effective** - Fewer resources to manage
- ✅ **Future-proof** - Easy to add new agents (just add subscription + filter)

---

## Message Structure with Metadata

All messages will include routing metadata in **custom properties**:

```json
{
  "body": "actual message content...",
  "application_properties": {
    "MessageType": "email_parsed",           // Workflow stage
    "TargetAgent": "loan_context",           // Specific agent routing
    "Priority": "normal",                     // normal | high | critical
    "LoanApplicationId": "LOAN-2025-12345",  // Correlation ID
    "Source": "email_intake",                 // Originating agent
    "Timestamp": "2025-10-03T10:30:00Z"
  }
}
```

---

## Subscription Filters

### SQL Filter Examples

Each subscription uses a **SQL filter** to receive only relevant messages:

```sql
-- Email Intake Agent
MessageType = 'email_received' OR TargetAgent = 'email_intake'

-- Loan Context Agent
MessageType = 'email_parsed' OR TargetAgent = 'loan_context'

-- Rate Quote Agent
MessageType = 'context_retrieved' OR TargetAgent = 'rate_quote'

-- Compliance Agent
MessageType = 'rate_quoted' OR TargetAgent = 'compliance'

-- Lock Confirmation Agent
MessageType = 'compliance_passed' OR TargetAgent = 'lock_confirmation'

-- Audit Agent (receives ALL messages for logging)
MessageType LIKE '%' OR TargetAgent = 'audit'

-- Exception Handler
Priority = 'high' OR Priority = 'critical' OR MessageType = 'exception'
```

---

## Workflow Message Types

| Stage | MessageType | Source Agent | Target Agent(s) |
|-------|------------|--------------|----------------|
| 1. Email arrives | `email_received` | Logic App | email_intake |
| 2. Email parsed | `email_parsed` | email_intake | loan_context |
| 3. Context validated | `context_retrieved` | loan_context | rate_quote |
| 4. Rate calculated | `rate_quoted` | rate_quote | compliance |
| 5. Compliance checked | `compliance_passed` | compliance | lock_confirmation |
| 6. Lock confirmed | `lock_confirmed` | lock_confirmation | (outbound queue) |
| 7. Audit log | `audit_log` | any agent | audit |
| 8. Exception | `exception` | any agent | exception_handler |

---

## Implementation Changes

### 1. Bicep Infrastructure (`servicebus.bicep`)

**BEFORE:** 4 topics
```bicep
resource loanLifecycleTopic 'Microsoft.ServiceBus/namespaces/topics@2021-11-01' = { ... }
resource complianceTopic 'Microsoft.ServiceBus/namespaces/topics@2021-11-01' = { ... }
resource auditTopic 'Microsoft.ServiceBus/namespaces/topics@2021-11-01' = { ... }
resource exceptionAlertsTopic 'Microsoft.ServiceBus/namespaces/topics@2021-11-01' = { ... }
```

**AFTER:** 1 topic with filters
```bicep
resource agentWorkflowTopic 'Microsoft.ServiceBus/namespaces/topics@2021-11-01' = {
  name: 'agent-workflow-events'
  properties: {
    maxMessageSizeInKilobytes: 256
    defaultMessageTimeToLive: 'P1D'
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    requiresDuplicateDetection: true
    supportOrdering: true
  }
}

// Subscriptions with SQL filters
resource emailIntakeSub 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: agentWorkflowTopic
  name: 'email-intake-subscription'
  properties: { ... }
}

resource emailIntakeFilter 'Microsoft.ServiceBus/namespaces/topics/subscriptions/rules@2021-11-01' = {
  parent: emailIntakeSub
  name: 'EmailIntakeFilter'
  properties: {
    filterType: 'SqlFilter'
    sqlFilter: {
      sqlExpression: "MessageType = 'email_received' OR TargetAgent = 'email_intake'"
    }
  }
}

// Repeat for other agents...
```

### 2. Azure Config (`azure_config.py`)

**BEFORE:**
```python
def get_servicebus_topic_loan_lifecycle(self) -> str:
    return os.getenv('AZURE_SERVICEBUS_TOPIC_LOAN_LIFECYCLE', 'loan-lifecycle-events')

def get_servicebus_topic_audit_events(self) -> str:
    return os.getenv('AZURE_SERVICEBUS_TOPIC_AUDIT_EVENTS', 'audit-events')

def get_servicebus_topic_compliance_events(self) -> str:
    return os.getenv('AZURE_SERVICEBUS_TOPIC_COMPLIANCE_EVENTS', 'compliance-events')

def get_servicebus_topic_exception_alerts(self) -> str:
    return os.getenv('AZURE_SERVICEBUS_TOPIC_EXCEPTION_ALERTS', 'exception-alerts')
```

**AFTER:**
```python
def get_servicebus_topic_agent_workflow(self) -> str:
    """Get the unified agent workflow events topic name"""
    return os.getenv('AZURE_SERVICEBUS_TOPIC_AGENT_WORKFLOW', 'agent-workflow-events')
```

### 3. Service Bus Operations (`service_bus_operations.py`)

**BEFORE:**
```python
self.topics = {
    'loan_lifecycle_events': config.get_servicebus_topic_loan_lifecycle(),
    'audit_events': config.get_servicebus_topic_audit_events(),
    'compliance_events': config.get_servicebus_topic_compliance_events(),
    'exception_alerts': config.get_servicebus_topic_exception_alerts()
}
```

**AFTER:**
```python
self.topics = {
    'agent_workflow_events': config.get_servicebus_topic_agent_workflow()
}

# Message type constants for routing
self.MESSAGE_TYPES = {
    'email_received': 'email_received',
    'email_parsed': 'email_parsed',
    'context_retrieved': 'context_retrieved',
    'rate_quoted': 'rate_quoted',
    'compliance_passed': 'compliance_passed',
    'lock_confirmed': 'lock_confirmed',
    'audit_log': 'audit_log',
    'exception': 'exception'
}
```

**Enhanced `send_message()` method:**
```python
async def send_message(
    self, 
    destination_name: str, 
    message_body: str,
    message_type: str,           # NEW: Workflow stage
    target_agent: str = None,    # NEW: Optional specific routing
    priority: str = 'normal',    # NEW: Priority level
    correlation_id: str = None,
    destination_type: str = 'topic'
) -> bool:
    """
    Send a message with routing metadata for subscription filters.
    """
    try:
        # Create message with custom properties for filtering
        message_to_send = ServiceBusMessage(
            body=message_body,
            content_type="text/plain",
            correlation_id=correlation_id or str(uuid.uuid4()),
            application_properties={
                'MessageType': message_type,
                'Priority': priority,
                'Timestamp': datetime.utcnow().isoformat()
            }
        )
        
        # Add optional target agent for direct routing
        if target_agent:
            message_to_send.application_properties['TargetAgent'] = target_agent
        
        # Send message
        async with sender:
            await sender.send_messages(message_to_send)
        
        return True
    except Exception as e:
        console_error(f"Failed to send message: {e}")
        return False
```

### 4. Agent Updates

Each agent publishes to the **single topic** with appropriate `MessageType`:

**Email Intake Agent:**
```python
await self.service_bus.send_message(
    destination_name='agent_workflow_events',
    message_body=json.dumps(loan_data),
    message_type='email_parsed',          # ✅ Triggers loan_context subscription
    target_agent='loan_context',          # ✅ Explicit routing
    correlation_id=loan_application_id,
    destination_type='topic'
)
```

**Loan Context Agent:**
```python
await self.service_bus.send_message(
    destination_name='agent_workflow_events',
    message_body=json.dumps(context_data),
    message_type='context_retrieved',     # ✅ Triggers rate_quote subscription
    target_agent='rate_quote',
    correlation_id=loan_application_id,
    destination_type='topic'
)
```

**Audit messages (sent by any agent):**
```python
await self.service_bus.send_message(
    destination_name='agent_workflow_events',
    message_body=json.dumps(audit_data),
    message_type='audit_log',             # ✅ Triggers audit subscription
    target_agent='audit',
    priority='normal',
    correlation_id=loan_application_id,
    destination_type='topic'
)
```

---

## Migration Strategy

### Phase 1: Add New Topic Alongside Old Topics ✅
1. Deploy new `agent-workflow-events` topic via Bicep
2. Create subscriptions with SQL filters
3. Update code to publish to BOTH old and new topics
4. Verify messages route correctly with filters

### Phase 2: Switch Agents to New Topic ✅
1. Update agents one-by-one to consume from new subscriptions
2. Monitor for correct message routing
3. Verify no messages lost during transition

### Phase 3: Deprecate Old Topics ✅
1. Stop publishing to old topics
2. Monitor dead-letter queues for any stuck messages
3. Delete old topic subscriptions
4. Delete old topics

### Phase 4: Cleanup ✅
1. Remove old topic configuration from `azure_config.py`
2. Remove old topic names from `service_bus_operations.py`
3. Update documentation

---

## Testing Strategy

### Unit Tests
```python
async def test_message_routing_by_type():
    """Test that MessageType routes to correct subscription"""
    # Send message with MessageType = 'email_parsed'
    await service_bus.send_message(
        destination_name='agent_workflow_events',
        message_body='test',
        message_type='email_parsed',
        correlation_id='TEST-123'
    )
    
    # Verify loan_context subscription receives it
    messages = await service_bus.receive_messages(
        topic_name='agent_workflow_events',
        subscription_name='loan-context-subscription'
    )
    assert len(messages) == 1
    assert messages[0]['body'] == 'test'
```

### Integration Tests
1. Send email to `inbound-email-queue`
2. Verify EmailIntake processes it
3. Verify message published to `agent-workflow-events` with `MessageType = 'email_parsed'`
4. Verify LoanContext receives it via subscription filter
5. Continue through entire workflow

---

## Performance Considerations

### Subscription Filter Performance
- **SQL filters** add ~5-10ms latency (negligible)
- **Correlation filters** (simpler) add ~1-2ms latency
- For this use case, SQL filters are recommended for flexibility

### Topic Throughput
- Standard tier: **2000 operations/second per topic**
- Current: 4 topics × 500 ops/sec = 2000 ops/sec total
- Proposed: 1 topic × 2000 ops/sec = **same capacity, simpler architecture**

### Subscription Limits
- Standard tier: **2000 subscriptions per topic**
- Current need: **7 subscriptions** (one per agent)
- Plenty of room for growth!

---

## Cost Analysis

### Before (4 Topics)
```
4 topics × $0.05/month = $0.20/month (base)
10 subscriptions × $0.01/month = $0.10/month
Total: ~$0.30/month base cost
```

### After (1 Topic)
```
1 topic × $0.05/month = $0.05/month (base)
7 subscriptions × $0.01/month = $0.07/month
Total: ~$0.12/month base cost
```

**Savings: ~60% reduction in base costs** (actual savings will depend on message volume)

---

## Summary

### ✅ Benefits
1. **Simpler architecture** - 1 topic instead of 4
2. **Flexible routing** - Add new agents without infrastructure changes
3. **Better observability** - All workflow events in one place
4. **Lower cost** - Fewer resources to manage
5. **Easier debugging** - Single topic to monitor
6. **Future-proof** - Easy to extend with new message types

### 📋 Action Items
1. ✅ Review this design with team
2. ⬜ Update Bicep infrastructure
3. ⬜ Update `azure_config.py` 
4. ⬜ Update `service_bus_operations.py`
5. ⬜ Update all 7 agents to use new message format
6. ⬜ Deploy and test
7. ⬜ Deprecate old topics

Ready to implement? 🚀
