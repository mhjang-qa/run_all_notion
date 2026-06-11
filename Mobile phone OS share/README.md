# Mobile phone OS share

StatCounter의 대한민국 Mobile/Tablet/Console OS share 데이터를 수집해 Notion DB에 업로드하는 로컬 실행용 Python 스크립트입니다.

## 프로젝트 구조

```text
Mobile phone OS share/
├── main.py
├── statcounter_client.py
├── notion_client.py
├── config.py
├── requirements.txt
├── .env.example
└── README.md
```

## 설치 방법

```bash
cd "/Users/jangminho/Desktop/One_click_0519/Mobile phone OS share"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## `.env` 작성 예시

`.env.example`을 복사해 `.env`를 만들고 Notion 정보를 입력합니다.

```bash
cp .env.example .env
```

```dotenv
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=2a473fbd1951804d99c3c3f49c14d450

STATCOUNTER_PAGE_URL=https://gs.statcounter.com/vendor-market-share/mobile-tablet-console/south-korea/
COUNTRY=South Korea
DATA_SOURCE=StatCounter
REQUEST_TIMEOUT=30
```

`NOTION_DATABASE_ID`는 Notion URL에서 코드가 자동 추출하지 않습니다. 반드시 `.env`에 직접 입력해야 합니다.
입력한 ID가 database가 아니라 상위 page ID인 경우에는 해당 page 아래의 child database가 1개일 때 자동으로 찾아 사용합니다.

## Notion DB 속성 매핑

공유된 `OS` DB는 아래 wide-format 구조로 감지되어 실행 시점 현재월 1개 행을 생성하거나 업데이트합니다.

| 코드 키 | Notion 속성명 | 타입 |
| --- | --- | --- |
| `title` | `구분` | `title` |
| `basis_month` | `조사 일자` | `date` |
| `aos` | `AOS` | `number` |
| `ios` | `iOS` | `number` |
| `etc` | `etc` | `number` |

이 구조에서는 StatCounter OS share의 `Android` 값을 `AOS`, `iOS` 값을 `iOS`, 나머지 OS 합계를 `etc`에 저장합니다.

Notion DB 속성명이 확정되지 않았거나 변경되면 `config.py` 상단의 `NOTION_PROPERTIES`를 수정하세요.

기본 매핑은 다음과 같습니다.

| 코드 키 | 기본 Notion 속성명 | 기본 타입 |
| --- | --- | --- |
| `basis_month` | `기준월` | `date` |
| `vendor` | `OS/Vendor 명` | `title` |
| `share` | `점유율(%)` | `number` |
| `country` | `국가` | `select` |
| `source` | `데이터 출처` | `select` |
| `collected_at` | `수집일시` | `date` |
| `source_url` | `원본 URL` | `url` |

중복 방지는 `기준월 + OS/Vendor 명` 조합으로 처리합니다.

## 실행 방법

```bash
cd "/Users/jangminho/Desktop/One_click_0519/Mobile phone OS share"
source .venv/bin/activate
python main.py
```

실행 시 출력되는 로그:

- 수집 성공 건수
- 기존 데이터로 skip된 건수
- Notion 업로드 성공 건수
- 실패 건수 및 사유

## 수집 방식

스크립트는 실행 시점의 현재월(`YYYY-MM`)을 기준월로 사용합니다. 예를 들어 2026년 5월에 실행하면 `2026-05` 데이터를 요청합니다.

수집은 StatCounter `chart.php` 단일월 데이터를 우선 사용합니다. 페이지 스냅샷은 여전히 직전 완료월만 보일 수 있으므로, 현재월 데이터는 스냅샷이 아니라 차트 엔드포인트에서 직접 가져옵니다.

예시 패턴:

```text
https://gs.statcounter.com/chart.php?vendor-KR-monthly-YYYYMM-YYYYMM-bar&device_hidden=mobile%2Btablet%2Bconsole
```

`chart.php` 파싱이 실패했을 때만, 그리고 페이지 스냅샷 월과 요청 월이 같을 때만 HTML 테이블 fallback을 사용합니다.

## 월 1회 실행 방법 예시

macOS crontab을 사용하면 매월 3일 오전 9시에 실행할 수 있습니다.

```bash
crontab -e
```

아래 줄을 추가합니다.

```cron
0 9 3 * * cd "/Users/jangminho/Desktop/One_click_0519/Mobile phone OS share" && /bin/zsh -lc 'source .venv/bin/activate && python main.py' >> "/Users/jangminho/Desktop/One_click_0519/Mobile phone OS share/run.log" 2>&1
```

StatCounter 페이지 스냅샷은 보통 직전 완료월로 보일 수 있습니다. 이 스크립트는 그 값과 무관하게 실행일 기준 현재월을 직접 요청해 업로드합니다.

## 주의사항

- Notion Integration이 대상 DB에 접근 권한을 가져야 합니다.
- Notion DB 속성 타입이 `config.py`의 `type` 값과 다르면 업로드가 실패할 수 있습니다.
- `원본 URL` 같은 선택 속성이 DB에 없으면 경고 후 해당 필드는 업로드에서 제외됩니다.
- `기준월`, `OS/Vendor 명`은 중복 조회에 필요하므로 반드시 DB에 존재해야 합니다.
