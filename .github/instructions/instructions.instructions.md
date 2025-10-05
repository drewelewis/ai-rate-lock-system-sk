---
applyTo: '**'
---

# AI Rate Lock System - GitHub Copilot Instructions

## ü§ñ CRITICAL PROJECT CONTEXT - READ THIS FIRST
This is a **REAL AUTONOMOUS MULTI-AGENT AI SYSTEM** using Azure OpenAI GPT-4 for intelligent processing. This is NOT a simulation, demo, or placeholder system. Every agent uses actual LLM capabilities for decision making, natural language processing, and intelligent automation.

**NEVER** implement regex parsing, hardcoded logic, or placeholder functions where LLM processing should be used. Always leverage the full power of Azure OpenAI through Semantic Kernel.

## üö® CRITICAL ARCHITECTURAL PRINCIPLES

### **Principle 1: Semantic Kernel Plugins are for AUTONOMOUS LLM Invocation**
‚ùå **NEVER DO THIS:**
```python
# Explicit plugin calls - WRONG!
await self.cosmos_plugin.create_rate_lock(...)
await self.servicebus_plugin.send_workflow_event(...)
```

‚úÖ **ALWAYS DO THIS:**
```python
# Plugins registered with kernel for LLM autonomous invocation
self.kernel.add_plugin(self.cosmos_plugin, plugin_name="CosmosDB")
self.kernel.add_plugin(self.servicebus_plugin, plugin_name="ServiceBus")

# LLM decides which functions to call via FunctionChoiceBehavior.Auto()
execution_settings = OpenAIChatPromptExecutionSettings(
    function_choice_behavior=FunctionChoiceBehavior.Auto()
)
```

**WHY:** Semantic Kernel plugins are designed for autonomous invocation by LLMs, not explicit calls. Agents should define WHAT to do (via prompts), and the LLM decides HOW (by calling available plugin functions).

### **Principle 2: Agents are Thin LLM Wrappers**
- Agents should be **50-100 lines** (not 500-700 lines)
- NO explicit plugin calls in agent code
- NO business logic in agents
- NO custom parsing, validation, or error handling
- ONLY: System prompt definition + message building

**Agent Structure:**
```python
class MyAgent(BaseAgent):
    def _get_system_prompt(self) -> str:
        return """You are an AI agent that [describes role].
        
        AVAILABLE TOOLS:
        - plugin_function_1(...) - description
        - plugin_function_2(...) - description
        
        YOUR TASK: [what to accomplish]
        
        Use the tools autonomously to complete your task!
        """
    
    # Optional: Override _build_user_message() if needed
    # NO _process_llm_response() - LLM handles everything!
```

### **Principle 3: Main.py is Just an Entry Point**
- main.py should ONLY start agents and route messages
- NO agent-specific logic
- NO message transformation
- NO special-case handling
- Just generic orchestration

### **Principle 4: All Work Happens in Plugins**
- CosmosDB Plugin: All database operations
- Service Bus Plugin: All messaging
- Email Plugin: All notifications
- LOS Plugin: All loan system integrations

Plugins contain business logic and are invoked autonomously by LLMs.

## Core System Architecture
- **7 Autonomous AI Agents** - Each uses Azure OpenAI for intelligent processing
- **Semantic Kernel Framework** - Orchestrates LLM interactions with automatic function calling
- **Azure Service Bus** - Reliable inter-agent messaging and workflow coordination
- **Azure Cosmos DB** - Persistent state management for loan lock records
- **Managed Identity** - Secure authentication across all Azure services

## AI/LLM Usage Guidelines - CRITICAL
- **Email Intake Agent**: Uses LLM to parse natural language emails and autonomously invoke plugins to create records
- **Loan Context Agent**: Uses LLM to validate loan eligibility and autonomously retrieve data
- **Rate Quote Agent**: Uses LLM to analyze market conditions and autonomously generate quotes
- **Compliance Agent**: Uses LLM to assess regulatory compliance and autonomously flag issues
- **Lock Confirmation Agent**: Uses LLM to make final lock decisions and autonomously send confirmations
- **Audit Agent**: Uses LLM to analyze patterns and autonomously log audit trails
- **Exception Handler**: Uses LLM to intelligently categorize and autonomously route exceptions

**REMEMBER:** LLMs autonomously decide which plugin functions to call based on system prompts. Do NOT explicitly call plugins in agent code!

## Required Environment Variables
```properties
AZURE_OPENAI_ENDPOINT="https://your-openai.openai.azure.com/"
AZURE_OPENAI_API_KEY="your-api-key-here"
AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o"
```

## Terminal and Shell Preferences - CRITICAL
- **ALWAYS use Windows Command Prompt (cmd.exe) for ALL terminal operations**
- **NEVER use PowerShell** - if PowerShell spawns, this is an error
- Generate terminal commands using cmd syntax only, not PowerShell syntax
- Use cmd.exe commands: `dir`, `cd`, `type`, `copy`, etc.
- Avoid PowerShell-specific commands like `Get-*`, `Set-*`, etc.
- VS Code is configured to use cmd as the default terminal via `.vscode/settings.json`
- When running Python commands, always use the full path: `C:\gitrepos\ai-rate-lock-system\.venv\Scripts\python.exe`

## Azure Infrastructure Guidelines
- Use Infrastructure as Code (Bicep) for all Azure resource deployments
- For Service Bus managed identity connections, use ARM templates when Bicep limitations exist
- Follow the declarative approach - avoid post-deployment scripts when possible
- All Azure resources should use managed identities for authentication
- Follow Option 2 implementation pattern (full declarative) as documented

## Python Development Standards
- Use virtual environment (.venv) for Python package management
- Follow async/await patterns for I/O operations
- Use proper logging throughout the application
- Implement proper error handling and exception management
- Follow PEP 8 style guidelines

## Multi-Agent System Architecture
- Each agent should be autonomous and stateless where possible
- Use Semantic Kernel with **automatic function calling** (FunctionChoiceBehavior.Auto)
- Agents define system prompts that describe available plugin functions
- LLMs autonomously decide which plugin functions to invoke
- NO explicit plugin calls in agent code - LLM handles all function invocation
- Follow the established agent communication patterns via Service Bus
- Ensure proper audit logging for all agent actions

## Agent Implementation Guidelines
1. **Inherit from BaseAgent** - Provides standard message handling and LLM invocation
2. **Override _get_system_prompt()** - Define agent's role and available plugin functions (~60 lines)
3. **Optional: Override _build_user_message()** - Customize message format if needed (~10 lines)
4. **NO _process_llm_response()** - Not needed! LLM autonomously invokes plugins
5. **Total agent code: 50-100 lines** - Everything else handled by BaseAgent and plugins

## Plugin Development Guidelines
- Plugins contain ALL business logic and integrations
- Use `@kernel_function` decorator for LLM-callable functions
- Provide detailed descriptions in function decorators (LLM reads these!)
- Use `Annotated[type, "description"]` for all parameters
- Return JSON strings that LLM can parse
- Plugins should be stateless and reusable
- Never put business logic in agents - always in plugins

## Data Storage Patterns
- Use Cosmos DB for primary rate lock record storage
- Use Service Bus for inter-agent communication
- Implement proper data models for loan lock entities
- Follow the established JSON schema for rate lock records

## Security and Compliance
- All API connections must use managed identity authentication
- Implement proper audit trails for compliance requirements
- Ensure sensitive data is properly handled and encrypted
- Follow financial services security best practices

## Testing and Validation
- Write unit tests for all plugin functionality (not agents - agents just define prompts)
- Test Service Bus message processing end-to-end
- Validate managed identity authentication works correctly
- Test the complete workflow from email intake to lock confirmation
- Test LLM autonomous function calling with different scenarios
- Verify plugins return properly formatted JSON for LLM parsing

## Code Quality Standards
- **Agents: 50-100 lines each** - Just system prompt and optional message formatting
- **Plugins: Where all logic lives** - Can be as complex as needed
- **Main.py: Generic orchestration only** - No agent-specific code
- Keep business logic in plugins, not agents or main.py
- Use proper type hints and docstrings
- Follow async/await patterns for I/O operations
- Use proper logging throughout the application
- Implement proper error handling in plugins (agents don't handle errors)

## Common Pitfalls to Avoid
1. ‚ùå **Explicitly calling plugins in agent code** - Let LLM invoke them autonomously
2. ‚ùå **Hardcoded parsing/validation logic in agents** - Use LLM reasoning or move to plugins
3. ‚ùå **Agent-specific logic in main.py** - Keep it generic
4. ‚ùå **Business logic in agents** - Always put in plugins
5. ‚ùå **Not using FunctionChoiceBehavior.Auto()** - Required for autonomous function calling
6. ‚ùå **Agents over 100 lines** - They should be thin wrappers
7. ‚ùå **Forgetting to register plugins with kernel** - LLM can't see unregistered plugins

## Documentation Standards
- Keep README.md updated with current setup instructions
- Document any architectural decisions and trade-offs
- Maintain clear API documentation for external integrations
- Update deployment documentation when infrastructure changes 
 # #   K e y   A r c h i t e c t u r e   D o c u m e n t s   ( M U S T   R E A D   B E F O R E   A N Y   A G E N T   W O R K )  
  
 1 .   * * A U T O N O M O U S _ A G E N T _ A R C H I T E C T U R E . m d * *   -   P r o p e r   S e m a n t i c   K e r n e l   p l u g i n   u s a g e  
       -   W h y   e x p l i c i t   p l u g i n   c a l l s   a r e   W R O N G  
       -   H o w   a u t o n o m o u s   f u n c t i o n   c a l l i n g   w o r k s      
       -   L L M   a u t o n o m o u s l y   i n v o k e s   p l u g i n s   v i a   F u n c t i o n C h o i c e B e h a v i o r . A u t o ( )  
       -   F l o w   d i a g r a m s   s h o w i n g   p r o p e r   a r c h i t e c t u r e  
  
 2 .   * * A G E N T _ A R C H I T E C T U R E _ R E F A C T O R I N G . m d * *   -   M i g r a t i o n   g u i d a n c e  
       -   7 6 %   c o d e   r e d u c t i o n   g o a l   ( 4 , 5 7 5   l i n e s   ‚      1 , 0 9 0   l i n e s )  
       -   B e f o r e / a f t e r   c o d e   e x a m p l e s  
       -   P h a s e - b y - p h a s e   m i g r a t i o n   p l a n  
  
 * * ‚ a† Ô ∏ è   C R I T I C A L :   A L W A Y S   c o n s u l t   t h e s e   d o c u m e n t s   b e f o r e   i m p l e m e n t i n g   o r   m o d i f y i n g   a g e n t s ! * *  
 * * I f   y o u   f o r g e t   t h e s e   p r i n c i p l e s   d u r i n g   c o n v e r s a t i o n ,   r e - r e a d   t h e s e   d o c u m e n t s ! * *  
 