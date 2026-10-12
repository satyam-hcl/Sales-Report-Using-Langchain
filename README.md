# Daily Sales Report

A local LangChain application that reads Excel and CSV sales files, calculates sales metrics, and uses Ollama or OpenRouter to write a concise analysis. Reports are saved as Markdown in `reports/`.

## Setup

1. Install Python 3.10 or newer.
2. Create and activate a virtual environment, then install dependencies:

	```bash
	python -m venv .venv
	source .venv/bin/activate
	pip install -r requirements.txt
	```

3. Optionally put `.xlsx`, `.xls`, `.xlsm`, or `.csv` sales files in `data/` to load them automatically.
4. Edit `.env` to select and configure a model. The OpenRouter key belongs only in `OPENROUTER_API_KEY` in this ignored local file.

## Run the app

```bash
streamlit run app.py
```

The app lets you upload one or more `.xlsx`, `.xls`, or `.csv` sales reports, extracts their rows, and previews the loaded data. Uploaded files take precedence over files in `data/`; if no files are uploaded, the app loads from that folder. It suggests date and sales amount columns, lets you adjust the mappings, and saves a report when you submit. If your files use different headers, select the matching columns in the form.

For Ollama, start Ollama and download the configured model first, for example:

```bash
ollama pull llama3.1
```

For OpenRouter, set `LLM_PROVIDER=openrouter` and add your key to `.env`. The model name is configurable with `OPENROUTER_MODEL`.

## Daily automation

Run the scheduler in a separate terminal or as a managed background service:

```bash
python scheduler.py
```

It generates one report each day at `DAILY_REPORT_TIME` using the provider in `LLM_PROVIDER`. Keep the process running for scheduled jobs to execute. The scheduler logs failures and continues running; report generation falls back to quantitative metrics if the LLM is unavailable.

The report includes total sales, sales dated today, average sales per active day, and top products/categories/regions when those columns are detected or mapped. It analyzes all loaded rows; “sales dated today” is a separate metric, so historical data remains represented in the report.