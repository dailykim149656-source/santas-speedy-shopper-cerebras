# Santa’s Speedy Shopper | 우리 평균 1,355 TPS를 넘은 신규 출품작

2026년 11월 23일 01:31 KST 기준, Cerebras Discord의 `#share-your-demo`에서 우리 D5027 제출의 **1,355 TPS mean**을 기준으로 조사했다. 당시 포럼에 표시된 게시물 60개의 제목과 미리보기를 훑고, 바운티 후보는 본문과 후속 댓글을 확인했다. 기존에 조사한 BrightyBrainiac 4개 스레드와 Akghost96의 1,673 스레드는 중복에서 뺐다. 아래 두 건은 공개 GitHub 저장소가 있고 Discord 영상에서 공식 패치의 세션 평균이 1,355를 넘는 것을 확인한 신규 게시글이다. 이번 조사에서는 모델을 다시 호출하지 않았다. [우리 제출](https://discord.com/channels/1085960591052644463/1573948252687040512/1573948252687040512)

## 저장소에 관한 공식 문구

공지에는 **“GitHub Repository (recommended)”**라고 적혀 있다. 11월 22일 11:58 KST에 InventorBlack은 저장소가 있는 상위 출품작의 수치를 운영진이 직접 재검증할 가능성이 높다고 했고, 팀과 확인해야 한다고 덧붙였다. 12:04에는 GitHub 저장소를 열어 두고 프로젝트를 쉽게 재현할 수 있게 해 달라고 했다. 확인한 공지와 후속 답변에는 공개 저장소 미제출을 자동 실격으로 정한 문구가 없다. **공개 저장소를 요구한 것은 이번 비교의 조사 조건**이다. 최종 수상 여부는 운영진이 판단한다. [공지](https://discord.com/channels/1085960591052644463/1573839018964029450/1573839018964029450) · [11:58 운영진 답변](https://discord.com/channels/1085960591052644463/1573839018964029450/1573895377885855805) · [12:04 운영진 답변](https://discord.com/channels/1085960591052644463/1573839018964029450/1573896905308774414)

## 조사 결과

| 출품작 | 영상의 mean | 우리와 차이 | 영상의 p90 | 영상 길이 | 확인할 수 있는 근거 |
|---|---:|---:|---:|---:|---|
| [DeLunar · Cerebras OpenClaw Search](https://discord.com/channels/1085960591052644463/1574090300102676531/1574090300102676531) | 1,469 | +114 | 1,483 | 35.00초 | 영상 수치와 호출 2건의 공개 CSV가 일치한다. |
| [nishia 팀 · agyoneshot](https://discord.com/channels/1085960591052644463/1574026992167292958/1574026992167292958) | 1,464 | +109 | 1,678 | 84.72초 | Discord 영상과 저장소 이력에 같은 점수가 있다. 해당 실행의 호출별 기록은 미확인이다. |

### DeLunar | 호출 기록을 재계산할 수 있는 제출

- Kimi의 첫 응답은 `kids toy`, `candle`, `blanket`, `dog toy`, `coffee mug` 다섯 카테고리에 대해 도구를 한 번씩 병렬 호출한다. 검색 MCP 서버가 Shopify 카탈로그를 조회해 카테고리별 한 상품을 돌려주면, Kimi의 둘째 응답이 다섯 결과를 한 줄 JSON으로 출력한다. 미국 배송 조건으로 결과가 비면 그 조건을 빼고 다시 조회하므로 실제 HTTP 요청 수는 달라질 수 있다. [프롬프트](https://github.com/Ahmad-FP/cerebras-openclaw-search/blob/7ddb3f5e17af23d31c0f646695ff8ece8dd13a67/prompt.txt#L1-L8) · [검색 구현](https://github.com/Ahmad-FP/cerebras-openclaw-search/blob/7ddb3f5e17af23d31c0f646695ff8ece8dd13a67/gift-search-mcp.mjs#L44-L75)
- 같은 실행 ID에 Cerebras 응답 ID 2개가 있다. 공개 CSV의 서버 생성 시간으로 각각 계산하면 281토큰 ÷ 0.189492009초 = 1,482.91 TPS와 285토큰 ÷ 0.195978377초 = 1,454.24 TPS다. 두 값의 산술평균은 **1,468.58**로 영상의 1,469와 일치한다. 저자는 다른 실행 상당수가 950~1,150 수준이었다고 설명한다. 이 1,469는 한 세션 안의 평균이며 반복 실험 전체의 평균을 뜻하지 않는다. [호출별 CSV](https://github.com/Ahmad-FP/cerebras-openclaw-search/blob/7ddb3f5e17af23d31c0f646695ff8ece8dd13a67/evidence/cf12d9ba-d865-425e-b803-b15f98f75c2c.csv#L1-L3) · [저장소 설명](https://github.com/Ahmad-FP/cerebras-openclaw-search/tree/7ddb3f5e17af23d31c0f646695ff8ece8dd13a67)
- CLI 실행을 마친 뒤 찍은 35초 영상에 패치 수치와 다섯 상품이 나온다. 게시글의 캔들 주소는 `/products`에서 끝나지만 영상과 저장소에는 전체 주소가 있다. 로봇 자동차, 캔들, 담요, 반려견 장난감, 머그잔 다섯 판매 페이지 모두 조사 시점에 HTTP 200과 상품 메타데이터를 반환했다. 원본 도구 응답과 전체 대화는 저장소에 없으며, 재실행할 때 MCP 파일 경로를 현지 설치 경로에 맞춰야 한다. [원본 영상이 있는 게시글](https://discord.com/channels/1085960591052644463/1574090300102676531/1574090300102676531) · [상품 목록](https://github.com/Ahmad-FP/cerebras-openclaw-search/blob/7ddb3f5e17af23d31c0f646695ff8ece8dd13a67/README.md#L42-L55) · [캔들 판매 페이지](https://goosecreek.com/products/warm-welcome-large-3-wick-candle?variant=40236410830923)

### nishia 팀 | 영상에서 평균을 확인할 수 있고 재현에는 추가 준비가 필요한 제출

- Discord 영상 약 12.5초에 **1,464 mean / 1,678 p90 (server)**, 약 15초에 다섯 상품 링크가 보인다. 제목이 ‘max’로 부른 1,678은 화면에서 p90으로 표시된다. 성공 세션에는 로봇 자동차, 책상, 캔들, 담요, 반려견 장난감이 있다. 초반 재시도와 성공 화면의 세션 이름이 다르다. 첨부 원본은 **84.72초**로 공지의 60초 상한을 **24.72초** 넘는다. [제출 영상·다섯 상품 링크](https://discord.com/channels/1085960591052644463/1574026992167292958/1574026992167292958)
- 첫 모델 호출이 Shopify에서 카테고리 5개를 한 턴에 병렬 검색하고, 두 번째 호출이 상품별 일곱 필드를 한 줄 JSON에 복사한다. 실행 스크립트는 설치된 OpenClaw의 전송 코드에 패치를 적용하며 두 번째 호출에서 도구 정의를 제거한다. 재실행하려면 스크립트가 예상하는 OpenClaw 빌드 파일과 경로, MCP 등록, 공식 속도 패치 설치가 필요하다. [전송 코드](https://github.com/xinjiav2/agyoneshot/blob/4f65cb6e328b062f19a36348d527c98342d60a87/openclaw-patches/apply-patches.mjs#L127-L156) · [필수 파일 경로](https://github.com/xinjiav2/agyoneshot/blob/4f65cb6e328b062f19a36348d527c98342d60a87/openclaw-patches/apply-patches.mjs#L29-L45) · [Shopify 검색](https://github.com/xinjiav2/agyoneshot/blob/a6836efe69e14dc49c3e949811f1f0f60f8be7c3/openclaw-patches/shopify-catalog-mcp.mjs#L35-L75)
- 게시글이 안내하는 `1402` 브랜치 README의 기록은 **1,402 mean / 1,523 p90**이다. **1,464**라고 표시된 후속 커밋과 **1,464 / 1,678**을 명시한 별도 README는 찾았다. 두 커밋에 들어 있는 MP4는 이전 **923 mean / 1,082 p90** 영상이다. 해당 실행을 확인할 때는 Discord 첨부 영상이 맞고, 호출별 원본으로 1,464를 독립 재계산할 수 있는 자료는 이 커밋들에서 찾지 못했다. [게시글이 가리키는 README](https://github.com/xinjiav2/agyoneshot/blob/a6836efe69e14dc49c3e949811f1f0f60f8be7c3/README.md#L41-L46) · [1,464 커밋](https://github.com/xinjiav2/agyoneshot/commit/4f65cb6e328b062f19a36348d527c98342d60a87) · [두 수치가 있는 README](https://github.com/xinjiav2/agyoneshot/blob/dcb4a8cd71d4d0a731f6fbf04c493c04a9218793/README.md#L38-L44)

## 큰 숫자를 내걸었지만 비교 대상에서 빠진 공개 저장소

| 게시글 | 확인한 내용 |
|---|---|
| [Herobrine · 1,522.84 TPS](https://discord.com/channels/1085960591052644463/1574026394147623083/1574026394147623083) | 공개 재현 명령은 자체 Python CLI에서 Cerebras API를 한 번 호출한다. 측정 요약의 mean과 peak가 같고, 프롬프트에는 다섯 상품과 가격·URL이 이미 들어 있다. 공개 증거에서 공식 패치로 실시간 선물 검색을 수행한 세션 평균은 확인할 수 없다. [원시 요약](https://github.com/sagarrathi16/hypertps/blob/929a24c78271048a082a80033f42685439c22669/dist/benchmark_summary_run02_santa_1522tps.json#L5-L13) · [프롬프트](https://github.com/sagarrathi16/hypertps/blob/929a24c78271048a082a80033f42685439c22669/src/hypertps/bounty.py#L83-L96) |
| [your_jo · Repo Reborn 1,797 TPS](https://discord.com/channels/1085960591052644463/1574067852795973682/1574067852795973682) | 저장소를 수정하고 PR을 여는 과제다. 본문에 세 차례 중 최고 기록이고 Kimi 접근 대기 중 대체 모델로 실행했다고 적었다. [프로젝트](https://github.com/Prasannaverse13/Repo-Reborn) |
| [$Jimmy · +2k TPS](https://discord.com/channels/1085960591052644463/1573910713498472559/1573910713498472559) | 3D 레이싱 게임을 생성한 제출이다. 선물 검색 세션의 패치 평균은 제시하지 않았다. [프로젝트](https://github.com/JimmyOgb/Kimi-k3.1_Pro) |

이번 두 건 모두 **모델 호출 2회, 첫 응답에서 카테고리 검색 도구 5회 병렬 호출**이라는 구조다. **카탈로그 도구 한 번이 다섯 상품을 모두 반환하는 방식**을 이 두 건이 입증하지는 않는다. 또한 두 사례만으로 병렬 검색이 우리 제출과의 109~114 TPS 차이를 만들었다고 단정할 수 없다.
