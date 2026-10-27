# AI 디자인 작업의 UX 흐름 안티패턴 방지: 조사 보고서

대상 앱은 Vite + React 19 + Tailwind v4 + Base UI 기반 한국어 관리 도구입니다. 아래 항목은 검증을 통과한 것만 인용했습니다.

## 1. 결론

**공용으로 재사용할 수 있는 것이 이미 있는가: 부분적으로 있습니다.**

- **시각 UI와 정적 규칙은 재사용할 자산이 있습니다.**
  - 규칙 파일: Vercel Web Interface Guidelines
  - 디자인 스킬과 정적 검출기: Impeccable
  - 토큰 스펙: DESIGN.md
- **이번 사례 (a)의 레이아웃 이동, (b)의 점진적 공개, (d)의 팁 남발, 한국어 keep-all 규칙은 어떤 공개 자료에도 없습니다.** 조사한 모든 렌더 기반 도구와 규칙 파일에서 확인되지 않았습니다.
  - Carbon, PatternFly, Cloudscape 같은 디자인 시스템 문서도 "선택하면 툴바가 생긴다"까지만 말합니다.
  - 그 때문에 표가 밀리는 문제는 다루지 않습니다.
  - 따라서 이 부분은 자체 규칙 파일(`ux-rules.md` 또는 기존 `PATTERNS.md`)과 Playwright 좌표 검증 테스트로 직접 만들어야 합니다.
- **시중의 "디자인 하네스"에 대한 평가: 시각 마감은 돕지만, 상호작용 중 발생하는 UX 흐름 안티패턴은 실제로 막지 못합니다.**
  - Impeccable README는 "깨끗한 검출 결과는 증거일 뿐 증명이 아니다"라고 스스로 밝힙니다. 레이아웃 이동도 언급하지 않습니다.
  - CLS 지표는 사용자 입력 후 500ms 이내의 이동을 `hadRecentInput`으로 제외할 수 있어, 이번 오클릭 버그를 구조적으로 놓칩니다 (https://web.dev/articles/cls).
  - 스크린샷 비평 루프(https://claude-codex.fr/en/mcp/workflow-design-playwright/)는 정지 화면만 보므로 "클릭하면 좌표가 변한다"를 못 잡습니다.
  - 개발자가 겪은 "Playwright로 눌러 봐도 판단이 부실하다"는 현상의 원인은 모델의 안목 부족보다, 판정 기준이 숫자(전후 좌표 차이)로 주어지지 않은 데 있습니다.
  - "더 나은 프롬프트가 아니라 더 나은 측정"이라는 원칙이 근거입니다 (https://www.buildmvpfast.com/blog/figma-to-code-pixel-perfect-loop-ai-agent-screenshot-iterate-2026). 이 글은 Figma 명세 대비 픽셀 루프를 다루므로, UX 규칙에는 방식만 차용합니다.
- **수치 효과는 검증되지 않았습니다.** 안티패턴 감소를 정량으로 보고한 자료는 없습니다. Luca Becker의 "10~15회에서 2~3회"도 저자 본인이 주관적 인상이라고 밝혔습니다.

## 2. 재사용 가능한 자산

신뢰도는 모두 "직접 확인"입니다. 페이지를 열어 인용문을 확인했다는 뜻이며, 해당 도구를 실제로 설치해 돌려 본 것은 아닙니다.

### 규칙 파일 및 스킬

| 이름 | URL | 막아 주는 것 | 도입 방법 |
|---|---|---|---|
| Vercel Web Interface Guidelines | https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/AGENTS.md | `min-w-0` 없는 flex 말줄임 실패, 숫자 정렬, 스켈레톤으로 인한 CLS, "클릭 가능해 보이면 클릭 가능해야 함", 막다른 길 금지 | `docs/ux-rules.md` 뼈대로 복사해 CLAUDE.md에서 import합니다. 상호작용 중 레이아웃 이동 규칙은 없으므로 직접 추가합니다. |
| 같은 저장소 `command.md` | https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md | 콘텐츠 처리(`truncate`, `line-clamp-*`, `break-words`), 제목에 balance/pretty, 구체적 버튼 라벨, 체크박스 단일 히트 영역 | 콘텐츠 처리와 카피 규칙만 프로젝트 룰에 옮깁니다. 글꼴 크기, 툴팁, 툴바 규칙은 없습니다. |
| Impeccable | https://github.com/pbakaus/impeccable | 결정론적 검출 규칙 62개(README 기준, 기사에는 59로 상충), critique/audit/harden/clarify/typeset/layout 명령 | `npx impeccable detect src/ --json`을 CI나 pre-commit에 넣습니다. `--list-rules`로 규칙 목록을 먼저 확인합니다. 훅은 `.claude/settings.local.json`에 설치되어 팀 공유가 안 되므로 CI에도 넣습니다. 이 저장소는 이미 `PRODUCT.md`가 수정된 상태라 Impeccable 설정이 일부 있는 것으로 보이나, 확인하지 못했습니다. |
| Anthropic frontend-design SKILL.md | https://raw.githubusercontent.com/anthropics/claude-code/main/plugins/frontend-design/skills/frontend-design/SKILL.md | 문구 규칙(버튼은 결과를 말함, 오류는 원인과 해결), 품질 하한(반응형, 포커스, reduced motion) | 카피 규칙을 한국어로 번역해 `ux-rules.md`에 넣습니다. 관리 도구에서는 "독특한 미학" 지시보다 PRODUCT.md 톤이 우선한다고 명시합니다. |
| Anthropic 블로그: Improving frontend design through Skills | https://claude.com/blog/improving-frontend-design-through-skills | 안전한 기본값으로 수렴하는 현상을 약 400토큰 스킬로 완화하는 형식 참고 | 자체 UX 스킬을 같은 형태로 씁니다. 맥락 한 단락, XML 태그 섹션, 마지막에 "Avoid:" 목록. 정량 효과는 글에 없습니다. |
| UI UX Pro Max Skill | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | 119개 UX 가이드 CSV, 텍스트 리플로우, 칩 wrap, 375/768/1024/1440 점검 | 통째 설치하지 말고 `data/` CSV에서 필요한 항목만 한국어로 번역해 옮깁니다. |
| DESIGN.md 스펙 (Google) | https://github.com/google-labs-code/design.md | 토큰의 단일 출처, `lint`(대비 등 11개 규칙), Layout 및 Do's and Don'ts 섹션 | `npx @google/design.md export --format css-tailwind`로 Tailwind v4 `@theme` CSS를 얻습니다. `--format tailwind`는 v3 JSON 별칭입니다. alpha 단계라 스키마가 바뀔 수 있습니다. 행동 규칙 섹션은 없습니다. |
| awesome-design-md (VoltAgent) | https://github.com/voltagent/awesome-design-md | 브랜드별 DESIGN.md 9개 섹션과 `preview.html`(Linear, Vercel, Sentry 등) | 관리 도구와 가까운 Linear, Vercel, Sentry 2~3개의 Do's and Don'ts와 Responsive Behavior만 읽고 병합할 항목을 고릅니다. |
| bitdoze 스킬 비교 | https://www.bitdoze.com/best-ai-skills-for-web-design/ | 스킬 비교표(2차 요약) | jakubkrehel/skills의 리뷰 워크플로, emilkowalski/skills의 44px 최소 히트 영역 항목을 열어 체크리스트만 발췌합니다. |
| awesome-cursorrules | https://github.com/PatrickJS/awesome-cursorrules | Toss-Style 항목 등 | 우선순위 낮음. 본문은 열어 보지 않았습니다. |

### 레퍼런스 소스

| 이름 | URL | 비고 |
|---|---|---|
| Refero MCP | https://doc.refero.design/mcp/getting-started | 유료(Pro/Team/Lifetime), 월 8,000 호출. 토큰은 커밋 금지 |
| Mobbin MCP | https://mobbin.com/mcp | 유료. 60초당 60회 제한. 흐름 검색에 강점. 관리 콘솔에 약하다는 말은 추정 |
| Lazyweb | https://www.lazyweb.com/ | 281k+ 화면. 설치 스크립트는 파이프 실행이라 먼저 받아서 읽고 실행. 비Pro는 부분 리포트 |
| 레퍼런스 선행 워크플로 글 | https://www.ai.joaoqueiros.com/blog/mobbin-mcp-claude-code-ui-reference-workflow | 레퍼런스 단계를 빌드 앞에 분리. 질문 5개 게이트는 필수 절차가 아닌 프롬프트 예시 |

### 렌더 및 검수 하네스 (참고용)

| 이름 | URL | 비고 |
|---|---|---|
| OneRedOak design-review 에이전트 | https://raw.githubusercontent.com/OneRedOak/claude-code-workflows/main/design-review/design-review-agent.md | Playwright MCP 기반, Phase 0~7과 Blocker/High/Medium/Nitpick 분류, 뷰포트 1440/768/375. 저장소 메인 페이지에는 단계 구조가 없고 이 raw 파일에만 있음 |
| TechNickAI design-reviewer | https://www.claudepluginhub.com/agents/technickai-core-plugins-core/agents/design-reviewer | 비평 프롬프트 뼈대. 레이아웃 이동 항목은 없음 |
| jezweb responsiveness-check | https://www.skills.sh/jezweb/claude-skills/responsiveness-check | 오버플로, 스태킹, 내비 전환, 리플로 점검. Snyk 경고 있음, 설치 전 확인 필요 |
| Summit Simulator | https://github.com/abhishm/summit-simulator | 적대적 비평가가 점수와 결함 3개 이상을 내고, 다음 라운드에서 fixed/open을 검증. 루프 설계 참고용 |
| MindStudio Self-QA | https://www.mindstudio.ai/blog/what-is-self-qa-loop-ai-agents | 다른 비평가, 반복 상한 2~3회, 해결 불가 시 사람에게 에스컬레이션. 일반 원칙 글 |
| Zero overflow 글 | https://www.web-developpeur.com/en/blog/responsive-testing-claude-code-playwright | 폭마다 resize 후 오버플로 0일 때만 다음으로 진행하는 루프 |
| Vercel Toolbar Layout Shift Tool | https://vercel.com/docs/workflow-collaboration/layout-shift-tool | 이동 요소와 `data-allow-shifts` 예외 속성 설계를 차용할 수 있음. 사용자 입력 후 이동 판정 방식은 페이지에 없음 |

## 3. 안티패턴 8가지별 정리

**공통 전제.** 아래 해법 중 "자체 규칙"으로 표시한 것은 디자인 시스템 문서에서 직접 근거를 확인하지 못했습니다. 이 개발자가 명문화해야 합니다. 현재 저장소에는 `ux-patterns` 스킬이 있어 `PATTERNS.md`를 기준으로 삼으므로, 아래 규칙은 그 파일에 넣는 것이 자연스럽습니다.

### (a) 선택 툴바로 표가 밀리는 레이아웃 이동

- **원인.** 선택 상태에서 기존 콘텐츠 위에 DOM이 동적으로 추가되는 것이 이동의 대표 원인입니다 (https://web.dev/articles/cls). CLS는 입력 후 500ms 이내 이동을 `hadRecentInput`으로 제외할 수 있어 이 버그를 못 잡습니다. Carbon도 바가 선택 시 표 상단에 나타난다고만 하고 표가 밀리는 문제는 다루지 않습니다 (https://carbondesignsystem.com/components/data-table/usage/).
- **업계 표준 해법.**
  - 직접 근거가 있는 부분: Carbon은 일괄 바 높이를 행 높이와 맞추고, 일괄 모드에서 행 단위 액션과 오버플로 메뉴를 비활성화합니다. Cloudscape는 일괄 액션을 표 헤더에 상주시키고 sticky를 권합니다 (https://cloudscape.design/patterns/general/actions/global-actions/). PatternFly는 벌크 선택기를 툴바 첫 요소로 두고 선택 개수를 텍스트 라벨로 표시합니다 (https://www.patternfly.org/patterns/bulk-selection/). eBay는 일괄 작업 바를 스크롤 시 상단에 고정합니다 (https://playbook.ebay.com/design-system/patterns/bulk-edit).
  - 자체 규칙인 부분: "자리 예약 후 같은 자리에서 내용만 교체", "하단 fixed 오버레이"는 위 문서에 명시되어 있지 않습니다. 개발자가 직접 제시한 해법을 규칙으로 명문화합니다.
- **AI에게 줄 규칙 문장.**
  - "표 위 툴바 행은 선택 여부와 무관하게 항상 같은 높이로 렌더한다. 선택 전에는 비활성 액션과 '0개 선택'을 보이고, 선택 후에는 같은 자리에서 내용만 바꾼다."
  - "대안으로 일괄 툴바를 `position: fixed` 하단 오버레이로 두고, 표 컨테이너에 하단 패딩을 항상 확보한다."
  - "체크, 해제, 전체 선택, 필터 변경 어느 상호작용으로도 행의 y 좌표가 바뀌면 실패다."
  - "CLS 지표를 근거로 통과 판정하지 않는다."
- **Playwright 자동 판정.**
  ```ts
  const pos = () => page.locator('tbody tr input[type=checkbox], tbody tr [role=checkbox]')
    .evaluateAll(els => els.map(e => { const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y)]; }));
  const before = await pos();
  await page.getByRole('checkbox').nth(1).check();
  await page.waitForTimeout(300);
  expect(await pos()).toEqual(before);
  // 이어서 두 번째 체크, 첫 해제, 전체 선택, 필터 변경 순으로 반복
  ```
  - 스크롤을 고정한 상태에서 비교합니다 (`boundingBox`는 스크롤 영향을 받음, https://playwright.dev/docs/api/class-locator).
  - 같은 좌표를 다시 클릭했을 때 같은 체크박스가 토글되는지는 `page.mouse.click(x, y)` 후 상태로 확인합니다.
  - 오버레이 방식이면 `getComputedStyle(el).position`이 `fixed` 또는 `sticky`인지 단언합니다.
  - Chromium 보조 수단으로는 `addInitScript`에서 `PerformanceObserver`로 `layout-shift`를 모두 수집하고(`hadRecentInput` 필터 없이), 클릭 후 300ms 뒤 항목 수가 0인지 봅니다 (https://web.dev/articles/debug-layout-shifts의 변형으로, 이 변형은 페이지에 적힌 코드가 아니라 제안입니다). 주 검증은 좌표 비교입니다.

### (b) 점진적 공개 실패

- **원인.** 어느 공개 자료에도 점진적 공개 규칙은 없습니다 (ai-design-skills 조사 결론). AI가 정보를 빠뜨리지 않으려는 쪽으로 수렴하기 때문으로 보이나, 이는 추정입니다.
- **업계 표준 해법.** Carbon은 확장 행 내용이 답답하면 전용 페이지나 측면 패널을 쓰라고 합니다 (https://carbondesignsystem.com/components/data-table/usage/). 행 하나 대상 액션은 툴바가 아니라 행 kebab 메뉴에 둡니다 (https://www.patternfly.org/components/table/design-guidelines). DataTables Responsive는 공간이 모자라면 우선순위가 낮은 열부터 숨깁니다 (https://datatables.net/extensions/responsive/priority). 숨긴 값은 행 확장이나 드로어로 보여 줍니다.
- **AI에게 줄 규칙 문장.**
  - "목록과 표의 기본 열은 식별자, 상태, 핵심 수치 하나, 액션으로 제한한다. 나머지 필드는 행 클릭 시 드로어나 다이얼로그에서 보여 준다."
  - "한 화면의 표 열은 N개(프로젝트에서 정함) 이하로 한다."
  - "행 하나에만 해당하는 액션은 행 메뉴에 두고, 복수 선택 액션만 일괄 툴바에 둔다."
- **Playwright 자동 판정.** 열 수와 화면의 입력 필드 수를 숫자로 단언합니다. 예를 들어 `th` 개수가 상한 이하인지, 기본 화면에서 상세 필드 라벨이 보이지 않는지(드로어 열기 전)를 확인합니다. 상한값은 이 개발자가 정해야 하며 자료에 정답은 없습니다.

### (c) 개발 주석성 문구를 UI에 풀어 씀

- **원인.** 모델이 구현 의도를 사용자에게 설명하려는 경향입니다 (추정).
- **업계 표준 해법.** Anthropic frontend-design 스킬: "문구는 이해하고 사용하기 쉽게 만들 때만 디자인에 존재한다" (https://raw.githubusercontent.com/anthropics/claude-code/main/plugins/frontend-design/skills/frontend-design/SKILL.md). Vercel: 버튼 라벨은 구체적으로 (https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md). 다만 Vercel 가이드에 "Save API Key" 문구 규칙 원문은 없다고 검증 단계에서 정정되었으니, 이 문구를 규칙 근거로 직접 인용하지 않습니다.
- **AI에게 줄 규칙 문장.**
  - "구현 방식, 내부 동작, 데이터 흐름을 설명하는 문장을 UI에 쓰지 않는다. 그런 설명은 코드 주석에 둔다."
  - "버튼 라벨은 결과를 말한다(예: 저장, 업로드 시작). 확인과 제출은 금지한다."
  - "오류 문구는 원인과 해결 방법을 함께 쓴다."
- **Playwright 자동 판정.** 완전 자동화는 어렵습니다. 화면의 모든 텍스트 노드를 추출해 금지어 목록(예: "내부적으로", "API 호출", "state", "mutation")과 비교하는 보조 검사는 가능합니다. 금지어 목록은 프로젝트에서 정해야 합니다. Impeccable `clarify`를 LLM 리뷰 단계로 병행합니다.

### (d) 팁, 안내문 남발

- **원인.** (c)와 같습니다.
- **업계 표준 해법.** 직접 근거는 확인하지 못했습니다. Carbon의 열 제목 가이드(1~2어절, 길면 툴팁)와 frontend-design의 문구 원칙을 간접 근거로 씁니다.
- **AI에게 줄 규칙 문장.**
  - "안내문, 툴팁, 헬프 텍스트는 사용자가 오류를 낼 수 있는 입력이나 되돌릴 수 없는 동작에만 쓴다."
  - "한 화면의 상시 노출 안내문은 N개 이하로 한다. 툴팁은 잘린 전체 값 표시와 아이콘 단독 버튼 설명에 한정한다."
- **Playwright 자동 판정.** 상시 노출되는 `.notice`, `.hint`, 안내성 요소 개수를 세어 상한을 단언합니다. 클래스명은 프로젝트에 맞춰야 합니다. 상한값은 자료에 정답이 없어 개발자가 정합니다.

### (e) 표 머리글과 카드의 의도치 않은 줄바꿈

- **원인.** 한국어는 어절 단위 줄바꿈(`keep-all`) 없이는 글자 단위로 꺾이고, `balance`는 `keep-all`이 없으면 효과가 사라집니다 (https://daleseo.com/css-text-wrap/).
- **업계 표준 해법.**
  - Carbon: 열 제목은 1~2단어, 길면 2줄까지 줄바꿈 후 말줄임, 전체는 hover 툴팁 (https://carbondesignsystem.com/components/data-table/usage/).
  - Primer: 줄바꿈 우선, 말줄임은 열 너비가 고정일 때의 최후 수단 (https://primer.style/product/components/data-table/guidelines/).
  - MDN: `balance`는 Chromium 6줄, Firefox 10줄 이하에서만 적용되고 `pretty`는 본문 고아줄을 줄임 (https://developer.mozilla.org/docs/Web/CSS/text-wrap-style).
- **AI에게 줄 규칙 문장.**
  - "전역에 `html { word-break: keep-all; overflow-wrap: break-word }`를 둔다."
  - "제목과 카드 타이틀에는 `text-balance`, 본문 설명에는 `text-pretty`를 쓴다. `keep-all` 없이 `balance`를 쓰지 않는다. 표 전체 셀에 `balance`를 일괄 적용하지 않는다."
  - "표 머리글은 1~2어절로 쓰고 `line-clamp-2` + `title`을 단다."
  - "flex 자식에는 `min-w-0`을 둔다."
  - "카드의 한 줄 문구는 `truncate` 또는 폭에 맞는 `min-h`로 처리하고, 의도하지 않은 줄 수 변화가 없어야 한다."
- **Playwright 자동 판정.** 폭을 바꿔 가며(768/1024/1280/1440, 필요하면 375) 줄 수를 단언합니다.
  ```ts
  const lines = await page.locator('thead th, [data-card-title]').evaluateAll(els =>
    els.map(e => Math.round(e.getBoundingClientRect().height / parseFloat(getComputedStyle(e).lineHeight))));
  expect(Math.max(...lines)).toBeLessThanOrEqual(2);
  ```
  - 카드 제목은 폭별 줄 수가 기준 폭과 같은지를 비교합니다. `getClientRects` 기반 줄 수 측정은 못 잡는 경우가 있어 별도 보강이 필요하다고 조사에서 지적되었습니다.
  - `scrollWidth > clientWidth` 검사는 `overflow:auto` 표 래퍼, `truncate` 요소, 숨김 요소에서 오탐이 나므로 `getComputedStyle(el).overflowX === 'visible'`인 경우만 보고하도록 좁힙니다 (https://www.web-developpeur.com/en/blog/responsive-testing-claude-code-playwright).

### (f) margin, padding 누락으로 요소가 붙음

- **원인.** 간격을 임의값으로 쓰거나 근접성 원칙을 놓칩니다.
- **업계 표준 해법.** Atlassian은 8px 기반 토큰과 근접성, 위계, 리듬 원칙을 제시합니다. 실제 스케일은 0/2/4/6/8/12/16/20/24/32/40/48/64/80px입니다 (https://atlassian.design/foundations/spacing). 이 문서는 1:2 같은 비율을 명시하지 않으므로 비율은 프로젝트 규칙입니다.
- **AI에게 줄 규칙 문장.**
  - "간격은 Tailwind 스케일 토큰만 쓰고 `p-[13px]` 같은 임의값을 금지한다."
  - "그룹 내부 간격은 그룹 사이 간격보다 작아야 한다."
  - "인접한 형제 요소 사이 간격이 0인 쌍이 없어야 한다."
  - "고정 `height`를 쓰지 않고 `min-height`를 쓴다 (WCAG 1.4.12)."
- **Playwright 자동 판정.**
  - 인접 형제 요소의 bounding box 간 거리가 0인 쌍을 센다 (button, input, card 등 대상 한정).
  - WCAG 1.4.12 스모크: `page.addStyleTag({content:'*{line-height:1.5!important;letter-spacing:.12em!important;word-spacing:.16em!important} p{margin-bottom:2em!important}'})` 주입 후 잘림과 겹침을 검사합니다 (https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html).
  - 히트 영역은 최소 24x24 CSS px입니다 (https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html). `boundingBox`의 width, height가 24 이상인지 단언합니다. 이는 오클릭 방지의 하한이며 레이아웃 이동과는 별개입니다.
  - `npx impeccable detect`로 정적 간격 문제를 보조 검출합니다. 어떤 간격 규칙이 있는지는 `--list-rules`로 확인해야 합니다.

### (g) 글꼴 축소로 내용을 욱여넣음

- **원인.** 공간이 모자랄 때 정보를 줄이지 않고 글꼴을 줄입니다.
- **업계 표준 해법.** WCAG는 최소 글꼴 크기를 정하지 않습니다. 따라서 하한은 프로젝트 규칙으로 정해야 합니다. 공간 부족 시 열을 숨기는 것이 표준 대안입니다 (https://datatables.net/extensions/responsive/priority). Primer도 좁은 화면에서는 덜 중요한 열을 빼거나 가로 스크롤을 쓰라고 합니다.
- **AI에게 줄 규칙 문장.**
  - "본문과 표 셀은 13px 이상, 절대 하한은 12px이다 (프로젝트 규칙, 값은 개발자가 확정)."
  - "공간이 모자라면 글꼴을 줄이지 말고 열을 숨기거나 드로어로 옮긴다."
  - "Tailwind v4에서 `hidden @3xl:table-cell` 같은 컨테이너 쿼리나 `xl:table-cell`로 열 우선순위를 구현한다."
- **Playwright 자동 판정.**
  ```ts
  const small = await page.evaluate(() => [...document.querySelectorAll('body *')]
    .filter(e => e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
    .filter(e => parseFloat(getComputedStyle(e).fontSize) < 12).length);
  expect(small).toBe(0);
  ```
  가시 텍스트 노드의 12px 미만 개수를 센다는 지표입니다 (buildmvpfast 글의 "숫자로 판정" 방식). 임계값 12는 위 프로젝트 규칙 가정입니다.

### (h) 폼 폭과 저장 버튼 위치

- **원인.** 폼 컨테이너 폭이 정해지지 않아 오른쪽 여백이 남고, 저장 버튼이 맥락 없이 배치됩니다.
- **업계 표준 해법.** 이 사례에 직접 맞는 폼 폭이나 저장 버튼 위치 규칙은 이번 검증 통과 자료에 없습니다. 근접성 원칙(Atlassian)으로 필드 그룹과 버튼을 묶는 정도가 근거입니다. DESIGN.md의 Layout 섹션에 폼 최대폭과 버튼 위치를 문장으로 박는 방식이 제안되었습니다 (https://github.com/google-labs-code/design.md).
- **AI에게 줄 규칙 문장 (자체 규칙, 값은 개발자가 확정).**
  - "설정 폼은 `max-w-*` 한 값으로 폭을 제한하고 페이지 안에서 일관된 정렬(좌측 정렬 또는 중앙)을 유지한다."
  - "저장 버튼은 해당 폼 카드의 하단 또는 sticky 푸터에 둔다. 페이지 전역 저장 버튼과 폼별 저장 버튼을 섞지 않는다."
  - "변경이 없으면 저장 버튼은 비활성화한다."
- **Playwright 자동 판정.**
  - 폼 컨테이너의 우측 여백(`viewport.width - right`)이 좌측 여백과 허용 오차 내에서 같은지, 또는 `max-w` 값과 일치하는지 단언합니다.
  - 저장 버튼의 y 좌표가 폼 마지막 필드보다 아래인지 확인합니다.
  - 이 항목은 스크린샷 비교(`toHaveScreenshot`, https://playwright.dev/docs/test-snapshots)를 보조로 쓰되, 한국어 폰트를 CI와 로컬에서 고정해야 합니다.

## 4. 레퍼런스 큐레이션 부담을 줄이는 운영 방식

조사된 도구(Refero, Mobbin, Lazyweb)는 화면 단위 근거를 줍니다. 규칙은 못 줍니다. 따라서 레퍼런스는 "규칙을 보강하는 보조"로 쓰고, 선택은 사람이 아니라 정해진 질문으로 좁히는 구조가 낫습니다. 아래 구조는 조사 결과에서 근거가 있는 부분(레퍼런스 선행 워크플로, DESIGN.md 섹션 구조, 레퍼런스 MCP 검색 질의)을 조합한 설계 제안이며, 한 번 가동해 본 검증은 없습니다.

```
docs/
  ux-rules.md          # 명령형, 검증 가능한 규칙 (3절의 규칙 문장)
  references/
    _index.md          # 장르별 파일 목록, 읽는 순서
    table-bulk-select.md
    settings-form.md
    upload-queue.md
    file-explorer.md
    capture/           # 화면 캡처 (파일명: 패턴-출처-날짜.png)
```

- **각 `references/<패턴>.md`의 구성**
  - 레퍼런스 3~5개(출처 URL, 캡처 경로)
  - 공통 패턴 한 줄
  - "왜 좋은가" 메모 (예: 툴바가 상주해 표가 안 밀림)
  - 정답 예시와 오답 예시 (오답은 이 앱에서 실제로 발생한 사례 캡처, 예: 체크박스 클릭 후 표가 한 칸 내려간 화면)
  - 이 앱 적용안과 체크 항목(레이아웃 이동, 점진적 공개, 카피)
- **AI가 읽게 하는 규약.** CLAUDE.md에 다음을 둡니다. "신규 화면이나 큰 변경은 코드 전에 `references/<화면>.md`를 읽거나 작성하고, 사용자 승인 후 구현한다. 레퍼런스를 복제하지 않고 기존 토큰, 간격, 컴포넌트를 유지한다" (https://www.ai.joaoqueiros.com/blog/mobbin-mcp-claude-code-ui-reference-workflow의 가드레일과 같은 취지). 이 저장소에는 이미 `ux-patterns` 스킬이 있어 `PATTERNS.md`를 기준으로 삼으므로, 이 규약은 그 스킬에 합치는 편이 작업량이 적습니다.
- **사람이 고르는 일을 줄이는 방법**
  - 사람은 "한 장짜리 문서"만 검토합니다. 레퍼런스 선택 자체를 AI에게 맡기되 질의를 고정합니다. 예: "파일 목록 표의 bulk selection 상태 화면 5개를 찾아, 툴바가 표를 밀어내는지/고정 영역인지/하단 오버레이인지 분류하고 `references/file-table.md`에 기록하라. 코드는 쓰지 마라."
  - 레퍼런스 검색은 밀어내는지 여부 같은 "분류 질문"으로 던집니다. "좋은 디자인을 찾아라"는 질문이 뻔한 결과를 부른다는 개발자의 불만에 대한 대응입니다. 이 질의 방식이 실제로 더 나은 결과를 내는지는 검증하지 못했습니다.
  - 사람 개입은 오답 예시 캡처를 쌓는 것입니다. 이번 체크박스 사례처럼 실제 실패가 발견될 때마다 오답 캡처와 규칙 한 줄을 추가합니다.
  - 무료인 Lazyweb으로 시험한 뒤 Refero 구독 여부를 정합니다 (Lazyweb 비Pro는 부분 리포트).
  - 한국어 제품 레퍼런스(Toss 등)는 awesome-cursorrules의 Toss-Style 항목 본문을 확인하지 못했습니다.

## 5. 권장 하네스 설계

**루프: 생성, 렌더, 상호작용 검수, 비평, 수정.** 구현과 리뷰는 서로 다른 서브에이전트로 분리하고, 리뷰어에게는 구현 의도 없이 결과와 체크리스트만 줍니다 (MindStudio). 반복 상한은 2~3회이고 미해결 항목은 "미해결 + 사유"로 사람에게 넘깁니다. Summit Simulator의 방식을 차용해, 비평 출력에 결함 목록과 이전 결함의 fixed/open 검증 표를 두고, 2라운드 동안 개선이 없으면 중단합니다 (이 중단 규칙은 원문에서 전체 redesign 루프 기준이었습니다).

| 단계 | 구성 | 판정 기준 |
|---|---|---|
| 생성 | 메인 에이전트가 `ux-rules.md`와 `references/`를 읽고 구현 | 규칙 위반 사전 점검 |
| 정적 검수 | `npx impeccable detect src/ --json` | 결정론적 규칙 위반 수 |
| 렌더 검수 | Playwright 테스트(스크립트) | 아래 표 |
| 비평 | `design-review` 서브에이전트(OneRedOak 정의 포크) | Blocker/High/Medium/Nitpick |
| 수정 | 메인 에이전트 | 위반 수가 줄지 않으면 구조 문제로 보고 분할 |

**Playwright 스크립트 구성 (숫자로 판정).**

| 검사 | 단언 |
|---|---|
| 행 좌표 불변 | 선택, 해제, 필터 후 체크박스 y 차이 0 |
| 같은 좌표 재클릭 | 같은 체크박스가 토글됨 |
| 줄 수 | 표 머리글 최대 2줄, 카드 제목은 폭별 줄 수 동일 |
| 오버플로 | `overflowX: visible`인 요소의 `scrollWidth > clientWidth` 0개 |
| 글꼴 하한 | 12px 미만 가시 텍스트 0개 |
| 히트 영역 | 24x24 이상 |
| 간격 | 인접 요소 간격 0인 쌍 0개 |
| 접근성 | `@axe-core/playwright`로 기본, 모달 열림, 행 선택 상태에서 `violations` 빈 배열 (https://playwright.dev/docs/accessibility-testing). 색 대비 등은 잡지만 레이아웃 이동과 카피는 못 잡음 |
| 스크린샷 | 선택 전/후/해제 후 표 영역 `toHaveScreenshot`, 폭 3개 매트릭스. 보조 수단 |

**비평 에이전트 정의.** OneRedOak `design-review-agent.md`를 `.claude/agents/design-review.md`로 복사하고 Phase 1(상호작용)에 다음을 추가합니다.
- 체크박스 선택 전 모든 행의 `boundingBox.y`를 기록한다.
- 선택 후 다시 기록해 한 행이라도 다르면 Blocker로 분류한다.
- 같은 좌표를 다시 클릭해 같은 행이 해제되는지 확인한다.

TechNickAI의 비평 프롬프트 뼈대를 쓰되, 점검 항목에 레이아웃 이동, 첫 화면 정보량, 개발 주석성 문구, 12px 미만 글꼴, 표 머리글 줄바꿈을 직접 추가합니다 (원문에 없는 항목들입니다).

**최소 구현 순서.**
1. `docs/ux-rules.md` 작성: Vercel `AGENTS.md`를 뼈대로 하고 3절의 규칙 문장을 추가합니다. 기존 `PATTERNS.md`가 있으면 거기에 합칩니다. CLAUDE.md에서 import합니다.
2. 행 좌표 불변 Playwright 테스트 한 개(3절 (a))를 가장 먼저 작성합니다. 이번 사례를 직접 막는 유일한 수단입니다.
3. `npx impeccable detect`를 CI에 추가하고 기준선을 기록합니다.
4. 줄 수, 오버플로, 글꼴 하한, 간격 검사를 한 스펙 파일로 묶습니다.
5. `design-review` 에이전트를 포크합니다.
6. `references/` 구조를 만들고 실제 실패 사례부터 오답 예시로 쌓습니다.
7. 필요할 때 Refero나 Lazyweb을 붙입니다 (선택 사항, 후순위).

## 6. 한계와 확인하지 못한 것

- **자체 규칙이 필요한 부분.** 레이아웃 이동(툴바 자리 예약 또는 하단 오버레이), 점진적 공개, 팁 남발, 개발 주석성 문구 금지, 한국어 keep-all은 검증 통과 자료에서 직접 근거를 찾지 못했습니다. 이 부분의 규칙 문장과 테스트는 이 보고서가 제안한 것이며, 업계 표준이 아닙니다.
- **디자인 시스템 문서의 한계.** Carbon, Cloudscape, PatternFly, Primer는 모두 체크박스 선택으로 표가 밀리는 문제를 직접 다루지 않습니다. 해법 A(자리 예약)와 B(오버레이)의 직접 출처는 없습니다.
- **제외한 항목.**
  - Elastic EUI 표 선택 패턴: 선택 시 개수 표시가 교체된다는 문장을 확인하지 못했습니다.
  - Shopify Polaris IndexTable: 원 URL이 301로 이동했고 주장을 확인하지 못했습니다.
  - Material Design: 리다이렉트 후 JS 렌더링으로 내용 확인 불가였습니다.
  - LANL Mesa: 인증서 만료로 열리지 않았습니다 (Carbon에서 같은 규칙을 직접 확인했습니다).
  - playwright-spatial-layout-mcp: 403으로 존재와 내용을 확인하지 못했습니다. `boundingBox` 전후 비교를 직접 작성하면 됩니다.
  - x1xhlol/system-prompts-and-models-of-ai-tools: 저장소는 실존하나 디자인 규칙 본문을 열어 보지 못했고 비공식 추출물이라 제외했습니다.
- **실제 호출하지 않은 도구.** 레퍼런스 MCP(Refero, Mobbin, Lazyweb)는 문서와 페이지로만 확인했고, 실제 검색 결과의 품질은 확인하지 못했습니다. 여기서 나온 도구 중 어느 것도 이 저장소에서 실행해 보지 않았습니다.
- **수치와 임계값은 가정.** 12px 글꼴 하한, 13px 본문 권장, 열 수 상한, 안내문 개수 상한, 24px 히트 영역 외의 모든 임계값은 프로젝트에서 정해야 합니다. WCAG에 최소 글꼴 크기는 없습니다. 24px는 WCAG 2.5.8 근거가 있습니다.
- **정정 사항.**
  - Impeccable 검출기 규칙 수는 README 기준 62개이고 기사에는 59개로 적혀 있어 엇갈립니다. `--list-rules`로 직접 확인하십시오.
  - Vercel 가이드에 "Save API Key" 문구 규칙 원문은 없습니다.
  - DESIGN.md의 Tailwind v4 export 형식명은 `css-tailwind`입니다.
- **브라우저 한계.** `LayoutShift` API는 실험적이고 Chromium 전용입니다. 좌표 비교가 주 검증이고 observer는 보조입니다. Base UI Checkbox는 `role=checkbox`인 span/button일 수 있어 셀렉터를 실제 DOM에 맞춰야 합니다.
- **자동 검사의 한계.** `axe-core`는 일부 접근성 문제만 잡습니다 (Playwright 공식 문서도 명시). 정적 검출기와 스크린샷 비교는 이번 사례를 못 잡습니다. 카피 품질(c, d)은 완전 자동 판정이 어렵고 LLM 리뷰와 사람 검수가 필요합니다.
- **저장소 상태.** 현재 `PRODUCT.md`와 다수의 `apps/web` 파일이 미커밋 수정 상태입니다. `ux-patterns` 스킬과 `PATTERNS.md`의 실제 내용은 읽어 보지 않았으므로, 위 규칙과 겹치거나 충돌하는지는 확인하지 못했습니다.