@description('Primary location for all resources')
param location string = resourceGroup().location

@description('Connection name')
param connectionName string = 'servicebus-v2'

// Deploy basic Service Bus connection - managed identity authentication will be 
// configured at the Logic App level through connectionProperties
resource serviceBusV2Connection 'Microsoft.Web/connections@2016-06-01' = {
  name: connectionName
  location: location
  properties: {
    displayName: 'Service Bus V2 Managed Identity'
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'servicebus')
    }
    // Empty parameterValues - Logic Apps will override with connectionProperties
    parameterValues: {}
  }
}

output connectionId string = serviceBusV2Connection.id
output connectionName string = serviceBusV2Connection.name
