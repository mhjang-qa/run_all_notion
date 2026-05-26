# run_all_notion 저장소 설정

`mhjang-qa/run_all_notion` 저장소에는 아래 구성이 필요합니다.

## 필수 파일

- `run_all_notion.py`
- `Bug_Dashboard/`
- `HQI/`
- `notion_hit/`
- `gohanpass_automation/Monitor/`
- `.github/workflows/run_all_notion.yml`

## GitHub Secrets

- `NOTION_TOKEN`
- `NOTION_DB_ID`
- `PUBLISH_GITHUB_TOKEN`

`PUBLISH_GITHUB_TOKEN`은 아래 저장소에 push 권한이 있어야 합니다.

- `mhjang-qa/qa_hitmap`
- `mhjang-qa/HQI`
- `mhjang-qa/gohanpass-web-monitor`
- `mhjang-qa/Bug_Dashboard`

## 실행 방식

대시보드의 `동기화` 버튼은 GitHub Actions `workflow_dispatch`로 `run_all_notion.yml`을 호출합니다.
