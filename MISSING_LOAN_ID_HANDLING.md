# Missing Loan ID Handling - Implementation Summary

## Overview
Implemented intelligent handling for rate lock requests that are missing a loan_application_id. When the LLM cannot extract a valid loan ID from the email, the system now automatically sends a professional email to the user requesting the missing information, while tracking the pending request in Cosmos DB.

## Problem Statement
Previously, if an email arrived without a clear loan application ID, the system would either:
- Generate a placeholder ID (APP-XXXXXX)
- Skip processing the request entirely
- Fail silently

This resulted in lost rate lock requests and poor user experience.

## Solution
The system now:
1. ✅ Detects missing or invalid loan IDs
2. ✅ Generates a temporary tracking ID
3. ✅ Sends a professional email requesting the loan ID
4. ✅ Creates a pending record in Cosmos DB
5. ✅ Logs the request for audit tracking

## Changes Made

### 1. Updated LLM Extraction Prompt (`_extract_loan_data_with_llm()`)

**Modified Instructions:**
```python
- loan_application_id: The loan ID found in the email. Look for patterns like 
  "APP-123456", "LA-123456", "Loan Application ID:", "Application #:", "Loan #:", 
  "ID:", etc. If NO loan ID is found, return null.

CRITICAL RULES:
1. Return ONLY valid JSON, no explanation or markdown formatting
2. Use null for missing values (do NOT generate placeholder IDs)
3. Extract actual data from the email content - do NOT make up or generate data
4. Be precise and accurate
5. If no loan ID found anywhere in the email, set loan_application_id to null
```

**Key Changes:**
- ❌ Removed instruction to generate placeholder IDs (APP-XXXXXX)
- ✅ Added instruction to return `null` when loan ID not found
- ✅ Emphasized "do NOT make up or generate data"

### 2. Enhanced Validation Logic (`_process_raw_email_with_llm()`)

**Added Smart Detection:**
```python
# Check if loan_application_id is missing or invalid
if not loan_application_id or loan_application_id in [None, "", "null", "unknown"]:
    logger.warning(f"{self.agent_name}: ⚠️ Missing loan_application_id - requesting from user")
    await self._request_loan_id_from_user(from_address, subject, raw_email_content, extracted_data)
    return

# Validate if it's a generated placeholder (APP-XXXXXX format from LLM)
if loan_application_id.startswith("APP-") and loan_application_id.count("X") >= 4:
    logger.warning(f"{self.agent_name}: ⚠️ LLM generated placeholder ID '{loan_application_id}' - requesting real ID from user")
    await self._request_loan_id_from_user(from_address, subject, raw_email_content, extracted_data)
    return
```

**Detection Cases:**
- `None` - No loan ID extracted
- `""` - Empty string
- `"null"` - String literal "null"
- `"unknown"` - Generic unknown value
- `APP-XXXXXX` - LLM-generated placeholder pattern

### 3. New Method: `_request_loan_id_from_user()`

**Purpose:** Send professional email requesting missing loan ID and track the pending request.

**Key Features:**

#### A. Temporary Tracking ID Generation
```python
from utils.id_generator import generate_rate_lock_request_id

# Generate a temporary tracking ID for this request
temp_request_id = generate_rate_lock_request_id("PENDING", prefix="TMP")
# Example: TMP-PENDING-20251003-a7f3b2c1
```

#### B. Professional Email Template
```
Subject: Action Required: Missing Loan Application ID

Dear {borrower_name},

Thank you for submitting your rate lock request. We have received your email 
regarding {property_address}.

However, we were unable to identify your Loan Application ID from your message. 
To process your rate lock request, we need this information.

**Please reply to this email with your Loan Application ID.**

Your Loan Application ID should look like one of these formats:
  • LA-123456
  • APP-789012
  • Loan #345678
  • Application ID: 456789

Once we receive your Loan Application ID, we will immediately process your 
rate lock request.

Temporary Tracking Reference: {temp_request_id}

If you need assistance locating your Loan Application ID, please contact your 
loan officer.
```

#### C. Email Delivery via Service Bus
```python
await self.servicebus_plugin.send_message_to_queue(
    queue_name="outbound_confirmations",  # → outbound-email-queue
    message_type="send_email_notification",
    loan_application_id=temp_request_id,
    message_data=email_payload
)
```

**Queue Flow:**
1. Email Intake Agent → `outbound_confirmations` queue
2. Logic Apps picks up from `outbound-email-queue`
3. Logic Apps sends email via Office 365 connector
4. User receives professional request email

#### D. Pending Record in Cosmos DB
```python
pending_record = {
    "temp_request_id": temp_request_id,
    "status": "PENDING_LOAN_ID",
    "source_email": from_address,
    "original_subject": original_subject,
    "received_at": datetime.utcnow().isoformat(),
    "extracted_data": extracted_data,
    "raw_email_content": raw_email_content[:1000],
    "awaiting_response": True,
    "request_sent_at": datetime.utcnow().isoformat()
}

await self.cosmos_plugin.create_rate_lock(
    loan_application_id=temp_request_id,  # Use temp ID as partition key
    borrower_name=borrower_name,
    borrower_email=from_address,
    # ... other fields
    additional_data=json.dumps(pending_record)
)
```

**Cosmos DB Record Structure:**
```json
{
  "id": "rate_lock_TMP-PENDING-20251003-a7f3b2c1_20251003_153045",
  "rate_lock_request_id": "RLR-TMP-PENDING-20251003-a7f3b2c1-20251003-b8c9d0e1",
  "loanApplicationId": "TMP-PENDING-20251003-a7f3b2c1",
  "temp_request_id": "TMP-PENDING-20251003-a7f3b2c1",
  "status": "PENDING_LOAN_ID",
  "source_email": "john.smith@example.com",
  "borrower_name": "John Smith",
  "property_address": "123 Main St",
  "awaiting_response": true,
  "request_sent_at": "2025-10-03T15:30:45.123456",
  "extracted_data": { ... }
}
```

#### E. Audit Trail
```python
await self._send_audit_message(
    action="LOAN_ID_REQUESTED",
    loan_application_id=temp_request_id,
    audit_data={
        "from_address": from_address,
        "reason": "Missing loan_application_id in email",
        "temp_request_id": temp_request_id,
        "borrower_name": borrower_name
    }
)
```

### 4. Updated LLM Response Handling

**Normalized Null Handling:**
```python
# Check if loan_application_id is missing (null is acceptable - we'll request it from user)
loan_id = parsed_data.get('loan_application_id')
if loan_id is None or loan_id in ["", "null"]:
    logger.info(f"{self.agent_name}: ⚠️ LLM returned null for loan_application_id - will request from user")
    parsed_data['loan_application_id'] = None  # Normalize to None
else:
    logger.info(f"{self.agent_name}: ✅ LLM successfully extracted loan ID: {loan_id}")
```

## Workflow Examples

### Example 1: Email Without Loan ID

**Incoming Email:**
```
From: john.smith@example.com
Subject: Rate Lock Request

Hi, I need to lock in my rate for my property at 123 Main Street.
Can you help me with a 30-day lock?

Thanks,
John Smith
```

**System Processing:**
1. ✅ LLM extracts: borrower_name="John Smith", property_address="123 Main Street"
2. ⚠️ LLM returns: loan_application_id=null (not found)
3. 🎯 System detects missing loan ID
4. 📧 System sends request email to john.smith@example.com
5. 💾 System creates pending record: TMP-PENDING-20251003-a7f3b2c1
6. 📊 System logs audit event: LOAN_ID_REQUESTED

**Email Sent to User:**
```
Subject: Action Required: Missing Loan Application ID

Dear John Smith,

Thank you for submitting your rate lock request. We have received your email 
regarding 123 Main Street.

However, we were unable to identify your Loan Application ID from your message...

Temporary Tracking Reference: TMP-PENDING-20251003-a7f3b2c1
```

### Example 2: Email With Valid Loan ID

**Incoming Email:**
```
From: jane.doe@example.com
Subject: Rate Lock for LA-456789

Please lock my rate for loan application LA-456789.
Property: 456 Oak Avenue
30 day lock please.

Jane Doe
```

**System Processing:**
1. ✅ LLM extracts: loan_application_id="LA-456789"
2. ✅ System validates ID is present and not placeholder
3. ✅ System creates rate lock record with ID: LA-456789
4. ✅ System proceeds to workflow (sends to Loan Context Agent)
5. ✅ System sends acknowledgment email

**No intervention needed - normal workflow continues!**

### Example 3: LLM Generates Placeholder (Legacy Behavior)

**If LLM Still Generates:**
```json
{
  "loan_application_id": "APP-XXXXXX"
}
```

**System Processing:**
1. ⚠️ System detects placeholder pattern (starts with "APP-" and contains "X"s)
2. 📧 System treats as missing and requests loan ID from user
3. 💾 System creates pending record with temp ID

## Architecture Integration

### Service Bus Queue Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Missing Loan ID Flow                          │
└─────────────────────────────────────────────────────────────────┘

1. Email arrives → inbound-email-queue

2. Email Intake Agent processes:
   ├─ LLM extracts data
   ├─ loan_application_id = null
   └─ Triggers _request_loan_id_from_user()

3. Email request sent → outbound_confirmations queue

4. Logic Apps sends email via Office 365

5. User receives professional request email

6. Pending record stored in Cosmos DB:
   └─ status: "PENDING_LOAN_ID"
   └─ temp_request_id: "TMP-PENDING-20251003-a7f3"
   └─ awaiting_response: true
```

### Cosmos DB State Management

```
┌──────────────────────────────────────────────────────────────┐
│              Pending Request Lifecycle                        │
└──────────────────────────────────────────────────────────────┘

State 1: PENDING_LOAN_ID
├─ User hasn't responded yet
├─ System waiting for loan ID
└─ Tracked by temp_request_id

State 2: (Future Enhancement - User Responds)
├─ User replies with loan ID
├─ System updates record
├─ Changes loanApplicationId to real ID
└─ Proceeds with normal workflow
```

## Benefits

### 🎯 For Users
- ✅ Clear, professional communication
- ✅ Specific guidance on what's needed
- ✅ Temporary tracking reference for follow-up
- ✅ No silent failures - always get a response

### 🎯 For Support Teams
- ✅ Pending requests tracked in Cosmos DB
- ✅ Can query by temp_request_id
- ✅ Audit trail shows when requests were sent
- ✅ Status field shows "PENDING_LOAN_ID"

### 🎯 For System
- ✅ No data loss - all requests tracked
- ✅ Professional error handling
- ✅ Consistent with existing email queue architecture
- ✅ Leverages existing outbound email infrastructure

## Testing Scenarios

### Test Case 1: Email with No Loan ID
```python
# Send email without any loan ID reference
email_content = """
From: test@example.com
Subject: Rate Lock Request

I need to lock my rate for my new home at 789 Pine Street.
Can you help?

Thanks
"""

# Expected: 
# - Email sent to test@example.com requesting loan ID
# - Pending record created with status="PENDING_LOAN_ID"
# - Audit log entry: LOAN_ID_REQUESTED
```

### Test Case 2: Email with Placeholder ID
```python
# LLM generates placeholder (shouldn't happen with new prompt, but defensive)
extracted_data = {
    "loan_application_id": "APP-XXXXXX",
    "borrower_name": "Test User"
}

# Expected:
# - System detects placeholder pattern
# - Treats as missing loan ID
# - Sends request email
```

### Test Case 3: Email with Valid Loan ID
```python
email_content = """
From: test@example.com
Subject: Lock Request - LA-12345

Please lock rate for loan LA-12345.
"""

# Expected:
# - Normal processing continues
# - No loan ID request sent
# - Proceeds to Loan Context Agent
```

## Future Enhancements

### 1. User Response Processing
Add logic to handle when user replies with loan ID:
```python
async def _process_loan_id_response(self, temp_request_id: str, real_loan_id: str):
    """
    Update pending record when user provides loan ID.
    """
    # 1. Retrieve pending record by temp_request_id
    # 2. Validate real_loan_id
    # 3. Update loanApplicationId partition key (requires new record)
    # 4. Update status to "PROCESSING"
    # 5. Resume workflow with real loan ID
```

### 2. Auto-Reminder System
Send follow-up if no response after 24 hours:
```python
# Query Cosmos DB for records:
# WHERE status = "PENDING_LOAN_ID"
# AND request_sent_at < (now - 24 hours)
# AND reminder_sent = false

# Send gentle reminder email
```

### 3. Dashboard Integration
Display pending loan ID requests in monitoring dashboard:
```
┌─────────────────────────────────────────┐
│      Pending Loan ID Requests           │
├─────────────────────────────────────────┤
│ TMP-001  │ john@ex.com  │ 2h ago      │
│ TMP-002  │ jane@ex.com  │ 5h ago      │
│ TMP-003  │ bob@ex.com   │ 1d ago ⚠️   │
└─────────────────────────────────────────┘
```

### 4. Loan Officer Notification
Escalate to loan officer if no response after 48 hours:
```python
if (now - request_sent_at) > timedelta(hours=48):
    # Send alert to loan officer
    # Include: borrower info, property address, temp_request_id
```

## Files Modified

1. **MODIFIED:** `agents/email_intake_agent.py`
   - Updated LLM extraction prompt (don't generate placeholders)
   - Enhanced validation logic (detect missing/placeholder IDs)
   - **NEW METHOD:** `_request_loan_id_from_user()` - Send request email
   - Updated LLM response handling (normalize null values)

2. **USED:** `utils/id_generator.py`
   - Leveraged existing `generate_rate_lock_request_id()` for temp IDs
   - Prefix: "TMP" for temporary tracking references

3. **USED:** `outbound_confirmations` queue
   - Existing email infrastructure (Logic Apps → Office 365)
   - No infrastructure changes required

## Configuration Requirements

### Environment Variables (Already Configured)
```properties
AZURE_SERVICEBUS_NAMESPACE="your-namespace.servicebus.windows.net"
AZURE_SERVICEBUS_QUEUE_OUTBOUND_CONFIRMATIONS="outbound-email-queue"
```

### Queue Permissions (Already Configured)
- Email Intake Agent has "Send" permission on `outbound_confirmations` queue
- Logic Apps has "Receive" permission on `outbound-email-queue`

## Monitoring & Observability

### Log Messages
```
⚠️ Missing loan_application_id - requesting from user
📧 Requesting loan_application_id from user at john@example.com
✅ Created pending record with temp ID: TMP-PENDING-20251003-a7f3
📨 Loan ID request email sent to john@example.com (Tracking: TMP-PENDING-20251003-a7f3)
```

### Audit Events
```json
{
  "action": "LOAN_ID_REQUESTED",
  "agent_name": "email_intake_agent",
  "loan_application_id": "TMP-PENDING-20251003-a7f3b2c1",
  "audit_data": {
    "from_address": "john.smith@example.com",
    "reason": "Missing loan_application_id in email",
    "temp_request_id": "TMP-PENDING-20251003-a7f3b2c1",
    "borrower_name": "John Smith"
  }
}
```

### Cosmos DB Queries
```sql
-- Find all pending loan ID requests
SELECT * FROM c 
WHERE c.status = "PENDING_LOAN_ID"

-- Find requests older than 24 hours
SELECT * FROM c 
WHERE c.status = "PENDING_LOAN_ID"
AND c.request_sent_at < "2025-10-02T15:30:00Z"

-- Find by temp tracking ID
SELECT * FROM c 
WHERE c.temp_request_id = "TMP-PENDING-20251003-a7f3b2c1"
```

## Implementation Date
October 3, 2025

## Related Documentation
- `RATE_LOCK_REQUEST_ID_IMPLEMENTATION.md` - Rate lock request ID generation
- `README.md` - System architecture and email queue flow
- `ROUTING_METADATA_IMPLEMENTATION.md` - Message routing with application_properties
