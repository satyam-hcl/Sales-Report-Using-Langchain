"""Load sales spreadsheets and create a daily Markdown report."""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".csv"}

FIELD_ALIASES = {
    "date": ("date", "orderdate", "salesdate", "transactiondate", "invoicedate"),
    "amount": (
        "sales", "revenue", "amount", "total", "totalamount", "netsales",
        "salesamount", "ordertotal", "lineamount",
    ),
    "product": ("product", "productname", "item", "itemname", "sku", "description"),
    "quantity": ("quantity", "qty", "units", "unitssold", "salesquantity"),
    "category": ("category", "productcategory", "department", "producttype"),
    "region": ("region", "territory", "state", "country", "location", "market"),
}


def load_sales_data(directory: Path = DATA_DIR) -> pd.DataFrame:
    """Read all supported spreadsheets and CSV files in a directory."""
    if not directory.exists():
        raise FileNotFoundError(f"Create the {directory.name}/ folder and add sales files.")

    frames: list[pd.DataFrame] = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith("~$") or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            if path.suffix.lower() == ".csv":
                sheets = {"CSV": pd.read_csv(path)}
            else:
                sheets = pd.read_excel(path, sheet_name=None)
        except Exception as exc:
            raise ValueError(f"Could not read {path.name}: {exc}") from exc

        for sheet_name, frame in sheets.items():
            if frame.empty or len(frame.columns) == 0:
                continue
            frame = frame.dropna(how="all").copy()
            if frame.empty:
                continue
            frame["_source_file"] = path.name
            frame["_source_sheet"] = str(sheet_name)
            frames.append(frame)

    if not frames:
        raise FileNotFoundError(
            f"No usable Excel or CSV files found in {directory.name}/."
        )
    return pd.concat(frames, ignore_index=True, sort=False)


def _normalize_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def detect_columns(frame: pd.DataFrame) -> dict[str, str | None]:
    """Pick likely sales columns by matching common header names."""
    result: dict[str, str | None] = {}
    candidates = [column for column in frame.columns if not str(column).startswith("_")]
    for field, aliases in FIELD_ALIASES.items():
        normalized = {_normalize_name(alias) for alias in aliases}
        match = next(
            (column for column in candidates if _normalize_name(column) in normalized),
            None,
        )
        result[field] = str(match) if match is not None else None
    return result


def _numeric_values(values: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_numeric(values, errors="coerce")
    cleaned = values.astype(str).str.strip()
    negative = cleaned.str.match(r"^\(.*\)$")
    cleaned = cleaned.str.replace(r"[^0-9.+-]", "", regex=True)
    numbers = pd.to_numeric(cleaned, errors="coerce")
    return numbers.where(~negative, -numbers.abs())


def _llm_narrative(metrics: dict[str, Any], provider: str) -> tuple[str, str | None]:
    load_dotenv(ROOT / ".env")
    provider = provider.lower()
    try:
        if provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY is missing from .env")
            from langchain_openai import ChatOpenAI

            model = ChatOpenAI(
                model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                temperature=0.2,
            )
        elif provider == "ollama":
            from langchain_ollama import ChatOllama

            model = ChatOllama(
                model=os.getenv("OLLAMA_MODEL", "llama3.1"),
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                temperature=0.2,
            )
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

        response = model.invoke([
            SystemMessage(content=(
                "You are a careful sales analyst. Interpret only the supplied "
                "aggregated metrics. Do not invent causes or facts. Note when "
                "the data is incomplete, and keep the report concise."
            )),
            HumanMessage(content=f"Write an executive sales summary with notable trends and caveats.\n{metrics}"),
        ])
        return str(response.content), None
    except Exception as exc:
        return (
            "LLM narrative unavailable. The quantitative report below was still generated.",
            str(exc),
        )


def generate_report(
    frame: pd.DataFrame,
    columns: dict[str, str | None] | None = None,
    provider: str = "ollama",
    output_dir: Path = REPORTS_DIR,
) -> Path:
    """Create an LLM-assisted report from the selected date and amount columns."""
    columns = columns or detect_columns(frame)
    date_column, amount_column = columns.get("date"), columns.get("amount")
    if not date_column or not amount_column:
        raise ValueError("Map both a date column and a sales amount column to generate a report.")
    if date_column not in frame or amount_column not in frame:
        raise ValueError("A selected column is not present in the loaded sales data.")

    data = frame.copy()
    data["_report_date"] = pd.to_datetime(data[date_column], errors="coerce")
    data["_report_amount"] = _numeric_values(data[amount_column])
    valid = data.dropna(subset=["_report_date", "_report_amount"]).copy()
    if valid.empty:
        raise ValueError("No rows have both a readable date and numeric sales amount.")

    valid["_report_day"] = valid["_report_date"].dt.date
    daily_sales = valid.groupby("_report_day")["_report_amount"].sum().sort_index()
    total_sales = float(valid["_report_amount"].sum())
    today_sales = float(daily_sales.get(date.today(), 0.0))
    average_daily = float(daily_sales.mean())
    metrics: dict[str, Any] = {
        "rows_included": int(len(valid)),
        "rows_skipped": int(len(data) - len(valid)),
        "period_start": str(valid["_report_day"].min()),
        "period_end": str(valid["_report_day"].max()),
        "total_sales": round(total_sales, 2),
        "today_sales": round(today_sales, 2),
        "average_sales_per_day": round(average_daily, 2),
        "days_with_sales": int(daily_sales.size),
    }

    for field in ("product", "category", "region"):
        source_column = columns.get(field)
        if source_column and source_column in valid:
            top_values = (
                valid.groupby(source_column, dropna=True)["_report_amount"]
                .sum().nlargest(5).round(2).to_dict()
            )
            metrics[f"top_{field}_by_sales"] = {
                str(key): value for key, value in top_values.items()
            }

    narrative, warning = _llm_narrative(metrics, provider)
    lines = [
        f"# Sales Report: {date.today().isoformat()}",
        "",
        f"**Data period:** {metrics['period_start']} to {metrics['period_end']}",
        f"**Rows included:** {metrics['rows_included']} ({metrics['rows_skipped']} skipped)",
        "",
        "## Key Metrics",
        f"- Total sales: {total_sales:,.2f}",
        f"- Sales dated today: {today_sales:,.2f}",
        f"- Average sales per active day: {average_daily:,.2f}",
        f"- Days with sales: {metrics['days_with_sales']}",
        "",
        "## Analysis",
        narrative,
    ]
    for field in ("product", "category", "region"):
        top_values = metrics.get(f"top_{field}_by_sales")
        if top_values:
            lines.extend(["", f"## Top {field.title()} by Sales"])
            lines.extend(f"- {name}: {value:,.2f}" for name, value in top_values.items())
    if warning:
        lines.extend(["", f"> LLM detail: {warning}"])

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"sales-report-{date.today().isoformat()}.md"
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path