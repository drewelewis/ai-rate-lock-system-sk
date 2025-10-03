#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Adds missing Service Bus topics to align with the consolidated architecture

.DESCRIPTION
    This script adds any Service Bus topics that are missing from the current Azure deployment
    to match the consolidated architecture defined in the code. It only creates topics that
    don't already exist, making it safe to run multiple times.

.PARAMETER ResourceGroupName
    The name of the resource group containing the Service Bus namespace

.PARAMETER NamespaceName  
    The name of the Service Bus namespace

.PARAMETER DryRun
    When specified, shows what would be created without actually creating resources

.EXAMPLE
    .\add-missing-servicebus-topics.ps1 -ResourceGroupName "rg-ai-rate-lock-dev" -NamespaceName "ai-rate-lock-dev-t6eaj464kxjt2-servicebus"

.EXAMPLE
    .\add-missing-servicebus-topics.ps1 -ResourceGroupName "rg-ai-rate-lock-dev" -NamespaceName "ai-rate-lock-dev-t6eaj464kxjt2-servicebus" -DryRun
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroupName,
    
    [Parameter(Mandatory=$true)]
    [string]$NamespaceName,
    
    [switch]$DryRun
)

# Set error action preference
$ErrorActionPreference = "Stop"

Write-Host "🚌 Service Bus Topic Configuration Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Azure CLI is installed and logged in
try {
    $account = az account show --query "name" -o tsv 2>$null
    if (-not $account) {
        throw "Not logged in"
    }
    Write-Host "✅ Azure CLI authenticated as: $account" -ForegroundColor Green
} catch {
    Write-Host "❌ Azure CLI not authenticated. Please run 'az login'" -ForegroundColor Red
    exit 1
}

# Define the required topics based on our consolidated architecture
$RequiredTopics = @(
    @{
        Name = "loan-lifecycle-events"
        Description = "Main workflow coordination for all loan processing steps"
        MaxSizeInMegabytes = 1024
        DefaultMessageTimeToLive = "P1D"
        RequiresDuplicateDetection = $true
        EnablePartitioning = $false
        SupportOrdering = $true
    },
    @{
        Name = "audit-events" 
        Description = "All audit logging and compliance tracking"
        MaxSizeInMegabytes = 2048
        DefaultMessageTimeToLive = "P7D"
        RequiresDuplicateDetection = $true
        EnablePartitioning = $true
        SupportOrdering = $false
    },
    @{
        Name = "compliance-events"
        Description = "Regulatory compliance notifications"
        MaxSizeInMegabytes = 1024
        DefaultMessageTimeToLive = "P7D"
        RequiresDuplicateDetection = $true
        EnablePartitioning = $false
        SupportOrdering = $true
    },
    @{
        Name = "exception-alerts"
        Description = "Error handling and exception notifications"
        MaxSizeInMegabytes = 1024
        DefaultMessageTimeToLive = "P1D"
        RequiresDuplicateDetection = $true
        EnablePartitioning = $false
        SupportOrdering = $true
    }
)

Write-Host "📊 Checking current Service Bus configuration..." -ForegroundColor Yellow
Write-Host "Resource Group: $ResourceGroupName" -ForegroundColor Gray
Write-Host "Namespace: $NamespaceName" -ForegroundColor Gray
Write-Host ""

# Get existing topics
try {
    $existingTopics = az servicebus topic list --namespace-name $NamespaceName --resource-group $ResourceGroupName --query "[].name" -o tsv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to list topics"
    }
    
    Write-Host "📋 Existing topics:" -ForegroundColor Green
    if ($existingTopics) {
        $existingTopics | ForEach-Object { Write-Host "  • $_" -ForegroundColor Gray }
    } else {
        Write-Host "  (No topics found)" -ForegroundColor Gray
    }
    Write-Host ""
} catch {
    Write-Host "❌ Failed to retrieve existing topics: $_" -ForegroundColor Red
    exit 1
}

# Determine which topics need to be created
$topicsToCreate = @()
foreach ($topic in $RequiredTopics) {
    if ($existingTopics -notcontains $topic.Name) {
        $topicsToCreate += $topic
    }
}

if ($topicsToCreate.Count -eq 0) {
    Write-Host "✅ All required topics already exist. No action needed." -ForegroundColor Green
    exit 0
}

Write-Host "🔨 Topics to create:" -ForegroundColor Yellow
$topicsToCreate | ForEach-Object { 
    Write-Host "  • $($_.Name) - $($_.Description)" -ForegroundColor Cyan 
}
Write-Host ""

if ($DryRun) {
    Write-Host "🏃‍♂️ DRY RUN MODE - No resources will be created" -ForegroundColor Magenta
    Write-Host ""
    
    foreach ($topic in $topicsToCreate) {
        Write-Host "Would create topic: $($topic.Name)" -ForegroundColor Yellow
        Write-Host "  Description: $($topic.Description)" -ForegroundColor Gray
        Write-Host "  Max Size: $($topic.MaxSizeInMegabytes) MB" -ForegroundColor Gray
        Write-Host "  TTL: $($topic.DefaultMessageTimeToLive)" -ForegroundColor Gray
        Write-Host "  Duplicate Detection: $($topic.RequiresDuplicateDetection)" -ForegroundColor Gray
        Write-Host "  Partitioning: $($topic.EnablePartitioning)" -ForegroundColor Gray
        Write-Host "  Ordering: $($topic.SupportOrdering)" -ForegroundColor Gray
        Write-Host ""
    }
    
    Write-Host "To actually create these topics, run the script without -DryRun" -ForegroundColor Magenta
    exit 0
}

# Create missing topics
Write-Host "🚀 Creating missing topics..." -ForegroundColor Green
Write-Host ""

$createdCount = 0
$failedCount = 0

foreach ($topic in $topicsToCreate) {
    Write-Host "Creating topic: $($topic.Name)..." -ForegroundColor Yellow
    
    try {
        # Build the az command parameters
        $params = @(
            "servicebus", "topic", "create"
            "--namespace-name", $NamespaceName
            "--resource-group", $ResourceGroupName
            "--name", $topic.Name
            "--max-size", $topic.MaxSizeInMegabytes
            "--default-message-time-to-live", $topic.DefaultMessageTimeToLive
            "--duplicate-detection-history-time-window", "PT10M"
            "--max-message-size", "256"
        )
        
        if ($topic.RequiresDuplicateDetection) {
            $params += "--enable-duplicate-detection"
        }
        
        if ($topic.EnablePartitioning) {
            $params += "--enable-partitioning"
        }
        
        if ($topic.SupportOrdering) {
            $params += "--support-ordering"
        }
        
        # Execute the command
        $result = & az @params 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✅ Successfully created $($topic.Name)" -ForegroundColor Green
            $createdCount++
        } else {
            Write-Host "  ❌ Failed to create $($topic.Name): $result" -ForegroundColor Red
            $failedCount++
        }
    } catch {
        Write-Host "  ❌ Exception creating $($topic.Name): $_" -ForegroundColor Red
        $failedCount++
    }
    
    Write-Host ""
}

# Create basic subscriptions for the new topics
if ($createdCount -gt 0) {
    Write-Host "📫 Creating basic subscriptions for new topics..." -ForegroundColor Yellow
    Write-Host ""
    
    foreach ($topic in $topicsToCreate) {
        if ($existingTopics -notcontains $topic.Name) {
            $subscriptionName = "$($topic.Name)-main-subscription"
            Write-Host "Creating subscription: $subscriptionName..." -ForegroundColor Yellow
            
            try {
                $result = az servicebus topic subscription create `
                    --namespace-name $NamespaceName `
                    --resource-group $ResourceGroupName `
                    --topic-name $topic.Name `
                    --name $subscriptionName `
                    --max-delivery-count 3 `
                    --default-message-time-to-live "P1D" `
                    --lock-duration "PT5M" `
                    --enable-dead-lettering-on-message-expiration `
                    --enable-dead-lettering-on-filter-evaluation-exceptions 2>&1
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "  ✅ Successfully created subscription $subscriptionName" -ForegroundColor Green
                } else {
                    Write-Host "  ⚠️  Warning: Failed to create subscription $subscriptionName" -ForegroundColor Yellow
                }
            } catch {
                Write-Host "  ⚠️  Warning: Exception creating subscription $subscriptionName: $_" -ForegroundColor Yellow
            }
            
            Write-Host ""
        }
    }
}

# Summary
Write-Host "📊 Summary:" -ForegroundColor Cyan
Write-Host "============" -ForegroundColor Cyan
Write-Host "Topics created: $createdCount" -ForegroundColor Green
if ($failedCount -gt 0) {
    Write-Host "Topics failed: $failedCount" -ForegroundColor Red
}
Write-Host ""

if ($createdCount -gt 0) {
    Write-Host "✅ Service Bus topics successfully updated!" -ForegroundColor Green
    Write-Host ""
    Write-Host "🔄 Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Update your application configuration if needed" -ForegroundColor Gray
    Write-Host "  2. Test the agent communication flows" -ForegroundColor Gray
    Write-Host "  3. Monitor the new topics in Azure Portal" -ForegroundColor Gray
} else {
    Write-Host "❌ No topics were created successfully." -ForegroundColor Red
    Write-Host "Please check the errors above and try again." -ForegroundColor Red
}

Write-Host ""
Write-Host "🎯 Run 'az servicebus topic list --namespace-name $NamespaceName --resource-group $ResourceGroupName' to verify" -ForegroundColor Cyan