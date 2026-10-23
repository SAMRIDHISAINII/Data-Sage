# Σ DataSage — AI Data Analysis Agent

**Ask your data anything. No SQL required.**


DataSage is an AI-powered, natural-language data analyst that enables users to explore datasets, generate insights, execute validated SQL or Python analyses, visualize results, and understand business trends through plain-language explanations.

Upload a CSV or Excel file, select a sample dataset, or connect a database, then ask questions such as:

> “Show me the top 10 customers by revenue and explain the trend.”

DataSage plans the analysis, selects the appropriate execution tool, validates the generated code, analyzes the data, and returns charts, tables, reproducible code, and actionable insights.

## ✨ Key Features

### 01. Dataset Understanding
- Automatic dataset profiling and statistical summaries.
- Column identification and semantic understanding.
- Data quality checks and missing-value analysis.
- Suggested questions based on the dataset.

### 02. Agentic SQL & Python
- Converts natural-language questions into analytical workflows.
- Selects SQL or Python based on the task.
- Executes validated queries and sandboxed pandas operations.
- Retries failed analyses with self-correction.

### 03. Security & Guardrails
- Read-only SQL execution.
- SQL validation and Python AST checks.
- Sandboxed data analysis.
- Execution timeout of 30 seconds.
- Maximum result size of 500 rows.
- Validation checks and explicit assumptions.

### 04. Explainable Results
- Interactive analytical charts and result tables.
- Exact SQL or Python code used for analysis.
- Plain-language explanations of findings.
- Business trends, comparisons, and actionable recommendations.

## 🧠 How It Works

The DataSage analytical workflow follows four stages:

1. **Understand:** Profile the dataset, identify columns, and understand the user's question.
2. **Plan:** Break the question into analytical steps and choose SQL or Python.
3. **Execute & Validate:** Run the analysis within defined guardrails, validate the results, and correct errors when possible.
4. **Explain:** Present the findings through charts, tables, code, and natural-language explanations.

## 📊 Sample Datasets

Explore DataSage using sample business datasets:

| Dataset | Description |
|---|---|
| B2B Orders | 2,400 orders across regions, products, channels, and sales representatives (2023–2025). |
| SaaS Analytics | 600 accounts with customer segments, spend, NPS, churn, and acquisition channels. |
| Workforce Analytics | 450 employees with department, salary, performance, tenure, and attrition data. |

## 🛡️ Analytical Guardrails

DataSage is designed to make AI-assisted analysis more controlled and transparent
