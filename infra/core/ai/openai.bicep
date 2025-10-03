@description('The name of the Azure OpenAI service')
param name string

@description('The location into which the Azure OpenAI resources should be deployed')
param location string = resourceGroup().location

@description('The tags to apply to the Azure OpenAI service')
param tags object = {}

@description('The pricing tier for the Azure OpenAI service')
@allowed(['S0'])
param skuName string = 'S0'

@description('The principal ID to assign roles to')
param principalId string = ''

resource openAIAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: skuName
  }
  properties: {
    customSubDomainName: toLower(name)
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
    disableLocalAuth: false
  }
}

// Deploy GPT-4o model for the rate lock agents
resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAIAccount
  name: 'gpt-4o'
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-08-06'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'OnceCurrentVersionExpired'
    currentCapacity: 10
  }
  sku: {
    name: 'Standard'
    capacity: 10
  }
}

// Deploy text embedding model for document processing
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAIAccount
  name: 'text-embedding-3-small'
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-small'
      version: '1'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'OnceCurrentVersionExpired'
    currentCapacity: 10
  }
  sku: {
    name: 'Standard'
    capacity: 10
  }
  dependsOn: [
    gpt4oDeployment
  ]
}

// Assign Cognitive Services OpenAI User role to the principal
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: openAIAccount
  name: guid(openAIAccount.id, principalId, 'a97b65f3-24c7-4388-baec-2e87135dc908')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908') // Cognitive Services OpenAI User
    principalId: principalId
    principalType: 'User'
  }
}

output endpoint string = openAIAccount.properties.endpoint
output name string = openAIAccount.name
output id string = openAIAccount.id
