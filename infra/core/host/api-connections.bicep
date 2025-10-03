@description('Primary location for all resources')
param location string = resourceGroup().location

@description('Tags to apply to all resources')
param tags object = {}

// Office 365 API Connection
resource office365Connection 'Microsoft.Web/connections@2016-06-01' = {
  name: 'office365'
  location: location
  tags: tags
  properties: {
    displayName: 'Office 365 Outlook'
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'office365')
    }
  }
}

output office365ConnectionId string = office365Connection.id
output office365ConnectionName string = office365Connection.name
