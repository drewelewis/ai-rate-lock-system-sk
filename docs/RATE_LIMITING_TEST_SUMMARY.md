# Rate Limiting Test Summary

## Changes Implemented

### 1. Base Agent Rate Limiting (`agents/base_agent.py`)
✅ **Global Semaphore**: Limits concurrent OpenAI calls to 3
✅ **Exponential Backoff**: Automatic retry with delays: 2s, 4s, 8s, 16s, 32s
✅ **Jitter**: Random 0-25% added to prevent thundering herd
✅ **Max Retries**: Up to 5 retry attempts for 429 errors

### 2. Service Bus Batch Size Reduction (`operations/service_bus_operations.py`)
✅ **Topic Subscription**: Reduced from 10 to 3 messages per batch
✅ **Queue**: Reduced from 10 to 3 messages per batch

## Expected Behavior

### Before Changes
```
📨 Received 10 message(s) from queue inbound-email-queue
[All 10 agents call OpenAI simultaneously]
❌ HTTP 429 errors occur
⚠️  Retrying after 54 seconds (OpenAI's default retry)
```

### After Changes
```
📨 Received 3 message(s) from queue inbound-email-queue
🔒 Agent 1: Acquiring OpenAI call slot (3 available)
🔒 Agent 2: Acquiring OpenAI call slot (2 available)
🔒 Agent 3: Acquiring OpenAI call slot (1 available)
⏳ Agent 4: Waiting for slot... (queued)
✅ All requests processed without 429 errors
```

## Testing Instructions

### Test 1: Verify Rate Limiting
```bash
# Start the system (already running)
# Watch for rate limiting logs

# Expected logs:
# "Acquiring OpenAI call slot (X available)"
# Should see max 3 concurrent calls
```

### Test 2: Send Test Messages
```bash
# In a new terminal:
C:\gitrepos\ai-rate-lock-system-sk\.venv\Scripts\python.exe test_send_message.py

# Watch main.py logs for:
# 1. Batch size: "Received 3 message(s)"
# 2. Semaphore: "Acquiring OpenAI call slot"
# 3. NO 429 errors
```

### Test 3: Monitor for 429 Errors
```bash
# After running for 5 minutes, check for 429 errors:
grep "429" logs\ai_rate_lock_system_*.log

# Expected: Zero or very few 429 errors
# If still seeing 429s: Reduce MAX_CONCURRENT_OPENAI_CALLS to 2
```

## Configuration Tuning

### If Still Getting 429 Errors
Edit `agents/base_agent.py`:
```python
MAX_CONCURRENT_OPENAI_CALLS = 2  # Reduce from 3 to 2
```

### If System Too Slow
1. Check Azure OpenAI quota usage
2. Request quota increase
3. Consider upgrading to PTU (Provisioned Throughput Units)

### Recommended Settings by Quota

| Azure OpenAI Quota | Recommended Setting |
|-------------------|---------------------|
| 30K TPM (Standard GPT-4o) | 2-3 concurrent calls |
| 60K TPM (Increased) | 5-6 concurrent calls |
| 100K TPM (High) | 10-15 concurrent calls |
| PTU (Provisioned) | 20-50 concurrent calls |

## Monitoring Commands

### Real-time Log Monitoring
```bash
# Watch logs in real-time
tail -f logs\ai_rate_lock_system_*.log

# Or on Windows:
Get-Content logs\ai_rate_lock_system_*.log -Wait -Tail 50
```

### Count 429 Errors
```bash
# Check for rate limit errors
grep "429" logs\ai_rate_lock_system_*.log | wc -l

# Check retry attempts
grep "Rate limit hit" logs\ai_rate_lock_system_*.log
```

### Success Rate Calculation
```bash
# Count successful completions
grep "Completed processing" logs\ai_rate_lock_system_*.log | wc -l

# Count failures
grep "Failed to process" logs\ai_rate_lock_system_*.log | wc -l
```

## Files Modified

1. **agents/base_agent.py**
   - Added global semaphore for rate limiting
   - Enhanced `_call_llm()` with retry logic
   - Added exponential backoff + jitter

2. **operations/service_bus_operations.py**
   - Reduced `max_message_count` from 10 → 3 (line 527)
   - Reduced `max_message_count` from 10 → 3 (line 618)

3. **RATE_LIMITING_GUIDE.md** (NEW)
   - Comprehensive documentation
   - Troubleshooting guide
   - Configuration recommendations

4. **RATE_LIMITING_TEST_SUMMARY.md** (THIS FILE)
   - Quick reference for testing
   - Expected behaviors
   - Monitoring commands

## Next Steps

1. ✅ **System Running**: Monitoring for 429 errors
2. ⏳ **Send Test Message**: Run `test_send_message.py`
3. ⏳ **Monitor Logs**: Check for rate limiting behavior
4. ⏳ **Validate**: Confirm zero or minimal 429 errors
5. ⏳ **Tune**: Adjust `MAX_CONCURRENT_OPENAI_CALLS` if needed

## Success Criteria

✅ **Zero or minimal 429 errors** in logs
✅ **Messages processed in batches of 3**
✅ **Semaphore limiting visible** in debug logs
✅ **Exponential backoff working** if any 429s occur
✅ **All messages eventually processed** successfully

## System Status
- 🟢 **RUNNING** - 7 agent listeners active
- 🔧 **RATE LIMITING ENABLED** - Max 3 concurrent calls
- 🔍 **MONITORING** - Waiting for test messages
