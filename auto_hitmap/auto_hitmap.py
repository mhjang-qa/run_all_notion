#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import math
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd


class DefectHeatmapGeneratorGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("결함 유형/심각도 히트맵 HTML 생성기")
        self.root.geometry("980x760")
        self.root.minsize(860, 680)

        self.excel_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(Path.home()))
        self.status_text = tk.StringVar(value="엑셀 파일을 선택하세요.")

        self.build_ui()

    def build_ui(self):
        wrap = ttk.Frame(self.root, padding=16)
        wrap.pack(fill="both", expand=True)

        title = ttk.Label(
            wrap,
            text="결함 유형/심각도 히트맵 HTML 생성기",
            font=("Apple SD Gothic Neo", 18, "bold")
        )
        title.pack(anchor="w")

        desc = ttk.Label(
            wrap,
            text="엑셀(.xlsx) 파일을 읽어 결함 유형 + 심각도 기준 히트맵 HTML을 생성합니다. "
                 "Plotly 없이 순수 HTML/CSS로 생성되어 브라우저에서 안정적으로 열립니다.",
            foreground="#555555"
        )
        desc.pack(anchor="w", pady=(6, 18))

        file_frame = ttk.LabelFrame(wrap, text="1. 엑셀 파일 선택", padding=12)
        file_frame.pack(fill="x", pady=(0, 12))

        ttk.Entry(file_frame, textvariable=self.excel_path).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ttk.Button(file_frame, text="찾아보기", command=self.select_excel).pack(side="left")

        out_frame = ttk.LabelFrame(wrap, text="2. 저장 폴더 선택", padding=12)
        out_frame.pack(fill="x", pady=(0, 12))

        ttk.Entry(out_frame, textvariable=self.output_dir).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ttk.Button(out_frame, text="찾아보기", command=self.select_output_dir).pack(side="left")

        action_frame = ttk.LabelFrame(wrap, text="3. 생성", padding=12)
        action_frame.pack(fill="x", pady=(0, 12))

        ttk.Button(action_frame, text="HTML 생성", command=self.generate_html).pack(side="left")
        ttk.Button(action_frame, text="필수 컬럼 안내", command=self.show_required_columns).pack(
            side="left", padx=(8, 0)
        )

        log_frame = ttk.LabelFrame(wrap, text="로그 / 결과", padding=12)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(log_frame, wrap="word", font=("Menlo", 11))
        self.log_text.pack(fill="both", expand=True)

        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_text,
            anchor="w",
            relief="sunken",
            padding=(8, 4)
        )
        status_bar.pack(fill="x", side="bottom")

    def log(self, message: str):
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def select_excel(self):
        file_path = filedialog.askopenfilename(
            title="엑셀 파일 선택",
            filetypes=[("Excel Files", "*.xlsx"), ("All Files", "*.*")]
        )
        if file_path:
            self.excel_path.set(file_path)
            self.status_text.set("엑셀 파일이 선택되었습니다.")

    def select_output_dir(self):
        directory = filedialog.askdirectory(title="저장 폴더 선택")
        if directory:
            self.output_dir.set(directory)
            self.status_text.set("저장 폴더가 선택되었습니다.")

    def show_required_columns(self):
        messagebox.showinfo(
            "필수 컬럼 안내",
            "필수 컬럼\n"
            "- 결함 유형\n"
            "- 심각도\n\n"
            "선택 컬럼\n"
            "- 상태\n"
            "- 등록일자\n\n"
            "심각도 값 예시\n"
            "- Blocker\n"
            "- Critical\n"
            "- Major\n"
            "- Minor"
        )

    def validate_inputs(self):
        excel_path = self.excel_path.get().strip()
        output_dir = self.output_dir.get().strip()

        if not excel_path:
            raise ValueError("엑셀 파일을 선택해주세요.")
        if not os.path.exists(excel_path):
            raise FileNotFoundError("선택한 엑셀 파일이 존재하지 않습니다.")
        if not excel_path.lower().endswith(".xlsx"):
            raise ValueError(".xlsx 파일만 지원합니다.")
        if not output_dir:
            raise ValueError("저장 폴더를 선택해주세요.")
        if not os.path.isdir(output_dir):
            raise ValueError("유효한 저장 폴더가 아닙니다.")

        return excel_path, output_dir

    def generate_html(self):
        try:
            self.log_text.delete("1.0", "end")

            excel_path, output_dir = self.validate_inputs()
            self.log(f"[INFO] 엑셀 로딩: {excel_path}")

            df = pd.read_excel(excel_path)

            for col in ["결함 유형", "심각도"]:
                if col not in df.columns:
                    raise KeyError(f"필수 컬럼이 없습니다: {col}")

            html = self.build_html(df, Path(excel_path).name)

            output_path = Path(output_dir) / f"{Path(excel_path).stem}_heatmap.html"
            output_path.write_text(html, encoding="utf-8")

            self.log(f"[INFO] HTML 생성 완료: {output_path}")
            self.status_text.set("HTML 생성 완료")
            messagebox.showinfo("완료", f"HTML 생성 완료\n\n{output_path}")

        except Exception as e:
            self.log("[ERROR] HTML 생성 실패")
            self.log(str(e))
            self.log(traceback.format_exc())
            self.status_text.set("오류 발생")
            messagebox.showerror("오류", str(e))

    def build_html(self, df: pd.DataFrame, source_name: str) -> str:
        work_df = df.copy()

        work_df["결함 유형"] = work_df["결함 유형"].fillna("").astype(str).str.strip()
        work_df["심각도"] = work_df["심각도"].fillna("").astype(str).str.strip()

        work_df = work_df[(work_df["결함 유형"] != "") & (work_df["심각도"] != "")].copy()

        if work_df.empty:
            raise ValueError("결함 유형 / 심각도 데이터가 없습니다.")

        if "상태" not in work_df.columns:
            work_df["상태"] = "미분류"
        else:
            work_df["상태"] = (
                work_df["상태"]
                .fillna("미분류")
                .astype(str)
                .str.strip()
                .replace("", "미분류")
            )

        if "등록일자" in work_df.columns:
            work_df["등록일자"] = pd.to_datetime(work_df["등록일자"], errors="coerce")
            min_date = work_df["등록일자"].min()
            max_date = work_df["등록일자"].max()
            date_range_text = (
                f"{min_date.strftime('%Y-%m-%d')} ~ {max_date.strftime('%Y-%m-%d')}"
                if pd.notna(min_date) and pd.notna(max_date)
                else "-"
            )
        else:
            date_range_text = "-"

        severity_order = ["Blocker", "Critical", "Major", "Minor"]
        severity_rank = {"Blocker": 4, "Critical": 3, "Major": 2, "Minor": 1}
        severity_color = {
            "Blocker": "#7c3aed",
            "Critical": "#ef4444",
            "Major": "#f59e0b",
            "Minor": "#3b82f6",
        }

        def normalize_severity(value: str) -> str:
            value = str(value).strip().lower()
            mapping = {
                "blocker": "Blocker",
                "critical": "Critical",
                "major": "Major",
                "minor": "Minor",
            }
            return mapping.get(value, str(value).strip())

        work_df["심각도"] = work_df["심각도"].apply(normalize_severity)

        total_count = len(work_df)

        type_summary = (
            work_df.groupby("결함 유형")
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
            .reset_index(drop=True)
        )

        if type_summary.empty:
            raise ValueError("결함 유형 집계 결과가 없습니다.")

        pivot = pd.crosstab(work_df["결함 유형"], work_df["심각도"])
        pivot = pivot.reindex(columns=severity_order, fill_value=0)
        pivot["합계"] = pivot.sum(axis=1)
        pivot = pivot.sort_values("합계", ascending=False)

        sev_summary = work_df["심각도"].value_counts().reindex(severity_order, fill_value=0)
        status_summary = work_df["상태"].value_counts().head(8)

        top_type = str(type_summary.iloc[0]["결함 유형"])
        top_count = int(type_summary.iloc[0]["count"])
        crit_block = int(sev_summary["Critical"] + sev_summary["Blocker"])
        crit_block_pct = round((crit_block / total_count) * 100, 1) if total_count else 0
        type_count = int(type_summary.shape[0])

        # 히트맵 카드 생성
        max_count = max(type_summary["count"].max(), 1)
        heatmap_cards = []

        for _, row in type_summary.iterrows():
            defect_type = str(row["결함 유형"])
            count = int(row["count"])
            ratio = count / total_count if total_count else 0

            blocker = int(pivot.loc[defect_type, "Blocker"]) if defect_type in pivot.index else 0
            critical = int(pivot.loc[defect_type, "Critical"]) if defect_type in pivot.index else 0
            major = int(pivot.loc[defect_type, "Major"]) if defect_type in pivot.index else 0
            minor = int(pivot.loc[defect_type, "Minor"]) if defect_type in pivot.index else 0

            font_scale = 14 + int((count / max_count) * 10)
            min_height = 180 + int((count / max_count) * 170)

            severity_total = blocker + critical + major + minor
            if severity_total == 0:
                blocker_pct = critical_pct = major_pct = 0
                minor_pct = 100
            else:
                blocker_pct = round((blocker / severity_total) * 100, 2)
                critical_pct = round((critical / severity_total) * 100, 2)
                major_pct = round((major / severity_total) * 100, 2)
                minor_pct = round((minor / severity_total) * 100, 2)

                # 합계 100 보정
                diff = round(100 - (blocker_pct + critical_pct + major_pct + minor_pct), 2)
                minor_pct += diff

            heatmap_cards.append(f"""
            <div class="heat-card" style="min-height:{min_height}px;">
              <div class="heat-card-header">
                <div class="heat-card-title">{self.escape_html(defect_type)}</div>
                <div class="heat-card-count">{count}건</div>
              </div>

              <div class="heat-card-sub">전체 대비 {round(ratio * 100, 1)}%</div>

              <div class="severity-stack" title="Blocker {blocker}건 / Critical {critical}건 / Major {major}건 / Minor {minor}건">
                <div class="seg seg-blocker" style="width:{blocker_pct}%;"></div>
                <div class="seg seg-critical" style="width:{critical_pct}%;"></div>
                <div class="seg seg-major" style="width:{major_pct}%;"></div>
                <div class="seg seg-minor" style="width:{minor_pct}%;"></div>
              </div>

              <div class="severity-detail">
                <div><span class="dot blocker"></span>Blocker <b>{blocker}</b></div>
                <div><span class="dot critical"></span>Critical <b>{critical}</b></div>
                <div><span class="dot major"></span>Major <b>{major}</b></div>
                <div><span class="dot minor"></span>Minor <b>{minor}</b></div>
              </div>
            </div>
            """)

        type_rows = []
        for defect_type, row in pivot.iterrows():
            type_rows.append(
                f"<tr>"
                f"<td>{self.escape_html(str(defect_type))}</td>"
                f"<td class='num'>{int(row['Blocker'])}</td>"
                f"<td class='num'>{int(row['Critical'])}</td>"
                f"<td class='num'>{int(row['Major'])}</td>"
                f"<td class='num'>{int(row['Minor'])}</td>"
                f"<td class='num'>{int(row['합계'])}</td>"
                f"</tr>"
            )

        badge_class = {
            "Blocker": "b-blocker",
            "Critical": "b-critical",
            "Major": "b-major",
            "Minor": "b-minor",
        }

        severity_rows = []
        for sev in severity_order:
            count = int(sev_summary[sev])
            pct = round((count / total_count) * 100, 1) if total_count else 0
            severity_rows.append(
                f"<tr>"
                f"<td><span class='badge {badge_class[sev]}'>{sev}</span></td>"
                f"<td class='num'>{count}건</td>"
                f"<td class='num'>{pct}%</td>"
                f"</tr>"
            )

        status_rows = []
        for status_name, cnt in status_summary.items():
            status_rows.append(
                f"<tr>"
                f"<td>{self.escape_html(str(status_name))}</td>"
                f"<td class='num'>{int(cnt)}건</td>"
                f"</tr>"
            )

        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>결함 유형/심각도 히트맵</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px;
      font-family: Arial, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
      background: #f5f6f8;
      color: #1f2937;
    }}

    .wrap {{
      max-width: 1500px;
      margin: 0 auto;
    }}

    .page-title {{
      font-size: 24px;
      font-weight: 800;
      margin: 0 0 6px;
    }}

    .sub-title {{
      color: #6b7280;
      font-size: 13px;
      margin-bottom: 18px;
    }}

    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(180px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }}

    .card {{
      background: #fff;
      border-radius: 18px;
      padding: 18px 20px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
      border: 1px solid #e5e7eb;
    }}

    .metric-label {{
      font-size: 12px;
      color: #6b7280;
      margin-bottom: 8px;
    }}

    .metric-value {{
      font-size: 30px;
      font-weight: 800;
      line-height: 1;
    }}

    .metric-sub {{
      margin-top: 8px;
      font-size: 12px;
      color: #6b7280;
    }}

    .panel-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.7fr) minmax(360px, 0.9fr);
      gap: 18px;
      align-items: start;
    }}

    .panel-title {{
      font-size: 16px;
      font-weight: 800;
      margin: 0 0 14px;
    }}

    .heatmap-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 14px;
      align-items: stretch;
    }}

    .heat-card {{
      border-radius: 18px;
      padding: 16px;
      color: #fff;
      position: relative;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.12);
    }}

    .heat-card::after {{
      content: "";
      position: absolute;
      inset: 0;
      background: radial-gradient(circle at top right, rgba(255,255,255,0.14), transparent 40%);
      pointer-events: none;
    }}

    .heat-card-header {{
      position: relative;
      z-index: 1;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
    }}

    .heat-card-title {{
      font-size: 22px;
      font-weight: 800;
      line-height: 1.25;
      word-break: keep-all;
    }}

    .heat-card-count {{
      white-space: nowrap;
      font-size: 15px;
      font-weight: 700;
      opacity: 0.95;
    }}

    .heat-card-sub {{
      position: relative;
      z-index: 1;
      margin-top: 8px;
      font-size: 13px;
      color: rgba(255,255,255,0.88);
    }}

    .severity-stack {{
      position: relative;
      z-index: 1;
      margin-top: 18px;
      height: 22px;
      border-radius: 999px;
      overflow: hidden;
      display: flex;
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.18);
    }}

    .seg {{
      height: 100%;
    }}

    .seg-blocker {{ background: #7c3aed; }}
    .seg-critical {{ background: #ef4444; }}
    .seg-major {{ background: #f59e0b; }}
    .seg-minor {{ background: #3b82f6; }}

    .severity-detail {{
      position: relative;
      z-index: 1;
      margin-top: 14px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 12px;
      font-size: 13px;
      color: rgba(255,255,255,0.95);
    }}

    .dot {{
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 999px;
      margin-right: 6px;
      vertical-align: middle;
    }}

    .dot.blocker {{ background: #7c3aed; }}
    .dot.critical {{ background: #ef4444; }}
    .dot.major {{ background: #f59e0b; }}
    .dot.minor {{ background: #3b82f6; }}

    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
      align-items: center;
    }}

    .legend-chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: #4b5563;
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 999px;
      padding: 5px 10px;
    }}

    .legend-dot {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    th, td {{
      padding: 10px 8px;
      border-bottom: 1px solid #eef2f7;
      text-align: left;
      vertical-align: middle;
    }}

    th {{
      color: #6b7280;
      font-weight: 600;
      font-size: 12px;
    }}

    td.num {{
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}

    .badge {{
      display: inline-block;
      min-width: 64px;
      text-align: center;
      padding: 5px 10px;
      border-radius: 999px;
      font-weight: 700;
      font-size: 11px;
      color: #fff;
    }}

    .b-minor {{ background: #3b82f6; }}
    .b-major {{ background: #f59e0b; }}
    .b-critical {{ background: #ef4444; }}
    .b-blocker {{ background: #7c3aed; }}

    .footnote {{
      margin-top: 16px;
      color: #6b7280;
      font-size: 12px;
      line-height: 1.7;
    }}

    @media (max-width: 1180px) {{
      .summary-grid {{
        grid-template-columns: repeat(2, minmax(160px, 1fr));
      }}

      .panel-grid {{
        grid-template-columns: 1fr;
      }}

      .heatmap-grid {{
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      }}
    }}

    @media (max-width: 700px) {{
      .summary-grid {{
        grid-template-columns: 1fr;
      }}

      .severity-detail {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="page-title">결함 유형/심각도 히트맵</div>
    <div class="sub-title">
      소스 파일: {self.escape_html(source_name)} · 등록일자 범위: {self.escape_html(date_range_text)} · 총 {total_count}건
    </div>

    <div class="summary-grid">
      <div class="card">
        <div class="metric-label">총 결함 수</div>
        <div class="metric-value">{total_count}</div>
        <div class="metric-sub">결함 유형 + 심각도 값 기준</div>
      </div>

      <div class="card">
        <div class="metric-label">최다 결함 유형</div>
        <div class="metric-value" style="font-size:24px;">{self.escape_html(top_type)}</div>
        <div class="metric-sub">{top_count}건</div>
      </div>

      <div class="card">
        <div class="metric-label">Critical + Blocker</div>
        <div class="metric-value">{crit_block}</div>
        <div class="metric-sub">전체 대비 {crit_block_pct}%</div>
      </div>

      <div class="card">
        <div class="metric-label">결함 유형 수</div>
        <div class="metric-value">{type_count}</div>
        <div class="metric-sub">유형 분류 기준</div>
      </div>
    </div>

    <div class="panel-grid">
      <div class="card">
        <div class="panel-title">결함 유형 + 심각도 히트맵</div>

        <div class="heatmap-grid">
          {''.join(heatmap_cards)}
        </div>

        <div class="legend">
          <span class="legend-chip"><span class="legend-dot" style="background:#7c3aed;"></span>Blocker</span>
          <span class="legend-chip"><span class="legend-dot" style="background:#ef4444;"></span>Critical</span>
          <span class="legend-chip"><span class="legend-dot" style="background:#f59e0b;"></span>Major</span>
          <span class="legend-chip"><span class="legend-dot" style="background:#3b82f6;"></span>Minor</span>
        </div>
      </div>

      <div class="card">
        <div class="panel-title">유형별 심각도 분포</div>
        <table>
          <thead>
            <tr>
              <th>결함 유형</th>
              <th class="num">Blocker</th>
              <th class="num">Critical</th>
              <th class="num">Major</th>
              <th class="num">Minor</th>
              <th class="num">합계</th>
            </tr>
          </thead>
          <tbody>
            {''.join(type_rows)}
          </tbody>
        </table>

        <div style="height:14px;"></div>

        <div class="panel-title">심각도 분포</div>
        <table>
          <tbody>
            {''.join(severity_rows)}
          </tbody>
        </table>

        <div style="height:14px;"></div>

        <div class="panel-title">상태 상위 분포</div>
        <table>
          <tbody>
            {''.join(status_rows)}
          </tbody>
        </table>
      </div>
    </div>

    <div class="footnote">
      각 박스는 결함 유형이며, 박스 내부 색상 바는 해당 유형 내 심각도 비율입니다.<br/>
      즉, 박스 개별 크기/높이는 유형 건수 크기를 강조하고, 색상 바는 Blocker / Critical / Major / Minor 분포를 보여줍니다.
    </div>
  </div>
</body>
</html>
"""
        return html

    @staticmethod
    def escape_html(text: str) -> str:
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )


def main():
    root = tk.Tk()
    try:
        if sys.platform == "darwin":
            root.tk.call("tk", "scaling", 1.2)
    except Exception:
        pass

    DefectHeatmapGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()