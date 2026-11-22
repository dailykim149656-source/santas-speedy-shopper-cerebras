# 카탈로그 검색 한 번으로 선물 다섯 개 찾기 — 2026년 11월 22일 실험 인계

**현재는 중단 상태다.** 23:55 KST에 다른 세션의 실험을 우선해 이 실험의 실행기와 전용 게이트웨이(포트 19867)를 종료했다. 추가 실행은 수동으로 시작한다.

기존 제출의 `web_fetch` 5회를 `search_catalog` 1회로 바꾸어 상품 5개를 찾는 데 성공했다. 17회 시도 중 상품과 서버 측정값을 모두 검증한 실행은 1회였고, 두 모델 호출의 공식 평균은 **936.57 TPS**였다. 화면 반올림값은 **937 TPS**다. 목표인 1,673 TPS를 넘긴 유효 실행은 없었다.

나머지 16회는 Cerebras가 `429 queue_exceeded`를 반환했다. 15회는 첫 모델 호출에서, 1회는 검색 성공 후 최종 답변 호출에서 막혔다. 유효 표본이 하나라 평소 기대할 수 있는 속도나 달성 가능성을 추정하기 어렵다. 현재 근거로는 기존 1,355 TPS 제출을 유지하고, 이 변경은 후속 실험에 사용하는 편이 타당하다.

## 실험 방법

모델의 첫 호출이 검색어를 지정해 OpenClaw 도구 `search_catalog`를 한 번 호출한다. 도구는 Shopify Global Catalog에 HTTP POST 한 번을 보내 미국 배송·재고·USD 조건으로 최대 20개 후보를 받고, 서로 다른 상품 다섯 개를 고른다. 판매처가 다른 상품을 우선한다. 모델의 두 번째 호출이 상품명과 구매 링크를 출력한다. 매 실행마다 새 세션을 만들고, 전체 실험에서 동일한 프롬프트와 플러그인을 썼다. 추론 설정은 `low`, 온도는 0.2, 최대 출력 토큰은 1,024다.

점수는 공식 패치의 `generationSpeed` 함수를 그대로 호출해 서버 출력 토큰 수와 생성 시간으로 산출하고 별도 검증기로 재계산했다. 세션 평균은 두 모델 호출의 TPS 산술평균이다. 전체 평균에는 유효한 각 세션을 같은 비중으로 반영했다. Shopify 검색, 네트워크 대기와 외부 판매 페이지 검증에 걸린 시간은 서버 생성 속도에서 제외된다. [공식 계산 코드](https://github.com/wkasekende/openclaw-speed-patch/blob/e40e9f7b7ec41ad3fa68181ad297db119e755171/openclaw-cerebras-kimi-on-8b18b55.patch#L385-L455) · [환경과 소스 해시](environment.json)

프롬프트는 다음과 같다.

> Find five Christmas gifts that ship to the US. Search the live catalog once for Christmas gifts. Give five Markdown links using the exact product titles and URLs.

## 실행별 결과

| 그룹·회차 | 요청 시각 (KST) | 검색 요청 TPS | 최종 답변 TPS | 세션 평균 TPS | 소요 시간 | 검증 결과 |
|---|---|---:|---:|---:|---:|---|
| [01·01](series-01/catalog-01.json) | 11-22 23:45:33 | — | — | — | 7.82초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [01·02](series-01/catalog-02.json) | 11-22 23:45:53 | — | — | — | 1.39초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [01·03](series-01/catalog-03.json) | 11-22 23:46:08 | — | — | — | 1.51초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [01·04](series-01/catalog-04.json) | 11-22 23:46:22 | — | — | — | 1.05초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [01·05](series-01/catalog-05.json) | 11-22 23:46:35 | 618.03 | 1,255.11 | 936.57 | 49.60초 | 상품 5/5 |
| [01·06](series-01/catalog-06.json) | 11-22 23:47:37 | — | — | — | 2.46초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [01·07](series-01/catalog-07.json) | 11-22 23:47:52 | — | — | — | 1.01초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [01·08](series-01/catalog-08.json) | 11-22 23:48:05 | — | — | — | 0.89초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [01·09](series-01/catalog-09.json) | 11-22 23:48:18 | 371.28 | — | — | 24.95초 | 호출 2 · HTTP 429 (High traffic (provider queue exceeded)) |
| [01·10](series-01/catalog-10.json) | 11-22 23:48:55 | — | — | — | 1.01초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [02·01](series-02/catalog-01.json) | 11-22 23:49:11 | — | — | — | 0.96초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [02·02](series-02/catalog-02.json) | 11-22 23:50:12 | — | — | — | 2.15초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [02·03](series-02/catalog-03.json) | 11-22 23:51:14 | — | — | — | 0.81초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [02·04](series-02/catalog-04.json) | 11-22 23:52:15 | — | — | — | 1.88초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [02·05](series-02/catalog-05.json) | 11-22 23:53:17 | — | — | — | 0.94초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [02·06](series-02/catalog-06.json) | 11-22 23:54:19 | — | — | — | 0.71초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |
| [02·07](series-02/catalog-07.json) | 11-22 23:55:19 | — | — | — | 0.90초 | 호출 1 · HTTP 429 (High traffic (provider queue exceeded)) |

소요 시간은 클라이언트가 프롬프트를 보내고 게이트웨이의 종료 응답을 받을 때까지다. 호출 일부만 측정된 경우에는 해당 호출 속도만 표시했다. 평균과 최고 기록으로 인정하려면 새 세션에서 `search_catalog` 한 번, 성공한 Shopify 응답 한 번, Cerebras가 측정한 모델 호출 두 번, 최종 답안과 일치하는 서로 다른 구매 링크 다섯 개 및 제품 페이지 확인을 모두 통과해야 한다.

- 01그룹은 12초 간격으로 10회 시도해 1회 검증했다. [실행 계획](series-01/plan.json) · [공급자 오류](series-01/provider-errors.json)
- 02그룹은 60초 간격으로 8회를 계획했다. 7회 전송했고 모두 첫 호출에서 429로 끝났다. 8번째 세션은 만들거나 전송하기 전에 중단했다. [실행 계획](series-02/plan.json) · [공급자 오류](series-02/provider-errors.json)

## 이전 제출 기록과 비교

이번 최고 세션에서 첫 호출은 106토큰을 171.51ms에 생성했고, 최종 호출은 288토큰을 229.46ms에 생성했다. 기존 1,355 TPS 제출의 첫 호출은 447토큰·1,035.39 TPS, 최종 호출은 161토큰·1,673.94 TPS였다. 두 방식은 측정한 시간대와 상품이 달라 그 차이만으로 카탈로그 도구의 속도 효과를 분리할 수 없다. [이번 최고 실행](series-01/catalog-05.json) · [기존 제출 원본](../runs/cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77/evidence.json)

## 나중에 이 컴퓨터에서 재개하기

다른 세션의 Cerebras 실험이 끝나고 측정할 시간이 생기면 진행한다. 이 Mac의 공식 패치 런타임과 기존 Cerebras 인증 설정을 재사용한다. 두 터미널 모두 프로젝트 루트에서 시작한다. 첫 터미널에서 전용 게이트웨이를 띄운다.

```sh
python3 speed-bounty-evidence-test/tools/catalog_gateway.py
```

두 번째 터미널에서 준비 상태에 `ready: true`가 표시되는지 확인한 뒤 새 출력 폴더에 실행한다. 아래 예시는 같은 프롬프트로 60초 간격을 두는 8회 반복이다. 실행 수와 간격은 다음 측정자가 가용 시간에 맞춰 조정할 수 있다.

```sh
base="$HOME/Library/Caches/cerebras-speed-bounty/2026-11-22"
state="$HOME/Library/Caches/cerebras-speed-bounty/2026-11-22-catalog/shopper-test"
curl -fsS http://127.0.0.1:19867/readyz
out="$(mktemp -d speed-bounty-evidence-test/catalog-benchmark/resume-XXXXXX)"
"$base/bin/node" --experimental-transform-types speed-bounty-evidence-test/tools/run_catalog_trials.mjs \
  --openclaw "$base/openclaw" --state "$state" --port 19867 --out "$out" --count 8 --pause-seconds 60
python3 speed-bounty-evidence-test/tools/catalog_trial_score.py "$out"/catalog-*.json \
  --receipts "$state/catalog-receipts" --output "$out/results.json"
python3 speed-bounty-evidence-test/tools/catalog_upstream_errors.py \
  --state "$state" --plan "$out/plan.json" --out "$out/provider-errors.json"
```

다음 측정에서도 상품 5개가 검증된 **최고 세션 평균**, **유효 세션 평균들의 산술평균**, **공식 표시 1,673을 넘긴 횟수**, **429가 난 단계**를 함께 비교한다. 유효 실행이 여러 개 쌓이면 첫 호출의 토큰 수와 TPS를 따로 살펴본다. 첫 호출이 짧아져도 초당 생성 속도가 함께 오르지는 않을 수 있다. 측정을 마친 뒤 첫 터미널에서 `Ctrl-C`로 이 실험의 게이트웨이를 종료한다.

[전체 집계와 제품 페이지 검증](results.json) · [실제 카탈로그 요청 증빙](receipts/) · [검색 플러그인](../tools/catalog-search-plugin/index.cjs)
