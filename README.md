# Yomi Bot (요미 봇)

[한국어](#korean) | [English](#english)

---

<a name="korean"></a>
## 한국어

**요미 봇**은 `discord.py` 기반의 다기능 디스코드 봇입니다. Cog(확장 모듈) 구조로 구성되어 있고, 서버 설정/관리, 경제/미니게임, 초대·로그 추적, 인증(캡차), 그리고 Google Gemini 기반의 챗봇 기능을 제공합니다.

### 핵심 기능

- **AI 챗봇 + 호감도**: Gemini 연동 대화, 유저 가입/호감도 시스템, 자동 일기 등
- **경제/콘텐츠**: 재화·인벤토리·강화·던전/낚시 등(데이터는 SQLite에 저장)
- **서버 관리/설정**: 추방·차단·타임아웃, 환영/퇴장 메시지, 로그 채널/웹훅 생성, 공지 등
- **운영 편의**: 개발자 전용 리로드, 블랙리스트, 역할/인증/초대 추적/경품 추첨 등

### 빠른 시작

### 다운로드(릴리스/ZIP)

GitHub에서 배포(릴리스) 기준으로 내려받는 방법입니다.

1) **Releases에서 다운로드(권장)**
- https://github.com/froxies/Yomibot/releases/latest 로 이동
- Assets에서 `latest (zip)` 파일을 다운로드 후 압축 해제

2) **ZIP으로 다운로드(브랜치 기준)**
- [https://github.com/froxies/Yomibot/archive/refs/heads/main.zip](https://github.com/froxies/Yomibot/releases/download/Latest/latest.zip) 다운로드 후 압축 해제

3) **Git으로 클론**

```bash
git clone https://github.com/froxies/Yomibot.git
cd Yomibot
```

1) **Python 준비**
- Python 3.10+ 권장(현재 프로젝트는 3.12 환경에서 실행 흔적이 있습니다)

2) **의존성 설치**

```bash
pip install -r requirements.txt
```

3) **환경 변수(.env) 설정**
- 루트에 `.env`를 만들고, `.env.example`을 참고해 값을 채웁니다.

| 키 | 필수 | 설명 |
| --- | --- | --- |
| TOKEN | 예 | 디스코드 봇 토큰 |
| COMMAND_PREFIX | 아니오 | 접두사 커맨드 프리픽스(기본값 `!`) |
| GEMINI_API_KEY | 아니오 | Gemini 기능 사용 시 필요(없으면 챗봇의 일부 기능이 비활성화) |
| WEATHER_API_KEY | 아니오 | 날씨 기능 사용 시 필요 |

4) **실행**

```bash
python main.py
```

### 디스코드 개발자 포털 설정

- **Privileged Intents 활성화 권장**: 이 봇은 `Intents.all()`을 사용합니다. 최소한 Message Content / Server Members / Presence 등의 인텐트가 필요할 수 있습니다.
- **초대(Invite) 시 권장 스코프**: `bot`, `applications.commands`

### 사용 방법(커맨드)

- **DM에서는 동작하지 않음**: 전역 체크로 DM 커맨드를 차단합니다(서버에서만 사용).
- **두 가지 커맨드 스타일**
  - 접두사 커맨드: `COMMAND_PREFIX` 기반(기본 `!`)
  - 슬래시 커맨드: `/...` 형태(`discord.app_commands`)

자주 쓰는 예시:
- `/설정 환영`, `/설정 퇴장`, `/설정 확인`
- `/설정 로그채널생성` (전용 로그 채널과 웹훅 자동 생성)
- `!리로드` / `!reload` (개발자/오너 전용: Cog 및 유틸 모듈 리로드 + `.env` 재로딩)
- `!블랙`, `!화이트` (개발자/오너 전용: 블랙리스트 관리)
- `!fsync` (개발자/오너 전용: 슬래시 명령어 즉시 동기화)

### 프로젝트 구조

- `main.py`: 봇 엔트리포인트, DB 초기화, `cogs/` 내 Cog 자동 로드
- `cogs/`: 기능별 Cog 모음(챗봇/경제/관리/유틸/초대/이벤트/인증 등)
- `utils/`: DB/로거/유틸리티 모듈
- `data/yomi.db`: SQLite DB 파일(최초 실행 시 자동 생성/스키마 생성)
- `prompt/`: 챗봇 시스템 프롬프트 텍스트

### 데이터/로그

- DB: `data/yomi.db` (SQLite, `aiosqlite` 사용)
- 로그: `logs/` 및 `*.log` 형태로 생성될 수 있습니다(`.gitignore`에서 기본적으로 제외됨)

### 트러블슈팅

- 실행 즉시 `TOKEN 환경 변수가 설정되지 않았습니다` 오류
  - `.env` 파일에 `TOKEN=...`이 설정되어 있는지 확인하세요.
- Cog 로드 실패가 콘솔에 출력됨
  - 해당 Cog가 요구하는 API 키/권한이 없는지, 의존성이 설치되어 있는지 확인하세요.
- 이미지/차트 출력 관련 오류
  - `plotly`, `kaleido`, `Pillow`가 설치되어 있는지 확인하세요.

### 라이선스

이 프로젝트는 [MIT 라이선스](LICENSE)를 따릅니다.

> [!WARNING]
> - 이 라이선스는 본 레포지토리의 소스코드에 적용됩니다. Discord, Google Gemini, OpenWeather 등 **외부 서비스의 약관/정책**은 별도로 준수해야 합니다.
> - `TOKEN`, `GEMINI_API_KEY`, `WEATHER_API_KEY` 같은 값은 **절대 커밋하지 마세요**. (`.env`는 `.gitignore`로 제외되어 있습니다.)
> - 의존성(패키지) 및 데이터/이미지/폰트 등 제3자 리소스의 라이선스는 각각 다를 수 있으니 배포 전 확인하세요.

### 스타 히스토리

[![Star History Chart](https://api.star-history.com/svg?repos=froxies/Yomibot&type=Date)](https://star-history.com/#froxies/Yomibot&Date)

---

<a name="english"></a>
## English

**Yomi Bot** is a multi-purpose Discord bot built with `discord.py`. It uses a Cog-based modular architecture and provides moderation/server settings, economy/minigames, invite/log tracking, verification (captcha), and an optional Gemini-powered chatbot.

### Quick Start

### Download (Release/ZIP)

Ways to download the project from GitHub.

1) **Download from Releases (Recommended)**
- Go to https://github.com/froxies/Yomibot/releases/latest
- Download `Source code (zip)` (or a packaged asset) and extract it

2) **Download as ZIP (branch)**
- Download and extract: [https://github.com/froxies/Yomibot/archive/refs/heads/main.zip](https://github.com/froxies/Yomibot/releases/download/Latest/latest.zip)

3) **Clone with Git**

```bash
git clone https://github.com/froxies/Yomibot.git
cd Yomibot
```

```bash
pip install -r requirements.txt
python main.py
```

Create a `.env` file (see `.env.example`) and set at least:
- `TOKEN` (required)
- `COMMAND_PREFIX` (optional, default: `!`)
- `GEMINI_API_KEY` / `WEATHER_API_KEY` (optional; enable related features)

### License

MIT License. See [LICENSE](LICENSE).

> [!WARNING]
> - This license applies to the source code in this repository. You must also comply with the Terms/Policies of external services (Discord, Google Gemini, OpenWeather, etc.).
> - Never commit secrets such as `TOKEN`, `GEMINI_API_KEY`, or `WEATHER_API_KEY`. (`.env` is excluded via `.gitignore`.)
> - Third-party dependencies and assets (data/images/fonts) may have their own licenses. Review them before redistribution.

### Star History
[![Star History Chart](https://api.star-history.com/svg?repos=froxies/Yomibot&type=Date)](https://star-history.com/#froxies/Yomibot&Date)
