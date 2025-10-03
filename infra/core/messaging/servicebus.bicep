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
HYBRID SERVICE BUS ARCHITECTURE

This template implements a hybrid messaging architecture combining:

QUEUES (Point-to-Point):
- inbound-email-queue: Logic Apps → Email Intake Agent
- outbound-email-queue: Lock confirmations ready to send
- high-priority-exceptions: Direct routing for urgent manual intervention

TOPICS (Pub/Sub):
- loan-lifecycle-events: Main workflow coordination between all agents
- compliance-events: Compliance-specific events requiring special handling
- audit-events: System-wide audit trail for all operations

WHY HYBRID?
- Queues: Reliable email processing, guaranteed single delivery, Logic Apps integration
- Topics: Multi-agent coordination, audit trails, event broadcasting, loose coupling
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

// Queues for Logic Apps direct communication
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

// High-priority exceptions queue for urgent issues
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

// Topics for internal agent coordination (hybrid architecture)
resource loanLifecycleTopic 'Microsoft.ServiceBus/namespaces/topics@2021-11-01' = {
  parent: serviceBusNamespace
  name: 'loan-lifecycle-events'
  properties: {
    maxMessageSizeInKilobytes: 256
    defaultMessageTimeToLive: 'P1D' // 1 day
    maxSizeInMegabytes: 1024
    duplicateDetectionHistoryTimeWindow: 'PT10M' // 10 minutes
    requiresDuplicateDetection: true
    enablePartitioning: false
    supportOrdering: true
  }
}

// Compliance-specific topic for regulatory events
resource complianceTopic 'Microsoft.ServiceBus/namespaces/topics@2021-11-01' = {
  parent: serviceBusNamespace
  name: 'compliance-events'
  properties: {
    maxMessageSizeInKilobytes: 256
    defaultMessageTimeToLive: 'P7D' // 7 days for compliance
    maxSizeInMegabytes: 1024
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    requiresDuplicateDetection: true
    enablePartitioning: false
    supportOrdering: true
  }
}

// Audit topic for comprehensive logging
resource auditTopic 'Microsoft.ServiceBus/namespaces/topics@2021-11-01' = {
  parent: serviceBusNamespace
  name: 'audit-events'
  properties: {
    maxMessageSizeInKilobytes: 256
    defaultMessageTimeToLive: 'P7D' // 7 days
    maxSizeInMegabytes: 2048
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    requiresDuplicateDetection: true
    enablePartitioning: true // Enable partitioning for high throughput
  }
}

// Exception alerts topic for error handling
resource exceptionAlertsTopic 'Microsoft.ServiceBus/namespaces/topics@2021-11-01' = {
  parent: serviceBusNamespace
  name: 'exception-alerts'
  properties: {
    maxMessageSizeInKilobytes: 256
    defaultMessageTimeToLive: 'P1D' // 1 day
    maxSizeInMegabytes: 1024
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    requiresDuplicateDetection: true
    enablePartitioning: false
    supportOrdering: true
  }
}

// Agent subscriptions for loan lifecycle events
resource emailIntakeSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: loanLifecycleTopic
  name: 'email-intake-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
  }
}

resource loanContextSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: loanLifecycleTopic
  name: 'loan-context-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
  }
}

resource rateQuoteSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: loanLifecycleTopic
  name: 'rate-quote-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
  }
}

resource complianceSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: loanLifecycleTopic
  name: 'compliance-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M' // Max allowed for Standard tier
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
  }
}

resource lockConfirmationSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: loanLifecycleTopic
  name: 'lock-confirmation-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
  }
}

// Audit subscription for comprehensive logging
resource auditLoggingSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: auditTopic
  name: 'audit-logging-subscription'
  properties: {
    maxDeliveryCount: 5
    defaultMessageTimeToLive: 'P7D'
    lockDuration: 'PT1M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
  }
}

// Additional compliance subscriptions for regulatory events
resource complianceAuditSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: complianceTopic
  name: 'compliance-audit-subscription'
  properties: {
    maxDeliveryCount: 5
    defaultMessageTimeToLive: 'P7D'
    lockDuration: 'PT1M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
  }
}

resource complianceExceptionSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: complianceTopic
  name: 'compliance-exception-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
  }
}

resource exceptionHandlerSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: auditTopic
  name: 'exception-handler-subscription'
  properties: {
    maxDeliveryCount: 5
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
  }
}

// Exception alerts subscriptions
resource exceptionAlertsMainSubscription 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2021-11-01' = {
  parent: exceptionAlertsTopic
  name: 'exception-alerts-main-subscription'
  properties: {
    maxDeliveryCount: 3
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
    deadLetteringOnMessageExpiration: true
    deadLetteringOnFilterEvaluationExceptions: true
  }
}

// Assign Service Bus Data Owner role to the principal
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: serviceBusNamespace
  name: guid(serviceBusNamespace.id, principalId, '090c5cfd-751d-490a-894a-3ce6f1109419')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '090c5cfd-751d-490a-894a-3ce6f1109419') // Azure Service Bus Data Owner
    principalId: principalId
    principalType: 'User'
  }
}

output serviceBusEndpoint string = serviceBusNamespace.properties.serviceBusEndpoint
output endpoint string = 'https://${serviceBusNamespace.name}.servicebus.windows.net'
output namespaceName string = serviceBusNamespace.name
output id string = serviceBusNamespace.id

var rootManageSharedAccessKeyName = 'RootManageSharedAccessKey'

@secure()
output connectionString string = listKeys(resourceId('Microsoft.ServiceBus/namespaces/authorizationRules', serviceBusNamespace.name, rootManageSharedAccessKeyName), '2021-11-01').primaryConnectionString
