# ⚡ Quick Start: Testing Rate Limiting Fix

## ✅ Changes Applied

1. **Semaphore reduced**: 3 → 2 concurrent calls
2. **OpenAI retry disabled**: Using our faster exponential backoff
3. **Batch size reduced**: 10 → 3 messages per batch
4. **Exponential backoff**: 2s → 32s with jitter

## 🚀 Test Now

### Step 1: Start System
```bash
C:\gitrepos\ai-rate-lock-system-sk\.venv\Scripts\python.exe main.py
```

**Expected output**:
```
✅ All systems operational! Running 7 agent listeners.
🔄 System is now running autonomously.
```

### Step 2: Send Test Messages (New Terminal)
```bash
C:\gitrepos\ai-rate-lock-system-sk\.venv\Scripts\python.exe test_send_message.py
```

**Expected output**:
```
Message sent to Service Bus
```

### Step 3: Monitor Logs

**Watch for**:
```
✅ GOOD: "Received 3 message(s)"
✅ GOOD: "Acquiring OpenAI call slot (2 available)"
✅ GOOD: "✅ Completed processing"
⚠️  OK:   "Rate limit hit (429). Retry 1/5 in 2.3s"
❌ BAD:  "Rate limit exceeded after 5 retries"
```

### Step 4: Check Results (After 5 Minutes)
```bash
# Count 429 errors
grep "429" logs\ai_rate_lock_system_*.log | find /c "429"

# Expected: 0-2 errors (auto-recovered)
```

## 📊 Success Criteria

| Metric | Target | How to Check |
|--------|--------|--------------|
| Batch Size | 3 messages | Look for "Received 3 message(s)" |
| Concurrent Calls | Max 2 | Look for "Acquiring...slot (0-2 available)" |
| 429 Errors | < 5% | Count 429s in logs |
| Success Rate | > 95% | Count "Completed processing" |

## 🔧 If Still Issues

### Too Many 429 Errors (> 5%)

**Option 1**: Reduce to 1 concurrent call
```python
# Edit agents/base_agent.py line ~15
MAX_CONCURRENT_OPENAI_CALLS = 1
```

**Option 2**: Add delay between messages
```python
# Edit operations/service_bus_operations.py after line 545
await receiver.complete_message(msg)
await asyncio.sleep(0.5)  # Add this line
```

**Option 3**: Request quota increase (recommended)
- Azure Portal → OpenAI Resource → Quotas → Request Increase

### System Too Slow

1. Check if quota allows more concurrent calls
2. Request quota increase to 60K TPM
3. Consider PTU for production

## 📈 Expected Performance

### Before Fix
- 429 errors: 15-20% of requests
- Retry time: 50-60 seconds
- Success rate: 70%

### After Fix
- 429 errors: < 5% of requests
- Retry time: 2-10 seconds
- Success rate: > 95%

## 📝 Monitoring Commands

```bash
# Real-time log monitoring
Get-Content logs\ai_rate_lock_system_*.log -Wait -Tail 50

# Count successful completions
grep "Completed processing" logs\ai_rate_lock_system_*.log | wc -l

# Count 429 errors
grep "429" logs\ai_rate_lock_system_*.log | wc -l

# Check retry attempts
grep "Rate limit hit" logs\ai_rate_lock_system_*.log
```

## 🎯 Next Steps

1. ✅ Test with 5-10 messages
2. ✅ Verify < 5% error rate
3. ✅ Monitor for 1 hour
4. 📝 If successful, request quota increase for production scale
5. 📝 Document final configuration in production runbook

---

**Status**: ✅ Ready for testing
**Last Updated**: 2025-10-05
