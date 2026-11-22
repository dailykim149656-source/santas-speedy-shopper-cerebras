# 쇼핑 바운티 1,500 TPS 실험 결과

탐색 18/18회, 별도 확인 미배정. 예정된 실행을 마쳤다.

유효 최고는 [D5085-speed1500-a](<runs/1d100e81-3b0f-4d5e-8d26-fd930a340d78/evidence.json>)의 **1,154.82 TPS**다. 같은 실행에서 재검산한 정수 표시값은 1,155이다. [최고 실행 영상](<speed1500-artifacts/slots/006/attempt-001/media/demo.mp4>)

이전 자체 최고 **1,354.66 TPS**를 넘은 유효 세션 0회, 영상·화면까지 확인된 경신 0회, 공식 평균과 화면이 모두 **1,500 이상**인 검증 기록 0회. [D5027 원본](<runs/cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77/evidence.json>)

## 조건별 결과

탐색 6개 블록의 결과다. A는 D5027의 기본 조회, F는 같은 조회 후 최종 호출의 도구 정의 제거, P는 상품 실시간 선조회 후 Kimi가 답하는 조건이다. 중앙값과 최고에는 상품·방식 모두 유효한 세션만 포함했다.

| 조건 | 전송 | 상품 성공 | 상품·방식 유효 | 중앙값 TPS | 최고 TPS | 첫 호출 중앙값 | 최종 호출 중앙값 | 429 응답 / 종료 세션 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 6 | 2 | 2 | 1,072.57 | 1,154.82 | 1,186.95 | 958.20 | 46 / 4 |
| F | 6 | 3 | 3 | 903.72 | 1,033.90 | 761.55 | 950.72 | 40 / 3 |
| P | 6 | 2 | 2 | 661.23 | 728.42 | 661.23 | 661.23 | 49 / 4 |

## 최종 호출에서 관측한 추론 길이

탐색 중 상품과 방식을 모두 검증하고 최종 답변을 생성한 세션만 집계했다. 글자 수는 최종 응답에 기록된 추론 문자열의 길이다. 텍스트 블록만 있으면 관측값은 0자이며, 서버 내부의 추론량은 이 기록으로 알 수 없다. 블록 형식이 불완전하거나 가려진 경우는 관측 불가로 센다.

| 조건 | 유효 최종 | 0자 | 1자 이상 | 관측 불가 | 글자 수 중앙값 | 출력 토큰 중앙값 | 정확히 161토큰 | 최종 TPS 중앙값 (0자 / 1자 이상) | 0자이면서 최종 ≥1,500 TPS |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| A | 2 | 0 | 2 | 0 | 289.00 | 234.50 | 0 | — / 958.20 | 0 |
| F | 3 | 0 | 3 | 0 | 291.00 | 236.00 | 0 | — / 950.72 | 0 |
| P | 2 | 0 | 2 | 0 | 115.00 | 182.50 | 0 | — / 661.23 | 0 |

## 같은 블록 안에서의 비교

선별 기준은 완료한 18회 중 유효 대조쌍 4개 이상, A 대비 4승 이상, 차이 중앙값 +100 TPS 이상, 상품 성공 횟수 A 이상이다. 차이는 후보 세션 평균에서 같은 블록의 A 세션 평균을 뺀 값이다.

| 블록 | 전송 순서 | F − A TPS | P − A TPS |
|---:|---|---:|---:|
| 1 | AFP | — | — |
| 2 | PFA | — | -560.78 |
| 3 | FPA | — | — |
| 4 | APF | — | — |
| 5 | PAF | — | — |
| 6 | FAP | — | — |

F는 유효 0쌍 중 0승, 차이 중앙값 — TPS였다.

P는 유효 1쌍 중 0승, 차이 중앙값 -560.78 TPS였다.

선별 기준을 충족한 후보가 없어 추가 확인 4회는 배정하지 않았다.

## 실행별 근거

점수는 각 세션에서 제공사가 측정한 모든 생성의 출력 토큰 ÷ 서버 생성 초를 산술평균한 값이다. 실패 도중 남은 표본도 표시했다. 첫·최종 열의 같은 값은 단일 생성일 수 있다. 촬영 열은 요청 전 빈 세션 준비 / 화면의 점수와 상품 링크 5개가 확인된 영상 순서다. 429 열은 재시도 응답과 각 요청의 마지막 429까지 모두 센다.

| 슬롯 | 시작 KST | 조건 | 실행 증빙 | 상품 / 방식 | 측정 호출 | 첫 / 최종 TPS | 공식 평균 | UI 환산 | 촬영 | 429 응답 |
|---:|---|---|---|---|---:|---|---:|---:|---|---:|
| 1 | 11-22 21:50:23 | A | [D5080-speed1500-a](<runs/465ba4e8-bfe2-4722-b473-7d0ee418ffb4/evidence.json>) · [계획](<runs/465ba4e8-bfe2-4722-b473-7d0ee418ffb4/plan.json>) | × / × | 1 | 1,406.95 / — | 1,406.95 | 1407 | ✓ / × · [부분 영상](<speed1500-artifacts/slots/001/attempt-001/media/demo.mp4>) | 10 (종료) |
| 2 | 11-22 21:52:35 | F | [D5081-speed1500-f](<runs/28fb566b-2026-44b2-8b65-c328674734b2/evidence.json>) · [계획](<runs/28fb566b-2026-44b2-8b65-c328674734b2/plan.json>) | ✓ / ✓ | 2 | 700.45 / 1,106.98 | 903.72 | 904 | ✓ / ✓ · [영상](<speed1500-artifacts/slots/002/attempt-001/media/demo.mp4>) | 9 |
| 3 | 11-22 21:54:17 | P | [D5082-speed1500-p](<runs/33918883-0ac4-4135-a9dd-ea52eeff7fb8/evidence.json>) · [계획](<runs/33918883-0ac4-4135-a9dd-ea52eeff7fb8/plan.json>) | × / × | 0 | — / — | — | — | ✓ / × · [부분 영상](<speed1500-artifacts/slots/003/attempt-001/media/demo.mp4>) | 10 (종료) |
| 4 | 11-22 21:56:06 | P | [D5083-speed1500-p](<runs/4743db14-b132-45f7-a6be-38c772882920/evidence.json>) · [계획](<runs/4743db14-b132-45f7-a6be-38c772882920/plan.json>) | ✓ / ✓ | 1 | 594.04 / 594.04 | 594.04 | 594 | ✓ / ✓ · [영상](<speed1500-artifacts/slots/004/attempt-001/media/demo.mp4>) | 3 |
| 5 | 11-22 21:57:23 | F | [D5084-speed1500-f](<runs/e59bc099-20c7-41db-b7d7-7980567ac196/evidence.json>) · [계획](<runs/e59bc099-20c7-41db-b7d7-7980567ac196/plan.json>) | × / × | 1 | 801.82 / — | 801.82 | 802 | ✓ / × · [부분 영상](<speed1500-artifacts/slots/005/attempt-001/media/demo.mp4>) | 10 (종료) |
| 6 | 11-22 21:59:23 | A | [D5085-speed1500-a](<runs/1d100e81-3b0f-4d5e-8d26-fd930a340d78/evidence.json>) · [계획](<runs/1d100e81-3b0f-4d5e-8d26-fd930a340d78/plan.json>) | ✓ / ✓ | 2 | 1,206.65 / 1,102.99 | 1,154.82 | 1155 | ✓ / ✓ · [영상](<speed1500-artifacts/slots/006/attempt-001/media/demo.mp4>) | 6 |
| 7 | 11-22 22:00:56 | F | [D5086-speed1500-f](<runs/76d7f298-699e-4068-a082-319a95db477f/evidence.json>) · [계획](<runs/76d7f298-699e-4068-a082-319a95db477f/plan.json>) | ✓ / ✓ | 2 | 761.55 / 662.29 | 711.92 | 712 | ✓ / ✓ · [영상](<speed1500-artifacts/slots/007/attempt-001/media/demo.mp4>) | 0 |
| 8 | 11-22 22:02:12 | P | [D5087-speed1500-p](<runs/058d3a3a-0131-44e8-8367-5bbe14d73bd5/evidence.json>) · [계획](<runs/058d3a3a-0131-44e8-8367-5bbe14d73bd5/plan.json>) | × / × | 0 | — / — | — | — | ✓ / × · [부분 영상](<speed1500-artifacts/slots/008/attempt-001/media/demo.mp4>) | 10 (종료) |
| 9 | 11-22 22:04:02 | A | [D5088-speed1500-a](<runs/e4b4ce0b-f794-4aea-83fa-76f37095f560/evidence.json>) · [계획](<runs/e4b4ce0b-f794-4aea-83fa-76f37095f560/plan.json>) | × / × | 0 | — / — | — | — | ✓ / × · [부분 영상](<speed1500-artifacts/slots/009/attempt-001/media/demo.mp4>) | 10 (종료) |
| 10 | 11-22 22:05:49 | A | [D5089-speed1500-a](<runs/60639bee-cbde-4ca4-b646-63ba18dee125/evidence.json>) · [계획](<runs/60639bee-cbde-4ca4-b646-63ba18dee125/plan.json>) | × / × | 0 | — / — | — | — | ✓ / × · [부분 영상](<speed1500-artifacts/slots/010/attempt-001/media/demo.mp4>) | 10 (종료) |
| 11 | 11-22 22:07:37 | P | [D5090-speed1500-p](<runs/bca8114e-28fe-4d07-ae0e-4b863788dacc/evidence.json>) · [계획](<runs/bca8114e-28fe-4d07-ae0e-4b863788dacc/plan.json>) | ✓ / ✓ | 1 | 728.42 / 728.42 | 728.42 | 728 | ✓ / ✓ · [영상](<speed1500-artifacts/slots/011/attempt-001/media/demo.mp4>) | 6 |
| 12 | 11-22 22:09:08 | F | [D5091-speed1500-f](<runs/2557403a-d577-4d11-820f-8d0fe11e8a1a/evidence.json>) · [계획](<runs/2557403a-d577-4d11-820f-8d0fe11e8a1a/plan.json>) | × / × | 0 | — / — | — | — | ✓ / × · [부분 영상](<speed1500-artifacts/slots/012/attempt-001/media/demo.mp4>) | 10 (종료) |
| 13 | 11-22 22:10:57 | P | [D5092-speed1500-p](<runs/7b358226-5b83-4399-9af9-bb39b1db867e/evidence.json>) · [계획](<runs/7b358226-5b83-4399-9af9-bb39b1db867e/plan.json>) | × / × | 0 | — / — | — | — | ✓ / × · [부분 영상](<speed1500-artifacts/slots/013/attempt-001/media/demo.mp4>) | 10 (종료) |
| 14 | 11-22 22:12:48 | A | [D5093-speed1500-a](<runs/6d0f041f-3bba-4029-9ab4-1587fff0deb1/evidence.json>) · [계획](<runs/6d0f041f-3bba-4029-9ab4-1587fff0deb1/plan.json>) | × / × | 0 | — / — | — | — | ✓ / × · [부분 영상](<speed1500-artifacts/slots/014/attempt-001/media/demo.mp4>) | 10 (종료) |
| 15 | 11-22 22:14:36 | F | [D5094-speed1500-f](<runs/54279a8c-36a9-4316-b50d-0d797873b69e/evidence.json>) · [계획](<runs/54279a8c-36a9-4316-b50d-0d797873b69e/plan.json>) | ✓ / ✓ | 2 | 1,117.07 / 950.72 | 1,033.90 | 1034 | ✓ / ✓ · [영상](<speed1500-artifacts/slots/015/attempt-001/media/demo.mp4>) | 1 |
| 16 | 11-22 22:15:56 | F | [D5095-speed1500-f](<runs/8205f87a-71eb-4fcb-aa13-217b81a723b4/evidence.json>) · [계획](<runs/8205f87a-71eb-4fcb-aa13-217b81a723b4/plan.json>) | × / × | 0 | — / — | — | — | ✓ / × · [부분 영상](<speed1500-artifacts/slots/016/attempt-001/media/demo.mp4>) | 10 (종료) |
| 17 | 11-22 22:17:45 | A | [D5096-speed1500-a](<runs/aee0624e-ec5b-4b15-8266-a48d0f586cb9/evidence.json>) · [계획](<runs/aee0624e-ec5b-4b15-8266-a48d0f586cb9/plan.json>) | ✓ / ✓ | 2 | 1,167.26 / 813.40 | 990.33 | 990 | ✓ / ✓ · [영상](<speed1500-artifacts/slots/017/attempt-001/media/demo.mp4>) | 0 |
| 18 | 11-22 22:19:05 | P | [D5097-speed1500-p](<runs/633ed6af-d7b3-4b3b-af47-30c775cf2181/evidence.json>) · [계획](<runs/633ed6af-d7b3-4b3b-af47-30c775cf2181/plan.json>) | × / × | 0 | — / — | — | — | ✓ / × · [부분 영상](<speed1500-artifacts/slots/018/attempt-001/media/demo.mp4>) | 10 (종료) |

## 호출별 서버 측정값

입력 해시는 릴레이가 전송한 요청 본문의 SHA-256 앞 12자리다. 링크에서 전체 해시와 각 시도의 HTTP 응답을 확인할 수 있다.

| 슬롯 | 생성 | 종료 | 출력 토큰 | 생성 ms | TPS | 입력 해시 |
|---:|---:|---|---:|---:|---:|---|
| 1 | 1 | toolUse | 388 | 275.77465 | 1,406.95 | [b52ebbc21ad7](<speed1500-artifacts/slots/001/relay.json>) |
| 2 | 1 | toolUse | 391 | 558.21296 | 700.45 | [3cf2428ff6a4](<speed1500-artifacts/slots/002/relay.json>) |
| 2 | 2 | stop | 235 | 212.28870 | 1,106.98 | [0084fa7172b9](<speed1500-artifacts/slots/002/relay.json>) |
| 4 | 1 | stop | 182 | 306.37715 | 594.04 | [8940220b20de](<speed1500-artifacts/slots/004/relay.json>) |
| 5 | 1 | toolUse | 398 | 496.37083 | 801.82 | [b59d8e89488f](<speed1500-artifacts/slots/005/relay.json>) |
| 6 | 1 | toolUse | 396 | 328.18047 | 1,206.65 | [d401107e6435](<speed1500-artifacts/slots/006/relay.json>) |
| 6 | 2 | stop | 236 | 213.96442 | 1,102.99 | [3ff408dbe410](<speed1500-artifacts/slots/006/relay.json>) |
| 7 | 1 | toolUse | 407 | 534.43914 | 761.55 | [f2499bf00f50](<speed1500-artifacts/slots/007/relay.json>) |
| 7 | 2 | stop | 236 | 356.33747 | 662.29 | [3418223cc216](<speed1500-artifacts/slots/007/relay.json>) |
| 11 | 1 | stop | 183 | 251.22970 | 728.42 | [190977a18135](<speed1500-artifacts/slots/011/relay.json>) |
| 15 | 1 | toolUse | 391 | 350.02259 | 1,117.07 | [d24ea91683d4](<speed1500-artifacts/slots/015/relay.json>) |
| 15 | 2 | stop | 236 | 248.23311 | 950.72 | [6b0141ff476b](<speed1500-artifacts/slots/015/relay.json>) |
| 17 | 1 | toolUse | 383 | 328.12021 | 1,167.26 | [d4e1d10a0caa](<speed1500-artifacts/slots/017/relay.json>) |
| 17 | 2 | stop | 233 | 286.45035 | 813.40 | [f447cdb91151](<speed1500-artifacts/slots/017/relay.json>) |

## 원본 검산과 해석

새 세션 전송 18회에서 고유 실행 ID 18개를 대조했다. 릴레이에 기록된 제공사 HTTP 요청은 재시도 포함 149회, 시간 측정이 있는 생성은 14회다. 429 응답은 총 135회로, 다음 시도로 이어진 429는 124회다. 촬영 준비가 전송보다 빠른 세션은 18회다. P의 판매처 영수증 5개와 실제 모델 입력을 대조한 실행 6회, 상품·방식 모두 유효한 P 단일 생성 2회, P 전체 전송 6회다.

상세 페이지의 HTTP 상태와 본문 해시는 당시 검증 기록을 사용했다. F의 처음·복구 요청은 수신·전송 바이트 해시로, 최종 요청은 릴레이의 변경 필드 기록 및 보관한 전송 본문으로 확인했다. 429는 제공사 요청 횟수와 세션 성공률에 반영한다. 서비스 부하와 개별 생성 속도의 인과관계는 이 자료에서 분리할 수 없다.

사용자는 Claude에서 같은 API 키로 진행하던 별도 재실험을 중지했다고 알려 왔으며, 해당 진단은 탐색 18회 집계에서 제외했고 두 실험의 정확한 중첩 시각과 429의 원인은 확인되지 않았다.

**유효 비교에서 제외한 실행**

- D5080-speed1500-a · 제공사 429로 최종 응답 실패. [검증 내역](<speed1500-artifacts/slots/001/validation.json>)
- D5082-speed1500-p · 제공사 429로 최종 응답 실패. [검증 내역](<speed1500-artifacts/slots/003/validation.json>)
- D5084-speed1500-f · 제공사 429로 최종 응답 실패. [검증 내역](<speed1500-artifacts/slots/005/validation.json>)
- D5087-speed1500-p · 제공사 429로 최종 응답 실패. [검증 내역](<speed1500-artifacts/slots/008/validation.json>)
- D5088-speed1500-a · 제공사 429로 최종 응답 실패. [검증 내역](<speed1500-artifacts/slots/009/validation.json>)
- D5089-speed1500-a · 제공사 429로 최종 응답 실패. [검증 내역](<speed1500-artifacts/slots/010/validation.json>)
- D5091-speed1500-f · 제공사 429로 최종 응답 실패. [검증 내역](<speed1500-artifacts/slots/012/validation.json>)
- D5092-speed1500-p · 제공사 429로 최종 응답 실패. [검증 내역](<speed1500-artifacts/slots/013/validation.json>)
- D5093-speed1500-a · 제공사 429로 최종 응답 실패. [검증 내역](<speed1500-artifacts/slots/014/validation.json>)
- D5095-speed1500-f · 제공사 429로 최종 응답 실패. [검증 내역](<speed1500-artifacts/slots/016/validation.json>)
- D5097-speed1500-p · 제공사 429로 최종 응답 실패. [검증 내역](<speed1500-artifacts/slots/018/validation.json>)

## 다음 비교

비교 가능한 블록이 4개 미만인 후보가 있다. 다음 탐색은 같은 설정으로 A와 해당 후보를 교차해 빠졌던 유효 쌍을 확보하는 데 우선 배정할 수 있다.

최고 실행의 원본과 검증 자료 · [세션 원본](<runs/1d100e81-3b0f-4d5e-8d26-fd930a340d78/evidence.json>) · [상품 검증](<speed1500-artifacts/slots/006/validation.json>) · [릴레이 요청](<speed1500-artifacts/slots/006/relay.json>)

완료된 슬롯의 원본 해시·호출별 산식·전송 식별자 대조에서 불일치가 없었다.
