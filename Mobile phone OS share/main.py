"""
Mobile/Tablet/Console OS share + 모바일 브라우저 점유율 자동 수집 및 Notion 업로드 실행 파일.

브라우저 점유율은 OS DB 페이지 하단에 함께 업로드됩니다.
"""

from __future__ import annotations

from datetime import datetime

from chart_renderer import render_horizontal_bar_chart
from config import load_settings
from notion_client import NotionClient
from statcounter_client import StatCounterClient, latest_basis_month

# 브라우저 점유율 StatCounter URL (한국, 모바일)
BROWSER_PAGE_URL = "https://gs.statcounter.com/browser-market-share/mobile/south-korea/"
BROWSER_STAT_KEY = "browser"


def main() -> int:
    collected = 0
    skipped = 0
    uploaded = 0
    failed = 0
    failure_reasons: list[str] = []

    try:
        settings = load_settings()
    except Exception as exc:
        print(f"[ERROR] 설정 오류: {exc}")
        return 1

    # ------------------------------------------------------------------ #
    # 1. StatCounter 데이터 수집                                           #
    # ------------------------------------------------------------------ #
    try:
        collected_at = datetime.now().astimezone()
        target_month = collected_at.strftime("%Y-%m")

        # OS 점유율
        statcounter = StatCounterClient(
            page_url=settings.statcounter_page_url,
            stat_key=settings.statcounter_stat_key,
            timeout=settings.request_timeout,
        )
        records = statcounter.fetch_month_records(
            basis_month=target_month,
            country=settings.country,
            source=settings.source,
        )
        # Android 버전
        android_version_records = StatCounterClient(
            page_url="https://gs.statcounter.com/os-version-market-share/android/mobile-tablet/south-korea/",
            stat_key="android_version",
            timeout=settings.request_timeout,
        ).fetch_month_records(
            basis_month=target_month,
            country=settings.country,
            source=settings.source,
        )
        # iOS 버전
        ios_version_records = StatCounterClient(
            page_url="https://gs.statcounter.com/os-version-market-share/ios/mobile-tablet/south-korea/",
            stat_key="ios_version",
            timeout=settings.request_timeout,
        ).fetch_month_records(
            basis_month=target_month,
            country=settings.country,
            source=settings.source,
        )
        # 모바일 브라우저 점유율
        browser_records = StatCounterClient(
            page_url=BROWSER_PAGE_URL,
            stat_key=BROWSER_STAT_KEY,
            timeout=settings.request_timeout,
        ).fetch_month_records(
            basis_month=target_month,
            country=settings.country,
            source=settings.source,
        )

        collected = len(records)
        basis_month = latest_basis_month(records)
        print(f"[INFO] StatCounter 실행 기준월: {basis_month}")
        print(f"[INFO] OS 수집 건수: {collected}")
        print(f"[INFO] 브라우저 수집 건수: {len(browser_records)}")
    except Exception as exc:
        print(f"[ERROR] StatCounter 데이터 수집 실패: {exc}")
        return 1

    # ------------------------------------------------------------------ #
    # 2. Notion DB 조회                                                    #
    # ------------------------------------------------------------------ #
    try:
        notion = NotionClient(
            token=settings.notion_token,
            database_id=settings.notion_database_id,
            timeout=settings.request_timeout,
        )
        if notion.supports_wide_os_schema():
            existing_page = notion.find_wide_os_page(basis_month)
            print("[INFO] Notion wide-format OS DB 감지")
            print(f"[INFO] Notion 기존 OS 데이터 조회 건수: {1 if existing_page else 0}")
        else:
            existing = notion.existing_keys(basis_month)
            print("[INFO] Notion row-format DB 감지")
            print(f"[INFO] Notion 기존 OS 데이터 조회 건수: {len(existing)}")
    except Exception as exc:
        print(f"[ERROR] Notion DB 조회 실패: {exc}")
        return 1

    # ------------------------------------------------------------------ #
    # 3-A. OS wide-format 업로드 (브라우저 차트 포함)                      #
    # ------------------------------------------------------------------ #
    if notion.supports_wide_os_schema():
        try:
            os_chart_images = [
                render_horizontal_bar_chart(
                    records,
                    f"South Korea Mobile OS Share - {basis_month}",
                    f"StatCounter-os_combined-KR-monthly-{basis_month.replace('-', '')}.png",
                ),
                render_horizontal_bar_chart(
                    android_version_records,
                    f"South Korea Android Version Share - {basis_month}",
                    f"StatCounter-android_version-KR-monthly-{basis_month.replace('-', '')}.png",
                ),
                render_horizontal_bar_chart(
                    ios_version_records,
                    f"South Korea iOS Version Share - {basis_month}",
                    f"StatCounter-ios_version-KR-monthly-{basis_month.replace('-', '')}.png",
                ),
            ]

            # 브라우저 차트: 수집 성공 시 OS 페이지 하단에 함께 업로드
            browser_chart_images = None
            if browser_records:
                browser_chart_images = [
                    render_horizontal_bar_chart(
                        browser_records,
                        f"South Korea Mobile Browser Share - {basis_month}",
                        f"StatCounter-browser-KR-monthly-{basis_month.replace('-', '')}.png",
                    ),
                ]
                print("[INFO] 브라우저 차트 렌더링 완료 — OS 페이지에 함께 업로드합니다.")

            result = notion.upsert_wide_os_summary(
                records,
                collected_at,
                os_chart_images,
                browser_records=browser_records or None,
                browser_chart_images=browser_chart_images,
            )
            uploaded += 1
            action = "업데이트" if result == "updated" else "신규 업로드"
            print(f"[OK] wide-format {action} 완료: {basis_month}")
        except Exception as exc:
            failed += 1
            reason = f"{basis_month}: {exc}"
            failure_reasons.append(reason)
            print(f"[FAIL] 업로드 실패: {reason}")

        print("")
        print("========== 실행 결과 ==========")
        print(f"수집 성공 건수 (OS): {collected}")
        print(f"수집 성공 건수 (브라우저): {len(browser_records)}")
        print(f"기존 데이터 skip 건수: {skipped}")
        print(f"Notion 업로드 성공 건수: {uploaded}")
        print(f"실패 건수: {failed}")
        if failure_reasons:
            print("실패 사유:")
            for reason in failure_reasons:
                print(f"- {reason}")
        return 0 if failed == 0 else 1

    # ------------------------------------------------------------------ #
    # 3-B. OS row-format 업로드 (기존 로직)                                #
    # ------------------------------------------------------------------ #
    for record in records:
        key = (record.basis_month, record.vendor)
        if key in existing:
            skipped += 1
            print(f"[SKIP] 이미 등록됨: {record.basis_month} / {record.vendor}")
            continue

        try:
            notion.create_record(record, collected_at)
            uploaded += 1
            print(f"[OK] 업로드 완료: {record.basis_month} / {record.vendor} / {record.share}%")
        except Exception as exc:
            failed += 1
            reason = f"{record.basis_month} / {record.vendor}: {exc}"
            failure_reasons.append(reason)
            print(f"[FAIL] 업로드 실패: {reason}")

    print("")
    print("========== 실행 결과 ==========")
    print(f"수집 성공 건수 (OS): {collected}")
    print(f"수집 성공 건수 (브라우저): {len(browser_records)}")
    print(f"기존 데이터 skip 건수: {skipped}")
    print(f"Notion 업로드 성공 건수: {uploaded}")
    print(f"실패 건수: {failed}")
    if failure_reasons:
        print("실패 사유:")
        for reason in failure_reasons:
            print(f"- {reason}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())