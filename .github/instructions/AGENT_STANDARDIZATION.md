# Agent Standardization Guide

## Overview
All agents in the AI Rate Lock System should follow the **SAME standardized pattern** using the `BaseAgent` class. This ensures consistency, reduces code duplication, and makes the system easier to maintain.

## Standard Agent Structure

### 1. Minimal Agent Implementation (50-100 lines)

```python
from agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_name="my_agent")
    
    def _get_system_prompt(self) -> str:
        return """You are an AI agent that [describes role].
        
        AVAILABLE TOOLS (plugins):
        - plugin_function_1(...) - description
        - plugin_function_2(...) - description
        
        YOUR TASK: [what to accomplish]
        
        Use the tools autonomously to complete your task!
        """
    
    # OPTIONAL: Filter message types
    def _get_expected_message_types(self) -> list:
        return ['message_type_1', 'message_type_2']
```

### 2. BaseAgent Provides

**Automatic functionality - NO need to implement:**
- ✅ `handle_message()` - Standardized message handling
- ✅ `_initialize_kernel()` - Azure OpenAI setup with managed identity
- ✅ `_call_llm()` - LLM invocation with automatic function calling
- ✅ `_send_exception_alert()` - Error reporting to Service Bus
- ✅ `cleanup()` - Resource cleanup
- ✅ Plugin registration (CosmosDB, ServiceBus)

**Required to override:**
- ❌ `_get_system_prompt()` - Define agent's role and available tools (~60 lines)

**Optional to override:**
- 🔵 `_get_expected_message_types()` - Filter incoming messages (~3 lines)
- 🔵 `_build_user_message()` - Customize LLM input format (~10 lines)

### 3. Message Structure

All agents receive the same standardized message dict:

```python
{
    'message_type': 'email_parsed',           # Workflow event type
    'loan_application_id': 'APP-123456',      # Loan tracking ID
    'body': {...},                            # Message payload (dict or string)
    'metadata': {                             # Service Bus metadata
        'correlation_id': '...',
        'message_id': '...',
        'content_type': '...',
        'properties': {...},
        'delivery_count': 1,
        'enqueued_time': '...'
    }
}
```

### 4. Message Type Routing (Infrastructure Filters)

**CRITICAL:** Agents must send/receive message types that match Service Bus SQL filters!

| Workflow Step | Message Type Sent | Next Agent Expects | Infrastructure Filter |
|---------------|-------------------|-------------------|----------------------|
| Email Intake → Loan Context | `email_parsed` | `email_parsed` | `MessageType = 'email_parsed'` |
| Loan Context → Rate Quote | `context_retrieved` | `context_retrieved` | `MessageType = 'context_retrieved'` |
| Rate Quote → Compliance | `rate_quoted` | `rate_quoted` | `MessageType = 'rate_quoted'` |
| Compliance → Lock Confirm | `compliance_passed` | `compliance_passed` | `MessageType = 'compliance_passed'` |

## Example: Email Intake Agent (BaseAgent Pattern)

```python
from agents.base_agent import BaseAgent
from typing import Dict, Any

class EmailIntakeAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_name="email_intake_agent")
    
    def _get_system_prompt(self) -> str:
        return """You are an Email Intake Agent for a mortgage rate lock system.

AVAILABLE TOOLS:
- CosmosDB.create_rate_lock(...) - Create new rate lock record
- ServiceBus.send_workflow_event(...) - Trigger next agent
- ServiceBus.send_audit_log(...) - Log processing event

YOUR TASK:
1. Extract loan data from the email (loan ID, borrower, amount, etc.)
2. Create a rate lock record in Cosmos DB
3. Send workflow event "email_parsed" to trigger loan_context_agent
4. Send audit log for compliance

IMPORTANT: Use message_type="email_parsed" for workflow events!
"""
    
    def _build_user_message(self, message_type: str, loan_id: str, body: Any, metadata: Dict) -> str:
        # Email intake receives raw email text in body
        return f"""Process this incoming rate lock request email:

{body}

Extract loan data and create rate lock record with status PENDING_CONTEXT.
"""
```

## DO NOT Do These Things

❌ **Don't implement custom message handlers** - Use BaseAgent.handle_message()
❌ **Don't explicitly call plugins** - Let LLM autonomously invoke them
❌ **Don't add business logic in agents** - Put it in plugins
❌ **Don't duplicate code** - Use BaseAgent helpers
❌ **Don't hardcode message types** - They must match infrastructure filters
❌ **Don't parse/validate in agents** - Plugins handle that

## DO Do These Things

✅ **Inherit from BaseAgent** - Consistent foundation
✅ **Override _get_system_prompt()** - Define agent's role (~60 lines)
✅ **Use _get_expected_message_types()** - Filter messages (~3 lines)
✅ **Keep agents 50-100 lines** - Everything else in plugins/BaseAgent
✅ **Match message types to infrastructure** - Check Bicep filters
✅ **Let LLM autonomously invoke plugins** - FunctionChoiceBehavior.Auto()

## Migration Checklist

When migrating an agent to BaseAgent pattern:

- [ ] Change inheritance: `class MyAgent(BaseAgent):`
- [ ] Call super().__init__() with agent_name
- [ ] Remove custom `_initialize_kernel()` - BaseAgent handles it
- [ ] Remove custom `handle_message()` - BaseAgent handles it
- [ ] Extract system prompt to `_get_system_prompt()`
- [ ] Add `_get_expected_message_types()` if message filtering needed
- [ ] Remove explicit plugin calls - describe in system prompt instead
- [ ] Remove custom error handling - BaseAgent handles it
- [ ] Verify message types match infrastructure filters
- [ ] Test with real messages

## File Size Targets

- **BaseAgent**: ~250 lines (shared infrastructure)
- **Each Agent**: 50-100 lines (just system prompt + optional overrides)
- **Total System**: ~1,000 lines (vs current ~4,500 lines) = 76% reduction ✅

## Benefits

1. **Consistency** - All agents work the same way
2. **Maintainability** - Change BaseAgent, all agents benefit
3. **Testability** - Standard pattern makes testing easier
4. **Simplicity** - New agents are just a system prompt
5. **Reliability** - Less code = fewer bugs
6. **Autonomous** - LLMs make intelligent decisions, not hardcoded logic
