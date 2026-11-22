# 쇼핑 바운티 실행 기록

각 실행 ID를 열면 Git 계획 커밋, Cerebras가 반환한 출력 토큰 수와 생성 시간, 판매처 조회 결과를 확인할 수 있다. 현재 표시 평균 900 tok/s 이상이면 녹화를 검증한다. 검증된 공식 평균이 종전 최고 기록을 갱신하면 기준 미만이어도 보관한다. 최고 기록의 원본과 60초 이하 영상 한 쌍을 로컬에 보관한다. 실행별 측정값과 보관했던 영상 해시는 Git에서 확인할 수 있다.

| 실행 | 요청 | 공식 평균 (tok/s) | 상품 검증 | 영상 |
|---|---|---:|---|---|
| [D6007-exp2k-call0-zero-think](runs/732e44a1-4a8f-4008-a6c4-0137d613423c/evidence.json) | [요청문](runs/732e44a1-4a8f-4008-a6c4-0137d613423c/plan.json) | 931 | 0/5 · 검증 미통과 | 상품 검증 미통과 · 영상 미보관 |
| [D6006-synth-five-categories-cap-4000](runs/7f294f6b-6923-43d5-9b66-bbfbb9e1951c/evidence.json) | [요청문](runs/7f294f6b-6923-43d5-9b66-bbfbb9e1951c/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D6005-exp2k-call0-zero-think](runs/ff460801-bc47-4304-8eed-288cd80a26f3/evidence.json) | [요청문](runs/ff460801-bc47-4304-8eed-288cd80a26f3/plan.json) | 912 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D6004-synth-five-categories-cap-4000](runs/ad73a718-76b4-4d9e-8113-082f766e4e94/evidence.json) | [요청문](runs/ad73a718-76b4-4d9e-8113-082f766e4e94/plan.json) | 804 | 0/5 · 검증 미통과 | 기준 미만 |
| [D6003-exp2k-call0-zero-think](runs/951ffd9d-eeaa-42c1-9ad6-98d84f8d7042/evidence.json) | [요청문](runs/951ffd9d-eeaa-42c1-9ad6-98d84f8d7042/plan.json) | 894 | 5/5 | 기준 미만 |
| [D6002-exp2k-call0-zero-think](runs/01eed585-4abf-4dc1-9d5b-03e44077f03f/evidence.json) | [요청문](runs/01eed585-4abf-4dc1-9d5b-03e44077f03f/plan.json) | 1037 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D6001-synth-five-categories-cap-4000](runs/aa69d31e-0e7d-48d1-a9f0-c642074c9340/evidence.json) | [요청문](runs/aa69d31e-0e7d-48d1-a9f0-c642074c9340/plan.json) | 1220 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5017-synth-five-categories-cap-4000](runs/2fe4b0df-f98c-474f-9bb9-00ea69c7bab0/evidence.json) | [요청문](runs/2fe4b0df-f98c-474f-9bb9-00ea69c7bab0/plan.json) | 944 | 5/5 | 검증 대기 · 촬영 원본은 복구용 폴더에 보관 |
| [D5016-synth-five-categories-cap](runs/7679d3a4-47ac-488a-ae2f-745a411215a0/evidence.json) | [요청문](runs/7679d3a4-47ac-488a-ae2f-745a411215a0/plan.json) | 588 | 5/5 | 기준 미만 |
| [D5015-synth-five-categories-cap](runs/711e5e42-3760-4d39-916a-520b12cc0009/evidence.json) | [요청문](runs/711e5e42-3760-4d39-916a-520b12cc0009/plan.json) | 777 | 5/5 | 기준 미만 |
| [D5014-synth-five-categories-cap](runs/5e8b6697-24d0-4ce6-b823-26dca2a64cfc/evidence.json) | [요청문](runs/5e8b6697-24d0-4ce6-b823-26dca2a64cfc/plan.json) | 897 | 5/5 | 기준 미만 |
| [D5013-synth-first-five](runs/ae055c24-fcb9-4e05-92f2-11dd6e6a6986/evidence.json) | [요청문](runs/ae055c24-fcb9-4e05-92f2-11dd6e6a6986/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5012-synth-five-categories-cap](runs/8c0618a4-c73e-4e93-9272-42d4697ec02d/evidence.json) | [요청문](runs/8c0618a4-c73e-4e93-9272-42d4697ec02d/plan.json) | 875 | 5/5 | 기준 미만 |
| [D5011-synth-five-categories-cap](runs/0f3d9367-99ab-41ae-975f-5df9c7f845ee/evidence.json) | [요청문](runs/0f3d9367-99ab-41ae-975f-5df9c7f845ee/plan.json) | 1139 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5010-synth-five-categories-cap](runs/ec8a1f02-2fc0-4783-a4bb-6601bc3b9108/evidence.json) | [요청문](runs/ec8a1f02-2fc0-4783-a4bb-6601bc3b9108/plan.json) | 1048 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5009-synth-five-categories-cap](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) | [요청문](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/plan.json) | 1301 | 5/5 | [원본](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/original.mp4) · [60초 이내](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/demo.mp4) · 로컬 보관 |
| [D5008-synth-first-five](runs/7cb8366c-9d44-422b-861e-c6649deac3b4/evidence.json) | [요청문](runs/7cb8366c-9d44-422b-861e-c6649deac3b4/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5007-synth-five-categories-cap](runs/ad645a7f-b4ef-4e4d-a688-c0a75a634bfe/evidence.json) | [요청문](runs/ad645a7f-b4ef-4e4d-a688-c0a75a634bfe/plan.json) | 1138 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5006-synth-first-five-short-cap](runs/260ce679-020f-4230-be3f-2ac04e70766d/evidence.json) | [요청문](runs/260ce679-020f-4230-be3f-2ac04e70766d/plan.json) | 701 | 5/5 | 기준 미만 |
| [D5005-synth-first-five-short-cap](runs/f85deda5-5cbb-4ab2-8e7a-91dd697ac1d6/evidence.json) | [요청문](runs/f85deda5-5cbb-4ab2-8e7a-91dd697ac1d6/plan.json) | 1095 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5004-synth-first-five](runs/b11ab278-42de-485c-bbb2-e41d79d96851/evidence.json) | [요청문](runs/b11ab278-42de-485c-bbb2-e41d79d96851/plan.json) | 715 | 5/5 | 기준 미만 |
| [D0071-synth-first-five-direct-fetch](runs/7bd1e221-bcdc-4606-9826-28d82d564faa/evidence.json) | [요청문](runs/7bd1e221-bcdc-4606-9826-28d82d564faa/plan.json) | 561 | 5/5 | 기준 미만 |
| [D0070-synth-first-five](runs/4799b3be-cd06-4ace-845d-fce9880aa269/evidence.json) | [요청문](runs/4799b3be-cd06-4ace-845d-fce9880aa269/plan.json) | 734 | 5/5 | 기준 미만 |
| [D0069-synth-first-five-direct-fetch](runs/0b200914-fc24-4535-a570-e3ace6593ac4/evidence.json) | [요청문](runs/0b200914-fc24-4535-a570-e3ace6593ac4/plan.json) | 858 | 5/5 | 기준 미만 |
| [D0068-synth-first-five-direct-fetch](runs/a0ed98ba-2594-47e0-a081-8ce21873afdf/evidence.json) | [요청문](runs/a0ed98ba-2594-47e0-a081-8ce21873afdf/plan.json) | 539 | 0/5 · 검증 미통과 | 기준 미만 |
| [D0066-synth-first-five](runs/a2a07285-0cd9-451f-82e4-9e98d63ffdd6/evidence.json) | [요청문](runs/a2a07285-0cd9-451f-82e4-9e98d63ffdd6/plan.json) | 835 | 5/5 | 기준 미만 |
| [D0065-synth-first-five](runs/192ea8c6-a758-499d-9823-ee730f42130a/evidence.json) | [요청문](runs/192ea8c6-a758-499d-9823-ee730f42130a/plan.json) | 708 | 5/5 | 기준 미만 |
| [D0064-research-reasoning-max](runs/27dccf07-cea5-4ce6-8f8d-91e76c079429/evidence.json) | [요청문](runs/27dccf07-cea5-4ce6-8f8d-91e76c079429/plan.json) | 482 | 5/5 | 기준 미만 |
| [D0063-synth-first-five](runs/e7b2c169-0b73-4057-b923-3fee2429471c/evidence.json) | [요청문](runs/e7b2c169-0b73-4057-b923-3fee2429471c/plan.json) | 935 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D0062-synth-first-five](runs/9e52f8c0-dcae-4acc-bba1-5139caf0d13a/evidence.json) | [요청문](runs/9e52f8c0-dcae-4acc-bba1-5139caf0d13a/plan.json) | 1049 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D0061-synth-first-five-six](runs/42ce71ce-a705-4d6a-ace5-9346c958a3f2/evidence.json) | [요청문](runs/42ce71ce-a705-4d6a-ace5-9346c958a3f2/plan.json) | 738 | 5/5 | 기준 미만 |
| [D0060-synth-first-five](runs/1fff9c7b-ec8c-45af-9295-32fd9c2b60f1/evidence.json) | [요청문](runs/1fff9c7b-ec8c-45af-9295-32fd9c2b60f1/plan.json) | 602 | 0/5 · 검증 미통과 | 기준 미만 |
| [D0059-synth-first-five](runs/6d264092-8437-4a39-959c-ef80c9e70eeb/evidence.json) | [요청문](runs/6d264092-8437-4a39-959c-ef80c9e70eeb/plan.json) | 641 | 5/5 | 기준 미만 |
| [D0058-synth-links-temp-one](runs/9fe67598-bae9-4a31-90e4-6fa7786e43de/evidence.json) | [요청문](runs/9fe67598-bae9-4a31-90e4-6fa7786e43de/plan.json) | 694 | 5/5 | 기준 미만 |
| [D0057-synth-first-five](runs/40fd2fa7-57b9-4af1-9c1f-9af7a6cfbf26/evidence.json) | [요청문](runs/40fd2fa7-57b9-4af1-9c1f-9af7a6cfbf26/plan.json) | 791 | 5/5 | 기준 미만 |
| [D0056-synth-first-five](runs/561ce393-5ab5-4fe7-9515-b7d60c3cd2d3/evidence.json) | [요청문](runs/561ce393-5ab5-4fe7-9515-b7d60c3cd2d3/plan.json) | 919 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D0055-synth-links-no-workspace](runs/df246b66-1882-4021-baf2-9da4e3a74b4e/evidence.json) | [요청문](runs/df246b66-1882-4021-baf2-9da4e3a74b4e/plan.json) | 612 | 5/5 | 기준 미만 |
| [D0054-synth-first-five](runs/eb9dc7e4-9416-4b58-8355-3b088387cb6a/evidence.json) | [요청문](runs/eb9dc7e4-9416-4b58-8355-3b088387cb6a/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D0053-synth-first-five](runs/644885b4-c3ae-467f-8147-0b4b4dce21c1/evidence.json) | [요청문](runs/644885b4-c3ae-467f-8147-0b4b4dce21c1/plan.json) | 561 | 0/5 · 검증 미통과 | 기준 미만 |
| [D0052-synth-links-brief](runs/5fc79a59-d9ec-4569-9c5f-cca0959aea3d/evidence.json) | [요청문](runs/5fc79a59-d9ec-4569-9c5f-cca0959aea3d/plan.json) | 729 | 5/5 | 기준 미만 |
| [D0051-synth-first-five](runs/32d0c9ee-14ff-4846-8a5f-1fbd2b278370/evidence.json) | [요청문](runs/32d0c9ee-14ff-4846-8a5f-1fbd2b278370/plan.json) | 617 | 5/5 | 기준 미만 |
| [D0050-synth-first-five](runs/e7c9e231-6cdc-42d4-aa8f-f8fb809834f2/evidence.json) | [요청문](runs/e7c9e231-6cdc-42d4-aa8f-f8fb809834f2/plan.json) | 857 | 5/5 | 기준 미만 |
| [D0049-synth-first-five](runs/9d7eae61-fb03-45b8-b59b-4dda67887c92/evidence.json) | [요청문](runs/9d7eae61-fb03-45b8-b59b-4dda67887c92/plan.json) | 744 | 5/5 | 기준 미만 |
| [D0048-synth-links](runs/fe3f0a6d-44cc-4443-9dc9-4c62e6382bb6/evidence.json) | [요청문](runs/fe3f0a6d-44cc-4443-9dc9-4c62e6382bb6/plan.json) | 531 | 5/5 | 기준 미만 |
| [D0047-source-order-synth](runs/e7f144c7-ac55-46e4-ba74-9318985e29d6/evidence.json) | [요청문](runs/e7f144c7-ac55-46e4-ba74-9318985e29d6/plan.json) | 602 | 5/5 | 기준 미만 |
| [D0046-synth-links](runs/7d4ff600-5be0-43be-a78a-d2ffdd36370d/evidence.json) | [요청문](runs/7d4ff600-5be0-43be-a78a-d2ffdd36370d/plan.json) | 846 | 5/5 | 기준 미만 |
| [D0045-source-order-synth](runs/a0a91043-9502-44cb-b482-ae450d41d28e/evidence.json) | [요청문](runs/a0a91043-9502-44cb-b482-ae450d41d28e/plan.json) | 564 | 5/5 | 기준 미만 |
| [D0044-source-order-synth](runs/ec6023c4-3ceb-4776-9a8a-766bb84b741e/evidence.json) | [요청문](runs/ec6023c4-3ceb-4776-9a8a-766bb84b741e/plan.json) | 531 | 5/5 | 기준 미만 |
| [D0043-synth-autolinks](runs/bad81978-a2b8-4e60-9a1a-245ae7fc17c1/evidence.json) | [요청문](runs/bad81978-a2b8-4e60-9a1a-245ae7fc17c1/plan.json) | 617 | 5/5 | 기준 미만 |
| [D0042-source-order-synth](runs/28de323b-7e9c-4827-9ed2-34bea65c92f6/evidence.json) | [요청문](runs/28de323b-7e9c-4827-9ed2-34bea65c92f6/plan.json) | 775 | 5/5 | 기준 미만 |
| [D0041-source-order-synth](runs/45157197-40cb-40f6-92bb-fd765c96ecd1/evidence.json) | [요청문](runs/45157197-40cb-40f6-92bb-fd765c96ecd1/plan.json) | 707 | 5/5 | 기준 미만 |
| [D0040-source-order-synth](runs/a1b16a0d-7423-45c3-b860-20c3b34cb150/evidence.json) | [요청문](runs/a1b16a0d-7423-45c3-b860-20c3b34cb150/plan.json) | 687 | 5/5 | 기준 미만 |
| [D0039-source-order](runs/efb2dfa6-a5ae-40cf-a992-2d80aa573f5c/evidence.json) | [요청문](runs/efb2dfa6-a5ae-40cf-a992-2d80aa573f5c/plan.json) | 574 | 5/5 | 기준 미만 |
| [D0038-source-order](runs/bf7ea924-c2b4-4ecf-b8d8-fb6ded8e30bf/evidence.json) | [요청문](runs/bf7ea924-c2b4-4ecf-b8d8-fb6ded8e30bf/plan.json) | 684 | 5/5 | 기준 미만 |
| [D0037-synth-table](runs/613d3cd2-0988-4268-97e5-2d72336bdc63/evidence.json) | [요청문](runs/613d3cd2-0988-4268-97e5-2d72336bdc63/plan.json) | 603 | 5/5 | 기준 미만 |
| [D0036-source-order](runs/32feb76b-7050-4ea9-b567-988eacadb832/evidence.json) | [요청문](runs/32feb76b-7050-4ea9-b567-988eacadb832/plan.json) | 789 | 5/5 | 기준 미만 |
| [D0035-hardware-links](runs/d438daf0-8988-47fd-9114-a4d6fb017429/evidence.json) | [요청문](runs/d438daf0-8988-47fd-9114-a4d6fb017429/plan.json) | 516 | 5/5 | 기준 미만 |
| [D0034-hardware-links](runs/31fea6f5-aeb7-4ff6-9d00-456d656c8b60/evidence.json) | [요청문](runs/31fea6f5-aeb7-4ff6-9d00-456d656c8b60/plan.json) | 896 | 4/5 · 검증 미통과 | 기준 미만 |
| [D0033-synth-links-temp-zero](runs/b93472cf-4269-41b3-8a6e-d904e505325b/evidence.json) | [요청문](runs/b93472cf-4269-41b3-8a6e-d904e505325b/plan.json) | 604 | 5/5 | 기준 미만 |
| [D0032-synth-links](runs/6899cb98-6377-4d35-9e8d-290ccfa4c3a1/evidence.json) | [요청문](runs/6899cb98-6377-4d35-9e8d-290ccfa4c3a1/plan.json) | 946 | 0/5 · 검증 미통과 | 기준 미만 |
| [D0031-synth-links-six](runs/0bd82a95-f6a3-439c-a2dd-686e76801f2d/evidence.json) | [요청문](runs/0bd82a95-f6a3-439c-a2dd-686e76801f2d/plan.json) | 484 | 0/5 · 검증 미통과 | 기준 미만 |
| [D0030-synth-links](runs/f5262507-5cb9-4a96-8122-8d39057c7839/evidence.json) | [요청문](runs/f5262507-5cb9-4a96-8122-8d39057c7839/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D0029-synth-links](runs/40c52a1d-7180-462a-8fab-ce48ef2deabd/evidence.json) | [요청문](runs/40c52a1d-7180-462a-8fab-ce48ef2deabd/plan.json) | 714 | 0/5 · 검증 미통과 | 기준 미만 |
| [D0028-research-price-total](runs/ea7c785c-e679-4b9e-b5aa-f676b32c9fe5/evidence.json) | [요청문](runs/ea7c785c-e679-4b9e-b5aa-f676b32c9fe5/plan.json) | 521 | 0/5 · 검증 미통과 | 기준 미만 |
| [D0027-research-prose](runs/7c1ebdba-28f8-4813-a92c-d93bb453194f/evidence.json) | [요청문](runs/7c1ebdba-28f8-4813-a92c-d93bb453194f/plan.json) | 510 | 5/5 | 기준 미만 |
| [D0026-research-table](runs/70efaf09-5525-45cf-a64d-8062b51b3027/evidence.json) | [요청문](runs/70efaf09-5525-45cf-a64d-8062b51b3027/plan.json) | 550 | 5/5 | 기준 미만 |
| [D0025-source-order-synth](runs/be6497d1-235e-4cc4-a56d-752248786928/evidence.json) | [요청문](runs/be6497d1-235e-4cc4-a56d-752248786928/plan.json) | 677 | 5/5 | 기준 미만 |
| [D0024-synth-links](runs/f627023f-15a2-4c82-b0bc-0bc584ad5964/evidence.json) | [요청문](runs/f627023f-15a2-4c82-b0bc-0bc584ad5964/plan.json) | 827 | 5/5 | 기준 미만 |
| [D0023-hardware-links](runs/35756174-c151-4957-a1b0-a23ac3b19c0e/evidence.json) | [요청문](runs/35756174-c151-4957-a1b0-a23ac3b19c0e/plan.json) | 716 | 5/5 | 기준 미만 |
| [D0022-source-order](runs/a78cc0eb-42b8-4f97-9cfa-92ef62bea0f3/evidence.json) | [요청문](runs/a78cc0eb-42b8-4f97-9cfa-92ef62bea0f3/plan.json) | 669 | 5/5 | 기준 미만 |
| [D0021-source-order](runs/66448590-43ea-494e-8058-2a1c8eeab09c/evidence.json) | [요청문](runs/66448590-43ea-494e-8058-2a1c8eeab09c/plan.json) | 595 | 5/5 | 기준 미만 |
| [D0020-source-order-max-2048](runs/42c3367c-5a08-4426-9f01-6e00796c9876/evidence.json) | [요청문](runs/42c3367c-5a08-4426-9f01-6e00796c9876/plan.json) | 579 | 5/5 | 기준 미만 |
| [D0019-source-order-top-p-045](runs/d09a8077-4d3e-4c18-bb20-24b9ee70fadd/evidence.json) | [요청문](runs/d09a8077-4d3e-4c18-bb20-24b9ee70fadd/plan.json) | 544 | 5/5 | 기준 미만 |
| [D0018-source-order-top-p-080](runs/2e5cce1a-a768-4b35-be62-ab67a309d06e/evidence.json) | [요청문](runs/2e5cce1a-a768-4b35-be62-ab67a309d06e/plan.json) | 479 | 5/5 | 기준 미만 |
| [D0017-wordpress-links](runs/a3ef0440-762c-4d8a-a557-aa845c62ce22/evidence.json) | [요청문](runs/a3ef0440-762c-4d8a-a557-aa845c62ce22/plan.json) | 588 | 5/5 | 기준 미만 |
| [D0016-source-order-compact](runs/6c9f5832-3022-472e-b5d6-78c22af41b84/evidence.json) | [요청문](runs/6c9f5832-3022-472e-b5d6-78c22af41b84/plan.json) | 541 | 5/5 | 기준 미만 |
| [D0015-source-order](runs/ed6fe6a3-8b0c-4292-82bc-5460326c5c61/evidence.json) | [요청문](runs/ed6fe6a3-8b0c-4292-82bc-5460326c5c61/plan.json) | 744 | 5/5 | 기준 미만 |
| [D0014-recipient-guide](runs/167aaf78-f0ae-46cc-81e8-f03533c1229f/evidence.json) | [요청문](runs/167aaf78-f0ae-46cc-81e8-f03533c1229f/plan.json) | 555 | 5/5 | 기준 미만 |
| [D0013-source-order](runs/fc63223b-d2dd-4945-a67e-3a6c194b51b4/evidence.json) | [요청문](runs/fc63223b-d2dd-4945-a67e-3a6c194b51b4/plan.json) | 746 | 5/5 | 기준 미만 |
| [D0012-price-cards](runs/64348773-2f18-4418-bd83-24b67f6c5e49/evidence.json) | [요청문](runs/64348773-2f18-4418-bd83-24b67f6c5e49/plan.json) | 571 | 5/5 | 기준 미만 |
| [D0011-kit-comparison](runs/8f8816ec-eb8e-4989-bef1-3adf62cdce3e/evidence.json) | [요청문](runs/8f8816ec-eb8e-4989-bef1-3adf62cdce3e/plan.json) | 502 | 5/5 | 기준 미만 |
| [D0010-kit-comparison](runs/23db4545-9646-4616-8732-7c72b1f3e3bb/evidence.json) | [요청문](runs/23db4545-9646-4616-8732-7c72b1f3e3bb/plan.json) | 478 | 4/5 · 검증 미통과 | 기준 미만 |
| [D0009-paired-links](runs/cb55e751-bcc1-4e22-85d8-7f24004aee56/evidence.json) | [요청문](runs/cb55e751-bcc1-4e22-85d8-7f24004aee56/plan.json) | 542 | 5/5 | 기준 미만 |
| [D0008-paired-links-small](runs/698fe425-c02b-471a-a535-6c6520bc81e0/evidence.json) | [요청문](runs/698fe425-c02b-471a-a535-6c6520bc81e0/plan.json) | 569 | 5/5 | 기준 미만 |
| [D0007-visible-receipt](runs/34bb53b4-bbc6-491d-a039-c801d4671d30/evidence.json) | [요청문](runs/34bb53b4-bbc6-491d-a039-c801d4671d30/plan.json) | 741 | 0/5 · 검증 미통과 | 기준 미만 |
| [D0006-hardware-links](runs/4b58fd09-490a-47ca-8e9b-d8615111bb14/evidence.json) | [요청문](runs/4b58fd09-490a-47ca-8e9b-d8615111bb14/plan.json) | 521 | 0/5 · 검증 미통과 | 기준 미만 |
| [D0005-paired-links](runs/d0a7c1a0-1753-4a3d-91bd-d1ddd0293e87/evidence.json) | [요청문](runs/d0a7c1a0-1753-4a3d-91bd-d1ddd0293e87/plan.json) | 605 | 5/5 | 기준 미만 |
| [D0004-paired-links](runs/24a7ab2a-edd0-4deb-80d2-863b115f5647/evidence.json) | [요청문](runs/24a7ab2a-edd0-4deb-80d2-863b115f5647/plan.json) | 664 | 5/5 | 기준 미만 |
| [D0001-native-links](runs/1c80bfa3-26ab-4b14-a000-dce76ef510c5/evidence.json) · 소급 | [요청문](runs/1c80bfa3-26ab-4b14-a000-dce76ef510c5/plan.json) | 671 | 5/5 | 기준 미만 |
| [C1](runs/694ee975-2931-4496-af62-38fc6650d6a6/evidence.json) · 소급 | [요청문](runs/694ee975-2931-4496-af62-38fc6650d6a6/plan.json) | 717 | 5/5 | 기준 미만 · [당시 화면](runs/694ee975-2931-4496-af62-38fc6650d6a6/historical-ui.jpg) |
| [A2](runs/4a2e1d7b-8bdd-44a6-8f25-840ff062c70b/evidence.json) · 소급 | [요청문](runs/4a2e1d7b-8bdd-44a6-8f25-840ff062c70b/plan.json) | 578 | 5/5 | 기준 미만 |
| [B2](runs/f35fa4e8-9f42-41a6-a543-2572167144d2/evidence.json) · 소급 | [요청문](runs/f35fa4e8-9f42-41a6-a543-2572167144d2/plan.json) | 636 | 5/5 | 기준 미만 |
| [B1](runs/6ab17693-d985-4325-a590-7ad94a9f57f3/evidence.json) · 소급 | [요청문](runs/6ab17693-d985-4325-a590-7ad94a9f57f3/plan.json) | 679 | 5/5 | 기준 미만 · [당시 화면](runs/6ab17693-d985-4325-a590-7ad94a9f57f3/historical-ui.jpg) |
| [A1](runs/e12296bd-7243-48e2-98f5-380094a66777/evidence.json) · 소급 | [요청문](runs/e12296bd-7243-48e2-98f5-380094a66777/plan.json) | 559 | 5/5 | 기준 미만 |
