# Cerebras × Kimi TPS Bounty 개막 전 준비 체크리스트

2026년 11월 20일 기준 · 모든 시각은 한국시간(KST)

**OpenClaw의 Cerebras 연결 설정은 완료했다.** 로컬 게이트웨이가 응답하고 Cerebras 인증 프로필이 등록돼 있다. 공개 모델 시험 호출은 `payment_required`로 끝났으며, 해커톤 Kimi의 실제 생성은 아직 확인되지 않았다. TPS 측정 스크립트는 [tps-bench](<tps-bench/README.md>)에 준비했고, 모의 서버로만 시험했다. [Cerebras Cloud](https://cloud.cerebras.ai/)

## 1. 완료한 준비

- [x] **행사 신청 및 Org ID 제출.** 참가자 확인. 제출 마감은 11월 21일(토) 낮 12시다. [행사 공지](https://luma.com/cerebras-kimi-hackathon)
- [x] **OpenClaw CLI 설치·실행.** 이 Mac에서 `npx --offline --yes=false openclaw@latest --version`을 실행해 **2026.11.6**을 확인했다. 로컬 설정 파일도 유효성 검사를 통과했다.
- [x] **Cerebras 공급자와 인증 프로필 등록.** 공식 Cerebras 플러그인이 로드되고 OpenClaw가 인증 프로필 1개를 인식한다. 행사 모델도 `cerebras/moonshotai-kimi-k3.1-pro-trial`로 로컬 설정에 등록했다.
- [x] **로컬 게이트웨이 실행.** macOS 사용자 LaunchAgent로 실행 중이며 `openclaw gateway status --require-rpc` 검사를 통과했다. 접속 범위는 이 Mac의 루프백이다.
- [x] **TPS 측정 스크립트 준비.** [tps-bench](<tps-bench/README.md>)의 `tps_bench.py`는 Python 3 표준 라이브러리만 쓴다. 접근 확인(`check`), 실험 실행(`run`), 집계(`summarize`)를 한다. 모의 서버로 접근 확인, 32회 실행, 429 재시도, 중단 후 재개, 집계를 확인했다. 실제 Kimi 응답으로는 아직 시험하지 못했다.
- [x] **측정 경로 정리.** 서버 측 TPS는 Cerebras API를 직접 호출해 잰다. OpenClaw CLI는 응답에 토큰 수만 주고 서버 생성 시간은 주지 않는다. 5토큰 응답에도 14~21초가 걸려 CLI 경로는 OpenClaw 사용 증빙용으로만 쓴다. OpenClaw 게이트웨이의 `/v1/chat/completions`는 현재 꺼져 있다. [OpenClaw infer](https://docs.openclaw.ai/cli/infer) · [게이트웨이 HTTP API](https://docs.openclaw.ai/gateway/openai-http-api)

## 2. 11월 22일 일요일 03:00 전까지 · 실행 환경과 제출 준비

- [ ] **모델 응답 확인.** OpenClaw에서 `cerebras/gpt-oss-120b`로 짧은 요청을 보냈을 때 Cerebras가 `payment_required`를 반환했다. OpenClaw는 이후 이 공급자 프로필의 호출을 일시 보류했다. 제출한 조직의 계정 상태·사용 한도를 확인하고, 행사 프리뷰가 활성화된 뒤 아래 명령으로 응답을 확인한다. 행사 모델 권한은 주최 측 안내와 실제 응답으로 확인한다. [Cerebras Cloud](https://cloud.cerebras.ai/) · [행사 FAQ](https://docs.google.com/document/d/1Vvf2SjScBt3yBeTVZRoKtOyE7rGEP-gWV_ApzwXepEQ/edit)

  ```sh
  openclaw infer model run --gateway --model cerebras/moonshotai-kimi-k3.1-pro-trial --prompt 'Reply with OK.'
  ```

  측정 스크립트는 OpenClaw 저장소의 키를 읽지 않는다. 직접 호출용 키는 셸 기록에 남지 않도록 입력해서 넣는다. 화면 녹화 중에는 실행하지 않는다.

  ```sh
  read -s CEREBRAS_API_KEY && export CEREBRAS_API_KEY
  ```

- [ ] **API 키 조직 확인.** API 키를 만든 조직이 행사에 제출한 Org ID와 같은지 Cerebras Cloud에서 확인한다. 다르면 행사 모델에 접근할 수 없다.
- [ ] **(선택) 모의 서버 리허설.** 터미널 두 개를 열고 `tps-bench` 폴더에서 차례로 실행한다. 결과는 `tps-bench/runs/`에 쌓이며 수치는 가짜다.

  ```sh
  python3 mock_cerebras.py --port 8765 --fail-every 7
  ```

  ```sh
  python3 tps_bench.py run --base-url http://127.0.0.1:8765/v1 --reps 1 --label rehearsal
  ```

- [x] **개인 Discord 계정으로 Cerebras 서버 참가.** 해커톤 전용 [공지](https://discord.com/channels/1085960591052644463/1572277577429549216), [채팅](https://discord.com/channels/1085960591052644463/1572153797390770186), [기술지원](https://discord.com/channels/1085960591052644463/1572281523518972047) 채널을 확인했다.
- [x] **X 계정과 작성 화면 확인.** 11월 20일 17:47 KST 기준, 로그인된 계정의 새 게시물 작성 화면에서 사진·영상 첨부 버튼을 확인했다. 최종 영상 파일은 녹화 후 첨부한다. 제출 프로젝트에는 OpenClaw와 Cerebras의 Kimi K3.1 Pro를 사용한다. [공식 FAQ](https://docs.google.com/document/d/1Vvf2SjScBt3yBeTVZRoKtOyE7rGEP-gWV_ApzwXepEQ/edit)
- [ ] **데모를 녹화하고 게시글 초안에 실측 결과를 채운다.** 데모는 60초 이하다. 예시 구성은 0~10초에 무엇을 비교하는지, 10~40초에 OpenClaw에서 기준·후보 프롬프트가 실행되는 모습, 40~55초에 실제 토큰 수·시간·TPS와 사용자 대기시간 차이를 보여 주는 것이다. 게시글에 프로젝트명, 팀원 계정, 설명 2~4문장, `@Cerebras`, `@Kimi_Moonshot`, `#KimiOnCerebras` 자리를 둔다. GitHub 링크는 권장, Reddit은 선택이다. [공식 제출 요건](https://docs.google.com/document/d/1Vvf2SjScBt3yBeTVZRoKtOyE7rGEP-gWV_ApzwXepEQ/edit)

  X 게시글에 채워 넣을 영문 초안

  > [Project name] by [team handles]. We built an OpenClaw agent that uses Kimi K3.1 Pro on Cerebras to [task]. In this demo it completes [observable result] in [measured time]. @Cerebras @Kimi_Moonshot #KimiOnCerebras

  녹화 리허설은 10초면 된다. 촬영할 앱 창에서 예시 입력과 결과를 한 번 보여 주고, 재생해서 글자가 읽히는지, 키·계정 정보·알림이 나오지 않는지 확인한다.

## 3. 개막 전 설계할 TPS 실험

기존 프레임워크·보일러플레이트는 허용된다. 개막 전에는 아래 비교표와 기록 양식까지 준비하고, 출품작의 핵심 기능 개발과 행사 모델을 이용한 실측은 24시간 행사 중에 진행한다. [공식 FAQ](https://docs.google.com/document/d/1Vvf2SjScBt3yBeTVZRoKtOyE7rGEP-gWV_ApzwXepEQ/edit)

아래 표의 프롬프트·조건·기록 항목은 측정 스크립트에 모두 반영했다. 프롬프트 원문은 [prompts.json](<tps-bench/prompts.json>)에 버전과 함께 저장했다. `python3 tps_bench.py run`의 기본값이 1차 비교 40회다. 요청마다 `requests.jsonl`에 한 줄, 출력 원문은 `outputs/<번호>.json`에 남는다.

| 준비물 | 미리 정해 둘 내용 |
|---|---|
| 프롬프트 후보표 | P1 산술 등식 200개, P2 규칙적인 Python 함수 100개, P3 JSONL 레코드 200개, P4 같은 네 단어 300회 반복. 원문 프롬프트를 보관하고 변경 시 버전을 붙인다. |
| 1차 비교표 | 4후보 × 추론 강도 low·max × 각 5회 = 40요청. 두 설정을 trial이 지원할 때 적용한다. 요청은 한 번에 하나씩 보내고 순서를 섞는다. 예를 들어 출력 상한은 2,048로 고정하고, 상한에 걸린 요청은 따로 표시한다. |
| 요청별 기록표 | 시각, 프롬프트 버전, 실제 모델 ID, 요청한 추론 강도, 출력 상한, 실제 생성 토큰 수, 서버 생성 시간, 클라이언트 경과시간, 종료 이유, 출력 완성 여부를 한 줄에 남긴다. 가능하면 응답 ID, 대기시간, 추론 토큰 수도 저장한다. |
| 후보 선정 기준 | 분석용 서버 TPS는 `usage.completion_tokens / time_info.completion_time`이다. 각 후보의 중앙값·최고값을 둘 다 보관하고 상위 2개는 같은 조건에서 각 10회 이상 재측정한다. 운영진이 공식 산식을 안내하면 그 기준을 적용한다. |

40회는 이전 대화의 **권장 실험안**이다. 공식 채점식과 최소 출력 길이는 FAQ에 명시돼 있지 않다. 추론 기본값도 행사 FAQ에는 꺼짐, 일반 Dedicated 문서에는 `max`로 적혀 있다. 설정을 생략한 요청과 명시한 요청을 기록표에서 구별한다. [원대화](<해커톤 수상 전략 - 대화 전문.md>) · [응답 필드](https://inference-docs.cerebras.ai/api-reference/chat-completions) · [Cerebras 추론 설정](https://inference-docs.cerebras.ai/capabilities/reasoning) · [행사 FAQ](https://docs.google.com/document/d/1Vvf2SjScBt3yBeTVZRoKtOyE7rGEP-gWV_ApzwXepEQ/edit)

  첫 실측부터 사용할 CSV 머리글

  ```csv
  run_at_kst,prompt_version,actual_model,reasoning_setting,max_output_tokens,output_tokens,server_generation_s,client_elapsed_s,finish_reason,request_id
  ```

  이 Mac의 OpenClaw CLI는 첫 요청 명령에 `--json`을 붙일 수 있다. 실제로 받은 필드만 기록하고, 제공되지 않은 값은 비워 둔다. 첫 비교에는 P1~P4 네 프롬프트를 모두 사용한다. 측정 스크립트의 `run` 기본값과 같다.

  측정 스크립트의 `requests.jsonl`에는 위 머리글의 항목이 모두 들어 있다. 대응 필드는 `ts_start`, `prompt_version`, `model_returned`, `reasoning_effort`, `max_completion_tokens`, `completion_tokens`, `completion_time`, `client_wall_s`, `finish_reason`, `response_id` 순서다. 받지 못한 값은 `null`로 남는다.

## 4. 개막 첫 30분에 확인할 것

모델 첫 응답과 운영진 새 답변 확인은 11월 22일 03:00과 05:00 KST로 예약했다. 결과는 이 채팅과 작업 폴더의 `해커톤 개막 확인 기록 - 2026-11-22.md`에 남긴다. 실험·촬영·게시 시간을 일요일 낮이나 저녁에 잡아 둔다.

- [ ] **03:00 킥오프 Q&A.** ① 채점 시간은 서버 생성 시간인가, 스트리밍 시간인가? ② 최고 1회와 반복 평균 중 무엇을 쓰며 추론 토큰을 포함하는가? ③ 최소 출력 길이와 반복 출력 제한이 있는가? ④ OpenClaw 실행을 입증할 로그·요청 ID·제출 양식이 필요한가?
- [ ] **trial에서 첫 요청 1건.** OpenClaw로 짧은 입력을 보내 모델 ID, 실제 출력, 토큰 수와 반환된 시간 필드를 확인한다. 접근이 막히면 첫 기술지원 시간인 **11월 22일 03:30~05:30**에 문의한다. 정상 응답이 확인되면 기준선부터 측정한다. [공식 일정·기술지원 시간](https://docs.google.com/document/d/1Vvf2SjScBt3yBeTVZRoKtOyE7rGEP-gWV_ApzwXepEQ/edit)
- [ ] **측정 스크립트로 응답 필드 확인.** `tps-bench` 폴더에서 실행한다. 추론 강도를 생략·low·max로 바꿔 가며 스트리밍과 비스트리밍 요청을 각각 1건씩 보낸다.

  ```sh
  python3 tps_bench.py check --efforts omit,low,max
  ```

  출력에서 세 가지를 본다. ① `time_info`가 스트리밍 응답에도 오는가. 오지 않으면 이후 `run`에 `--modes nostream`을 붙인다. ② `reasoning_tokens`가 보고되는가. ③ `low`·`max`가 거절되지 않는가. 거절되면 그 값을 `--efforts`에서 뺀다.

## 5. 실측 순서

- [ ] **1차 비교 40회.** 먼저 계획만 출력해 확인하고 실행한다. 분당 100요청·10만 토큰 한도 안에서 간격이 자동으로 조절되며, 2,048토큰 기준 최소 1분 남짓 걸린다. 중간에 Ctrl-C로 멈추면 화면에 나온 `--resume` 명령으로 이어 간다.

  ```sh
  python3 tps_bench.py run --dry-run
  ```

  ```sh
  python3 tps_bench.py run --label round1
  ```

- [ ] **집계.** 조건별 중앙값·최고값·표준편차, 출력 상한 도달 횟수, 완성도와 단일 최고 요청의 응답 ID를 확인한다. `--complete-only`는 끝까지 생성되고 형식 검사를 통과한 요청만 센다. 공식 산식이 공지되면 `--metric`으로 그 기준에 맞춰 정렬한다.

  ```sh
  python3 tps_bench.py summarize runs/<round1 폴더> --complete-only
  ```

- [ ] **상위 2개 재측정.** 같은 조건에서 각 10회 이상 실행한다. 아래 프롬프트와 추론 강도는 예시이므로 1차 결과로 바꾼다. 출력 상한을 바꿔 보려면 `--max-tokens 4096`을 붙인다.

  ```sh
  python3 tps_bench.py run --prompts P1,P2 --efforts max --reps 10 --label final
  ```

- [ ] **OpenClaw 사용 증빙.** 최종 후보 프롬프트를 OpenClaw로도 실행해 기록을 남긴다. CLI 경로의 TPS는 비교에 쓰지 않는다.

  ```sh
  python3 tps_bench.py run --path openclaw-cli --prompts P1 --efforts max --reps 1 --label openclaw-proof
  ```

  OpenClaw 경유 스트리밍 속도까지 필요하면 게이트웨이 HTTP 엔드포인트를 켜고 `--path openclaw-http`를 쓴다. 켜면 게이트웨이 토큰을 가진 로컬 호출자가 운영자 권한을 갖게 되므로, 필요할 때만 켜고 루프백 전용을 유지한다. 방법은 [README](<tps-bench/README.md>)에 있다.

**최종 출품 마감은 11월 23일 월요일 03:00 KST**다. 이때까지 데모를 X에 게시해야 한다. FAQ에 별도로 적힌 모델 접근 종료는 11월 24일 03:00이고, X·Reddit 반응 집계는 11월 25일 03:00이다. [공식 제출 일정](https://docs.google.com/document/d/1Vvf2SjScBt3yBeTVZRoKtOyE7rGEP-gWV_ApzwXepEQ/edit)
