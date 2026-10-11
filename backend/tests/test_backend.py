"""Backend API tests for AI Data Analysis Agent."""
import io
import json
import os
import time

import pandas as pd
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to local file
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"

session = requests.Session()


# --------- health / models / samples listing ----------
class TestBasics:
    def test_health(self):
        r = session.get(f"{API}/health", timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_models(self):
        r = session.get(f"{API}/models", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["default"] == "gpt-6-luna"
        keys = {m["key"] for m in data["models"]}
        assert {"gpt-6-luna", "claude-sonnet-5-5"} <= keys

    def test_samples_list(self):
        r = session.get(f"{API}/datasets/samples", timeout=15)
        assert r.status_code == 200
        data = r.json()
        keys = {s["key"] for s in data["samples"]}
        assert {"sales", "customers", "hr"} <= keys
        assert "demo_sql_url" in data and data["demo_sql_url"].startswith("sqlite:")


# --------- sample dataset load ----------
@pytest.fixture(scope="module")
def sales_ds():
    r = session.post(f"{API}/datasets/samples/sales", timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


class TestSamplesLoad:
    @pytest.mark.parametrize("key", ["sales", "customers", "hr"])
    def test_load_sample(self, key):
        r = session.post(f"{API}/datasets/samples/{key}", timeout=60)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert "id" in doc or "_id" in doc
        assert doc["row_count"] > 0
        assert doc["col_count"] > 0
        assert isinstance(doc["columns"], list) and len(doc["columns"]) > 0
        assert "preview" in doc
        c0 = doc["columns"][0]
        assert "type" in c0 and "stats" in c0


# --------- upload ----------
class TestUpload:
    def test_upload_csv_with_money_and_date(self):
        csv_data = (
            "name,amount,order_date\n"
            "Alpha,\"$1,200\",2024-01-15\n"
            "Beta,\"$2,350\",2024-02-10\n"
            "Gamma,\"$900\",2024-03-05\n"
            "Delta,\"$4,100\",2024-04-20\n"
            "Epsilon,\"$750\",2024-05-01\n"
        )
        files = {"file": ("test.csv", csv_data, "text/csv")}
        r = session.post(f"{API}/datasets/upload", files=files, timeout=60)
        assert r.status_code == 200, r.text
        doc = r.json()
        col_types = {c["name"]: c["type"] for c in doc["columns"]}
        assert col_types.get("amount") == "numeric", f"amount should be numeric, got {col_types}"
        assert col_types.get("order_date") == "datetime", f"order_date should be datetime, got {col_types}"

    def test_upload_xlsx(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        buf = io.BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        files = {"file": ("test.xlsx", buf.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = session.post(f"{API}/datasets/upload", files=files, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["row_count"] == 3

    def test_upload_unsupported(self):
        files = {"file": ("bad.txt", b"hello", "text/plain")}
        r = session.post(f"{API}/datasets/upload", files=files, timeout=30)
        assert r.status_code == 400
        assert "error" in r.json()


# --------- SQL connector ----------
DEMO_SQLITE = "sqlite:////app/backend/data/demo.sqlite"


class TestSQL:
    def test_sql_table(self):
        r = session.post(f"{API}/datasets/sql",
                         json={"connection_string": DEMO_SQLITE, "table": "sales"},
                         timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["row_count"] > 0

    def test_sql_select_query(self):
        r = session.post(f"{API}/datasets/sql",
                         json={"connection_string": DEMO_SQLITE,
                               "query": 'SELECT * FROM customers WHERE segment = "Enterprise"'},
                         timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["row_count"] > 0

    def test_sql_drop_blocked(self):
        r = session.post(f"{API}/datasets/sql",
                         json={"connection_string": DEMO_SQLITE, "query": "DROP TABLE sales"},
                         timeout=30)
        assert r.status_code == 400
        assert "SELECT" in r.json()["error"] or "WITH" in r.json()["error"]

    def test_sql_bad_conn(self):
        r = session.post(f"{API}/datasets/sql",
                         json={"connection_string": "sqlite:////nope/does_not_exist.db", "table": "x"},
                         timeout=30)
        assert r.status_code == 400


# --------- dataset detail/preview/404 ----------
class TestDatasetDetail:
    def test_get_dataset(self, sales_ds):
        ds_id = sales_ds["id"]
        r = session.get(f"{API}/datasets/{ds_id}", timeout=15)
        assert r.status_code == 200
        assert r.json()["id"] == ds_id

    def test_preview(self, sales_ds):
        ds_id = sales_ds["id"]
        r = session.get(f"{API}/datasets/{ds_id}/preview?n=10", timeout=15)
        assert r.status_code == 200
        assert len(r.json()["rows"]) == 10

    def test_unknown_404(self):
        r = session.get(f"{API}/datasets/does-not-exist-xyz", timeout=15)
        assert r.status_code == 404


# --------- overview (LLM) ----------
class TestOverview:
    def test_overview_and_cache(self, sales_ds):
        ds_id = sales_ds["id"]
        r = session.post(f"{API}/datasets/{ds_id}/overview",
                         json={"model": "gpt-6-luna"}, timeout=180)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("briefing")
        assert isinstance(data.get("insights"), list) and len(data["insights"]) >= 1
        assert isinstance(data.get("suggested_questions"), list) and len(data["suggested_questions"]) >= 3
        assert isinstance(data.get("column_descriptions"), dict)

        # second call cached
        r2 = session.post(f"{API}/datasets/{ds_id}/overview", json={}, timeout=30)
        assert r2.status_code == 200
        assert r2.json().get("cached") is True


# --------- ask (streaming NDJSON) ----------
def _consume_stream(ds_id, question, model="gpt-6-luna", session_id="pytest-session", timeout=180):
    r = session.post(f"{API}/datasets/{ds_id}/ask",
                     json={"question": question, "model": model, "session_id": session_id},
                     stream=True, timeout=timeout)
    assert r.status_code == 200, r.text
    events = []
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            pass
    return events


class TestAsk:
    def test_empty_question(self, sales_ds):
        r = session.post(f"{API}/datasets/{sales_ds['id']}/ask", json={"question": "  "}, timeout=15)
        assert r.status_code == 400

    def test_top_customers_sql(self, sales_ds):
        events = _consume_stream(sales_ds["id"],
                                 "Show me the top 10 customers by revenue and explain the trend",
                                 model="gpt-6-luna")
        types = [e["type"] for e in events]
        assert "plan" in types
        assert "result" in types
        assert "done" in types
        plan = next(e for e in events if e["type"] == "plan")
        result = next(e for e in events if e["type"] == "result")
        assert plan["approach"] in ("sql", "python")
        assert result["validation"]["status"] in ("passed", "warning")
        assert result["chart"]["type"] in ("bar", "line", "pie", "scatter", "none")

    def test_correlation_python(self, sales_ds):
        events = _consume_stream(sales_ds["id"],
                                 "What is the correlation between discount and quantity?",
                                 model="gpt-6-luna")
        types = [e["type"] for e in events]
        assert "result" in types or "clarification" in types
        assert "done" in types or "clarification" in types

    def test_off_topic_clarification(self, sales_ds):
        events = _consume_stream(sales_ds["id"], "Write a poem about cats", model="gpt-6-luna")
        types = [e["type"] for e in events]
        assert "clarification" in types, f"Expected clarification, got {types}"

    def test_followup_rag(self, sales_ds):
        sid = f"followup-{int(time.time())}"
        _ = _consume_stream(sales_ds["id"],
                            "Show me the top 5 customers by revenue",
                            session_id=sid)
        events = _consume_stream(sales_ds["id"],
                                 "What region are those customers mostly from?",
                                 session_id=sid)
        types = [e["type"] for e in events]
        # follow-up should either compute (result) or ask clarification but NOT error
        assert "error" not in types, [e for e in events if e["type"] == "error"]
        assert ("result" in types) or ("clarification" in types)

    def test_claude_model(self, sales_ds):
        events = _consume_stream(sales_ds["id"],
                                 "What is the total revenue by region?",
                                 model="claude-sonnet-5-5")
        types = [e["type"] for e in events]
        assert "result" in types
        assert "done" in types


# --------- messages history ----------
class TestHistory:
    def test_messages(self, sales_ds):
        sid = f"hist-{int(time.time())}"
        _consume_stream(sales_ds["id"], "What is the total revenue?", session_id=sid)
        r = session.get(f"{API}/datasets/{sales_ds['id']}/messages", params={"session_id": sid}, timeout=15)
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert len(msgs) >= 1
        assert msgs[0].get("question")
        assert msgs[0].get("answer") is not None
