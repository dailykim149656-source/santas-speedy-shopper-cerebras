# gift8 8회 비교 보고서

상태: **진행 중 또는 감사 보류**. 실제 전송 3/8회, 완료 기록 3/8회.

A는 모델의 gift_lookup 호출, B는 첫 모델 호출 전 상품 정보 주입입니다. 지정 순서는 ABBABAAB이며, 인접한 두 실행을 한 쌍으로 비교합니다.

공식 점수는 각 호출의 `outputTokens / (completionMs / 1000)`를 구한 뒤 모든 호출 속도를 산술평균합니다. 첫 호출과 최종 호출의 속도는 별도 진단값입니다.

| 조건 | 전송 | 유효 | 실패 | 종료 429 | 성공률 |
|---|---:|---:|---:|---:|---:|
| A | 1 | 1 | 0 | 0 | 100.0% |
| B | 2 | 1 | 1 | 1 | 50.0% |

| 실행 | 조건 | 유효 | 첫 호출 TPS | 최종 호출 TPS | 전체 호출 평균 TPS | UI | 호출 수 |
|---|---|---|---:|---:|---:|---:|---:|
| D5051-gift8-tool | A | 예 | 900.403 | 1,009.247 | 954.825 | 955 | 2 |
| D5052-gift8-prefetch | B | 예 | 1,059.615 | 1,059.615 | 1,059.615 | 1060 | 1 |
| D5053-gift8-prefetch | B | 아니요 | 749.564 | 없음 | 749.564 | 750 | 2 |

| 쌍 | A | B | 유효 | 첫 호출 B−A TPS | 공식 평균 B−A TPS | 제외 이유 |
|---|---|---|---|---:|---:|---|
| 1 | D5051-gift8-tool | D5052-gift8-prefetch | 예 | 159.212 | 104.790 | 없음 |
| 2 | 없음 | D5053-gift8-prefetch | 아니요 | 없음 | 없음 | A missing or invalid; B missing or invalid |
| 3 | 없음 | 없음 | 아니요 | 없음 | 없음 | A missing or invalid; B missing or invalid |
| 4 | 없음 | 없음 | 아니요 | 없음 | 없음 | A missing or invalid; B missing or invalid |

유효 비교쌍은 두 실행 모두 검증을 통과하고, 순서까지 같은 서로 다른 상품 URL 5개를 반환하며, 시작 시각 차이가 15분 이내인 경우입니다.

유효 1/4쌍. B의 첫 호출 우세 1쌍, 공식 평균 우세 1쌍. 첫 호출 차이 중앙값 159.212 TPS, 공식 평균 차이 중앙값 104.790 TPS.

로컬 실행 구간 비교 3003건(이 캠페인 관련 228건). 캠페인 중첩 0건, 미완료 전송 0건. 예약·해제 동일 PID 및 전 실행 구간 포함 검사는 미통과입니다.

중첩 감사 범위는 이번 gift8 전송과 로컬 main/exp의 모든 실행입니다. 같은 test 프로필의 과거 실행 41건은 상세 JSON에 제외 이유와 시각을 남겼으며, 이번 캠페인 중첩으로 계산하지 않았습니다.

| 영상 | 재검사 분류 | 첫 프레임 시점 | UI·5 URL 검증 | 1700 전체 실행 검증 |
|---|---|---|---|---|
| [D5051-gift8-tool-1e1b8cfa-attempt-01.mp4](<$SHOPPER_WORKSPACE/speed-bounty-evidence-test/.omo/evidence/gift8-report/demos/D5051-gift8-tool-1e1b8cfa-attempt-01.mp4>) | partial_or_post_run | first_frame_during_run | False | False |
| [D5052-gift8-prefetch-d88a6b09-attempt-01.mp4](<$SHOPPER_WORKSPACE/speed-bounty-evidence-test/.omo/evidence/gift8-report/demos/D5052-gift8-prefetch-d88a6b09-attempt-01.mp4>) | partial_or_post_run | first_frame_during_run | True | False |
| [D5053-gift8-prefetch-766237bd-attempt-01.mp4](<$SHOPPER_WORKSPACE/speed-bounty-evidence-test/.omo/evidence/gift8-report/demos/D5053-gift8-prefetch-766237bd-attempt-01.mp4>) | partial_or_post_run | first_frame_during_run | False | False |

원본 영상은 재생성하거나 편집하지 않았습니다. 복사한 모든 재생 가능 demo는 SHA256을 원본과 대조했습니다. 부분·종료 후 촬영은 전체 실행 증거로 인정하지 않습니다. 1700 TPS 대상은 같은 실행의 실제 UI 점수, 상품 URL 5개, 60초 이하 클립 및 전체 실행 시점 검증을 모두 요구합니다.

감사 오류: 없음

실행 실패 사유: D5053-gift8-prefetch: unsuccessful or unidentified assistant call, assistant call missing valid serverGeneration, run has no successful terminal event

주의 기록: legacy reservation lacks release: ~/Library/Caches/cerebras-speed-bounty/2026-11-22-test/mean-2000/first5027-5037-reservation.jsonl

미완료 전송 또는 닫히지 않은 예약이 있으면 완료 감사를 통과할 수 없습니다. 이 결과는 이번 실행 범위의 관측이며 하드웨어 성능이나 법적 사항으로 일반화하지 않습니다.

[상세 감사 JSON](<$SHOPPER_WORKSPACE/speed-bounty-evidence-test/.omo/evidence/gift8-report/current.audit.json>) · [출처·복사 파일 SHA256 목록](<$SHOPPER_WORKSPACE/speed-bounty-evidence-test/.omo/evidence/gift8-report/current.sha256.json>)
