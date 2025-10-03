---
applyTo: '**'
---

# AI Rate Lock System - GitHub Copilot Instructions

## 🤖 CRITICAL PROJECT CONTEXT - READ THIS FIRST
This is a **REAL AUTONOMOUS MULTI-AGENT AI SYSTEM** using Azure OpenAI GPT-4 for intelligent processing. This is NOT a simulation, demo, or placeholder system. Every agent uses actual LLM capabilities for decision making, natural language processing, and intelligent automation.

**NEVER** implement regex parsing, hardcoded logic, or placeholder functions where LLM processing should be used. Always leverage the full power of Azure OpenAI through Semantic Kernel.

## Core System Architecture
- **7 Autonomous AI Agents** - Each uses Azure OpenAI for intelligent processing
- **Semantic Kernel Framework** - Orchestrates LLM interactions and agent coordination
- **Azure Service Bus** - Reliable inter-agent messaging and workflow coordination
- **Azure Cosmos DB** - Persistent state management for loan lock records
- **Managed Identity** - Secure authentication across all Azure services

## AI/LLM Usage Guidelines - CRITICAL
- **Email Intake Agent**: Uses LLM to parse natural language emails and extract structured loan data
- **Loan Context Agent**: Uses LLM to validate loan eligibility and analyze complex scenarios  
- **Rate Quote Agent**: Uses LLM to analyze market conditions and generate optimal rate strategies
- **Compliance Agent**: Uses LLM to assess regulatory compliance and identify risk factors
- **Lock Confirmation Agent**: Uses LLM to make final lock decisions and generate confirmations
- **Audit Agent**: Uses LLM to analyze patterns and generate intelligent compliance reports
- **Exception Handler**: Uses LLM to intelligently categorize and route complex cases

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
- Use Semantic Kernel for AI-powered decision making
- Implement proper memory management for agent context
- Follow the established agent communication patterns via Service Bus
- Ensure proper audit logging for all agent actions

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
- Write unit tests for all agent functionality
- Test Service Bus message processing end-to-end
- Validate managed identity authentication works correctly
- Test the complete workflow from email intake to lock confirmation

## Documentation Standards
- Keep README.md updated with current setup instructions
- Document any architectural decisions and trade-offs
- Maintain clear API documentation for external integrations
- Update deployment documentation when infrastructure changes