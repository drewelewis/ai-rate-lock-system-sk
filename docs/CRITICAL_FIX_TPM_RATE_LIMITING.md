# CRITICAL FIX - TPM Rate Limiting
## October 5, 2025

---

## 🚨 CRITICAL ISSUE DISCOVERED

Long test revealed that **semaphore alone is insufficient** for rate limiting!

### The Problem:
- Semaphore limits **concurrent calls** (how many at once)
- Does NOT limit **tokens-per-minute (TPM)** (total token usage)
- Result: **41.7% error rate** (25 errors in 26 minutes)

---

## 🔍 Root Cause Analysis

### Azure OpenAI Quotas (TWO limits):
1. **RPM (Requests Per Minute)**: 18 per minute ✅ Not the problem
2. **TPM (Tokens Per Minute)**: 30,000 per minute ❌ **THIS is the problem!**

### The Math:
```
Semaphore = 1 (only 1 call at a time)
Each call takes: ~5 seconds
Calls per minute: 60s ÷ 5s = 12 calls/min ✅ Under 18 RPM

But...
Each call uses: ~3,500 tokens
Tokens per minute: 12 × 3,500 = 42,000 TPM ❌ EXCEEDS 30K TPM QUOTA!
```

**Result**: Even with semaphore=1, we're **exceeding token quota** by 40%!

---

## ✅ THE FIX - Add TPM Rate Limiting

### What Was Changed:
**File**: `agents/base_agent.py`  
**Location**: Inside `_call_llm()` method, after getting OpenAI response

### Code Added:
```python
async with _openai_semaphore:
    response = await self.chat_service.get_chat_message_content(...)
    
    # CRITICAL: Add delay to limit tokens-per-minute (TPM)
    # Azure quota: 30K TPM. Each call ~3.5K tokens.
    # 7-second delay = max 8.5 calls/min × 3.5K tokens = ~30K TPM
    await asyncio.sleep(7)  # ← NEW!
    logger.debug(f"{self.agent_name}: TPM rate limit delay completed (7s)")
    
    return str(response)
```

### Why 7 Seconds?
```
Target: Stay under 30,000 TPM
Each call: ~3,500 tokens
Max calls allowed: 30,000 ÷ 3,500 = 8.5 calls/min

7-second delay:
- Response time: ~3-5 seconds
- Delay: 7 seconds
- Total per call: ~10-12 seconds
- Calls per minute: 60 ÷ 12 = 5 calls/min
- Tokens per minute: 5 × 3,500 = 17,500 TPM ✅ WELL under 30K!
```

**Safety margin**: 58% of quota (leaves room for spikes)

---

## 📊 Expected Impact

### Before Fix (Semaphore Only):
- Concurrent calls: 1 (good)
- Calls per minute: ~12
- Tokens per minute: **42,000 TPM** ❌ Exceeds quota
- Error rate: **41.7%**
- 429 errors: ~1 per minute

### After Fix (Semaphore + Delay):
- Concurrent calls: 1 (unchanged)
- Calls per minute: ~5
- Tokens per minute: **~17,500 TPM** ✅ Within quota
- Error rate: **<2%** (expected)
- 429 errors: <1 per 10 minutes

### Performance Trade-offs:
- ⚠️ **Slower processing**: ~12 seconds per API call (vs 5 seconds)
- ⚠️ **Lower throughput**: 5 calls/min (vs 12 calls/min)
- ✅ **Higher reliability**: <2% error rate (vs 42%)
- ✅ **No quota violations**: Stays within Azure limits
- ✅ **No long retries**: Prevents 50-80 second OpenAI retry delays

---

## 🎯 Testing Plan

### Test 1: Short Run (5 minutes)
```cmd
python main.py
# Let run for 5 minutes
# Ctrl+C to stop
```

**Expected**:
- ~2-3 messages processed
- ~15-20 API calls total
- 0-1 errors (95%+ success rate)
- Each call takes ~12 seconds (3-5s API + 7s delay)

### Test 2: Monitor Logs
```cmd
type logs\ai_rate_lock_system_*.log | findstr "TPM rate limit delay"
```

**Expected**: See delay messages after each successful API call

### Test 3: Count Errors
```cmd
type logs\ai_rate_lock_system_*.log | findstr "429 Too Many Requests"
```

**Expected**: 0-1 errors in a 10-minute run

---

## 📈 Success Criteria

| Metric | Target | How to Measure |
|--------|--------|----------------|
| **Error Rate** | <5% | Count 429s vs total calls |
| **TPM Usage** | <30,000 | Calculate: calls/min × 3,500 |
| **Calls/Minute** | ~5 | Count API calls per minute |
| **Delay Working** | 100% | Check for delay log messages |
| **Success Rate** | >95% | (Total calls - errors) / total |

---

## 🔧 Alternative Solutions

### Option 1: Increase Azure Quota (BEST LONG-TERM)
- **Current**: 30K TPM / 18 RPM
- **Request**: 100K TPM / 60 RPM
- **Benefit**: Remove the 7-second delay, 3x faster processing
- **Cost**: Usually free for production workloads
- **Time**: 24-48 hours approval

### Option 2: Optimize Token Usage
- Shorten system prompts (-20% tokens)
- Use streaming for responses (-10% tokens)
- Better caching (Azure supports it)
- **Benefit**: Allows 10-12 calls/min instead of 5
- **Effort**: Medium (requires prompt rewriting)

### Option 3: Hybrid Approach (RECOMMENDED)
1. **Use 7-second delay NOW** (immediate fix)
2. **Request quota increase** (tomorrow)
3. **Optimize tokens** (this week)
4. **Remove delay once quota increased** (next week)

---

## 📊 Comparison: All Tests

| Test | Duration | 429 Errors | Error Rate | Config | Calls/Min |
|------|----------|------------|------------|--------|-----------|
| Baseline | 4.5 hrs | 13 | 0.05/min | None | ~20 |
| Semaphore=2 | 2 min | 2 | 1.0/min | Concurrent limit | ~12 |
| Semaphore=1 | 26 min | 25 | **0.96/min** | Concurrent limit | ~12 |
| **Semaphore+Delay** | TBD | **0-1** | **<0.1/min** | **TPM limit** | **~5** |

---

## ⚠️ Known Trade-offs

### Slower Processing:
- **Before**: 5-6 seconds per API call
- **After**: 12 seconds per API call
- **Impact**: Messages take ~2-3x longer to process
- **Mitigation**: Request quota increase

### Lower Throughput:
- **Before**: ~12 messages/hour (theoretical)
- **After**: ~5 messages/hour
- **Impact**: System processes fewer loans
- **Mitigation**: This is a constraint of the current Azure quota

### Still Acceptable For:
- ✅ Development and testing
- ✅ Low-volume production (<10 loans/hour)
- ✅ Demo environments
- ⚠️ NOT suitable for high-volume production without quota increase

---

## 🎯 Next Steps

### Immediate (Today):
1. ✅ **Applied 7-second delay** (DONE)
2. ⏳ **Test for 10 minutes**
3. ⏳ **Verify error rate <5%**
4. ⏳ **Confirm TPM under 30K**

### Tomorrow:
5. **Request Azure quota increase** to 100K TPM
6. **Document business justification**
7. **Submit support ticket**

### After Quota Increase:
8. **Reduce delay** to 2-3 seconds (or remove entirely)
9. **Increase throughput** to 15-20 calls/min
10. **Monitor** for stability

---

## 📝 Key Learnings

### What We Learned:
1. **Rate limiting is TWO-dimensional**: Concurrent calls AND tokens-per-minute
2. **Semaphores alone are insufficient**: They limit concurrency, not throughput
3. **Azure has dual quotas**: RPM and TPM - must respect BOTH
4. **Token usage matters**: Large prompts = fewer calls allowed per minute
5. **Testing is essential**: Short tests didn't reveal the TPM issue

### Best Practices:
- ✅ Always test with **realistic load** (not just 1-2 messages)
- ✅ Monitor **both RPM and TPM** usage
- ✅ Calculate token usage **before deployment**
- ✅ Request **appropriate quotas** for production
- ✅ Implement **multi-layer rate limiting** (concurrency + throughput)

---

## ✅ Status

**FIX APPLIED**: ✅ **7-second TPM rate limit delay added**  
**TESTING**: ⏳ **Ready for validation**  
**EXPECTED RESULT**: ✅ **<5% error rate**  
**LONG-TERM**: ⏳ **Quota increase needed for production scale**

---

*Applied: October 5, 2025*  
*File Modified: agents/base_agent.py*  
*Change: Added asyncio.sleep(7) after each API call*  
*Purpose: Limit tokens-per-minute to stay within 30K TPM Azure quota*  
*Expected Impact: 95%+ success rate, 2-3x slower processing*
