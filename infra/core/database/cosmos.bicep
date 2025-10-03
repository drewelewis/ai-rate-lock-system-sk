@description('The name of the Cosmos DB account')
param name string

@description('The location into which the Cosmos DB resources should be deployed')
param location string = resourceGroup().location

@description('The tags to apply to the Cosmos DB account')
param tags object = {}

@description('The principal ID to assign roles to')
param principalId string = ''

// Database name
var databaseName = 'RateLockSystem'

resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: name
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
      maxIntervalInSeconds: 5
      maxStalenessPrefix: 100
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
    enableAutomaticFailover: false
    enableMultipleWriteLocations: false
    publicNetworkAccess: 'Enabled'
    networkAclBypass: 'AzureServices'
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosDbAccount
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// Main container for rate lock records - partitioned by loan application ID
resource rateLockContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'RateLockRecords'
  properties: {
    resource: {
      id: 'RateLockRecords'
      partitionKey: {
        paths: ['/loanApplicationId']
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/auditLog/*'
          }
        ]
        compositeIndexes: [
          [
            {
              path: '/lockDetails/status'
              order: 'ascending'
            }
            {
              path: '/audit/lastModified'
              order: 'descending'
            }
          ]
          [
            {
              path: '/borrower/email'
              order: 'ascending'
            }
            {
              path: '/audit/created'
              order: 'descending'
            }
          ]
        ]
      }
      defaultTtl: -1 // Never expire by default
    }
  }
}

// Audit container for immutable audit logs - partitioned by date for time-series queries
resource auditContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'AuditLogs'
  properties: {
    resource: {
      id: 'AuditLogs'
      partitionKey: {
        paths: ['/auditDate']  // Format: YYYY-MM-DD for efficient date range queries
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [
          {
            path: '/*'
          }
          {
            path: '/timestamp/?'
          }
          {
            path: '/agentName/?'
          }
          {
            path: '/loanApplicationId/?'
          }
          {
            path: '/eventType/?'
          }
        ]
        excludedPaths: [
          {
            path: '/payload/*'
          }
        ]
      }
      defaultTtl: 2592000 // 30 days retention for audit logs
    }
  }
}

// Configuration container for system settings and business rules
resource configContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'Configuration'
  properties: {
    resource: {
      id: 'Configuration'
      partitionKey: {
        paths: ['/configType']  // e.g., 'agent-settings', 'business-rules', 'rate-tables'
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [
          {
            path: '/*'
          }
        ]
      }
      defaultTtl: -1 // Configuration never expires
    }
  }
}

// Exception tracking container for human escalation cases
resource exceptionContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'Exceptions'
  properties: {
    resource: {
      id: 'Exceptions'
      partitionKey: {
        paths: ['/priority']  // 'high', 'medium', 'low' for efficient priority-based queries
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [
          {
            path: '/*'
          }
          {
            path: '/status/?'    // open, in-progress, resolved
          }
          {
            path: '/created/?'
          }
          {
            path: '/assignee/?'
          }
          {
            path: '/loanApplicationId/?'
          }
        ]
        compositeIndexes: [
          [
            {
              path: '/status'
              order: 'ascending'
            }
            {
              path: '/created'
              order: 'ascending'
            }
          ]
        ]
      }
      defaultTtl: 7776000 // 90 days retention for resolved exceptions
    }
  }
}

// Assign DocumentDB Account Contributor role to the principal
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: cosmosDbAccount
  name: guid(cosmosDbAccount.id, principalId, '5bd9cd88-fe45-4216-938b-f97437e15450')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5bd9cd88-fe45-4216-938b-f97437e15450') // DocumentDB Account Contributor
    principalId: principalId
    principalType: 'User'
  }
}

// Assign Cosmos DB Built-in Data Contributor role to the principal for data plane operations
resource dataContributorRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (!empty(principalId)) {
  parent: cosmosDbAccount
  name: guid(cosmosDbAccount.id, principalId, '00000000-0000-0000-0000-000000000002')
  properties: {
    roleDefinitionId: '${cosmosDbAccount.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: principalId
  }
}

output endpoint string = cosmosDbAccount.properties.documentEndpoint
output name string = cosmosDbAccount.name
output databaseName string = databaseName
output id string = cosmosDbAccount.id
