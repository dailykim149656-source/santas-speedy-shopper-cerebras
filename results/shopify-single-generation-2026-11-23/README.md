# Shopify 선조회 단일 생성 실험

2026년 11월 23일 KST 기준 **32회 시도 중 11회가 유효했고 최고 기록은 1,255.33 TPS**였다. 유효 평균은 966.98 TPS, 중앙값은 962.12 TPS였다. 나머지 21회는 Cerebras HTTP 429로 끝났다. Shopify 카탈로그 조회는 160건 모두 HTTP 200이었다. D5027의 원점수 1,354.6625976356386 TPS, 1,500 TPS, 1,673 TPS를 각각 초과한 유효 세션은 0회였다. [실행별 시각·UUID·원점수](results.json)

| 운영 구간 | 시도 | 상품 5/5 | 유효 | Cerebras 429 | Shopify 429 | 유효 평균 TPS | 중앙값 | 최고 TPS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 02:35 마감 | 17 | 17 | 7 | 10 | 0 | 990.23 | 962.12 | 1,255.33 |
| 02:50 마감 | 15 | 15 | 4 | 11 | 0 | 926.29 | 973.79 | 1,096.81 |
| 전체 | 32 | 32 | 11 | 21 | 0 | 966.98 | 962.12 | 1,255.33 |

## 측정 방법

이 실험형 구성은 새 OpenClaw 세션마다 Shopify Global Catalog에 다섯 검색어를 병렬로 보내 미국 배송 가능·재고 있음·USD 기준 50달러 이하의 상품을 하나씩 골랐다. 상품 검증은 각 회차의 Shopify 응답에서 상품명, 판매처, 재고, 가격, 직접 링크와 판매자 설명을 대조했다. 모델의 최종 답변에서도 다섯 상품의 제목·판매처·가격·링크를 확인했다. 두 구간을 합쳐 유효 세션마다 Cerebras 생성은 한 번이었다.

Kimi K3.1 Pro에 온도 0.1, 추론 `low`, 출력 한도 2,400토큰을 적용했다. 도구 정의를 제거한 요청에 완성된 목록을 담아 한 번 출력하게 했다. 공식 패치의 세션 TPS는 출력 토큰을 서버 생성 시간(초)으로 나눈 값이다. 한 번 생성했으므로 해당 세션의 mean과 p90가 같다. 카탈로그 검색과 네트워크 대기는 이 점수의 분모에서 제외된다. 429 세션은 결과 파일의 시도 수와 HTTP 집계에 포함된다. [방법의 참고 커밋](https://github.com/simethan/santas-speedy-shopper/tree/121842981f3214db7066de4f12540d51195bcc36) · [공식 속도 패치](https://github.com/wkasekende/openclaw-speed-patch/tree/e40e9f7b7ec41ad3fa68181ad297db119e755171)

## 최고 세션

첫 구간 1번, UUID `5e042f4a-bac9-4ebb-b49d-52f25026ce16`의 출력은 702토큰, 서버 생성 시간은 559.21536ms였다. 원점수는 **1,255.3303256906247 TPS**다. 조회한 상품별 검색어·상품명·판매처·가격·직접 링크·요청 및 원응답 SHA-256과 서버 측정값을 함께 기록했다. [최고 세션 증빙](best-evidence.json)

[5.96초 영상](best-post-run.mp4)은 완료된 세션을 다시 열어 촬영한 **사후 녹화**다. 화면에는 반올림한 평균·p90 1,255 TPS와 다섯 구매 링크가 보인다.

## 재현

공개 저장소의 루트에서 실행한다. 배포된 코드는 `experiments/shopify-single-generation/tools/`에 있고 실험 개발용 `test` 저장소에서는 `tools/`에 있다. 실행기에는 공식 패치가 적용된 프로젝트 전용 OpenClaw 런타임, Node.js, 구성된 Cerebras 자격 증명, Shopify 및 Cerebras 접속이 필요하다. 실시간 조회를 다시 하므로 상품, 가용성, 속도는 달라질 수 있다. 로컬 결과 경로는 새 디렉터리를 사용한다. 아래 예시는 현재 시각부터 5분간 새 세션을 보내고 종료 후 저장한 증빙을 오프라인으로 검증한다.

```sh
work_dir="$(mktemp -d)"
out_dir="$work_dir/shopify-run"
cutoff="$(python3 -c 'from datetime import datetime,timedelta; print((datetime.now().astimezone()+timedelta(minutes=5)).isoformat())')"
python3 -B experiments/shopify-single-generation/tools/run_simethan_trials.py --out "$out_dir" --deadline "$cutoff"
python3 -B experiments/shopify-single-generation/tools/simethan_report.py "$out_dir"
```

실제 API 전송 없이 이 폴더의 공개 측정값만 검산하려면 다음 명령을 이 파일이 있는 디렉터리에서 실행한다.

```sh
python3 - <<'PY'
import json, math, statistics
from pathlib import Path
data = json.loads(Path("results.json").read_bytes())
rows = data["trials"]
rates = [r["output_tokens"] / (r["generation_ms"] / 1000) for r in rows if r["valid"]]
assert len(rows) == len({r["run_uuid"] for r in rows}) == 32
assert len(rates) == 11 and sum(r["provider_http"] == 429 for r in rows) == 21
for calculated, key in [(statistics.mean(rates), "average_tps"),
                        (statistics.median(rates), "median_tps"), (max(rates), "best_tps")]:
    assert math.isclose(calculated, data["summary"][key], rel_tol=1e-12)
print(len(rates), statistics.mean(rates), statistics.median(rates), max(rates))
PY
```
