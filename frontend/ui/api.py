import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


class ApiError(Exception):
    pass


def _check(r: requests.Response):
    if r.ok:
        return r.json()
    try:
        detail = r.json().get("error", r.text)
    except ValueError:
        detail = r.text[:300]
    raise ApiError(detail or f"HTTP {r.status_code}")


def get(path: str, **params):
    return _check(requests.get(BASE + path, params=params, timeout=60))


def post(path: str, body: dict | None = None, files=None, timeout: int = 180):
    return _check(requests.post(BASE + path, json=body, files=files, timeout=timeout))


def ask_stream(dataset_id: str, body: dict):
    with requests.post(f"{BASE}/datasets/{dataset_id}/ask", json=body, stream=True, timeout=600) as r:
        if not r.ok:
            _check(r)
        for line in r.iter_lines():
            if line:
                yield json.loads(line)
