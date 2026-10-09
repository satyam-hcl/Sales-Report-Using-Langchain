from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from sales_reporter import DATA_DIR, detect_columns, generate_report, load_sales_data


load_dotenv()
st.set_page_config(page_title="Daily Sales Report", page_icon="Sales", layout="wide")
st.title("Daily Sales Report")
st.caption("Sales files are read from the local data/ folder. Reports are saved in reports/.")

provider_default = os.getenv("LLM_PROVIDER", "ollama").lower()
provider = st.selectbox(
    "Narrative model",
    options=["ollama", "openrouter"],
    index=0 if provider_default != "openrouter" else 1,
)

try:
    frame = load_sales_data(DATA_DIR)
except (FileNotFoundError, ValueError) as exc:
    st.warning(str(exc))
    st.stop()

st.caption(f"Loaded {len(frame):,} rows across {frame['_source_file'].nunique()} file(s).")
st.dataframe(frame.drop(columns=["_source_file", "_source_sheet"], errors="ignore").head(100), use_container_width=True)

suggested = detect_columns(frame)
columns = {}
with st.form("report_columns"):
    st.subheader("Confirm column mapping")
    candidates = [str(column) for column in frame.columns if not str(column).startswith("_")]
    for field in ("date", "amount", "product", "quantity", "category", "region"):
        options = ["(not mapped)", *candidates]
        suggested_value = suggested.get(field)
        index = options.index(suggested_value) if suggested_value in options else 0
        chosen = st.selectbox(field.title(), options, index=index, key=f"column_{field}")
        columns[field] = None if chosen == "(not mapped)" else chosen
    submitted = st.form_submit_button("Generate today's report")

if submitted:
    try:
        report_path = generate_report(frame, columns, provider)
        report_text = report_path.read_text(encoding="utf-8")
        st.success(f"Report saved to {report_path.relative_to(DATA_DIR.parent)}")
        st.markdown(report_text)
        st.download_button("Download Markdown report", report_text, file_name=report_path.name)
    except ValueError as exc:
        st.error(str(exc))