# November 23 shopping experiments

The category-query campaign sent 17 OpenClaw sessions. All 17 encountered a provider HTTP 429 and none completed a verified final answer. Two sessions obtained all five products before their final generation failed.

The two Shopify prefetch campaigns sent 32 single model requests. Each recorded five fresh successful Shopify catalog searches. 11 produced five verified answers and 21 ended with Cerebras HTTP 429. Across verified sessions the arithmetic mean was 966.98 TPS and the median was 962.12 TPS. Each session’s official mean is its output token count divided by its server generation time in seconds.

The highest session reached **1,255.33 TPS** with 702 output tokens in 559.21536 ms. Its [demo](shopify-one-20261123-0221/videos/5e042f4a-bac9-4ebb-b49d-52f25026ce16/demo.mp4) was recorded after the model run. The fastest verified recording that started before model dispatch reached **977.60 TPS**. The submitted 1,355 mean record and these experimental results came from separate runs.

## Evidence

- [category-query-20261123-015349](category-query-20261123-015349/attempts.csv)
- [shopify-one-20261123-0221](shopify-one-20261123-0221/attempts.csv)
- [shopify-one-20261123-0235-0250](shopify-one-20261123-0235-0250/attempts.csv)
- [All Shopify sends in sequence](shopify-all-attempts.csv)
- [Combined statistics](shopify-combined.json)

Each campaign contains its submitted configuration, per-attempt records and an index. Shopify records retain the selected seller, SKU variant link, availability, actual price, query parameters and source digests. Successful runs include the model's visible answer, provider response ID, original usage and generation time. The five query payloads are shared by reference through their SHA-256 hashes. The offline verifier checked the private original bytes against these hashes and checked product names, prices and URLs against each model output. The public archive contains selected catalog fields. Full catalog replies also contain unrelated sellers' checkout links. Full raw chat histories and browser profiles remain in the local run archive. Video metadata distinguishes a post-run capture from a recording that started before model dispatch.

The per-attempt `wire/NNN/` folders contain the exact provider request body, response body and recorded trace, including provider errors. The reported SHA-256 values can be recomputed from these files. HTTP authentication headers were never part of these bodies. The highest-scoring session also has an earlier post-run recording whose viewport check failed. It is explicitly marked `unverified-post-run/`.
