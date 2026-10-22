# Notion 통합 실행기

`run_all_notion.py`는 챗봇을 제외한 Notion 기반 산출물을 한 번에 갱신합니다.

- QA 결함 히트맵: `notion_hit/qa_heatmap_embed.html`
- HQI 대시보드 데이터: `HQI/embed-data.json`
- 자동화 모니터 데이터: `gohanpass_automation/Monitor/app/static/monitor-data.json`
- 결함 대시보드: `Bug_Dashboard/defect_dashboard_embed.html`
- 실행 요약: `notion_run_summary.json`

## 실행

로컬 파일만 갱신:

```bash
python3 run_all_notion.py --no-publish
```

로컬 갱신 후 GitHub까지 커밋/푸시:

```bash
python3 run_all_notion.py
```

HQI를 저장 메타데이터와 무관하게 강제 재계산:

```bash
python3 run_all_notion.py --force-hqi
```

특정 단계 제외:

```bash
python3 run_all_notion.py --skip-heatmap
python3 run_all_notion.py --skip-hqi
python3 run_all_notion.py --skip-monitor
python3 run_all_notion.py --skip-defect-dashboard
```

결함 대시보드만 직접 갱신:

```bash
cd Bug_Dashboard
python3 generate_defect_dashboard.py --no-publish
python3 generate_defect_dashboard.py --publish --days 30
```

## 환경 변수

각 하위 폴더의 `.env`를 자동으로 읽습니다.

- `notion_hit/.env`
- `HQI/.env`
- `gohanpass_automation/Monitor/.env`

필수 값:

- `NOTION_TOKEN`
- 자동화 모니터용 `NOTION_DB_ID`
- 결함 대시보드용 `NOTION_DEFECT_DB_ID`

결함 대시보드는 기존 결함 DB 설정과의 호환을 위해 `NOTION_DEFECT_DB_ID`, `DEFECT_NOTION_DB_ID`, `NOTION_QA_DEFECT_DB_ID`, `NOTION_DATABASE_ID` 순서로 DB ID를 찾고, 없으면 기존 QA 결함 히트맵 DB ID를 기본값으로 사용합니다. 자동화 모니터용 `NOTION_DB_ID`와 충돌하지 않도록 결함 대시보드에서는 `NOTION_DB_ID`를 사용하지 않습니다.

자동화 모니터 GitHub 저장소를 바꾸려면:

```bash
MONITOR_REPO_URL=https://github.com/OWNER/REPO.git python3 run_all_notion.py
```

결함 대시보드 GitHub Pages 저장소를 지정하려면:

```bash
DEFECT_DASHBOARD_REPO_URL=https://github.com/OWNER/REPO.git python3 run_all_notion.py
```

## GitHub 반영 방식

- 히트맵은 기존 `notion_hit/generate_heatmap.py --publish` 흐름을 그대로 사용합니다.
- HQI는 `HQI` 폴더가 git 저장소이므로 `embed-data.json` 등 변경분을 커밋/푸시합니다.
- 자동화 모니터는 기본으로 `https://github.com/mhjang-qa/gohanpass-web-monitor.git`를 `gohanpass_automation/Monitor/.publish/gohanpass-web-monitor`에 clone한 뒤 최신 파일을 복사해 커밋/푸시합니다.
- 결함 대시보드는 `DEFECT_DASHBOARD_REPO_URL`이 있을 때만 `Bug_Dashboard/.publish/defect-dashboard`에 clone한 뒤 `defect_dashboard_embed.html`을 커밋/푸시합니다. 저장소가 없으면 HTML 생성까지만 수행하고 publish는 건너뜁니다.

## PHP 점검 및 의존성 보안 수정 (2026-10-22)

내부 PHP 소스·런타임·Composer 의존성은 없습니다. `Mobile phone OS share/statcounter_client.py`의 `https://gs.statcounter.com/chart.php`는 StatCounter 외부 데이터 API입니다. 월별 OS/브라우저 점유율 수집과 HTML fallback을 보존하기 위해 유지합니다. 로컬 PHP 설치는 필요하지 않습니다.

OS share와 Monitor의 고정 Requests/python-dotenv 및 Monitor의 FastAPI/Starlette 의존성을 보안 수정 버전으로 갱신했습니다. `pytest tests/test_statcounter_compatibility.py`는 외부 API 요청 없이 URL·응답 파싱·fallback을 검증합니다. 실제 Notion 동기화·Slack 알림·GitHub 자동 publish는 별도 운영 검증이 필요합니다.
