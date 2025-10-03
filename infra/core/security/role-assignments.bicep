@description('Service Bus namespace name')
param serviceBusNamespaceName string

@description('Logic App principal IDs that need access')
param logicAppPrincipalIds array

// Get the Service Bus namespace resource
resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2021-11-01' existing = {
  name: serviceBusNamespaceName
}

// Assign Service Bus Data Sender role to each Logic App
resource serviceBusDataSenderRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalId in logicAppPrincipalIds: {
  name: guid(serviceBusNamespace.id, principalId, 'Azure Service Bus Data Sender')
  scope: serviceBusNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39') // Azure Service Bus Data Sender
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}]

// Assign Service Bus Data Receiver role to each Logic App  
resource serviceBusDataReceiverRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalId in logicAppPrincipalIds: {
  name: guid(serviceBusNamespace.id, principalId, 'Azure Service Bus Data Receiver')
  scope: serviceBusNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0') // Azure Service Bus Data Receiver
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}]
