@description('The name of the inbound email processing Logic App.')
param inboundLogicAppName string = 'inbound-email-processor'

@description('The name of the outbound email sending Logic App.')
param outboundLogicAppName string = 'outbound-email-sender'

@description('The location for the Logic Apps.')
param location string = resourceGroup().location

@description('The resource ID of the Office 365 API Connection.')
param office365ApiConnectionId string

@description('The resource ID of the Service Bus API Connection.')
param serviceBusApiConnectionId string

resource inboundEmailProcessor 'Microsoft.Logic/workflows@2019-05-01' = {
  name: inboundLogicAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    definition: json(loadTextContent('workflows/inbound-email-processor.json'))
    parameters: {
      '$connections': {
        value: {
          office365: {
            connectionId: office365ApiConnectionId
            connectionName: 'office365'
            id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'office365')
          }
          servicebus: {
            connectionId: serviceBusApiConnectionId
            connectionName: 'servicebus-v2'
            id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'servicebus')
            connectionProperties: {
              authentication: {
                type: 'ManagedServiceIdentity'
              }
            }
          }
        }
      }
    }
  }
}

resource outboundEmailSender 'Microsoft.Logic/workflows@2019-05-01' = {
  name: outboundLogicAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    definition: json(loadTextContent('workflows/outbound-email-sender.json'))
    parameters: {
      '$connections': {
        value: {
          office365: {
            connectionId: office365ApiConnectionId
            connectionName: 'office365'
            id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'office365')
          }
          servicebus: {
            connectionId: serviceBusApiConnectionId
            connectionName: 'servicebus-v2'
            id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'servicebus')
            connectionProperties: {
              authentication: {
                type: 'ManagedServiceIdentity'
              }
            }
          }
        }
      }
    }
  }
}

output inboundLogicAppPrincipalId string = inboundEmailProcessor.identity.principalId
output outboundLogicAppPrincipalId string = outboundEmailSender.identity.principalId
