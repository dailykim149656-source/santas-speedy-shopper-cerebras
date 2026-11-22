# tps-bench

Cerebras에서 실행되는 Kimi K3.1 Pro(`moonshotai-kimi-k3.1-pro-trial`)의 프롬프트별 TPS를 재는 도구입니다. Python 3 표준 라이브러리만 쓰므로 설치할 패키지가 없습니다.

출품작의 핵심 기능이 아니라 측정용 뼈대입니다. 공식 TPS 산식은 아직 공지되지 않았으므로, 산식이 나오면 같은 기록으로 다시 계산할 수 있게 원자료를 모두 남깁니다.

| 파일 | 역할 |
|---|---|
| `tps_bench.py` | `check` 접근 확인 · `run` 실험 실행 · `summarize` 집계 |
| `prompts.json` | P1 산술, P2 Python 함수, P3 JSONL, P4 반복. 고치면 `version`을 올립니다 |
| `mock_cerebras.py` | 리허설용 모의 서버. 수치는 가짜입니다 |
| `runs/` | 실행할 때마다 폴더가 하나씩 생깁니다 |

## 측정 경로

| `--path` | 무엇을 거치나 | 쓰임 |
|---|---|---|
| `direct` (기본) | Cerebras API 직접 호출 | **주 측정.** 서버 `time_info`로 decode TPS 계산 |
| `openclaw-http` | OpenClaw 게이트웨이 `/v1/chat/completions` | OpenClaw 경유 스트리밍 TPS. 에이전트 실행이라 시스템 프롬프트가 붙습니다 |
| `openclaw-cli` | `openclaw infer model run --json` | 규정 충족 증빙용. CLI 기동 시간이 포함돼 TPS 비교에는 쓰지 않습니다 (5토큰 응답에 14~21초) |

## 1. 키 준비

키가 셸 기록에 남지 않도록 입력해서 넣습니다.

```bash
read -s CEREBRAS_API_KEY && export CEREBRAS_API_KEY
```

키는 요청 헤더에만 쓰고 기록 파일·오류 메시지에는 남기지 않습니다. 화면 녹화 중에는 이 명령을 실행하지 마세요.

## 2. 개막 전 리허설 (모의 서버)

터미널 두 개에서 실행합니다.

```bash
python3 mock_cerebras.py --port 8765 --fail-every 7
```

```bash
python3 tps_bench.py run --base-url http://127.0.0.1:8765/v1 --reps 1 --label rehearsal
```

`--fail-every 7`은 7번째 요청마다 429를 돌려줘 재시도 동작을 보여 줍니다.

## 3. 개막 직후 확인 (11월 22일 03:00 KST)

```bash
python3 tps_bench.py check --efforts omit,low,max
```

짧은 요청을 추론 강도마다 스트리밍·비스트리밍으로 한 번씩 보냅니다. 출력에서 다음을 봅니다.

- 모델 ID와 응답이 정상인지
- `time_info` 필드가 **스트리밍 응답에도** 오는지. 오지 않으면 서버 TPS는 `--modes nostream`으로만 잴 수 있습니다
- `reasoning_tokens`가 보고되는지, `low`·`max`가 거절되지 않는지

## 4. 1차 실험 40회

기본값이 P1~P4 × `low`·`max` × 5회, 스트리밍, 출력 상한 2,048입니다. 순서는 섞어서 한 번에 하나씩 보냅니다.

```bash
python3 tps_bench.py run --dry-run
```

```bash
python3 tps_bench.py run --label round1
```

Ctrl-C로 멈춰도 됩니다. 마지막에 출력되는 `--resume` 명령으로 이어서 실행하면 끝난 요청은 건너뜁니다.

분당 100요청·10만 토큰 한도에 걸리지 않도록 기본 예산을 90요청·9만 토큰으로 잡고 간격을 조절합니다. 서버가 출력 상한을 미리 차감하는지 확인되지 않아 (입력 추정 + 출력 상한)을 예약합니다. 출력 상한 8,192로 바꾸면 분당 약 10건이 한계입니다.

## 5. 집계

```bash
python3 tps_bench.py summarize runs/<폴더>
```

조건별 중앙값·최고값·표준편차, 출력 상한 도달 횟수, 완성도, TTFT와 단일 최고 요청(응답 ID 포함)을 보여 주고 `summary.csv`를 남깁니다.

- `--complete-only` 출력이 끝까지 생성되고(finish=stop) 형식 검사를 통과한 요청만 집계
- `--metric stream_tps` 등 공식 산식에 맞는 지표로 다시 정렬

## 6. 상위 후보 재측정

```bash
python3 tps_bench.py run --prompts P1,P2 --efforts max --reps 10 --label final
```

출력 상한을 바꿔 보려면 `--max-tokens 4096`, 요청 본문에 값을 더하려면 `--extra-body '{"temperature":1.0}'`을 씁니다.

## OpenClaw HTTP 경로 켜기

게이트웨이의 OpenAI 호환 엔드포인트는 기본으로 꺼져 있습니다. 켜면 게이트웨이 토큰을 가진 로컬 호출자가 운영자 권한을 갖게 되니, 루프백 전용 상태를 유지하세요.

```bash
openclaw config set gateway.http.endpoints.chatCompletions.enabled true --strict-json
```

```bash
openclaw gateway restart
```

```bash
python3 tps_bench.py check --path openclaw-http
```

게이트웨이 토큰은 `OPENCLAW_GATEWAY_TOKEN` 환경변수나 `~/.openclaw/openclaw.json`에서 읽습니다. 모델은 `x-openclaw-model: cerebras/moonshotai-kimi-k3.1-pro-trial` 헤더로 지정합니다.

## 지표 정의

| 필드 | 계산 |
|---|---|
| `server_decode_tps` | `completion_tokens ÷ time_info.completion_time` (분석용 주지표) |
| `server_total_tps` | `completion_tokens ÷ time_info.total_time` |
| `stream_tps` | `(completion_tokens − 1) ÷ (마지막 토큰 도착 − 첫 토큰 도착)`. SSE 청크 하나에 여러 토큰이 올 수 있어 근사값입니다 |
| `client_wall_tps` | `completion_tokens ÷ 요청 시작부터 응답 완료까지` (네트워크·대기·입력 처리 포함) |

`completion_tokens`에는 추론 토큰이 포함될 수 있습니다. `reasoning_tokens`는 따로 기록하고 분자에 다시 더하지 않습니다.

요청마다 `requests.jsonl`에 한 줄을 남깁니다. 시각, 경로, 프롬프트 버전과 해시, 추론 강도, 출력 상한, 응답 ID, 종료 이유, 토큰 수, `queue_time`·`prompt_time`·`completion_time`·`total_time`, 클라이언트 시각, 완성도, 재시도 횟수가 들어갑니다. 출력 원문과 추론문은 `outputs/<seq>.json`에 저장합니다.
