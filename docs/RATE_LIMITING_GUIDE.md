# Rate Limiting Guide - Azure OpenAI 429 Errors

## Problem
When processing multiple messages simultaneously, the system can exceed Azure OpenAI rate limits, resulting in **HTTP 429 "Too Many Requests"** errors.

## Root Cause
- **10 messages** arrive simultaneously from Service Bus queue
- **7 agents** all initialize and call Azure OpenAI at the same time
- Each agent may make **multiple LLM calls** (initial + function calling iterations)
- Result: **20-30 concurrent OpenAI requests** → quota exhaustion

## Solution Implemented

### 1. **Global Semaphore Rate Limiting**
```python
# In base_agent.py
MAX_CONCURRENT_OPENAI_CALLS = 3  # Only 3 simultaneous OpenAI calls allowed
_openai_semaphore = asyncio.Semaphore(MAX_CONCURRENT_OPENAI_CALLS)
```

**How it works:**
- Agents wait in a queue if 3 calls are already in progress
- Prevents overwhelming Azure OpenAI endpoint
- Automatically released when call completes

### 2. **Exponential Backoff Retry**
```python
# Retry logic in _call_llm()
- Retry 1: Wait 2 seconds (+ jitter)
- Retry 2: Wait 4 seconds (+ jitter)
- Retry 3: Wait 8 seconds (+ jitter)
- Retry 4: Wait 16 seconds (+ jitter)
- Retry 5: Wait 32 seconds (+ jitter)
```

**Benefits:**
- Automatically recovers from temporary rate limit spikes
- Prevents immediate retry storms
- Jitter prevents "thundering herd" problem

### 3. **Jitter (Randomization)**
```python
jitter = delay * random.uniform(0, 0.25)  # Add 0-25% randomness
total_delay = delay + jitter
```

**Why needed:**
- Prevents all agents from retrying at the exact same time
- Spreads out retry load across time window

## Configuration

### Adjusting Concurrent Call Limit

Edit `agents/base_agent.py`:
```python
MAX_CONCURRENT_OPENAI_CALLS = 3  # Default: 3 concurrent calls
```

**Recommendations based on Azure OpenAI tier:**

| Tier | TPM (Tokens/Min) | RPM (Requests/Min) | Recommended Setting |
|------|------------------|-------------------|---------------------|
| Standard (GPT-4o) | 30,000 | 18 | 2-3 |
| Standard (GPT-4) | 10,000 | 6 | 1-2 |
| Standard (GPT-3.5) | 240,000 | 144 | 10-15 |
| Premium (PTU) | Unlimited | High | 20-50 |

**Current deployment:** `gpt-4o` (Standard tier)
- Default quota: 30K TPM, 18 RPM
- Recommended: **MAX_CONCURRENT_OPENAI_CALLS = 2-3**

### Adjusting Retry Behavior

Edit `base_agent._call_llm()`:
```python
async def _call_llm(self, system_prompt: str, user_message: str, max_retries: int = 5):
    base_delay = 1  # Starting delay in seconds
    # Modify these values as needed
```

## Monitoring Rate Limits

### Log Messages to Watch
```
✅ Normal operation:
email_intake_agent: Acquiring OpenAI call slot (2 available)

⚠️  Rate limit hit:
email_intake_agent: ⚠️  Rate limit hit (429). Retry 1/5 in 2.3s

❌ Rate limit exhausted:
email_intake_agent: ❌ Rate limit exceeded after 5 retries
```

### Check Azure OpenAI Metrics
1. Azure Portal → Your OpenAI resource
2. Metrics → "Token Based Model Utilization"
3. Look for spikes near 100%

## Optimization Strategies

### Short-term (Immediate)
1. ✅ **DONE**: Add semaphore rate limiting (reduces concurrent calls)
2. ✅ **DONE**: Implement exponential backoff retry
3. ✅ **DONE**: Add jitter to prevent retry storms

### Medium-term (Recommended)
1. **Batch processing**: Process messages in smaller batches instead of all at once
2. **Message throttling**: Add delays between Service Bus receives
3. **Priority queues**: Process critical messages first, defer low-priority

### Long-term (Scalability)
1. **Increase Azure OpenAI quota**: Request quota increase from Azure support
2. **Multiple deployments**: Use multiple OpenAI deployments with load balancing
3. **Provisioned throughput**: Upgrade to PTU (Provisioned Throughput Units)
4. **Caching**: Cache common LLM responses to reduce API calls

## Testing Rate Limiting

### Test 1: Verify Semaphore Working
```bash
# Send 10 messages quickly
python test_send_message.py

# Check logs for:
# "Acquiring OpenAI call slot (X available)"
# Should see only 3 concurrent calls
```

### Test 2: Verify Retry Logic
```bash
# Temporarily set MAX_CONCURRENT_OPENAI_CALLS = 1
# Send 5 messages
# Should see retry messages in logs
```

### Test 3: Monitor Success Rate
```bash
# After changes, monitor for 1 hour
# Count 429 errors in logs
grep "429" logs/ai_rate_lock_system_*.log | wc -l

# Should be 0 or very low
```

## Troubleshooting

### Issue: Still getting 429 errors
**Solutions:**
1. Reduce `MAX_CONCURRENT_OPENAI_CALLS` to 2 or 1
2. Add delay between Service Bus message processing
3. Request quota increase from Azure support

### Issue: System too slow
**Solutions:**
1. Increase `MAX_CONCURRENT_OPENAI_CALLS` (if you have higher quota)
2. Upgrade to PTU (Provisioned Throughput)
3. Add more OpenAI deployments

### Issue: Retries taking too long
**Solutions:**
1. Reduce `max_retries` from 5 to 3
2. Reduce `base_delay` from 1 to 0.5
3. Reduce max_tokens in execution_settings

## Azure OpenAI Quota Management

### Check Current Quota
```bash
# Azure CLI
az cognitiveservices account list-usage \
  --name <your-openai-name> \
  --resource-group <resource-group>
```

### Request Quota Increase
1. Azure Portal → OpenAI resource
2. "Quotas" → Select deployment
3. "Request Quota Increase"
4. Justification: "Multi-agent AI system with 7 concurrent agents processing loan applications"

### Recommended Quotas for Production
- **TPM (Tokens/Minute):** 100,000+ (for 7 agents)
- **RPM (Requests/Minute):** 60+ (for 7 agents)
- **Deployment:** Consider PTU for guaranteed throughput

## Performance Metrics

### Before Rate Limiting
- Concurrent calls: 10-30 simultaneous
- 429 errors: 4-8 per batch
- Success rate: 60-70%

### After Rate Limiting (Expected)
- Concurrent calls: Max 3
- 429 errors: 0-1 per batch (handled by retry)
- Success rate: 99%+
- Processing time: +10-20% (due to queuing)

## Summary

✅ **Implemented:**
- Global semaphore (max 3 concurrent calls)
- Exponential backoff retry (up to 5 attempts)
- Jitter for retry distribution

📊 **Expected Results:**
- Eliminate 429 errors
- Slight increase in processing time
- 99%+ success rate

🔧 **Next Steps:**
1. Test with current settings
2. Monitor logs for 429 errors
3. Adjust `MAX_CONCURRENT_OPENAI_CALLS` if needed
4. Consider quota increase for production scale
