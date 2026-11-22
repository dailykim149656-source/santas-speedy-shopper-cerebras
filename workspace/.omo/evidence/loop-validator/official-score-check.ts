export type GenerationSpeed = {
  /** Mean of the per-call rates: the headline. */
  meanTokensPerSecond: number;
  /** 90th-percentile per-call rate (nearest rank); below 10 calls it is the fastest call. */
  p90TokensPerSecond: number;
  /** Completion tokens and decode time summed over the calls. */
  outputTokens: number;
  generationMs: number;
  calls: number;
};

type CallSpeed = { outputTokens: number; generationMs: number };

function readNumber(record: Record<string, unknown>, key: string): number | undefined {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

/** One model call's server decode timing, from an assistant message's `serverGeneration`. */
function readCall(message: unknown): CallSpeed | null {
  if (!message || typeof message !== "object") {
    return null;
  }
  const record = message as Record<string, unknown>;
  const server = record.serverGeneration;
  if (record.role !== "assistant" || !server || typeof server !== "object") {
    return null;
  }
  const completionMs = readNumber(server as Record<string, unknown>, "completionMs");
  const outputTokens = readNumber(server as Record<string, unknown>, "outputTokens");
  return completionMs !== undefined &&
    completionMs > 0 &&
    outputTokens !== undefined &&
    outputTokens >= 1
    ? { outputTokens, generationMs: completionMs }
    : null;
}

function callRate(call: CallSpeed): number {
  return call.outputTokens / (call.generationMs / 1000);
}

/** Mean and p90 of the per-call rates over the messages' server-timed model calls; null when there are none. */
export function generationSpeed(messages: readonly unknown[]): GenerationSpeed | null {
  const calls = messages.map(readCall).filter((call): call is CallSpeed => call !== null);
  if (calls.length === 0) {
    return null;
  }
  const rates = calls.map(callRate);
  const sorted = rates.toSorted((a, b) => a - b);
  return {
    meanTokensPerSecond: rates.reduce((sum, rate) => sum + rate, 0) / rates.length,
    p90TokensPerSecond: sorted[Math.max(0, Math.ceil(0.9 * sorted.length) - 1)] ?? 0,
    outputTokens: calls.reduce((sum, call) => sum + call.outputTokens, 0),
    generationMs: calls.reduce((sum, call) => sum + call.generationMs, 0),
    calls: calls.length,
  };
}

export function formatTokensPerSecond(rate: number): string {
  return rate >= 100 ? Math.round(rate).toLocaleString() : rate.toFixed(1);
}


import fs from "node:fs";
const outputs = [];
for (const name of ["C1", "A2"]) {
  const run = JSON.parse(fs.readFileSync(`/tmp/cerebras-shop-latency.3qQpiWCM/${name}.json`, "utf8"));
  const observed = JSON.parse(fs.readFileSync(`.omo/evidence/loop-validator/${name}.json`, "utf8"));
  const official = generationSpeed(run.history.messages);
  const pass = official?.meanTokensPerSecond === observed.score.mean_exact_tps && formatTokensPerSecond(official!.meanTokensPerSecond) === observed.score.ui_display && official?.p90TokensPerSecond === observed.score.p90_tps && official?.calls === observed.score.call_count;
  outputs.push({name, official, officialDisplay: formatTokensPerSecond(official!.meanTokensPerSecond), exactMatch: pass});
  if (!pass) process.exitCode = 1;
}
console.log(JSON.stringify(outputs, null, 2));
