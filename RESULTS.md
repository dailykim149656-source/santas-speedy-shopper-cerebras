# 쇼핑 바운티 실행 기록

각 실행 ID를 열면 Git 계획 커밋, Cerebras가 반환한 출력 토큰 수와 생성 시간, 판매처 조회 결과를 확인할 수 있다. 현재 표시 평균 900 tok/s 이상이면 녹화를 검증한다. 검증된 공식 평균이 종전 최고 기록을 갱신하면 기준 미만이어도 보관한다. 최고 기록의 원본과 60초 이하 영상 한 쌍을 로컬에 보관한다. 실행별 측정값과 보관했던 영상 해시는 Git에서 확인할 수 있다.

| 실행 | 요청 | 공식 평균 (tok/s) | 상품 검증 | 영상 |
|---|---|---:|---|---|
| [D5170-synth-five-categories-cap](runs/c7280fe0-f540-4797-b865-1e415ea7bc62/evidence.json) | [요청문](runs/c7280fe0-f540-4797-b865-1e415ea7bc62/plan.json) | 1202 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5169-synth-five-categories-cap](runs/05d00f2c-5aa6-4f5b-a916-223ff9beb723/evidence.json) | [요청문](runs/05d00f2c-5aa6-4f5b-a916-223ff9beb723/plan.json) | 785 | 5/5 | 기준 미만 |
| [D5168-synth-five-categories-cap](runs/fa7bd708-adc3-4742-8e3e-3c33552a1339/evidence.json) | [요청문](runs/fa7bd708-adc3-4742-8e3e-3c33552a1339/plan.json) | 741 | 5/5 | 기준 미만 |
| [D5167-synth-five-categories-cap](runs/a09843f1-c468-4bbe-b293-508b3274ecd2/evidence.json) | [요청문](runs/a09843f1-c468-4bbe-b293-508b3274ecd2/plan.json) | 853 | 5/5 | 기준 미만 |
| [D5166-synth-five-categories-cap](runs/a21eee0b-4133-4b2a-bc1f-4f3b894029d4/evidence.json) | [요청문](runs/a21eee0b-4133-4b2a-bc1f-4f3b894029d4/plan.json) | 892 | 5/5 | 기준 미만 |
| [D5165-synth-five-categories-cap](runs/83038581-b2bd-436c-8150-fea6d6d622d3/evidence.json) | [요청문](runs/83038581-b2bd-436c-8150-fea6d6d622d3/plan.json) | 741 | 5/5 | 기준 미만 |
| [D5164-synth-five-categories-cap](runs/7aa357fd-8f8b-4e90-96b7-d970e37e29f0/evidence.json) | [요청문](runs/7aa357fd-8f8b-4e90-96b7-d970e37e29f0/plan.json) | 884 | 5/5 | 기준 미만 |
| [D5163-synth-five-categories-cap](runs/04849a51-a39b-495e-b3e5-dd4ea8e1d0ed/evidence.json) | [요청문](runs/04849a51-a39b-495e-b3e5-dd4ea8e1d0ed/plan.json) | 824 | 5/5 | 기준 미만 |
| [D5162-synth-five-categories-cap](runs/114977b3-56e0-4027-bfa9-face198289c4/evidence.json) | [요청문](runs/114977b3-56e0-4027-bfa9-face198289c4/plan.json) | 986 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5161-synth-five-categories-cap](runs/d47df176-e143-4fa7-b8fa-206bd74a3fcd/evidence.json) | [요청문](runs/d47df176-e143-4fa7-b8fa-206bd74a3fcd/plan.json) | 964 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5160-synth-five-categories-cap](runs/1156061f-7ee2-4317-b522-d1ea99cbaa70/evidence.json) | [요청문](runs/1156061f-7ee2-4317-b522-d1ea99cbaa70/plan.json) | 823 | 5/5 | 기준 미만 |
| [D5159-synth-five-categories-cap](runs/fc0d975d-a0cf-4322-8b22-443bdc61b520/evidence.json) | [요청문](runs/fc0d975d-a0cf-4322-8b22-443bdc61b520/plan.json) | 793 | 5/5 | 기준 미만 |
| [D5158-synth-five-categories-cap](runs/08dc8eee-659d-45c9-a880-4e00959267bc/evidence.json) | [요청문](runs/08dc8eee-659d-45c9-a880-4e00959267bc/plan.json) | 862 | 5/5 | 기준 미만 |
| [D5157-synth-five-categories-cap](runs/11d7948e-193d-4887-86e5-7dcfb2d8caa4/evidence.json) | [요청문](runs/11d7948e-193d-4887-86e5-7dcfb2d8caa4/plan.json) | 891 | 5/5 | 기준 미만 |
| [D5156-synth-five-categories-cap](runs/a902cf13-0532-4648-b425-d5d844ceff58/evidence.json) | [요청문](runs/a902cf13-0532-4648-b425-d5d844ceff58/plan.json) | 772 | 5/5 | 기준 미만 |
| [D5155-synth-five-categories-cap](runs/496b4505-7357-473b-8e74-278fd3dae422/evidence.json) | [요청문](runs/496b4505-7357-473b-8e74-278fd3dae422/plan.json) | 780 | 5/5 | 기준 미만 |
| [D5154-synth-five-categories-cap](runs/9035ae44-1c90-401b-a384-34a4765d54fd/evidence.json) | [요청문](runs/9035ae44-1c90-401b-a384-34a4765d54fd/plan.json) | 689 | 5/5 | 기준 미만 |
| [D5153-synth-five-categories-cap](runs/c64e1170-6b20-412e-923d-9c63103335c2/evidence.json) | [요청문](runs/c64e1170-6b20-412e-923d-9c63103335c2/plan.json) | 1007 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5152-synth-five-categories-cap](runs/9a94ab52-8d98-4070-97ea-88b24f66fec0/evidence.json) | [요청문](runs/9a94ab52-8d98-4070-97ea-88b24f66fec0/plan.json) | 1043 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5151-synth-five-categories-cap](runs/0e4205d1-c831-4a35-86ed-0859668521e7/evidence.json) | [요청문](runs/0e4205d1-c831-4a35-86ed-0859668521e7/plan.json) | 826 | 5/5 | 기준 미만 |
| [D5150-synth-five-categories-cap](runs/562a20e7-247a-4a59-ade2-ce512016658c/evidence.json) | [요청문](runs/562a20e7-247a-4a59-ade2-ce512016658c/plan.json) | 619 | 5/5 | 기준 미만 |
| [D5149-synth-five-categories-cap](runs/87ec2c0d-bf77-40b4-8790-848e97c09996/evidence.json) | [요청문](runs/87ec2c0d-bf77-40b4-8790-848e97c09996/plan.json) | 1067 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5148-synth-five-categories-cap](runs/404b40d9-562a-4aa3-8319-d8352f371c76/evidence.json) | [요청문](runs/404b40d9-562a-4aa3-8319-d8352f371c76/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5147-synth-five-categories-cap](runs/1dc72c05-702d-45d7-bfb5-eb006aa7a076/evidence.json) | [요청문](runs/1dc72c05-702d-45d7-bfb5-eb006aa7a076/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5146-synth-five-categories-cap](runs/71b3e562-299e-4e4c-9b43-8cb33d5eb331/evidence.json) | [요청문](runs/71b3e562-299e-4e4c-9b43-8cb33d5eb331/plan.json) | 985 | 0/5 · 검증 미통과 | 상품 검증 미통과 · 영상 미보관 |
| [D5145-synth-five-categories-cap](runs/cba20258-882d-4488-b40b-002ab1453496/evidence.json) | [요청문](runs/cba20258-882d-4488-b40b-002ab1453496/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5144-synth-five-categories-cap](runs/bfb2d97e-c0e0-4764-ba93-d41e43b52897/evidence.json) | [요청문](runs/bfb2d97e-c0e0-4764-ba93-d41e43b52897/plan.json) | 888 | 5/5 | 기준 미만 |
| [D5143-synth-five-categories-cap](runs/c829170a-fc1b-43e6-8088-1b9d7481eb57/evidence.json) | [요청문](runs/c829170a-fc1b-43e6-8088-1b9d7481eb57/plan.json) | 705 | 0/5 · 검증 미통과 | 기준 미만 |
| [D5142-synth-five-categories-cap](runs/feb95270-b763-405f-b5d5-3dcf1b797d87/evidence.json) | [요청문](runs/feb95270-b763-405f-b5d5-3dcf1b797d87/plan.json) | 1023 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5141-synth-five-categories-cap](runs/d5ee4f34-c7c9-47e7-8c52-0539badb2ae0/evidence.json) | [요청문](runs/d5ee4f34-c7c9-47e7-8c52-0539badb2ae0/plan.json) | 824 | 5/5 | 기준 미만 |
| [D5140-synth-five-categories-cap](runs/3ac7b6d5-cf9c-4f8d-a2d6-71decbea43f8/evidence.json) | [요청문](runs/3ac7b6d5-cf9c-4f8d-a2d6-71decbea43f8/plan.json) | 869 | 5/5 | 기준 미만 |
| [D5139-synth-five-categories-cap](runs/f3927431-d4f3-48d9-a650-4b574e6813e1/evidence.json) | [요청문](runs/f3927431-d4f3-48d9-a650-4b574e6813e1/plan.json) | 1008 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5138-synth-five-categories-cap](runs/58aa7b0e-9168-47c2-a694-190a53574e23/evidence.json) | [요청문](runs/58aa7b0e-9168-47c2-a694-190a53574e23/plan.json) | 773 | 5/5 | 기준 미만 |
| [D5137-synth-five-categories-cap](runs/d2076b3b-c6e3-4ff7-bbe5-5b3228f4682b/evidence.json) | [요청문](runs/d2076b3b-c6e3-4ff7-bbe5-5b3228f4682b/plan.json) | 944 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5136-synth-five-categories-cap](runs/7defbac1-bf4d-4e97-9ca1-a626cd6ddd06/evidence.json) | [요청문](runs/7defbac1-bf4d-4e97-9ca1-a626cd6ddd06/plan.json) | 815 | 5/5 | 기준 미만 |
| [D5135-synth-five-categories-cap](runs/d7d72086-ef72-4af7-8a1d-501a223546cc/evidence.json) | [요청문](runs/d7d72086-ef72-4af7-8a1d-501a223546cc/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5134-synth-five-categories-cap](runs/522cc1bf-8c93-453f-a90a-e6fa62b7659f/evidence.json) | [요청문](runs/522cc1bf-8c93-453f-a90a-e6fa62b7659f/plan.json) | 715 | 5/5 | 기준 미만 |
| [D5133-synth-five-categories-cap](runs/61de3b9d-d0c6-4c97-8875-755794bffb62/evidence.json) | [요청문](runs/61de3b9d-d0c6-4c97-8875-755794bffb62/plan.json) | 993 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5132-synth-five-categories-cap](runs/b18b88fc-3271-4049-ae1f-3a93deb4356c/evidence.json) | [요청문](runs/b18b88fc-3271-4049-ae1f-3a93deb4356c/plan.json) | 1072 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5131-synth-five-categories-cap](runs/5a07c5d8-6fd7-49e5-82c9-ad5ac90f241c/evidence.json) | [요청문](runs/5a07c5d8-6fd7-49e5-82c9-ad5ac90f241c/plan.json) | 849 | 5/5 | 기준 미만 |
| [D5130-synth-five-categories-cap](runs/76895806-65fb-4537-8737-b67746f1e288/evidence.json) | [요청문](runs/76895806-65fb-4537-8737-b67746f1e288/plan.json) | 788 | 5/5 | 기준 미만 |
| [D5129-mercantile-five-categories-cap](runs/8b83c3ba-33e3-47a5-81f4-db4e84dea126/evidence.json) | [요청문](runs/8b83c3ba-33e3-47a5-81f4-db4e84dea126/plan.json) | 739 | 5/5 | 기준 미만 |
| [D5128-synth-five-categories-cap](runs/f72a9b26-892a-447e-bfce-278c48d9dcac/evidence.json) | [요청문](runs/f72a9b26-892a-447e-bfce-278c48d9dcac/plan.json) | 743 | 5/5 | 기준 미만 |
| [D5127-synth-five-categories-cap](runs/c17fec7c-2d18-47c3-9a2b-8308c5759f5a/evidence.json) | [요청문](runs/c17fec7c-2d18-47c3-9a2b-8308c5759f5a/plan.json) | 681 | 5/5 | 기준 미만 |
| [D5126-mercantile-five-categories-cap](runs/8b70bffb-c09b-47ac-aca6-f90b450158e3/evidence.json) | [요청문](runs/8b70bffb-c09b-47ac-aca6-f90b450158e3/plan.json) | 808 | 5/5 | 기준 미만 |
| [D5125-mercantile-five-categories-cap](runs/897884f4-b98e-4062-9e91-b1f8c135bda1/evidence.json) | [요청문](runs/897884f4-b98e-4062-9e91-b1f8c135bda1/plan.json) | 699 | 5/5 | 기준 미만 |
| [D5124-synth-five-categories-cap](runs/aa4eef22-700f-4d00-90cd-08a47d6d7468/evidence.json) | [요청문](runs/aa4eef22-700f-4d00-90cd-08a47d6d7468/plan.json) | 906 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5123-synth-five-categories-cap](runs/bad09ae1-d2f5-41f9-9d29-ec70075519dc/evidence.json) | [요청문](runs/bad09ae1-d2f5-41f9-9d29-ec70075519dc/plan.json) | 998 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5122-synth-five-categories-cap](runs/b3759dad-8c2e-49ac-98dd-5c74c96288fc/evidence.json) | [요청문](runs/b3759dad-8c2e-49ac-98dd-5c74c96288fc/plan.json) | 1127 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5121-synth-five-categories-cap](runs/414f5f33-6b58-421d-ac10-bbdb49ae7e24/evidence.json) | [요청문](runs/414f5f33-6b58-421d-ac10-bbdb49ae7e24/plan.json) | 794 | 5/5 | 기준 미만 |
| [D5120-synth-five-categories-cap](runs/782707fe-df76-4118-9ef8-155ada22b08b/evidence.json) | [요청문](runs/782707fe-df76-4118-9ef8-155ada22b08b/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5119-synth-five-categories-cap](runs/2f279e62-c518-4a79-ad14-d9e4eacbb0d8/evidence.json) | [요청문](runs/2f279e62-c518-4a79-ad14-d9e4eacbb0d8/plan.json) | 799 | 5/5 | 기준 미만 |
| [D5118-synth-five-categories-cap](runs/efa70c89-1449-42c2-b87c-ab59b62f8472/evidence.json) | [요청문](runs/efa70c89-1449-42c2-b87c-ab59b62f8472/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5117-synth-five-categories-cap](runs/c3a4b1ee-ce02-49c5-a9cb-3a00045bc6fd/evidence.json) | [요청문](runs/c3a4b1ee-ce02-49c5-a9cb-3a00045bc6fd/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5116-synth-five-categories-cap](runs/72b09262-8d05-4ef6-ac46-267cb82a068a/evidence.json) | [요청문](runs/72b09262-8d05-4ef6-ac46-267cb82a068a/plan.json) | 1042 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5115-synth-five-categories-cap](runs/fa0f817e-ee39-4e86-868e-96edc1830832/evidence.json) | [요청문](runs/fa0f817e-ee39-4e86-868e-96edc1830832/plan.json) | 844 | 5/5 | 기준 미만 |
| [D5114-synth-five-categories-cap](runs/ce1753ca-0ccf-4701-8aa8-c903c3c815a9/evidence.json) | [요청문](runs/ce1753ca-0ccf-4701-8aa8-c903c3c815a9/plan.json) | 806 | 5/5 | 기준 미만 |
| [D5113-synth-five-categories-cap](runs/e86b52f5-5f72-41df-acc8-ecfbbe7eedbc/evidence.json) | [요청문](runs/e86b52f5-5f72-41df-acc8-ecfbbe7eedbc/plan.json) | 656 | 5/5 | 기준 미만 |
| [D5112-synth-five-categories-cap](runs/4b9ea9e9-b006-40e2-9d8d-7fecfb54f957/evidence.json) | [요청문](runs/4b9ea9e9-b006-40e2-9d8d-7fecfb54f957/plan.json) | 1219 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5111-synth-five-categories-cap](runs/e0b4904a-4043-43aa-9f3e-8632c591801a/evidence.json) | [요청문](runs/e0b4904a-4043-43aa-9f3e-8632c591801a/plan.json) | 809 | 5/5 | 기준 미만 |
| [D5110-synth-five-categories-cap](runs/ca2abd04-4d26-4981-a745-93ad9e378e70/evidence.json) | [요청문](runs/ca2abd04-4d26-4981-a745-93ad9e378e70/plan.json) | 886 | 5/5 | 기준 미만 |
| [D5109-synth-five-categories-cap](runs/2c3c5f06-c296-4e4f-94c0-9fbc3f121855/evidence.json) | [요청문](runs/2c3c5f06-c296-4e4f-94c0-9fbc3f121855/plan.json) | 1204 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5108-synth-five-categories-cap](runs/f039d055-caa3-4ed7-bcc8-e571d4dea5fb/evidence.json) | [요청문](runs/f039d055-caa3-4ed7-bcc8-e571d4dea5fb/plan.json) | 1064 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5107-synth-five-categories-cap](runs/7757e7c5-96d3-4a37-8ee0-e2e08767e3b0/evidence.json) | [요청문](runs/7757e7c5-96d3-4a37-8ee0-e2e08767e3b0/plan.json) | 851 | 5/5 | 기준 미만 |
| [D5106-synth-five-categories-cap](runs/e32b612d-a4bf-417e-9566-a254dd56b924/evidence.json) | [요청문](runs/e32b612d-a4bf-417e-9566-a254dd56b924/plan.json) | 766 | 0/5 · 검증 미통과 | 기준 미만 |
| [D5105-synth-five-categories-cap](runs/7d036cae-1deb-40fa-b83e-e11564bb54af/evidence.json) | [요청문](runs/7d036cae-1deb-40fa-b83e-e11564bb54af/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5104-synth-five-categories-cap](runs/fba57960-801e-4cab-bfcf-20c059769d03/evidence.json) | [요청문](runs/fba57960-801e-4cab-bfcf-20c059769d03/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5103-synth-five-categories-cap](runs/2f1efef7-1246-40ae-bec0-d98f0be4116e/evidence.json) | [요청문](runs/2f1efef7-1246-40ae-bec0-d98f0be4116e/plan.json) | 845 | 5/5 | 기준 미만 |
| [D5102-synth-five-categories-cap](runs/8cc80670-9e66-4a59-9e74-fd3bfeadcf7e/evidence.json) | [요청문](runs/8cc80670-9e66-4a59-9e74-fd3bfeadcf7e/plan.json) | 1054 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5101-synth-five-categories-cap](runs/bca2576c-8e82-4612-8992-5771bde0b208/evidence.json) | [요청문](runs/bca2576c-8e82-4612-8992-5771bde0b208/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5100-synth-five-categories-cap](runs/877c6d73-926f-4f61-82d2-259b2798b920/evidence.json) | [요청문](runs/877c6d73-926f-4f61-82d2-259b2798b920/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5099-synth-five-categories-cap](runs/ee5b4d02-dd27-4542-958a-92b1f03097ee/evidence.json) | [요청문](runs/ee5b4d02-dd27-4542-958a-92b1f03097ee/plan.json) | 786 | 5/5 | 기준 미만 |
| [D5098-synth-five-categories-cap](runs/7ccce7d3-a456-4586-9d4a-65808cbb3986/evidence.json) | [요청문](runs/7ccce7d3-a456-4586-9d4a-65808cbb3986/plan.json) | 1132 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5097-speed1500-p](runs/633ed6af-d7b3-4b3b-af47-30c775cf2181/evidence.json) | [요청문](runs/633ed6af-d7b3-4b3b-af47-30c775cf2181/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5096-speed1500-a](runs/aee0624e-ec5b-4b15-8266-a48d0f586cb9/evidence.json) | [요청문](runs/aee0624e-ec5b-4b15-8266-a48d0f586cb9/plan.json) | 990 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5095-speed1500-f](runs/8205f87a-71eb-4fcb-aa13-217b81a723b4/evidence.json) | [요청문](runs/8205f87a-71eb-4fcb-aa13-217b81a723b4/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5094-speed1500-f](runs/54279a8c-36a9-4316-b50d-0d797873b69e/evidence.json) | [요청문](runs/54279a8c-36a9-4316-b50d-0d797873b69e/plan.json) | 1034 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5093-speed1500-a](runs/6d0f041f-3bba-4029-9ab4-1587fff0deb1/evidence.json) | [요청문](runs/6d0f041f-3bba-4029-9ab4-1587fff0deb1/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5092-speed1500-p](runs/7b358226-5b83-4399-9af9-bb39b1db867e/evidence.json) | [요청문](runs/7b358226-5b83-4399-9af9-bb39b1db867e/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5091-speed1500-f](runs/2557403a-d577-4d11-820f-8d0fe11e8a1a/evidence.json) | [요청문](runs/2557403a-d577-4d11-820f-8d0fe11e8a1a/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5090-speed1500-p](runs/bca8114e-28fe-4d07-ae0e-4b863788dacc/evidence.json) | [요청문](runs/bca8114e-28fe-4d07-ae0e-4b863788dacc/plan.json) | 728 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5089-speed1500-a](runs/60639bee-cbde-4ca4-b646-63ba18dee125/evidence.json) | [요청문](runs/60639bee-cbde-4ca4-b646-63ba18dee125/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5088-speed1500-a](runs/e4b4ce0b-f794-4aea-83fa-76f37095f560/evidence.json) | [요청문](runs/e4b4ce0b-f794-4aea-83fa-76f37095f560/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5087-speed1500-p](runs/058d3a3a-0131-44e8-8367-5bbe14d73bd5/evidence.json) | [요청문](runs/058d3a3a-0131-44e8-8367-5bbe14d73bd5/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5086-speed1500-f](runs/76d7f298-699e-4068-a082-319a95db477f/evidence.json) | [요청문](runs/76d7f298-699e-4068-a082-319a95db477f/plan.json) | 712 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5085-speed1500-a](runs/1d100e81-3b0f-4d5e-8d26-fd930a340d78/evidence.json) | [요청문](runs/1d100e81-3b0f-4d5e-8d26-fd930a340d78/plan.json) | 1155 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5084-speed1500-f](runs/e59bc099-20c7-41db-b7d7-7980567ac196/evidence.json) | [요청문](runs/e59bc099-20c7-41db-b7d7-7980567ac196/plan.json) | 802 | 0/5 · 검증 미통과 | 상품 검증 미통과 · 영상 미보관 |
| [D5083-speed1500-p](runs/4743db14-b132-45f7-a6be-38c772882920/evidence.json) | [요청문](runs/4743db14-b132-45f7-a6be-38c772882920/plan.json) | 594 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5082-speed1500-p](runs/33918883-0ac4-4135-a9dd-ea52eeff7fb8/evidence.json) | [요청문](runs/33918883-0ac4-4135-a9dd-ea52eeff7fb8/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5081-speed1500-f](runs/28fb566b-2026-44b2-8b65-c328674734b2/evidence.json) | [요청문](runs/28fb566b-2026-44b2-8b65-c328674734b2/plan.json) | 904 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5080-speed1500-a](runs/465ba4e8-bfe2-4722-b473-7d0ee418ffb4/evidence.json) | [요청문](runs/465ba4e8-bfe2-4722-b473-7d0ee418ffb4/plan.json) | 1407 | 0/5 · 검증 미통과 | 상품 검증 미통과 · 영상 미보관 |
| [D5079-synth-five-categories-cap](runs/2d153583-8dad-4fa3-8076-8428625f5fad/evidence.json) | [요청문](runs/2d153583-8dad-4fa3-8076-8428625f5fad/plan.json) | 1221 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5078-synth-five-categories-relay](runs/e6f66718-3001-457a-a103-6b186e231fa6/evidence.json) | [요청문](runs/e6f66718-3001-457a-a103-6b186e231fa6/plan.json) | 1128 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5077-synth-five-categories-cap](runs/73f999f2-cb9f-4fa5-a7a0-903e59b9e06c/evidence.json) | [요청문](runs/73f999f2-cb9f-4fa5-a7a0-903e59b9e06c/plan.json) | 1156 | 0/5 · 검증 미통과 | 상품 검증 미통과 · 영상 미보관 |
| [D5076-synth-five-categories-relay](runs/243e9123-7c23-4ac5-8c6b-af09fa557594/evidence.json) | [요청문](runs/243e9123-7c23-4ac5-8c6b-af09fa557594/plan.json) | 837 | 5/5 | 기준 미만 |
| [D5075-synth-five-categories-cap](runs/9033bdc7-3a56-4082-93ae-94a765e2cbfc/evidence.json) | [요청문](runs/9033bdc7-3a56-4082-93ae-94a765e2cbfc/plan.json) | 1068 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5074-synth-five-categories-relay](runs/24f1117e-c99a-45c4-bcbc-d3a424d4c8d8/evidence.json) | [요청문](runs/24f1117e-c99a-45c4-bcbc-d3a424d4c8d8/plan.json) | 865 | 5/5 | 기준 미만 |
| [D5073-synth-five-categories-cap](runs/c66e0c6d-be76-4178-9f68-d517ae62d56a/evidence.json) | [요청문](runs/c66e0c6d-be76-4178-9f68-d517ae62d56a/plan.json) | 934 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5072-synth-five-categories-relay](runs/900a7c42-7de5-46aa-8b53-8eee2d5682ad/evidence.json) | [요청문](runs/900a7c42-7de5-46aa-8b53-8eee2d5682ad/plan.json) | 773 | 5/5 | 기준 미만 |
| [D5071-synth-five-categories-cap](runs/6207ec7a-ebc0-4375-ae4f-40edda0fe78e/evidence.json) | [요청문](runs/6207ec7a-ebc0-4375-ae4f-40edda0fe78e/plan.json) | 948 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5070-synth-five-categories-relay](runs/85decc39-bf60-4377-bb37-16a9d0d35ed9/evidence.json) | [요청문](runs/85decc39-bf60-4377-bb37-16a9d0d35ed9/plan.json) | 902 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5069-synth-five-categories-cap](runs/1ea2b0cc-0385-42e0-af99-48fa2a4d984d/evidence.json) | [요청문](runs/1ea2b0cc-0385-42e0-af99-48fa2a4d984d/plan.json) | 886 | 5/5 | 기준 미만 |
| [D5068-synth-five-categories-relay](runs/7d584ece-d70d-45fb-9a26-b270b6cc30c6/evidence.json) | [요청문](runs/7d584ece-d70d-45fb-9a26-b270b6cc30c6/plan.json) | 1030 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5067-synth-five-categories-cap](runs/0d94296b-7dad-4b24-9194-629ba9375f53/evidence.json) | [요청문](runs/0d94296b-7dad-4b24-9194-629ba9375f53/plan.json) | 1023 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5066-synth-five-categories-relay](runs/c912b430-55c4-42e2-b118-300a687786b0/evidence.json) | [요청문](runs/c912b430-55c4-42e2-b118-300a687786b0/plan.json) | 1067 | 5/5 | 해시 보존 · [보관 중인 최고 기록](runs/a9530b69-3aed-4ea9-8fd9-9ee1fcb36b51/evidence.json) |
| [D5065-synth-five-categories-cap](runs/c40596c1-26af-4d05-ad85-52cfc4b160fb/evidence.json) | [요청문](runs/c40596c1-26af-4d05-ad85-52cfc4b160fb/plan.json) | 1222 | 0/5 · 검증 미통과 | 상품 검증 미통과 · 영상 미보관 |
| [D5064-synth-five-categories-cap](runs/2547ccf0-f68e-4322-8fc1-ff4a809fa122/evidence.json) | [요청문](runs/2547ccf0-f68e-4322-8fc1-ff4a809fa122/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5063-synth-five-categories-relay](runs/a1e19712-caf4-4f16-85db-b245dbcc9f67/evidence.json) | [요청문](runs/a1e19712-caf4-4f16-85db-b245dbcc9f67/plan.json) | 888 | 5/5 | 기준 미만 |
| [D5062-synth-five-categories-cap](runs/b6a58da7-dca1-48a8-bd8a-b964cea953d3/evidence.json) | [요청문](runs/b6a58da7-dca1-48a8-bd8a-b964cea953d3/plan.json) | 1365 | 0/5 · 검증 미통과 | 상품 검증 미통과 · 영상 미보관 |
| [D5061-synth-five-categories-cap](runs/45bc2c2c-08be-403d-92cb-2cafae4d85eb/evidence.json) | [요청문](runs/45bc2c2c-08be-403d-92cb-2cafae4d85eb/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5060-synth-five-categories-cap](runs/251ddb8e-ae54-4e8b-9d90-3c85b454b643/evidence.json) | [요청문](runs/251ddb8e-ae54-4e8b-9d90-3c85b454b643/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5059-synth-five-categories-relay](runs/9813e590-0d58-4f32-9a2c-4314b0a12491/evidence.json) | [요청문](runs/9813e590-0d58-4f32-9a2c-4314b0a12491/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5050-synth-five-categories-cap](runs/1a14a3c4-24de-448e-b729-244976e05948/evidence.json) | [요청문](runs/1a14a3c4-24de-448e-b729-244976e05948/plan.json) | 884 | 5/5 | 기준 미만 |
| [D5049-first5027-extract-text](runs/1c90ee25-c17e-4386-a0b4-d940814982bb/evidence.json) | [요청문](runs/1c90ee25-c17e-4386-a0b4-d940814982bb/plan.json) | 1060 | 5/5 | 확인 필요 |
| [D5048-first5027-defer-answer](runs/b9444c6a-4789-4958-a382-8f1a6076a304/evidence.json) | [요청문](runs/b9444c6a-4789-4958-a382-8f1a6076a304/plan.json) | 743 | 5/5 | 기준 미만 |
| [D5047-first5027-defer-answer](runs/1236be0d-9fd2-4d3b-ab83-067ad950aeea/evidence.json) | [요청문](runs/1236be0d-9fd2-4d3b-ab83-067ad950aeea/plan.json) | 795 | 5/5 | 기준 미만 |
| [D5046-first5027-extract-text](runs/197b3be1-e7b5-4c6c-a61d-c1f0fca509ac/evidence.json) | [요청문](runs/197b3be1-e7b5-4c6c-a61d-c1f0fca509ac/plan.json) | 819 | 0/5 · 검증 미통과 | 기준 미만 |
| [D5045-synth-five-categories-cap](runs/4c3d61dd-154e-4a8b-94d5-e3e2141068f6/evidence.json) | [요청문](runs/4c3d61dd-154e-4a8b-94d5-e3e2141068f6/plan.json) | 780 | 5/5 | 기준 미만 |
| [D5044-first5027-extract-text](runs/3fc351d6-cfad-4023-a881-e2e8a663cf03/evidence.json) | [요청문](runs/3fc351d6-cfad-4023-a881-e2e8a663cf03/plan.json) | 780 | 0/5 · 검증 미통과 | 기준 미만 |
| [D5043-synth-five-categories-cap](runs/68da0b94-98ea-4c39-b596-1743f243d8ba/evidence.json) | [요청문](runs/68da0b94-98ea-4c39-b596-1743f243d8ba/plan.json) | 809 | 0/5 · 검증 미통과 | 기준 미만 |
| [D5042-first5027-defer-answer](runs/c5e24f06-af95-4120-9067-0a3a15cd2a65/evidence.json) | [요청문](runs/c5e24f06-af95-4120-9067-0a3a15cd2a65/plan.json) | 1039 | 5/5 | 확인 필요 |
| [D5041-first5027-defer-answer](runs/ae405a59-fb82-4e7f-afa0-5eec10f2fad1/evidence.json) | [요청문](runs/ae405a59-fb82-4e7f-afa0-5eec10f2fad1/plan.json) | 793 | 5/5 | 기준 미만 |
| [D5040-synth-five-categories-cap](runs/21ac433c-2fe3-4193-9343-5ccaa31b38c5/evidence.json) | [요청문](runs/21ac433c-2fe3-4193-9343-5ccaa31b38c5/plan.json) | 760 | 5/5 | 기준 미만 |
| [D5039-first5027-extract-text](runs/3f6746b2-610f-45b5-8d39-38d7bbba32f3/evidence.json) | [요청문](runs/3f6746b2-610f-45b5-8d39-38d7bbba32f3/plan.json) | 858 | 5/5 | 기준 미만 |
| [D5036-synth-six-sorted-pages](runs/06f2ac3e-858c-46e4-8ea0-afdeda16de87/evidence.json) | [요청문](runs/06f2ac3e-858c-46e4-8ea0-afdeda16de87/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5035-synth-six-sorted](runs/5b6df3be-fc37-4502-903a-e3aad322331e/evidence.json) | [요청문](runs/5b6df3be-fc37-4502-903a-e3aad322331e/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5034-synth-six-sorted](runs/1aed0253-817b-41fd-ba04-9d8938b58809/evidence.json) | [요청문](runs/1aed0253-817b-41fd-ba04-9d8938b58809/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5033-synth-six-sorted-pages](runs/98034eb8-32fc-44a0-91ca-dafe7966ddf9/evidence.json) | [요청문](runs/98034eb8-32fc-44a0-91ca-dafe7966ddf9/plan.json) | 705 | 5/5 | 기준 미만 |
| [D5032-synth-six-sorted](runs/3bab61ee-6ffc-45c8-81da-cf287c602d8c/evidence.json) | [요청문](runs/3bab61ee-6ffc-45c8-81da-cf287c602d8c/plan.json) | 600 | 0/5 · 검증 미통과 | 기준 미만 |
| [D5031-synth-six-sorted-pages](runs/8a8072ce-fd4e-4359-b287-dc46d3bac178/evidence.json) | [요청문](runs/8a8072ce-fd4e-4359-b287-dc46d3bac178/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5030-synth-six-sorted-pages](runs/436c4627-0929-4891-b046-c3c13eadbf28/evidence.json) | [요청문](runs/436c4627-0929-4891-b046-c3c13eadbf28/plan.json) | 952 | 4/5 · 검증 미통과 | 상품 검증 미통과 · 영상 미보관 |
| [D5029-synth-six-sorted](runs/f4d93feb-36f0-41be-b33f-aa589a91f3ed/evidence.json) | [요청문](runs/f4d93feb-36f0-41be-b33f-aa589a91f3ed/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
| [D5028-synth-five-categories-cap-4000](runs/1708f7e9-a9f8-4cf7-aff7-3105962c72fc/evidence.json) | [요청문](runs/1708f7e9-a9f8-4cf7-aff7-3105962c72fc/plan.json) | 754 | 5/5 | 기준 미만 |
| [D5027-synth-five-categories-cap](runs/cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77/evidence.json) | [요청문](runs/cd75e5e0-be7c-471f-a9ab-c9e6f0d1bd77/plan.json) | 1355 | 5/5 | 확인 필요 |
| [D5026-synth-five-categories-cap](runs/6bf30fa2-535a-45da-a1c1-324c9f0a9368/evidence.json) | [요청문](runs/6bf30fa2-535a-45da-a1c1-324c9f0a9368/plan.json) | 1028 | 5/5 | 확인 필요 |
| [D5025-synth-five-categories-cap-4000](runs/2559637b-529b-4b98-a7c5-11a150fc23c0/evidence.json) | [요청문](runs/2559637b-529b-4b98-a7c5-11a150fc23c0/plan.json) | 1115 | 5/5 | 확인 필요 |
| [D5024-synth-five-categories-cap](runs/892a4796-e872-4662-85c9-fdb21ca9ac2a/evidence.json) | [요청문](runs/892a4796-e872-4662-85c9-fdb21ca9ac2a/plan.json) | 879 | 5/5 | 기준 미만 |
| [D5023-synth-five-categories-cap-4000](runs/49c30bf1-3221-4309-94e5-6c7f191629f5/evidence.json) | [요청문](runs/49c30bf1-3221-4309-94e5-6c7f191629f5/plan.json) | 1014 | 0/5 · 검증 미통과 | 상품 검증 미통과 · 영상 미보관 |
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
| [D5052-gift8-prefetch](runs/d88a6b09-4808-4f55-b67c-1bc699ab8781/evidence.json) | [요청문](runs/d88a6b09-4808-4f55-b67c-1bc699ab8781/plan.json) | 1060 | 5/5 | 기준 미만 |
| [D5058-gift8-prefetch](runs/ce9f8705-b34b-4eb7-9497-ce883f58fc01/evidence.json) | [요청문](runs/ce9f8705-b34b-4eb7-9497-ce883f58fc01/plan.json) | 1050 | 5/5 | 기준 미만 |
| [D5055-gift8-prefetch](runs/b9cd8be4-4968-4db3-a11c-b5d5520d1251/evidence.json) | [요청문](runs/b9cd8be4-4968-4db3-a11c-b5d5520d1251/plan.json) | 780 | 5/5 | 기준 미만 |
| [D5056-gift8-tool](runs/985017fb-afc8-40c7-887a-480ba6c25206/evidence.json) | [요청문](runs/985017fb-afc8-40c7-887a-480ba6c25206/plan.json) | 719 | 5/5 | 기준 미만 |
| [D5053-gift8-prefetch](runs/766237bd-75b8-4ba7-8dae-a07cd79d9f22/evidence.json) | [요청문](runs/766237bd-75b8-4ba7-8dae-a07cd79d9f22/plan.json) | 750 | 0/5 · 검증 미통과 | 기준 미만 |
| [D5051-gift8-tool](runs/1e1b8cfa-bdb4-4e92-b435-c4e66b94f44b/evidence.json) | [요청문](runs/1e1b8cfa-bdb4-4e92-b435-c4e66b94f44b/plan.json) | 955 | 5/5 | 기준 미만 |
| [D5057-gift8-tool](runs/19d752e4-25b1-4424-a931-1a1071eb9dd0/evidence.json) | [요청문](runs/19d752e4-25b1-4424-a931-1a1071eb9dd0/plan.json) | 1065 | 5/5 | 기준 미만 |
| [D5054-gift8-tool](runs/0303fe49-cb6b-46b2-bb7e-2304e3effcce/evidence.json) | [요청문](runs/0303fe49-cb6b-46b2-bb7e-2304e3effcce/plan.json) | 미측정 | 0/5 · 검증 미통과 | 미측정 |
