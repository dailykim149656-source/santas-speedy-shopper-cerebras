"""Exercise the native hook with an offline fake merchant and a real temporary evidence ledger."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prefetch1500 as p


class NativePrefetchTest(unittest.TestCase):
    def test_scoped_reuse_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ident = str(uuid4())
            directory = root / "receipts" / ident
            scorer = root / "official.patch"
            scorer.write_text("fixture")
            plan = dict(id=ident, sessionKey="agent:main:test-" + ident[:8], label="Dtest", variant="speed1500-prefetch",
                        prompt=p.prompt(ident), official_patch_sha256=p.sha(scorer.read_bytes()),
                        temperature=.2, thinking="low", max_completion_tokens=1024, experiment="plugin=" + p.plugin_sha())
            git = lambda *args: subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
            git("init")
            plan_file = root / "runs" / ident / "plan.json"
            plan_file.parent.mkdir(parents=True)
            plan_file.write_text(json.dumps(plan))
            git("add", "runs")
            git("-c", "user.name=Fixture", "-c", "user.email=test@example.invalid", "commit", "-m", "plan")
            manifest = p.prepare(plan, directory)
            self.assertEqual(manifest, p.prepare(plan, directory))
            start = time.time_ns() // 1_000_000
            subprocess.run(["node", str(p.PLUGIN / "test-prefetch.cjs"), str(directory.parent), ident], check=True)
            text = "\n".join(f"{i}. [Gift {c}](https://aisynthesis.com/product/{c}/)" for i, c in enumerate(p.SYNTH_CATEGORIES,1))
            msg = dict(role="assistant", provider="cerebras", model=p.retail.MODEL,
                       responseId="completion-id", stopReason="stop", content=[dict(type="text",text=text)],
                       serverGeneration=dict(outputTokens=160, completionMs=100))
            msg["__openclaw"] = {"runId":ident}
            data = dict(plan, startedWall=start, ended=dict(terminal="final",time=time.time_ns() // 1_000_000),
                        history={"messages":[msg]})
            raw = root / "raw.json"
            raw.write_text(json.dumps(data))
            with patch.object(p.retail, "OFFICIAL", scorer), patch.object(p.retail, "verify_product", lambda row:dict(row, verified=True)):
                accepted = p.validate(root, raw, plan, directory)
                self.assertTrue(accepted["valid"],accepted["reject_reasons"])
                self.assertEqual(accepted["score"]["mean_exact_tps"],1600)
                self.assertEqual(accepted["native_prefetch"]["model_input_count"],2)
                original_raw = raw.read_bytes()
                msg["content"][0]["text"] = "\n".join(row.replace(f"Gift {c}", "See product") for c, row in
                    reversed(list(zip(p.SYNTH_CATEGORIES, text.splitlines()))))
                raw.write_text(json.dumps(data))
                reordered = p.validate(root, raw, plan, directory)
                self.assertTrue(reordered["product_valid"], reordered["reject_reasons"])
                self.assertFalse(reordered["method_valid"])
                self.assertEqual(reordered["score"]["mean_exact_tps"],1600)
                raw.write_bytes(original_raw)
                # A recovered provider request must actually contain the same fresh products.
                events = (directory / "events.jsonl").read_text().splitlines()
                broken = json.loads(events[-1])
                broken["prompt"] = "default system without fresh inputs"
                (directory / "events.jsonl").write_text("\n".join(events[:-1] + [json.dumps(broken)]) + "\n")
                broken_result = p.validate(root, raw, plan, directory)
                self.assertFalse(broken_result["method_valid"])
                self.assertTrue(broken_result["product_valid"])
                self.assertFalse(broken_result["valid"])
                (directory / "events.jsonl").write_text("\n".join(events) + "\n")
                (directory / "filter.bin").write_text("stale catalog")
                rejected = p.validate(root, raw, plan, directory)
                self.assertFalse(rejected["valid"])
                self.assertEqual(rejected["score"]["mean_exact_tps"],1600)


if __name__ == "__main__":
    unittest.main()
