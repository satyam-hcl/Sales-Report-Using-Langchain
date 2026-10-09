"""Run once daily while this process remains running."""

from __future__ import annotations

import os
import time

import schedule
from dotenv import load_dotenv

from sales_reporter import detect_columns, generate_report, load_sales_data


def run_daily_report() -> None:
    try:
        data = load_sales_data()
        report = generate_report(
            data,
            detect_columns(data),
            os.getenv("LLM_PROVIDER", "ollama"),
        )
        print(f"Report saved: {report}", flush=True)
    except Exception as exc:
        print(f"Daily report failed: {exc}", flush=True)


if __name__ == "__main__":
    load_dotenv()
    report_time = os.getenv("DAILY_REPORT_TIME", "08:00")
    schedule.every().day.at(report_time).do(run_daily_report)
    print(f"Daily sales report scheduled for {report_time}. Keep this process running.", flush=True)
    while True:
        schedule.run_pending()
        time.sleep(30)