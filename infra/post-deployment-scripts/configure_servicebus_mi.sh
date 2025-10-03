#!/bin/bash
# Post-deployment script to configure Service Bus V2 connection for managed identity
echo "Configuring Service Bus V2 connection for managed identity..."

SUBSCRIPTION_ID="d201ebeb-c470-4a6f-82d5-c2f95bb0dc1e"
RESOURCE_GROUP="rg-ai-rate-lock-dev"
CONNECTION_NAME="servicebus-v2"
SERVICEBUS_NAMESPACE="ai-rate-lock-dev-t6eaj464kxjt2-servicebus"
INBOUND_LOGIC_APP_NAME="inbound-email-processor"
OUTBOUND_LOGIC_APP_NAME="outbound-email-sender"

echo "Step 1: Updating Service Bus connection configuration..."

# Create connection configuration
cat > temp-connection-config.json << EOF
{
    "location": "eastus2",
    "properties": {
        "displayName": "Service Bus V2 Managed Identity",
        "api": {
            "id": "/subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.Web/locations/eastus2/managedApis/servicebus"
        },
        "parameterValueSet": {
            "name": "managedIdentityAuth",
            "values": {
                "namespaceEndpoint": {
                    "value": "sb://$SERVICEBUS_NAMESPACE.servicebus.windows.net/"
                }
            }
        }
    }
}
EOF

# Update Service Bus connection
CONNECTION_URL="https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Web/connections/$CONNECTION_NAME?api-version=2016-06-01"
az rest --method put --url "$CONNECTION_URL" --body @temp-connection-config.json

if [ $? -eq 0 ]; then
    echo "Service Bus V2 connection configured for managed identity!"
else
    echo "Error configuring Service Bus connection"
    rm -f temp-connection-config.json
    exit 1
fi

echo "Step 2: Getting Logic App definitions..."

# Get current Logic App definitions using az logic workflow
az logic workflow show --resource-group "$RESOURCE_GROUP" --name "$INBOUND_LOGIC_APP_NAME" > temp-inbound-original.json
az logic workflow show --resource-group "$RESOURCE_GROUP" --name "$OUTBOUND_LOGIC_APP_NAME" > temp-outbound-original.json

echo "Step 3: Updating Logic Apps with managed identity connection properties..."

# Check if servicebus connection exists and add connectionProperties
if jq -e '.parameters["$connections"].value.servicebus' temp-inbound-original.json > /dev/null; then
    # Update inbound Logic App with managed identity properties using correct path
    jq '.parameters["$connections"].value.servicebus.connectionProperties = {"authentication": {"type": "ManagedServiceIdentity"}}' temp-inbound-original.json > temp-inbound-updated.json
    
    # Create proper update body with only necessary properties
    jq '{
        location: .location,
        identity: .identity,
        properties: {
            definition: .definition,
            parameters: .parameters
        }
    }' temp-inbound-updated.json > temp-inbound-config.json
    
    echo "Added connectionProperties to inbound Logic App"
else
    echo "Warning: servicebus connection not found in inbound Logic App"
fi

if jq -e '.parameters["$connections"].value.servicebus' temp-outbound-original.json > /dev/null; then
    # Update outbound Logic App with managed identity properties using correct path
    jq '.parameters["$connections"].value.servicebus.connectionProperties = {"authentication": {"type": "ManagedServiceIdentity"}}' temp-outbound-original.json > temp-outbound-updated.json
    
    # Create proper update body with only necessary properties
    jq '{
        location: .location,
        identity: .identity,
        properties: {
            definition: .definition,
            parameters: .parameters
        }
    }' temp-outbound-updated.json > temp-outbound-config.json
    
    echo "Added connectionProperties to outbound Logic App"
else
    echo "Warning: servicebus connection not found in outbound Logic App"
fi

# Update Logic Apps
INBOUND_URL="https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Logic/workflows/$INBOUND_LOGIC_APP_NAME?api-version=2019-05-01"
OUTBOUND_URL="https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Logic/workflows/$OUTBOUND_LOGIC_APP_NAME?api-version=2019-05-01"

az rest --method put --url "$INBOUND_URL" --body @temp-inbound-config.json
az rest --method put --url "$OUTBOUND_URL" --body @temp-outbound-config.json

if [ $? -eq 0 ]; then
    echo "Logic Apps updated with managed identity connection properties!"
    echo "Managed identity configuration complete!"
else
    echo "Error updating Logic Apps"
    # Clean up temp files
    rm -f temp-*config.json temp-*original.json temp-*updated.json
    exit 1
fi

# Clean up temp files
rm -f temp-*config.json temp-*original.json temp-*updated.json

echo "Configuration complete!"