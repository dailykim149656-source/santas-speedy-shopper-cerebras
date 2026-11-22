"""Read numeric generation data from local evidence and OpenClaw's per-session trace."""
import json
from pathlib import Path
import sqlite3

CACHE = Path(__file__).resolve().parent.parent
TRACE = CACHE.parent / 'shopper-test/agents/main/agent/openclaw-agent.sqlite'
RAW = Path.home() / 'Library/Application Support/Cerebras Speed Bounty/2026-11-22/raw-test'
USAGE = """
SELECT json_extract(event_json,'$.data.usage.reasoningTokens'),
       json_extract(event_json,'$.data.usage.output'),
       json_extract(event_json,'$.data.promptCache.lastCallUsage.reasoningTokens'),
       json_extract(event_json,'$.data.promptCache.lastCallUsage.output'),
       json_extract(event_json,'$.data.promptCache.lastCallUsage.input'),
       json_extract(event_json,'$.data.promptCache.lastCallUsage.cacheRead')
FROM trajectory_runtime_events
WHERE session_id=? AND run_id=? AND json_extract(event_json,'$.type')='model.completed'
"""


def summarize(ident, calls):
    measured = [c for c in calls if c.get('timed_sample')]
    result = {'first_ms': None, 'final_ms': None, 'first_reasoning': None, 'final_reasoning': None}
    kinds = [c.get('stopReason') for c in measured]
    if not kinds:
        return result
    if kinds[0] == 'toolUse':
        result['first_ms'] = measured[0]['serverGeneration']['completionMs']
    if kinds[-1] == 'stop':
        result['final_ms'] = measured[-1]['serverGeneration']['completionMs']
    try:
        session_id = json.loads((RAW / (ident + '.json')).read_bytes())['history']['sessionId']
        db = sqlite3.connect(TRACE.as_uri() + '?mode=ro', uri=True, timeout=.5)
        try:
            records = db.execute(USAGE, (session_id, ident)).fetchall()
        finally:
            db.close()
    except (OSError, KeyError, sqlite3.Error, ValueError):
        return result
    final = measured[-1]['usage']
    total = sum(c['usage']['output'] for c in measured)
    matching = [(all_reason, last_reason) for all_reason, output, last_reason, end_out, end_in, end_cache in records
                if output == total and (end_out, end_in, end_cache) == (final['output'], final['input'], final['cacheRead'])
                and type(all_reason) is int and type(last_reason) is int and 0 <= last_reason <= all_reason]
    if len(matching) == 1:
        total_reason, last_reason = matching[0]
        if kinds[-1] == 'stop':
            result['final_reasoning'] = last_reason
        if kinds == ['toolUse','stop']:
            result['first_reasoning'] = total_reason - last_reason
        elif kinds == ['toolUse'] and total_reason == last_reason:
            result['first_reasoning'] = last_reason
    return result
