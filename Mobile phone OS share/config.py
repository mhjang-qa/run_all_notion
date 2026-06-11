"""
환경설정 및 Notion 속성 매핑.

Notion DB의 속성명이 바뀌면 아래 NOTION_PROPERTIES만 수정하면 됩니다.
type 값은 Notion 속성 타입(title, rich_text, number, date, select, url)과 맞춰 주세요.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Notion DB 속성 매핑 영역
# ---------------------------------------------------------------------------
# - name: 실제 Notion DB 속성명
# - type: 실제 Notion DB 속성 타입
# - enabled: False로 바꾸면 업로드/조회 대상에서 제외
#
# 중복 체크에는 basis_month + vendor 조합을 사용합니다.
# title 속성은 Notion page 생성에 필수이므로 vendor를 title로 두는 구성을 기본값으로 합니다.
NOTION_PROPERTIES: dict[str, dict[str, Any]] = {
    "basis_month": {"name": "기준월", "type": "date", "enabled": True},
    "vendor": {"name": "OS/Vendor 명", "type": "title", "enabled": True},
    "share": {"name": "점유율(%)", "type": "number", "enabled": True},
    "country": {"name": "국가", "type": "select", "enabled": True},
    "source": {"name": "데이터 출처", "type": "select", "enabled": True},
    "collected_at": {"name": "수집일시", "type": "date", "enabled": True},
    "source_url": {"name": "원본 URL", "type": "url", "enabled": True},
}


# 공유된 OS DB처럼 월별 한 행에 AOS/iOS/etc 컬럼이 있는 경우의 매핑입니다.
# 이 구조가 감지되면 NOTION_PROPERTIES 대신 아래 매핑으로 업로드합니다.
NOTION_WIDE_OS_PROPERTIES: dict[str, dict[str, Any]] = {
    "title": {"name": "구분", "type": "title", "enabled": True},
    "basis_month": {"name": "조사 일자", "type": "date", "enabled": True},
    "aos": {"name": "AOS", "type": "number", "enabled": True},
    "ios": {"name": "iOS", "type": "number", "enabled": True},
    "etc": {"name": "etc", "type": "number", "enabled": True},
}

# 브라우저 점유율 DB 매핑 (모바일 기준, 한국).
# wide OS DB와 같은 패턴으로 월별 한 행에 Chrome/Samsung/Safari/etc 컬럼 구조를 가정합니다.
# DB 속성명이 다르면 아래 name 값을 실제 DB 속성명에 맞게 수정하세요.
NOTION_WIDE_BROWSER_PROPERTIES: dict[str, dict[str, Any]] = {
    "title": {"name": "구분", "type": "title", "enabled": True},
    "basis_month": {"name": "조사 일자", "type": "date", "enabled": True},
    "chrome": {"name": "Chrome", "type": "number", "enabled": True},
    "samsung_internet": {"name": "Samsung Internet", "type": "number", "enabled": True},
    "safari": {"name": "Safari", "type": "number", "enabled": True},
    "etc": {"name": "etc", "type": "number", "enabled": True},
}


@dataclass(frozen=True)
class Settings:
    notion_token: str
    notion_database_id: str
    notion_browser_database_id: str
    statcounter_page_url: str
    statcounter_stat_key: str
    country: str
    source: str
    request_timeout: int


def load_settings() -> Settings:
    """`.env`를 읽고 필수 환경변수를 검증합니다."""
    load_dotenv()

    notion_token = os.getenv("NOTION_TOKEN", "").strip()
    notion_database_id = os.getenv("NOTION_DATABASE_ID", "").strip()

    if not notion_token:
        raise ValueError("NOTION_TOKEN이 없습니다. .env 파일에 Notion Integration Token을 입력하세요.")
    if not notion_database_id:
        raise ValueError("NOTION_DATABASE_ID가 없습니다. .env 파일에 대상 Notion DB ID를 입력하세요.")

    return Settings(
        notion_token=notion_token,
        notion_database_id=notion_database_id,
        # 브라우저 점유율 DB ID. 비어있으면 브라우저 업로드를 건너뜁니다.
        notion_browser_database_id=os.getenv("NOTION_BROWSER_DATABASE_ID", "").strip(),
        statcounter_page_url=os.getenv(
            "STATCOUNTER_PAGE_URL",
            "https://gs.statcounter.com/os-market-share/mobile-tablet-console/south-korea/",
        ).strip(),
        statcounter_stat_key=os.getenv("STATCOUNTER_STAT_KEY", "os_combined").strip(),
        country=os.getenv("COUNTRY", "South Korea").strip(),
        source=os.getenv("DATA_SOURCE", "StatCounter").strip(),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "30")),
    )
