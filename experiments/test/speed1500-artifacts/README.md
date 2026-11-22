# Speed1500 campaign evidence

The 18 numbered slots match the [campaign report](../SPEED1500-RESULTS.md). Each slot retains its plan, gateway timing summary, validation and available request relay metadata. Slot media contains the published dashboard recording. Each prefetch request has its own receipts directory with five merchant response bodies and the associated SHA-256 digests.

The general ledger verifier checks links through model-issued tool calls. D5083 and D5090 used a plugin to fetch five products before the first model generation. For those two slots, check the run ID in the slot summary, the five `native_prefetch.receipts` in its validation, the corresponding body hashes in [receipts](receipts/), the final five links, and the provider-generation timings in the ledger. Their speed measurements are 594.04 and 728.42 TPS. The eight gift8 records use the separate evidence format in [gift8_evidence.py](../tools/gift8_evidence.py).

Private gateway transcripts are retained locally. This export preserves the original digests. Presentation video and validated shopping success are distinct for partial slots that ended with provider 429s.
