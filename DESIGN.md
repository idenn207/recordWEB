---
name: recordWEB
description: 블루 블랙 패널과 콘플라워 액션으로 만든, NAS 녹화 서버의 어두운 운영 콘솔
colors:
  ground: "#0a0d14"
  surface: "#131824"
  raised: "#1b2231"
  border: "#1f2636"
  control: "#39425a"
  ink: "#e9edf3"
  muted: "#8891a1"
  cornflower: "#5a9bfc"
  cornflower-ink: "#0a0d14"
  cornflower-soft: "#17243b"
  positive: "#4fbf8b"
  positive-bg: "#11291f"
  negative: "#f2667c"
  negative-bg: "#2a1620"
  warning: "#e0ab4a"
  warning-bg: "#2a2415"
typography:
  title:
    fontFamily: "Geist, Pretendard Variable, Pretendard, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Geist, Pretendard Variable, Pretendard, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "-0.01em"
  label:
    fontFamily: "Geist, Pretendard Variable, Pretendard, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.4
  mono:
    fontFamily: "Geist Mono, Pretendard Variable, ui-monospace, monospace"
    fontSize: "13px"
    fontWeight: 400
rounded:
  control: "8px"
  card: "12px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.cornflower}"
    textColor: "{colors.cornflower-ink}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "20px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  badge-recording:
    backgroundColor: "{colors.negative-bg}"
    textColor: "{colors.negative}"
    rounded: "{rounded.pill}"
    padding: "2px 10px"
  nav-item-active:
    backgroundColor: "{colors.cornflower-soft}"
    textColor: "{colors.cornflower}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
---

# Design System: recordWEB

## Overview

**Creative North Star: "The Night Console"**

NAS 소유자가 짧게 들어와 녹화가 돌고 있는지 보고, 끝난 파일을 정리하고, 문제가 있으면 바로 고치고 나가는 도구다. 화면은 그 일을 방해하지 않는 어두운 콘솔이다. 블루 블랙 패널이 층을 이루고, 콘플라워 하나가 주요 행동과 선택만 알린다. 장식은 없고, 정보가 곧 화면이다.

테마는 라이트, 다크, 시스템 설정 세 가지다. 상단 크롬과 로그인 배경은 두 테마 모두 어두운 네이비이고, 그 아래 작업면만 테마를 따른다. 다크는 stack-starter의 `night-cornflower` 토큰, 라이트는 같은 색상환(청색 계열)의 포슬린 작업면이다. 주 색은 다크에서 콘플라워(#5a9bfc), 라이트에서 코발트(#2c5bd0)이며 주요 버튼, 활성 메뉴, 선택, 포커스, 켜진 토글에만 쓴다. 화면 구조는 GAON(가온) ERP의 구조를 따른다: 어두운 상단 크롬, 중앙 정렬 컨테이너, 큰 카드 섹션, 알약형 메뉴.

판매용 대시보드의 문법은 쓰지 않는다. 그라데이션 히어로 수치, 장식 아이콘 카드, 글래스모피즘, 게이머풍 RGB가 없다. 상태가 가장 시끄러운 요소여야 한다.

**Key Characteristics:**
- 어두운 층 세 단계(ground, surface, raised)와 1px 테두리 하나로 구조를 만든다.
- 콘플라워는 주요 버튼, 활성 메뉴, 선택, 포커스, 켜진 토글에만 쓴다.
- 상태색(녹화 중 붉은색, 정상 초록, 경고 노랑)은 항상 글자와 함께 나온다.
- 문제는 숨지 않는다. 감시를 막는 오류는 모든 화면 위에 배너로 뜬다.

## Colors

블루 블랙 바탕에 차가운 회색 글자, 포인트는 콘플라워 한 색.

### Primary
- **Cornflower** (#5a9bfc): 주요 버튼, 켜진 토글, 링크, 포커스 링, 텍스트 선택. 한 화면 영역에서 채워진 버튼은 하나.
- **Cornflower Wash** (#17243b): 활성 메뉴와 선택 행의 배경 틴트.

### Neutral
- **Night Ground** (#0a0d14): 페이지 바탕. 순수 검정이 아니라 푸른 기가 도는 검정.
- **Panel Slate** (#131824): 카드, 사이드바, 입력, 표, 모달의 표면.
- **Raised Slate** (#1b2231): 한 단계 올라온 면(호버, 안내 칩, 단계 안내 칸).
- **Hairline** (#1f2636): 유일한 테두리 색. 1px.
- **Control Steel** (#39425a): 스크롤바와 비활성 컨트롤의 윤곽.
- **Console Ink** (#e9edf3): 본문 글자.
- **Dim Ink** (#8891a1): 보조 글자(크기, 시각, 설명, 라벨).

### Status
- **Recording Rose** (#f2667c) on #2a1620: 녹화 중, 오류, 파괴적 행동.
- **Signal Green** (#4fbf8b) on #11291f: 연결됨, 성공.
- **Amber** (#e0ab4a) on #2a2415: 예약녹화(감시 중), 경고, 쿠키 없음.

### Named Rules
**The One Voice Rule.** 콘플라워는 행동과 선택에만 쓴다. 영역을 "브랜드답게" 보이려고 칠하지 않는다.

**The Word Beside Color Rule.** 상태는 색만으로 전달하지 않는다. 배지는 항상 문구를 담고, 오류는 아이콘과 문장을 함께 둔다.

**The One Border Rule.** 테두리는 Hairline 하나, 1px. 강조가 필요하면 배경 틴트나 상태색 윤곽을 쓴다. 두껍거나 한쪽만 굵은 테두리는 쓰지 않는다.

## Typography

**Display/Body Font:** Geist (Latin), Pretendard Variable (한글), system-ui 대체
**Mono Font:** Geist Mono. 쿠키 값, 파일 경로, 파일명 패턴 같은 데이터에만.

**Character:** 한 글꼴군이 굵기와 크기만으로 모든 역할을 맡는다. 숫자는 표에서 tabular-nums로 맞춘다. 한글은 `word-break: keep-all`로 단어 중간에서 끊지 않는다.

### Hierarchy
- **Title** (600, 16px, 1.4): 페이지 제목, 카드 제목, 모달 제목.
- **Body** (400, 14px, 1.5, 자간 -0.01em): 표 셀, 폼, 일반 문장.
- **Label** (600, 12px): 필드 라벨, 배지, 표 머리글, 도움말.
- **Mono** (400, 13px): 비밀 값과 경로, 파일명 패턴.

### Named Rules
**The Filename Wins Rule.** 파일 표에서 이름 칸이 남는 폭을 전부 가진다. 크기, 시각, 종류는 고정폭의 조용한 보조 칸이다.

## Layout

어두운 상단 크롬(56px, 로고, 주 메뉴, 알림 벨, 테마 메뉴, 계정 메뉴) 아래에 작업면. 모든 화면의 내용은 최대 폭 1280px 컨테이너에 놓이고, 좌우 여백은 16, 24, 32px로 넓어진다(표만이 아니라 제목과 카드도 같은 폭). 모바일(768px 미만)에서는 주 메뉴가 아래 탭바(56px, 안전 영역 포함)로 내려간다.

녹화 화면은 필터 칩 한 줄(전체, 녹화 중, 방송 중, 녹화 대기, 오류, 꺼짐. 개수 포함, URL 쿼리 `?state=`)과 디스크 상태 텍스트, 보기 전환(갤러리, 리스트) 아래에 채널을 보인다. 보기 방식은 이 브라우저에 저장되고, 처음에는 좁은 화면이면 리스트, 넓으면 갤러리다. 상태가 늘어나면 칩 목록에 한 줄을 더하는 것으로 끝난다.

- **갤러리:** 모든 채널이 같은 크기의 카드(`auto-fill`, 최소 17rem). 위쪽 16:9 칸에 방송 중이면 라이브 썸네일, 아니면 채널 프로필 이미지, 그것도 없으면 이름 첫 글자를 둔다. 상태 배지는 칸 위에 겹친다.
- **리스트:** 작은 화면 칸이 있는 행. 정보(이름, 상태, 방송 제목)와 조작(자동 녹화, 버튼)이 넓으면 한 줄에, 좁으면 두 줄에 놓이고 모든 행의 높이가 같다.

오류는 알림 벨, 오류 칩 개수, 행의 오류 배지로 알리고, 새 오류는 화면 오른쪽 아래에 닫을 수 있는 알림으로 한 번 띄운다(본문을 밀거나 제목과 버튼을 가리지 않는다). 로딩은 문구 대신 실제 높이의 스켈레톤을 쓴다.

폼은 입력 수에 따라 자리를 정한다. 1~4개는 모달, 그 이상이거나 섹션이 나뉘면 페이지 안 카드로 둔다.

## Elevation & Depth

면의 단계(ground, surface, raised)와 테두리로 깊이를 만든다. 그림자는 떠 있는 층에만 쓴다.

- **Floating** (`box-shadow: 0 16px 36px rgba(0,0,0,.45)`): 모달, 행 메뉴, 알림.

### Named Rules
**The No-Card-Stack Rule.** 카드 안에 카드를 넣지 않는다. 묶음은 Raised Slate 배경으로 구분한다.

## Shapes

치지직(chzzk.naver.com)의 실측 값을 기준으로 한다. 행동하는 것은 알약, 보여 주는 것은 12px, 구분은 테두리가 아니라 색 대비.

- **버튼, 입력, 검색, 보기 전환, 칩:** 완전한 알약(`rounded-full`). 높이 36~40px, 14~15px, 굵기 600. 윤곽선은 글자색의 15% 투명도 1px(`border-ink/15`). 위험은 `rec/40`.
- **썸네일, 카드:** 12px. 갤러리 썸네일은 테두리와 카드 배경이 없고, 이름과 제목이 그 아래에 바로 온다. 리스트 썸네일은 8px.
- **사이드바 항목:** 8px, 높이 38~48px. 활성은 배경 없이 주 색 글자와 아이콘.
- **면 구분:** 테두리 대신 바탕 색 차이(ground, surface). 테두리는 입력과 윤곽 버튼, 표 머리글 아래 선에만 쓴다.
- **탭:** 밑줄 탭. 활성은 굵기와 글자색, 2px 밑줄.

## Components

### Buttons
- **Shape:** 8px 반경, 14px 가로 패딩, 아이콘은 17px 선 아이콘(획 1.75).
- **Primary:** Cornflower 배경에 Night Ground 글자, 굵기 600. 한 영역에 하나.
- **Secondary:** Panel Slate 배경, Hairline 테두리, 호버에서 Raised Slate.
- **Danger:** 보조 버튼 모양에 Recording Rose 글자. 일반 버튼과 붙여 두지 않는다.
- **Icon button:** 30px 정사각, 호버와 열림에서만 윤곽이 나온다. 행마다 버튼을 늘어놓는 대신 이 아이콘 하나가 메뉴를 연다.

### Chips / Badges
- 알약, 12px 600. 상태 배지는 색 배경과 짝이 되는 글자색, 항상 문구 포함.
- 녹화 중 배지는 점이 1.6초 주기로 깜빡인다. 이것이 유일한 상시 모션이며 `prefers-reduced-motion`에서는 멈춘다.

### Cards / Containers
- Panel Slate 배경, Hairline 1px, 12px 반경, 안쪽 20px. 그림자 없음.

### Inputs / Fields
- Panel Slate 배경, Hairline 테두리, 8px 반경. 라벨은 위, 도움말은 아래(12px Dim Ink). 비밀 값은 Mono.
- **Focus:** Cornflower 2px 윤곽, 2px 간격. **Disabled:** 불투명도 50%와 이유 문구.

### Navigation
- 사이드바 항목은 아이콘과 이름. 활성 항목은 Cornflower Wash 배경에 Cornflower 글자. 녹화 중 채널 수를 붉은 알약으로 붙인다.

### Notifications (signature)
- **Toast:** 화면 상단 중앙. 성공은 초록 윤곽으로 4초 뒤 사라지고, 오류는 붉은 윤곽으로 닫을 때까지 남는다. `role=alert`.
- **Problem banner:** 본문 맨 위. 감시를 막는 오류를 채널 이름, 원인 문장, 해결 버튼(예: 쿠키 다시 등록)과 함께 보인다.

### X 연결 카드 (signature)
- 3단계 안내 칸, 두 입력(auth_token, ct0), 연결 확인 버튼, 단계별 결과 목록, 상태 배지로 이루어진다. 한 칸에 붙여 넣으면 두 칸이 채워진다.

## Do's and Don'ts

### Do:
- **Do** 색은 토큰 별칭(`bg-surface`, `text-muted`, `border-line`)으로만 쓴다. 헥스를 컴포넌트에 직접 쓰지 않는다.
- **Do** 오류에는 무엇이 실패했는지와 다음 행동을 함께 적는다.
- **Do** 비활성 컨트롤 옆에 이유를 적는다.
- **Do** 긴 한국어 제목은 `line-clamp`나 줄바꿈으로 받고 단어 중간에서 자르지 않는다.

### Don't:
- **Don't** 장식용 그라데이션, 글래스 효과, 큰 히어로 수치, 같은 모양의 아이콘 카드 격자를 만들지 않는다.
- **Don't** 카드 안에 카드를 넣거나 한쪽만 굵은 색 테두리를 쓰지 않는다.
- **Don't** 상태를 색만으로 알리지 않는다.
- **Don't** 이모지나 유니코드 기호를 아이콘 대신 쓰지 않는다.
- **Don't** 녹화 점 말고 상시 반복 모션을 추가하지 않는다.
