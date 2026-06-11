"""
StatCounter 데이터 수집 클라이언트.

수집 전략:
1. 대상 페이지의 스냅샷 영역에서 StatCounter가 공개한 최신 월을 찾습니다.
2. 같은 월의 chart.php 데이터를 요청합니다.
3. chart.php 안의 FusionCharts XML에서 OS/Vendor별 점유율을 파싱합니다.
4. chart.php가 실패하면 스냅샷 테이블 파싱 결과로 fallback 합니다.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass(frozen=True)
class StatCounterRecord:
    basis_month: str  # YYYY-MM
    vendor: str
    share: float
    country: str
    source: str
    source_url: str


class StatCounterClient:
    def __init__(self, page_url: str, stat_key: str = "os_combined", timeout: int = 30) -> None:
        self.page_url = page_url
        self.stat_key = stat_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                # StatCounter가 일반 브라우저 요청으로 판단하도록 User-Agent를 명시합니다.
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def fetch_month_records(self, basis_month: str, country: str, source: str) -> list[StatCounterRecord]:
        """
        지정한 기준월(YYYY-MM)의 전체 데이터를 가져옵니다.

        우선 chart.php 단일월 데이터를 직접 조회하고,
        실패했을 때만 페이지 스냅샷 기준월과 일치하는 경우에 한해 HTML fallback을 사용합니다.
        """
        html = self._get_text(self.page_url)

        try:
            chart_js = self._get_text(self._build_chart_url(basis_month))
            records = self._parse_chart_js(chart_js, basis_month, country, source)
            if records:
                return records
        except Exception as exc:
            print(f"[WARN] chart.php 파싱 실패: {exc}")

        snapshot_month = self._extract_latest_month(html)
        if snapshot_month == basis_month:
            return self._parse_snapshot_table(html, basis_month, country, source)

        raise ValueError(
            f"StatCounter에서 {basis_month} 기준 데이터를 가져오지 못했습니다. "
            f"페이지 스냅샷 최신월은 {snapshot_month}입니다."
        )

    def _get_text(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def _build_chart_url(self, basis_month: str) -> str:
        """최신 단일 월 Bar chart용 chart.php URL을 만듭니다."""
        compact_month = basis_month.replace("-", "")
        chart_id = f"{self.stat_key}-KR-monthly-{compact_month}-{compact_month}-bar"
        # StatCounter chart.php는 URL path와 달리 device_hidden 값에 plus 표기
        # `mobile+tablet+console`을 사용해야 페이지 스냅샷과 같은 값을 반환합니다.
        query = urlencode({"device_hidden": "mobile+tablet+console"})
        return f"https://gs.statcounter.com/chart.php?{chart_id}&{query}"

    def _extract_latest_month(self, html: str) -> str:
        """페이지 HTML에서 최신 기준월(YYYY-MM)을 추출합니다."""
        soup = BeautifulSoup(html, "html.parser")

        # 스냅샷 표 하단 문구 예:
        # Mobile, Tablet & Console Vendor Market Share ... - April 2026
        footer_text = soup.select_one("table.stats-snapshot tfoot")
        if footer_text:
            parsed = self._parse_month_text(footer_text.get_text(" ", strip=True))
            if parsed:
                return parsed

        # 보조 fallback: OG 이미지 URL 예: os_combined-04-2026-mobile_tablet_console-KR.png
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image.get("content"):
            match = re.search(r"[a-z_]+-(\d{2})-(\d{4})-mobile_tablet_console-KR\.png", og_image["content"])
            if match:
                return f"{match.group(2)}-{match.group(1)}"

        raise ValueError("StatCounter 페이지에서 최신 기준월을 찾지 못했습니다.")

    def _parse_month_text(self, text: str) -> str | None:
        matches = re.findall(
            r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
            r"Aug(?:ust)?|Sep(?:t)?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{4})\b",
            text,
            flags=re.IGNORECASE,
        )
        if not matches:
            return None
        month_text, year_text = matches[-1]
        month = MONTHS[month_text.lower()]
        year = int(year_text)
        return f"{year:04d}-{month:02d}"

    def _parse_chart_js(
        self,
        chart_js: str,
        basis_month: str,
        country: str,
        source: str,
    ) -> list[StatCounterRecord]:
        """chart.php JavaScript에서 JSON/XML을 추출해 OS/Vendor별 값을 파싱합니다."""
        json_match = re.search(r"var json = (\{.*?\});\s*if \(FusionCharts", chart_js, flags=re.DOTALL)
        if not json_match:
            raise ValueError("chart.php 응답에서 JSON 블록을 찾지 못했습니다.")

        payload = json.loads(json_match.group(1))
        xml_text = payload.get("xml", "")
        if not xml_text:
            raise ValueError("chart.php JSON에 XML 데이터가 없습니다.")

        root = ET.fromstring(xml_text)
        records: list[StatCounterRecord] = []
        for item in root.findall("set"):
            vendor = (item.attrib.get("label") or "").strip()
            value = (item.attrib.get("value") or "").strip()
            if not vendor or value == "":
                continue
            records.append(
                StatCounterRecord(
                    basis_month=basis_month,
                    vendor=vendor,
                    share=float(value),
                    country=country,
                    source=source,
                    source_url=self.page_url,
                )
            )

        if not records:
            raise ValueError("chart.php XML에서 Vendor 데이터를 찾지 못했습니다.")

        return records

    def _parse_snapshot_table(
        self,
        html: str,
        basis_month: str,
        country: str,
        source: str,
    ) -> list[StatCounterRecord]:
        """chart.php 실패 시 HTML 스냅샷 표에서 데이터를 파싱합니다."""
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.stats-snapshot tbody tr")
        records: list[StatCounterRecord] = []

        for row in rows:
            vendor_cell = row.find("th")
            share_cell = row.select_one(".count")
            if not vendor_cell or not share_cell:
                continue
            records.append(
                StatCounterRecord(
                    basis_month=basis_month,
                    vendor=vendor_cell.get_text(strip=True),
                    share=float(share_cell.get_text(strip=True)),
                    country=country,
                    source=source,
                    source_url=self.page_url,
                )
            )

        if not records:
            raise ValueError("StatCounter 스냅샷 테이블에서 데이터를 찾지 못했습니다.")

        return records


def latest_basis_month(records: Iterable[StatCounterRecord]) -> str:
    """로그 출력용 최신 기준월 계산."""
    return max(record.basis_month for record in records)
