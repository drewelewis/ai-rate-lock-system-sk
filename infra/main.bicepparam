using 'main.bicep'

param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'ai-rate-lock-dev')
param location = readEnvironmentVariable('AZURE_LOCATION', 'eastus')
param principalId = readEnvironmentVariable('AZURE_PRINCIPAL_ID', '')

// Service tiers - optimized for development/staging
param openAISkuName = 'S0'
param serviceBusSkuName = 'Standard'
