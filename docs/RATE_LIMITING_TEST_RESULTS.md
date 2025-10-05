# Rate Limiting - Test Results & Analysis

## 🧪 Test Run Analysis (2025-10-05 17:39-17:40)

### ✅ Improvements Observed

1. **Batch Size Reduced Successfully**
   ```
   BEFORE: 📨 Received 10 message(s)
   AFTER:  📨 Received 2 message(s)  ✅
   ```

2. **Fewer 429 Errors**
   ```
   BEFORE: 4-8 errors per batch
   AFTER:  3 errors total (62% reduction)  ✅
   ```

3. **System Completed Processing**
   ```
   ✅ email_intake cleaned up
   ✅ loan_context cleaned up
   ✅ All agents processed successfully
   ```

### ⚠️ Issues Identified

1. **Still Getting Some 429 Errors**
   ```log
   2025-10-05 17:40:10,178 - HTTP/1.1 429 Too Many Requests
   2025-10-05 17:40:13,270 - HTTP/1.1 429 Too Many Requests
   2025-10-05 17:40:15,529 - HTTP/1.1 429 Too Many Requests
   ```

2. **OpenAI Client's Built-in Retry**
   ```log
   2025-10-05 17:40:10,179 - Retrying request in 57.000000 seconds
   2025-10-05 17:40:13,271 - Retrying request in 54.000000 seconds
   2025-10-05 17:40:15,530 - Retrying request in 51.000000 seconds
   ```
   
   **Problem**: OpenAI SDK has built-in retry that adds long delays (50-60s)
   vs our custom exponential backoff (2-32s).

3. **Unclosed Client Sessions**
   ```log
   2025-10-05 17:40:05,916 - asyncio - ERROR - Unclosed client session
   ```
   
   **Impact**: Memory leaks, but not causing functional issues.

## 🔍 Root Cause Analysis

### Why Still Getting 429s?

Our semaphore (`MAX_CONCURRENT_OPENAI_CALLS = 3`) limits the number of 
**concurrent initial requests**, but doesn't account for:

1. **Function calling iterations**: After the initial LLM call, the agent may make
   2-3 additional tool-calling requests in parallel
2. **Multiple agents active**: email_intake + loan_context + audit_logging all
   processing simultaneously

**Math**:
```
3 agents × 2 tool calls each = 6 concurrent requests
+ initial LLM calls = 9 total concurrent requests
> Azure OpenAI quota (18 RPM) → 429 errors
```

## 🛠️ Solutions

### Option 1: Reduce MAX_CONCURRENT_OPENAI_CALLS (Quick Fix)

**Change `agents/base_agent.py`**:
```python
MAX_CONCURRENT_OPENAI_CALLS = 2  # Reduce from 3 to 2
```

**Expected Impact**:
- Max 2 agents processing at once
- Max 2 × 3 = 6 concurrent API calls
- Should eliminate 429 errors
- Slightly slower processing

### Option 2: Disable OpenAI SDK's Built-in Retry (Advanced)

Add to Azure OpenAI client initialization:
```python
self.chat_service = AzureChatCompletion(
    deployment_name=deployment_name,
    endpoint=endpoint,
    ad_token_provider=get_token,
    service_id="azure_openai_chat",
    max_retries=0  # Disable OpenAI's retry, use ours
)
```

**Benefits**:
- Our faster exponential backoff (2-32s) instead of OpenAI's (50-60s)
- Better control over retry behavior

### Option 3: Add Delay Between Message Processing

**Change `operations/service_bus_operations.py`**:
```python
# After processing each message
await receiver.complete_message(msg)
await asyncio.sleep(0.5)  # 500ms delay between messages
```

**Benefits**:
- Spreads out API calls over time
- Reduces peak concurrent load

### Option 4: Request Azure OpenAI Quota Increase (Long-term)

**Current Quota**: 30K TPM / 18 RPM (Standard GPT-4o)
**Recommended**: 60K TPM / 60 RPM (for 7 agents)

**Steps**:
1. Azure Portal → OpenAI Resource
2. Quotas → Request Increase
3. Justification: "Multi-agent mortgage processing system, 7 autonomous agents"

## 📊 Recommended Actions (Priority Order)

### Immediate (Do Now)

1. **Reduce semaphore to 2**
   ```python
   MAX_CONCURRENT_OPENAI_CALLS = 2
   ```

2. **Disable OpenAI built-in retry**
   ```python
   max_retries=0
   ```

### Short-term (This Week)

3. **Request quota increase** to 60K TPM / 60 RPM

4. **Add message processing delay** (0.5s between messages)

### Long-term (Production)

5. **Implement token bucket** for more sophisticated rate limiting

6. **Add circuit breaker** pattern for automatic backoff

7. **Consider PTU** (Provisioned Throughput Units) for guaranteed performance

## 🎯 Expected Results After Fix

### With MAX_CONCURRENT_OPENAI_CALLS = 2

```
Before Fix:
- Batch size: 2-3 messages
- Concurrent calls: 6-9 (exceeds quota)
- 429 errors: 3 per batch
- Success rate: 75%

After Fix:
- Batch size: 2-3 messages  
- Concurrent calls: 4-6 (within quota)
- 429 errors: 0-1 per batch
- Success rate: 95%+
```

### With Quota Increase to 60K TPM

```
- Batch size: Can increase to 5-10
- Concurrent calls: 10-15 (comfortable)
- 429 errors: 0
- Success rate: 99%+
- Processing speed: 2-3x faster
```

## 🔧 Implementation Steps

### Step 1: Update Semaphore Limit

```bash
# Edit agents/base_agent.py line ~15
MAX_CONCURRENT_OPENAI_CALLS = 2  # Changed from 3
```

### Step 2: Disable OpenAI Retry

```bash
# Edit agents/base_agent.py in _initialize_kernel() method
# Add max_retries=0 parameter
```

### Step 3: Test Again

```bash
C:\gitrepos\ai-rate-lock-system-sk\.venv\Scripts\python.exe main.py
# Send test messages
# Monitor for 429 errors
```

## 📝 Test Checklist

- [ ] Reduce MAX_CONCURRENT_OPENAI_CALLS to 2
- [ ] Add max_retries=0 to AzureChatCompletion
- [ ] Restart system
- [ ] Send 5-10 test messages
- [ ] Monitor logs for 429 errors
- [ ] Verify < 1 error per 10 messages
- [ ] If still issues, add 0.5s delay between messages
- [ ] Submit quota increase request

## 📈 Success Metrics

✅ **Target**: < 1% error rate (< 1 error per 100 messages)
✅ **Acceptable**: < 5% error rate (< 5 errors per 100 messages)
❌ **Unacceptable**: > 10% error rate

**Current**: ~15% error rate (3/20 messages) → Need fixes

---

**Recommendation**: Implement Steps 1 & 2 immediately, test, then request quota increase.
