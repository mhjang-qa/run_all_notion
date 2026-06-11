"""
StatCounter 수집 결과를 로컬 PNG 차트로 렌더링합니다.
"""

from __future__ import annotations

from io import BytesIO
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from statcounter_client import StatCounterRecord


def render_horizontal_bar_chart(
    records: list[StatCounterRecord],
    title: str,
    filename: str,
    top_n: int = 10,
) -> tuple[str, bytes]:
    """수집 레코드를 수평 막대 차트 PNG로 렌더링합니다."""
    if not records:
        raise ValueError("렌더링할 레코드가 없습니다.")

    sorted_records = sorted(records, key=lambda item: item.share, reverse=True)[:top_n]
    labels = [record.vendor for record in sorted_records][::-1]
    values = [record.share for record in sorted_records][::-1]

    fig_height = max(4.5, len(labels) * 0.55)
    fig, ax = plt.subplots(figsize=(12, fig_height), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    bars = ax.barh(labels, values, color="#2563eb")
    ax.set_title(title, fontsize=18, fontweight="bold", loc="left", pad=16)
    ax.set_xlabel("Market Share (%)", fontsize=11)
    ax.set_xlim(0, max(values) * 1.15 if values else 1)
    ax.grid(axis="x", linestyle="--", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", labelsize=11)
    ax.tick_params(axis="x", labelsize=10)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_width() + max(values) * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.2f}%",
            va="center",
            ha="left",
            fontsize=10,
            color="#111827",
        )

    plt.tight_layout()
    buffer = BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return filename, buffer.getvalue()
