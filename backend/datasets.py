import io
import json
import re
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from db import datasets_col, now_iso, serialize
from sandbox import GuardrailError, validate_sql

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
MAX_SQL_ROWS = 50_000
_cache: dict[str, pd.DataFrame] = {}

DATE_HINT = re.compile(r"\d{1,4}[-/.]\d{1,2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", re.I)


def load_file(filename: str, content: bytes) -> pd.DataFrame:
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content))
    elif name.endswith(".csv"):
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(content), encoding=enc, sep=None, engine="python")
                break
            except UnicodeDecodeError:
                continue
        else:
            raise GuardrailError("Could not decode CSV file")
    else:
        raise GuardrailError("Unsupported file type. Upload a .csv, .xlsx or .xls file")
    if df.empty:
        raise GuardrailError("The file contains no rows")
    return coerce_types(df)


def coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~df.columns.str.startswith("Unnamed:")] if any(c.startswith("Unnamed:") for c in df.columns) else df
    for c in df.columns:
        s = df[c]
        if not (pd.api.types.is_string_dtype(s) or s.dtype == object):
            continue
        nonnull = s.dropna().astype(str)
        if nonnull.empty:
            continue
        cleaned = nonnull.str.replace(r"[$€£,%\s]", "", regex=True)
        nums = pd.to_numeric(cleaned, errors="coerce")
        if nums.notna().mean() >= 0.95 and cleaned.str.contains(r"\d").mean() > 0.9:
            df[c] = pd.to_numeric(s.astype(str).str.replace(r"[$€£,%\s]", "", regex=True), errors="coerce")
            continue
        sample = nonnull.head(50)
        if sample.str.contains(DATE_HINT).mean() >= 0.8:
            dates = pd.to_datetime(nonnull, errors="coerce", format="mixed")
            if dates.notna().mean() >= 0.9:
                df[c] = pd.to_datetime(s, errors="coerce", format="mixed")
    return df


def semantic_type(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    if pd.api.types.is_numeric_dtype(s):
        return "numeric"
    n = len(s)
    u = s.nunique(dropna=True)
    if u == n and re.search(r"\bid\b|_id$|^id", str(s.name), re.I):
        return "identifier"
    if u <= 100 and (n == 0 or u / max(n, 1) < 0.5):
        return "categorical"
    return "text"


def _py(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 4)
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v if isinstance(v, (int, float, str, bool)) else str(v)


def profile(df: pd.DataFrame) -> list[dict]:
    cols = []
    for c in df.columns:
        s = df[c]
        st = semantic_type(s)
        info = {
            "name": c,
            "dtype": str(s.dtype),
            "type": st,
            "non_null": int(s.notna().sum()),
            "nulls": int(s.isna().sum()),
            "unique": int(s.nunique(dropna=True)),
            "sample_values": [_py(v) for v in s.dropna().astype(str).unique()[:5]],
            "stats": {},
        }
        if st == "numeric" and info["non_null"]:
            info["stats"] = {k: _py(getattr(s, k)()) for k in ("min", "max", "mean", "median", "std")}
        elif st == "datetime" and info["non_null"]:
            info["stats"] = {"min": _py(s.min()), "max": _py(s.max())}
        elif st in ("categorical", "boolean"):
            vc = s.value_counts(dropna=True).head(5)
            info["stats"] = {"top_values": {str(k): int(v) for k, v in vc.items()}}
        cols.append(info)
    return cols


def preview_rows(df: pd.DataFrame, n: int = 5) -> list[dict]:
    return json.loads(df.head(n).to_json(orient="records", date_format="iso"))


def save_dataset(df: pd.DataFrame, name: str, source: str, source_detail: str = "") -> dict:
    ds_id = str(uuid.uuid4())
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).where(df[c].notna(), None)
    df.to_parquet(DATA_DIR / f"{ds_id}.parquet", index=False)
    _cache[ds_id] = df
    doc = {
        "_id": ds_id,
        "name": name,
        "source": source,
        "source_detail": source_detail,
        "row_count": int(len(df)),
        "col_count": int(df.shape[1]),
        "memory_mb": round(float(df.memory_usage(deep=True).sum()) / 1e6, 2),
        "columns": profile(df),
        "preview": preview_rows(df),
        "column_descriptions": {},
        "overview": None,
        "created_at": now_iso(),
    }
    datasets_col.insert_one(doc)
    return serialize(doc)


def get_dataset(ds_id: str) -> dict | None:
    return serialize(datasets_col.find_one({"_id": ds_id}))


def load_df(ds_id: str) -> pd.DataFrame:
    if ds_id not in _cache:
        path = DATA_DIR / f"{ds_id}.parquet"
        if not path.exists():
            raise GuardrailError("Dataset data not found. Please reload the dataset.")
        _cache[ds_id] = pd.read_parquet(path)
    return _cache[ds_id]


def from_sql(conn_str: str, table: str = "", query: str = "") -> tuple[pd.DataFrame, str]:
    if not conn_str.strip():
        raise GuardrailError("Connection string is required")
    if query.strip():
        sql = validate_sql(query)
        label = "custom query"
    elif table.strip():
        if not re.match(r"^[\w.\"]+$", table.strip()):
            raise GuardrailError("Invalid table name")
        sql = f"SELECT * FROM {table.strip()}"
        label = table.strip()
    else:
        raise GuardrailError("Provide a table name or a SELECT query")
    try:
        engine = create_engine(conn_str, pool_pre_ping=True)
        with engine.connect() as con:
            df = pd.read_sql(text(sql), con, chunksize=None)
    except GuardrailError:
        raise
    except Exception as e:
        raise GuardrailError(f"Database connection failed: {str(e).splitlines()[0][:300]}")
    if df.empty:
        raise GuardrailError("Query returned no rows")
    if len(df) > MAX_SQL_ROWS:
        df = df.head(MAX_SQL_ROWS)
    return coerce_types(df), label


# ---------------------------------------------------------------- sample data
_REGIONS = {"North America": ["USA", "Canada", "Mexico"], "Europe": ["Germany", "UK", "France", "Spain"],
            "APAC": ["India", "Japan", "Australia", "Singapore"], "LATAM": ["Brazil", "Argentina", "Chile"]}
_PRODUCTS = {
    "Electronics": {"Laptop Pro 15": 1450, "Wireless Earbuds": 129, "4K Monitor": 389, "Smart Watch": 249},
    "Office": {"Ergonomic Chair": 320, "Standing Desk": 540, "Desk Lamp": 45, "Notebook Pack": 18},
    "Software": {"Analytics Suite": 899, "Security Bundle": 499, "Cloud Storage 2TB": 96},
    "Accessories": {"USB-C Hub": 59, "Laptop Sleeve": 35, "Mechanical Keyboard": 139, "Webcam HD": 79},
}
_COMPANY_A = ["Northwind", "Acme", "Globex", "Initech", "Umbrella", "Stark", "Wayne", "Hooli", "Vandelay", "Aperture",
              "Blue Sky", "Redwood", "Summit", "Harbor", "Pioneer", "Lumen", "Vertex", "Orion", "Atlas", "Nimbus"]
_COMPANY_B = ["Traders", "Corp", "Industries", "Labs", "Logistics", "Retail", "Holdings", "Systems", "Partners", "Group"]


def _customers(rng, n):
    return [f"{rng.choice(_COMPANY_A)} {rng.choice(_COMPANY_B)} {i:03d}" for i in range(1, n + 1)]


def gen_sales() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 2400
    customers = _customers(rng, 120)
    cust_weights = rng.pareto(1.5, len(customers)) + 1
    cust_weights /= cust_weights.sum()
    dates = pd.to_datetime("2023-01-01") + pd.to_timedelta(rng.integers(0, 900, n), unit="D")
    rows = []
    for i in range(n):
        region = rng.choice(list(_REGIONS))
        country = rng.choice(_REGIONS[region])
        cat = rng.choice(list(_PRODUCTS), p=[0.35, 0.25, 0.2, 0.2])
        product = rng.choice(list(_PRODUCTS[cat]))
        price = _PRODUCTS[cat][product] * rng.uniform(0.95, 1.08)
        qty = int(rng.integers(1, 12))
        disc = float(rng.choice([0, 0, 0.05, 0.1, 0.15, 0.25]))
        d = dates[i]
        growth = 1 + 0.02 * ((d.year - 2023) * 12 + d.month)
        ci = rng.choice(len(customers), p=cust_weights)
        rows.append({
            "order_id": f"ORD-{10000 + i}", "order_date": d, "region": region, "country": country,
            "product_category": cat, "product": product, "customer_id": f"C{ci + 1:03d}", "customer_name": customers[ci],
            "quantity": qty, "unit_price": round(price, 2), "discount": disc,
            "revenue": round(qty * price * (1 - disc) * growth, 2),
            "channel": rng.choice(["Online", "Partner", "Direct Sales", "Retail"], p=[0.45, 0.2, 0.25, 0.1]),
            "sales_rep": rng.choice(["A. Patel", "J. Moreno", "L. Chen", "M. Okafor", "S. Novak", "T. Berg"]),
        })
    return pd.DataFrame(rows).sort_values("order_date").reset_index(drop=True)


def gen_customers() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n = 600
    seg = rng.choice(["Enterprise", "Mid-Market", "SMB", "Startup"], n, p=[0.15, 0.25, 0.4, 0.2])
    base = {"Enterprise": 48000, "Mid-Market": 16000, "SMB": 5200, "Startup": 2100}
    churn_p = {"Enterprise": 0.06, "Mid-Market": 0.12, "SMB": 0.22, "Startup": 0.3}
    signup = pd.to_datetime("2021-01-01") + pd.to_timedelta(rng.integers(0, 1500, n), unit="D")
    churned = np.array([rng.random() < churn_p[s] for s in seg])
    return pd.DataFrame({
        "customer_id": [f"C{i:04d}" for i in range(1, n + 1)],
        "company": _customers(rng, n),
        "segment": seg,
        "industry": rng.choice(["Retail", "Finance", "Healthcare", "Technology", "Manufacturing", "Education"], n),
        "country": rng.choice(sum(_REGIONS.values(), []), n),
        "signup_date": signup,
        "plan": rng.choice(["Basic", "Pro", "Business", "Enterprise"], n, p=[0.3, 0.35, 0.25, 0.1]),
        "monthly_spend": np.round([base[s] / 12 * rng.uniform(0.6, 1.5) for s in seg], 2),
        "lifetime_value": np.round([base[s] * rng.uniform(0.5, 2.2) for s in seg], 2),
        "orders_count": rng.integers(1, 60, n),
        "support_tickets": rng.poisson(3, n),
        "nps_score": np.clip(rng.normal(7.5, 2, n).round(), 0, 10).astype(int),
        "acquisition_channel": rng.choice(["Organic", "Paid Ads", "Referral", "Events", "Outbound"], n),
        "churned": churned,
    })


def gen_hr() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    n = 450
    depts = {"Engineering": 125000, "Sales": 85000, "Marketing": 78000, "Finance": 92000, "HR": 70000,
             "Operations": 68000, "Customer Success": 64000}
    dept = rng.choice(list(depts), n, p=[0.3, 0.2, 0.12, 0.1, 0.06, 0.12, 0.1])
    levels = rng.choice(["Junior", "Mid", "Senior", "Lead", "Manager"], n, p=[0.25, 0.3, 0.25, 0.12, 0.08])
    mult = {"Junior": 0.65, "Mid": 0.9, "Senior": 1.2, "Lead": 1.45, "Manager": 1.6}
    perf = np.clip(rng.normal(3.4, 0.8, n).round(1), 1, 5)
    hire = pd.to_datetime("2015-01-01") + pd.to_timedelta(rng.integers(0, 3800, n), unit="D")
    return pd.DataFrame({
        "employee_id": [f"E{i:04d}" for i in range(1, n + 1)],
        "department": dept,
        "job_level": levels,
        "gender": rng.choice(["Female", "Male", "Non-binary"], n, p=[0.46, 0.52, 0.02]),
        "age": rng.integers(22, 62, n),
        "hire_date": hire,
        "location": rng.choice(["New York", "London", "Bangalore", "Berlin", "Remote", "Toronto"], n),
        "remote": rng.random(n) < 0.38,
        "salary": np.round([depts[d] * mult[l] * rng.uniform(0.88, 1.15) for d, l in zip(dept, levels)], 0),
        "bonus_pct": np.round(rng.uniform(0, 0.25, n), 2),
        "performance_rating": perf,
        "training_hours": rng.integers(0, 80, n),
        "overtime_hours": rng.integers(0, 25, n),
        "attrition": (rng.random(n) < np.where(perf < 2.5, 0.35, 0.11)),
    })


SAMPLES = {
    "sales": {"title": "Sales Orders", "description": "2,400 B2B orders across regions, products, channels and reps (2023–2025)", "fn": gen_sales},
    "customers": {"title": "Customer Accounts", "description": "600 SaaS accounts with segment, spend, NPS, churn and acquisition channel", "fn": gen_customers},
    "hr": {"title": "HR & Workforce", "description": "450 employees with department, salary, performance, tenure and attrition", "fn": gen_hr},
}


def ensure_demo_sqlite() -> str:
    path = DATA_DIR / "demo.sqlite"
    if not path.exists():
        engine = create_engine(f"sqlite:///{path}")
        gen_sales().to_sql("sales", engine, index=False)
        gen_customers().to_sql("customers", engine, index=False)
    return f"sqlite:///{path}"
