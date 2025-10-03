# Post-deployment script to configure Service Bus V2 connection for managed identity
Write-Host "Configuring Service Bus V2 connection for managed identity..." -ForegroundColor Cyan

$subscriptionId = "d201ebeb-c470-4a6f-82d5-c2f95bb0dc1e"
$resourceGroup = "rg-ai-rate-lock-dev"
$connectionName = "servicebus-v2"
$serviceBusNamespace = "ai-rate-lock-dev-t6eaj464kxjt2-servicebus"
$inboundLogicAppName = "inbound-email-processor"
$outboundLogicAppName = "outbound-email-sender"

try {
    Write-Host "Step 1: Updating Service Bus connection configuration..." -ForegroundColor Yellow
    
    $connectionConfig = @"
{
    "location": "eastus2",
    "properties": {
        "displayName": "Service Bus V2 Managed Identity",
        "api": {
            "id": "/subscriptions/$subscriptionId/providers/Microsoft.Web/locations/eastus2/managedApis/servicebus"
        },
        "parameterValueSet": {
            "name": "managedIdentityAuth",
            "values": {
                "namespaceEndpoint": {
                    "value": "sb://$serviceBusNamespace.servicebus.windows.net/"
                }
            }
        }
    }
}
"@

    $connectionConfig | Out-File -FilePath "temp-connection-config.json" -Encoding utf8
    
    $connectionUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Web/connections/$connectionName" + "?api-version=2016-06-01"
    az rest --method put --url $connectionUrl --body "@temp-connection-config.json"
    
    Remove-Item -Path "temp-connection-config.json" -ErrorAction SilentlyContinue
    
    Write-Host "Service Bus V2 connection configured for managed identity!" -ForegroundColor Green

    Write-Host "Step 2: Getting Logic App definitions..." -ForegroundColor Yellow
    
    # Get current Logic App definitions using az logic workflow
    $inboundLogicAppJson = az logic workflow show --resource-group $resourceGroup --name $inboundLogicAppName
    $outboundLogicAppJson = az logic workflow show --resource-group $resourceGroup --name $outboundLogicAppName
    
    # Convert to PowerShell objects
    $inboundLogicApp = $inboundLogicAppJson | ConvertFrom-Json
    $outboundLogicApp = $outboundLogicAppJson | ConvertFrom-Json
    
    Write-Host "Step 3: Updating Logic Apps with managed identity connection properties..." -ForegroundColor Yellow
    
    # Add connectionProperties to Service Bus connections
    $connectionProperties = @{
        authentication = @{
            type = "ManagedServiceIdentity"
        }
    }
    
    # Check if servicebus connection exists and add connectionProperties
    if ($inboundLogicApp.parameters.'$connections'.value.servicebus) {
        $inboundLogicApp.parameters.'$connections'.value.servicebus | Add-Member -MemberType NoteProperty -Name "connectionProperties" -Value $connectionProperties -Force
        Write-Host "Added connectionProperties to inbound Logic App" -ForegroundColor Green
    } else {
        Write-Host "Warning: servicebus connection not found in inbound Logic App" -ForegroundColor Yellow
    }
    
    if ($outboundLogicApp.parameters.'$connections'.value.servicebus) {
        $outboundLogicApp.parameters.'$connections'.value.servicebus | Add-Member -MemberType NoteProperty -Name "connectionProperties" -Value $connectionProperties -Force
        Write-Host "Added connectionProperties to outbound Logic App" -ForegroundColor Green
    } else {
        Write-Host "Warning: servicebus connection not found in outbound Logic App" -ForegroundColor Yellow
    }
    
    # Save updated definitions - only include the necessary properties for update
    $inboundUpdateBody = @{
        location = $inboundLogicApp.location
        identity = $inboundLogicApp.identity
        properties = @{
            definition = $inboundLogicApp.definition
            parameters = $inboundLogicApp.parameters
        }
    }
    
    $outboundUpdateBody = @{
        location = $outboundLogicApp.location
        identity = $outboundLogicApp.identity
        properties = @{
            definition = $outboundLogicApp.definition
            parameters = $outboundLogicApp.parameters
        }
    }
    
    $inboundUpdateBody | ConvertTo-Json -Depth 20 | Out-File -FilePath "temp-inbound-config.json" -Encoding utf8
    $outboundUpdateBody | ConvertTo-Json -Depth 20 | Out-File -FilePath "temp-outbound-config.json" -Encoding utf8
    
    # Update Logic Apps using the full workflow endpoint
    $inboundUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Logic/workflows/$inboundLogicAppName" + "?api-version=2019-05-01"
    $outboundUrl = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Logic/workflows/$outboundLogicAppName" + "?api-version=2019-05-01"
    
    az rest --method put --url $inboundUrl --body "@temp-inbound-config.json"
    az rest --method put --url $outboundUrl --body "@temp-outbound-config.json"
    
    Remove-Item -Path "temp-inbound-config.json" -ErrorAction SilentlyContinue
    Remove-Item -Path "temp-outbound-config.json" -ErrorAction SilentlyContinue
    
    Write-Host "Logic Apps updated with managed identity connection properties!" -ForegroundColor Green
    Write-Host "Managed identity configuration complete!" -ForegroundColor Green

} catch {
    Write-Host "Error configuring Service Bus connection: $_" -ForegroundColor Red
    # Clean up temp files
    Remove-Item -Path "temp-connection-config.json" -ErrorAction SilentlyContinue
    Remove-Item -Path "temp-inbound-config.json" -ErrorAction SilentlyContinue
    Remove-Item -Path "temp-outbound-config.json" -ErrorAction SilentlyContinue
    exit 1
}