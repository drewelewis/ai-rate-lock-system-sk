@description('The name of the Service Bus namespace')
param name string

@description('The location into which the Service Bus resources should be deployed')
param location string = resourceGroup().location

@description('The tags to apply to the Service Bus namespace')
param tags object = {}

@description('The pricing tier for the Service Bus namespace')
@allowed(['Basic', 'Standard', 'Premium'])
param skuName string = 'Standard'

@description('The principal ID to assign roles to')
param principalId string = ''

/*
SIMPLIFIED SERVICE BUS ARCHITECTURE - SINGLE TOPIC WITH FILTERS

This template implements a simplified messaging architecture:

SINGLE TOPIC (Pub/Sub with Filters):
- agent-workflow-events: ALL agent coordination via subscription filters
  ├── email-intake-sub (filter: MessageType = 'email_received')
  ├── loan-context-sub (filter: MessageType = 'email_parsed')
  ├── rate-quote-sub (filter: MessageType = 'context_retrieved')
  ├── compliance-sub (filter: MessageType = 'rate_quoted')
  ├── lock-confirmation-sub (filter: MessageType = 'compliance_passed')
  ├── audit-sub (filter: MessageType = 'audit_log' OR all messages)
  └── exception-sub (filter: Priority = 'high' OR MessageType = 'exception')

QUEUES (Point-to-Point - External Integration):
- inbound-email-queue: Logic Apps → Email Intake Agent
- outbound-email-queue: Lock confirmations ready to send
- high-priority-exceptions: Direct routing for urgent manual intervention

WHY SINGLE TOPIC?
- Simplified architecture (1 topic vs 4)
- Flexible routing via SQL filters
- Easy to add new agents (just add subscription + filter)
- Better observability (all events in one place)
- Cost effective (fewer resources)
*/

resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2021-11-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  properties: {
    disableLocalAuth: false
  }
}

// ============================================================================
// QUEUES - External Integration Points
// ============================================================================

resource inboundEmailQueue 'Microsoft.ServiceBus/namespaces/queues@2021-11-01' = {
  parent: serviceBusNamespace
  name: 'inbound-email-queue'
  properties: {
    maxMessageSizeInKilobytes: 256
    defaultMessageTimeToLive: 'P1D' // 1 day
    maxSizeInMegabytes: 1024
    duplicateDetectionHistoryTimeWindow: 'PT10M' // 10 minutes
    requiresDuplicateDetection: false
    enablePartitioning: false
    lockDuration: 'PT1M'
    maxDeliveryCount: 10
    deadLetteringOnMessageExpiration: false
    enableBatchedOperations: true
  }
}

resource outboundEmailQueue 'Microsoft.ServiceBus/namespaces/queues@2021-11-01' = {
  parent: serviceBusNamespace
  name: 'outbound-email-queue'
  properties: {
    maxMessageSizeInKilobytes: 256
    defaultMessageTimeToLive: 'P1D' // 1 day
    maxSizeInMegabytes: 1024
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    requiresDuplicateDetection: false
    enablePartitioning: false
    lockDuration: 'PT1M'
    maxDeliveryCount: 10
    deadLetteringOnMessageExpiration: false
    enableBatchedOperations: true
  }
}

resource exceptionQueue 'Microsoft.ServiceBus/namespaces/queues@2021-11-01' = {
  parent: serviceBusNamespace
  name: 'high-priority-exceptions'
  properties: {
    maxMessageSizeInKilobytes: 256
    defaultMessageTimeToLive: 'P7D' // 7 days for compliance
    maxSizeInMegabytes: 1024
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    requiresDuplicateDetection: true
    enablePartitioning: false
    lockDuration: 'PT5M' // Longer lock for manual intervention
    maxDeliveryCount: 3
    deadLetteringOnMessageExpiration: true
    enableBatchedOperations: true
  }
}

// ============================================================================
// SINGLE TOPIC - All Agent Workflow Events
// ============================================================================

resource agentWorkflowTopic 'Microsoft.ServiceBus/namespaces/topics@2021-11-01' = {
  parent: serviceBusNamespace
  name: 'agent-workflow-events'
  properties: {
    maxMessageSizeInKilobytes: 256
    defaultMessageTimeToLive: 'P1D' // 1 day
    maxSizeInMegabytes: 2048 // Larger size for all events
    duplicateDetectionHistoryTimeWindow: 'PT10M' // 10 minutes
    requiresDuplicateDetection: true
    enablePartitioning: false // Keep false for message ordering
    supportOrdering: true // Maintain order within sessions
  }
}

// ============================================================================
// SUBSCRIPTIONS WITH SQL FILTERS - Agent-Specific Routing
// ============================================================================

// Email Intake Agent Subscription
resource emailIntakeSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: agentWorkflowTopic
  name: 'email-intake-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
    enableBatchedOperations: true
  }
}

resource emailIntakeFilter 'Microsoft.ServiceBus/namespaces/topics/subscriptions/rules@2021-11-01' = {
  parent: emailIntakeSubscription
  name: 'EmailIntakeFilter'
  properties: {
    filterType: 'SqlFilter'
    sqlFilter: {
      sqlExpression: 'MessageType = \'email_received\' OR TargetAgent = \'email_intake\''
      compatibilityLevel: 20
    }
  }
}

// Loan Context Agent Subscription
resource loanContextSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: agentWorkflowTopic
  name: 'loan-context-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
    enableBatchedOperations: true
  }
}

resource loanContextFilter 'Microsoft.ServiceBus/namespaces/topics/subscriptions/rules@2021-11-01' = {
  parent: loanContextSubscription
  name: 'LoanContextFilter'
  properties: {
    filterType: 'SqlFilter'
    sqlFilter: {
      sqlExpression: 'MessageType = \'email_parsed\' OR TargetAgent = \'loan_context\''
      compatibilityLevel: 20
    }
  }
}

// Rate Quote Agent Subscription
resource rateQuoteSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: agentWorkflowTopic
  name: 'rate-quote-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
    enableBatchedOperations: true
  }
}

resource rateQuoteFilter 'Microsoft.ServiceBus/namespaces/topics/subscriptions/rules@2021-11-01' = {
  parent: rateQuoteSubscription
  name: 'RateQuoteFilter'
  properties: {
    filterType: 'SqlFilter'
    sqlFilter: {
      sqlExpression: 'MessageType = \'context_retrieved\' OR TargetAgent = \'rate_quote\''
      compatibilityLevel: 20
    }
  }
}

// Compliance Risk Agent Subscription
resource complianceSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: agentWorkflowTopic
  name: 'compliance-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
    enableBatchedOperations: true
  }
}

resource complianceFilter 'Microsoft.ServiceBus/namespaces/topics/subscriptions/rules@2021-11-01' = {
  parent: complianceSubscription
  name: 'ComplianceFilter'
  properties: {
    filterType: 'SqlFilter'
    sqlFilter: {
      sqlExpression: 'MessageType = \'rate_quoted\' OR TargetAgent = \'compliance\''
      compatibilityLevel: 20
    }
  }
}

// Lock Confirmation Agent Subscription
resource lockConfirmationSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: agentWorkflowTopic
  name: 'lock-confirmation-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
    enableBatchedOperations: true
  }
}

resource lockConfirmationFilter 'Microsoft.ServiceBus/namespaces/topics/subscriptions/rules@2021-11-01' = {
  parent: lockConfirmationSubscription
  name: 'LockConfirmationFilter'
  properties: {
    filterType: 'SqlFilter'
    sqlFilter: {
      sqlExpression: 'MessageType = \'compliance_passed\' OR TargetAgent = \'lock_confirmation\''
      compatibilityLevel: 20
    }
  }
}

// Audit Logging Agent Subscription (receives ALL messages for comprehensive logging)
resource auditSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: agentWorkflowTopic
  name: 'audit-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P7D' // 7 days for compliance
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
    enableBatchedOperations: true
  }
}

resource auditFilter 'Microsoft.ServiceBus/namespaces/topics/subscriptions/rules@2021-11-01' = {
  parent: auditSubscription
  name: 'AuditFilter'
  properties: {
    filterType: 'SqlFilter'
    sqlFilter: {
      // Receive ALL messages for audit trail
      sqlExpression: 'MessageType IS NOT NULL OR TargetAgent = \'audit\''
      compatibilityLevel: 20
    }
  }
}

// Exception Handler Subscription (high priority and exceptions)
resource exceptionSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: agentWorkflowTopic
  name: 'exception-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
    enableBatchedOperations: true
  }
}

resource exceptionFilter 'Microsoft.ServiceBus/namespaces/topics/subscriptions/rules@2021-11-01' = {
  parent: exceptionSubscription
  name: 'ExceptionFilter'
  properties: {
    filterType: 'SqlFilter'
    sqlFilter: {
      sqlExpression: 'MessageType = \'exception\' OR Priority = \'high\' OR Priority = \'critical\' OR TargetAgent = \'exception_handler\''
      compatibilityLevel: 20
    }
  }
}

// ============================================================================
// ROLE ASSIGNMENTS - Azure RBAC for Managed Identity
// ============================================================================

// Azure Service Bus Data Sender role
resource serviceBusSenderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(serviceBusNamespace.id, principalId, 'ServiceBusSender')
  scope: serviceBusNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39')
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Azure Service Bus Data Receiver role
resource serviceBusReceiverRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(serviceBusNamespace.id, principalId, 'ServiceBusReceiver')
  scope: serviceBusNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0')
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// OUTPUTS
// ============================================================================

output serviceBusEndpoint string = 'https://${serviceBusNamespace.name}.servicebus.windows.net'
output serviceBusNamespaceName string = serviceBusNamespace.name
output serviceBusNamespaceId string = serviceBusNamespace.id

// Topic name
output agentWorkflowTopicName string = agentWorkflowTopic.name

// Queue names
output inboundEmailQueueName string = inboundEmailQueue.name
output outboundEmailQueueName string = outboundEmailQueue.name
output highPriorityExceptionsQueueName string = exceptionQueue.name

// Subscription names (for reference)
output emailIntakeSubscriptionName string = emailIntakeSubscription.name
output loanContextSubscriptionName string = loanContextSubscription.name
output rateQuoteSubscriptionName string = rateQuoteSubscription.name
output complianceSubscriptionName string = complianceSubscription.name
output lockConfirmationSubscriptionName string = lockConfirmationSubscription.name
output auditSubscriptionName string = auditSubscription.name
output exceptionSubscriptionName string = exceptionSubscription.name
