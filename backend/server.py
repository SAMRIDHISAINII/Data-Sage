import json
import logging

from a2wsgi import WSGIMiddleware
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, stream_with_context

load_dotenv()

import datasets as ds  # noqa: E402
import llm  # noqa: E402
from agent import ask_stream, generate_overview  # noqa: E402
from db import messages_col, serialize  # noqa: E402
from sandbox import GuardrailError  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

flask_app = Flask(__name__)
flask_app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
DEMO_SQLITE_URL = ds.ensure_demo_sqlite()


@flask_app.errorhandler(GuardrailError)
def _guardrail(e):
    return jsonify({"error": str(e)}), 400


@flask_app.errorhandler(Exception)
def _unhandled(e):
    log.exception("Unhandled error")
    return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@flask_app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "ai-data-analysis-agent"})


@flask_app.get("/api/models")
def models():
    return jsonify({"default": llm.DEFAULT_MODEL, "models": [{"key": k, **{kk: vv for kk, vv in v.items() if kk != "model"}} for k, v in llm.MODELS.items()]})


@flask_app.get("/api/datasets/samples")
def samples():
    return jsonify({"samples": [{"key": k, "title": v["title"], "description": v["description"]} for k, v in ds.SAMPLES.items()],
                    "demo_sql_url": DEMO_SQLITE_URL})


@flask_app.post("/api/datasets/samples/<key>")
def load_sample(key):
    spec = ds.SAMPLES.get(key)
    if not spec:
        raise GuardrailError("Unknown sample dataset")
    doc = ds.save_dataset(spec["fn"](), spec["title"], "sample", key)
    return jsonify(doc)


@flask_app.post("/api/datasets/upload")
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        raise GuardrailError("No file uploaded")
    df = ds.load_file(f.filename, f.read())
    doc = ds.save_dataset(df, f.filename, "upload", f.filename)
    return jsonify(doc)


@flask_app.post("/api/datasets/sql")
def connect_sql():
    body = request.get_json(silent=True) or {}
    df, label = ds.from_sql(body.get("connection_string", ""), body.get("table", ""), body.get("query", ""))
    dialect = body.get("connection_string", "").split(":")[0]
    doc = ds.save_dataset(df, f"{label} ({dialect})", "sql", label)
    return jsonify(doc)


@flask_app.get("/api/datasets/<ds_id>")
def get_dataset(ds_id):
    doc = ds.get_dataset(ds_id)
    if not doc:
        return jsonify({"error": "Dataset not found"}), 404
    return jsonify(doc)


@flask_app.get("/api/datasets/<ds_id>/preview")
def preview(ds_id):
    n = min(int(request.args.get("n", 50)), 500)
    return jsonify({"rows": ds.preview_rows(ds.load_df(ds_id), n)})


@flask_app.post("/api/datasets/<ds_id>/overview")
def overview(ds_id):
    doc = ds.get_dataset(ds_id)
    if not doc:
        return jsonify({"error": "Dataset not found"}), 404
    body = request.get_json(silent=True) or {}
    if doc.get("overview") and not body.get("force"):
        return jsonify({**doc["overview"], "column_descriptions": doc.get("column_descriptions", {}), "cached": True})
    return jsonify(generate_overview(doc, ds.load_df(ds_id), body.get("model", llm.DEFAULT_MODEL)))


@flask_app.post("/api/datasets/<ds_id>/ask")
def ask(ds_id):
    doc = ds.get_dataset(ds_id)
    if not doc:
        return jsonify({"error": "Dataset not found"}), 404
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        raise GuardrailError("Question is required")
    if len(question) > 1500:
        raise GuardrailError("Question is too long (max 1500 characters)")
    session_id = body.get("session_id") or "anonymous"
    model_key = body.get("model", llm.DEFAULT_MODEL)
    df = ds.load_df(ds_id)

    def gen():
        try:
            for ev in ask_stream(doc, df, question, session_id, model_key):
                yield json.dumps(ev, default=str) + "\n"
        except Exception as e:
            log.exception("ask failed")
            yield json.dumps({"type": "error", "message": f"{type(e).__name__}: {e}"}) + "\n"

    return Response(stream_with_context(gen()), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@flask_app.get("/api/datasets/<ds_id>/messages")
def history(ds_id):
    session_id = request.args.get("session_id", "anonymous")
    docs = messages_col.find({"dataset_id": ds_id, "session_id": session_id}).sort("created_at", 1)
    return jsonify({"messages": [serialize(d) for d in docs]})


app = WSGIMiddleware(flask_app)
