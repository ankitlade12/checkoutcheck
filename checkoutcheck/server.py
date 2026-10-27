"""Private single-operator workbench; use loopback or an IAM-authorized SSM tunnel."""

import asyncio
import hashlib
import html
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .evaluator import canonical, compare, digest, identifier as validate_identifier, keys, require, score, validate_suite
from .vision import validate_inputs
from .perception import MODELS as PERCEPTION_MODELS, load_manifest
from .aws_connection import connection_status

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("CHECKOUTCHECK_DATA", ROOT / "private-data")).resolve()
STOP = threading.Event()
TERMINAL = {"completed", "partial", "failed", "canceled"}


def read_only():
    return os.environ.get('CHECKOUTCHECK_READ_ONLY') == '1'


@contextmanager
def db():
    path = Path(os.environ.get('CHECKOUTCHECK_REVIEW_DB', str(DATA / 'workbench.sqlite'))) if read_only() else DATA / 'workbench.sqlite'
    connection = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=30) if read_only() else sqlite3.connect(path, timeout=30)
    if read_only():
        connection.execute('PRAGMA query_only=ON')
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "media").mkdir(exist_ok=True)
    with db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS suites(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, suite_id TEXT NOT NULL, status TEXT NOT NULL,
            created REAL NOT NULL, updated REAL NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0, request_key TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL,
            data TEXT NOT NULL, result TEXT, error TEXT);
        """)
        conn.execute("UPDATE runs SET status=CASE WHEN attempts<2 THEN 'queued' ELSE 'failed' END, error='Worker restarted' "
                     "WHERE status IN ('validating','running','scoring')")


def record(table, identifier):
    # Callers select table names from internal constants only.
    validate_identifier(identifier)
    with db() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise HTTPException(404, "Record not found")
    return json.loads(row["data"])


def run_record(identifier):
    with db() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise HTTPException(404, "Run not found")
    value = dict(row)
    for field in ("data", "result"):
        value[field] = json.loads(value[field]) if value[field] else None
    value.pop("request_key")
    value.pop("request_hash")
    return value


def update_run(identifier, **fields):
    fields["updated"] = time.time()
    with db() as conn:
        conn.execute(f"UPDATE runs SET {','.join(k+'=?' for k in fields)} WHERE id=? AND status!='canceled'",
                     (*fields.values(), identifier))


def process(command, timeout, run_id=None):
    # Files avoid pipe backpressure from frame-level evidence.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        child = subprocess.Popen(command, stdout=output, stderr=errors, cwd=ROOT)
        started = time.monotonic()
        try:
            while child.poll() is None:
                if STOP.is_set() or (run_id and run_record(run_id)["status"] == "canceled"):
                    raise InterruptedError("Run canceled or worker stopped")
                if time.monotonic() - started > timeout:
                    raise ValueError("Vision process exceeded its time limit")
                time.sleep(0.1)
            output.seek(0)
            raw = output.read(10_000_001)
            require(len(raw) <= 10_000_000, "Vision output exceeded limit")
            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ValueError("Vision worker failed to return valid output") from None
            require(child.returncode == 0 and "error" not in result, result.get("error", "Vision worker failed"))
            return result
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()


def execute_run(run):
    identifier, data = run["id"], run["data"]
    with db() as conn:
        claimed = conn.execute("UPDATE runs SET status='validating' WHERE id=? AND status='queued'", (identifier,)).rowcount
    if not claimed:
        return
    if data.get("task") == "rpc_perception":
        execute_perception_run(run)
        return
    frozen = record("suites", run["suite_id"])
    suite, entries = frozen["suite"], frozen["entries"]
    update_run(identifier, status="validating", progress=0, attempts=run["attempts"] + 1, error=None)
    validate_suite(suite)
    predictions, details, failures = [], {}, {}
    if data.get("imported") is not None:
        bundle = data["imported"]
    else:
        update_run(identifier, status="running")
        for index, entry in enumerate(entries):
            if STOP.is_set() or run_record(identifier)["status"] == "canceled":
                return
            try:
                asset = record("assets", entry["asset_id"])
                path = DATA / "media" / (entry["asset_id"] + ".mp4")
                require(hashlib.sha256(path.read_bytes()).hexdigest() == asset["sha256"], "Media hash changed")
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=DATA) as inputs:
                    json.dump(entry["inputs"], inputs)
                    inputs.flush()
                    result = process([sys.executable, "-m", "checkoutcheck.vision", str(path), "--inputs", inputs.name], 600, identifier)
                predictions.append({"case_id": entry["annotation"]["id"], "decision": result["decision"], "events": result["events"]})
                details[entry["annotation"]["id"]] = result
            except InterruptedError:
                return
            except (ValueError, OSError) as error:
                failures[entry["annotation"]["id"]] = str(error)
            update_run(identifier, progress=index + 1)
        bundle = {"schema_version": "1.0", "suite_hash": digest(suite), "input_track": "VP",
                  "model": {"id": "aruco-inventory", "version": "0.1.0", "config": {"dictionary": "DICT_4X4_50"},
                            "provenance": "CheckoutCheck OpenCV 5 marker instrumentation baseline"}, "predictions": predictions}
    if run_record(identifier)["status"] == "canceled" or STOP.is_set():
        return
    update_run(identifier, status="scoring")
    report = score(suite, bundle)
    result = {"report": report, "predictions": bundle, "vision": details, "failures": failures,
              "execution": {"location": "local", "source_hash": source_hash(), "inference_executed": data.get("imported") is None}}
    # Guard terminal commit against a concurrent cancellation.
    with db() as conn:
        conn.execute("UPDATE runs SET status=?,result=?,progress=?,updated=? WHERE id=? AND status='scoring'",
                     (report["status"], canonical(result), len(entries), time.time(), identifier))


def source_hash():
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "checkoutcheck").glob("*.py"))})


def execute_perception_run(run):
    identifier = run["id"]
    manifest = load_manifest(DATA / "rpc")
    require(manifest["hash"] == run["data"]["dataset_hash"], "Dataset changed after job was queued")
    update_run(identifier, status="running", attempts=run["attempts"] + 1, error=None)
    try:
        result = process([sys.executable, "-m", "checkoutcheck.perception", "--directory", str(DATA / "rpc"),
                          "--model", run["data"]["model"]], 600, identifier)
    except InterruptedError:
        return
    with db() as conn:
        conn.execute("UPDATE runs SET status=?,result=?,progress=?,updated=? WHERE id=? AND status='running'",
                     (result["status"], canonical(result), len(manifest["images"]), time.time(), identifier))


def worker():
    while not STOP.wait(0.2):
        with db() as conn:
            row = conn.execute("SELECT id FROM runs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
        if row:
            try:
                execute_run(run_record(row["id"]))
            except Exception as error:
                if run_record(row["id"])["status"] != "canceled":
                    update_run(row["id"], status="failed", error=str(error))


@asynccontextmanager
async def lifespan(app):
    if read_only():
        with db() as conn:
            conn.execute('SELECT count(*) FROM runs').fetchone()
        yield
        return
    initialize()
    STOP.clear()
    thread = threading.Thread(target=worker, daemon=True)
    app.state.worker = thread
    thread.start()
    yield
    STOP.set()
    await asyncio.to_thread(thread.join, 3)


app = FastAPI(title="CheckoutCheck", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])


@app.middleware("http")
async def local_boundary(request, call_next):
    if read_only():
        path=request.url.path
        demo_path=path in {'/demo','/demo.mp4'}
        allowed = path in {'/','/index.html','/favicon.svg','/style.css','/app.js','/evidence.js','/perception.js','/videos.js','/docs','/v1/state','/v1/health','/v1/perception','/v1/videos','/v1/cool','/licenses/RetailAction-LICENSE.txt','/licenses/RetailAction-NOTICE.txt','/licenses/RPC-NOTICE.txt'} or bool(re.fullmatch(r'/v1/perception/images/\d+|/v1/videos/[A-Za-z0-9_-]+/(media|analysis|export)|/v1/runs/[a-f0-9]{32}(/export)?|/v1/cool/(stock|cool|comparison|deployment)',path))
        comparison = path == '/v1/perception/comparisons' and request.method == 'POST'
        if not (((allowed or demo_path) and request.method in {'GET','HEAD'}) or comparison):
            return JSONResponse({'detail':'Public review only; operator actions require the private workspace'},status_code=403)
    elif request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.headers.get('host')}"
        if request.headers.get("x-checkoutcheck") != "local" or (origin and origin != expected):
            return JSONResponse({"detail": "Local same-origin request required"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; img-src 'self' data:; frame-ancestors 'none'"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ValueError)
async def validation_error(request, error):
    return JSONResponse({"detail": str(error)}, status_code=422)


async def body(request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 2_000_000:
            raise HTTPException(413, "JSON input exceeds 2 MB")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON field: {key}")
            result[key] = value
        return result
    try:
        value = json.loads(data, object_pairs_hook=unique)
        canonical(value)  # Reject NaN/Infinity before persisting.
        return value
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        raise ValueError("Invalid JSON") from None


@app.get("/v1/state")
def state():
    if read_only():
        return {'assets':[],'cases':[],'suites':[],'runs':[],
                'runtime':{'mode':'aws_public_review','read_only':True,'aws_connection':{'status':'not_applicable'}}}
    with db() as conn:
        collections = {table: [json.loads(r["data"]) for r in conn.execute(f"SELECT data FROM {table}")]
                       for table in ("assets", "cases", "suites")}
        collections["runs"] = [dict(r) for r in conn.execute(
            "SELECT id,suite_id,status,created,updated,progress,error FROM runs "
            "WHERE json_extract(data,'$.task') IS NULL ORDER BY created DESC LIMIT 100")]
    collections["runtime"] = {"mode": os.environ.get('CHECKOUTCHECK_RUNTIME', 'local_single_operator'), 'read_only':False,
        "aws_connection": connection_status(DATA),
        "adapter": "OpenCV 5 · ArUco inventory", "dataset": "Real recordings only; no bundled dataset"}
    return collections


@app.get('/v1/health')
def health():
    try:
        with db() as conn:conn.execute('SELECT 1').fetchone()
        thread=getattr(app.state,'worker',None)
        ready=read_only() or bool(thread and thread.is_alive() and not STOP.is_set())
        return JSONResponse({'status':'ready' if ready else 'degraded','database':'available','worker':'disabled_read_only' if read_only() else 'running' if ready else 'not_running',
                             'access':'public_read_only' if read_only() else 'private_single_operator','execution_environment':os.environ.get('CHECKOUTCHECK_RUNTIME','local_single_operator')},status_code=200 if ready else 503)
    except sqlite3.Error:
        return JSONResponse({'status':'degraded','database':'unavailable'},status_code=503)


@app.get("/v1/perception")
def perception_state():
    available = (DATA / "rpc" / "manifest.json").exists()
    manifest = load_manifest(DATA / "rpc") if available else None
    with db() as conn:
        runs = [dict(r) for r in conn.execute(
            "SELECT id,status,created,updated,progress,error,json_extract(data,'$.model') AS model "
            "FROM runs WHERE json_extract(data,'$.task')='rpc_perception' ORDER BY created DESC LIMIT 100")]
    reference_path = DATA / "rpc" / "references" / "manifest.json"
    references = json.loads(reference_path.read_text()) if reference_path.exists() else None
    models={key:{**value,'available':not value.get('requires_model') or (DATA/'models'/value['requires_model']).is_file()} for key,value in PERCEPTION_MODELS.items()}
    return {"available": available, "manifest": manifest, "runs": runs, "models": models, 'read_only':read_only(),
            "reference_bank": {"images": len(references["images"]), "categories": len(references["categories"]),
                               "hash": references["hash"], "source_split": references["source_split"]} if references else None}


@app.post("/v1/perception/runs", status_code=202)
async def start_perception(request: Request):
    value = await body(request)
    keys(value, ("model", "idempotency_key"))
    validate_identifier(value["model"])
    validate_identifier(value["idempotency_key"])
    require(value["model"] in PERCEPTION_MODELS, "Unknown perception adapter")
    model_file=PERCEPTION_MODELS[value['model']].get('requires_model')
    if model_file and not (DATA/'models'/model_file).is_file():
        raise HTTPException(409,'Install the registered model weights before starting this method')
    if value["model"] == "sift-reference-v1" and not (DATA / "rpc" / "references" / "manifest.json").exists():
        raise HTTPException(409, "Acquire the original training reference bank first")
    if not (DATA / "rpc" / "manifest.json").exists():
        raise HTTPException(409, "RPC data is not installed; acquire the real subset first")
    manifest = load_manifest(DATA / "rpc")
    data = {**value, "task": "rpc_perception", "dataset_hash": manifest["hash"]}
    request_hash = digest(data)
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT id,request_hash FROM runs WHERE request_key=?", (value["idempotency_key"],)).fetchone()
        if old:
            if old["request_hash"] != request_hash:
                raise HTTPException(409, "Idempotency key was used for another request")
            return {"id": old["id"]}
        if conn.execute("SELECT count(*) FROM runs WHERE status NOT IN ('completed','partial','failed','canceled')").fetchone()[0] >= 10:
            raise HTTPException(429, "Queue is full")
        identifier, now = uuid.uuid4().hex, time.time()
        conn.execute("INSERT INTO runs(id,suite_id,status,created,updated,request_key,request_hash,data) VALUES (?,?,?,?,?,?,?,?)",
                     (identifier, manifest["hash"], "queued", now, now, value["idempotency_key"], request_hash, canonical(data)))
    return {"id": identifier}


@app.get("/v1/perception/images/{image_id}")
def perception_image(image_id: int):
    if not (DATA / "rpc" / "manifest.json").exists():
        raise HTTPException(404, "Dataset not installed")
    manifest = load_manifest(DATA / "rpc")
    entry = next((entry for entry in manifest["images"] if entry["id"] == image_id), None)
    if entry is None:
        raise HTTPException(404, "Image not in the registered subset")
    path = DATA / "rpc" / "images" / entry["file_name"]
    if not path.is_file():
        raise HTTPException(404, "Source image is missing")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], "Source image checksum mismatch")
    return FileResponse(path, media_type="image/jpeg")


@app.post("/v1/perception/comparisons")
async def perception_comparison(request: Request):
    value = await body(request)
    keys(value, ("baseline", "candidate"))
    results = [run_record(value[field])["result"] for field in ("baseline", "candidate")]
    require(all(result and result.get("kind") == "rpc_perception" for result in results), "Select two scored perception runs")
    before, after = results
    for field in ("dataset_hash", "evaluator_version", "iou_threshold"):
        require(before["report"][field] == after["report"][field], f"Incompatible comparison: {field}")
    return {"baseline": before["report"], "candidate": after["report"],
            "models": [result["adapter"]["name"] for result in results]}


@app.get("/docs", response_class=HTMLResponse)
def api_documentation():
    content = html.escape((ROOT / "docs" / "contracts.md").read_text())
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>CheckoutCheck API contracts</title><link rel="stylesheet" href="/style.css"></head>'
            '<body><article class="prose"><a href="/">← Workbench</a><h1>API contracts</h1>'
            '<a href="/openapi.json">OpenAPI JSON</a><pre>' + content + '</pre></article></body></html>')


@app.post("/v1/assets", status_code=201)
async def upload(request: Request):
    if request.headers.get("content-type", "").split(';')[0] != "video/mp4":
        raise HTTPException(415, "Upload an MP4 as video/mp4")
    if sum(p.stat().st_size for p in (DATA / "media").glob("*.mp4")) >= 2_000_000_000:
        raise HTTPException(429, "Local media storage limit reached (2 GB)")
    identifier = uuid.uuid4().hex
    path = DATA / "media" / (identifier + ".mp4")
    total, checksum = 0, hashlib.sha256()
    try:
        with path.open("xb") as stream:
            async for chunk in request.stream():
                total += len(chunk)
                if total > 250_000_000:
                    raise HTTPException(413, "Video exceeds 250 MB")
                checksum.update(chunk)
                stream.write(chunk)
        with path.open("rb") as stream:
            require(b"ftyp" in stream.read(64), "Expected an MP4 container")
        metadata = await asyncio.to_thread(process, [sys.executable, "-m", "checkoutcheck.vision", str(path)], 30)
        asset = {"id": identifier, "bytes": total, "sha256": checksum.hexdigest(), **metadata}
        with db() as conn:
            conn.execute("INSERT INTO assets VALUES (?,?)", (identifier, canonical(asset)))
        return asset
    except BaseException:
        path.unlink(missing_ok=True)
        raise


@app.post('/v1/scan-logs/validate')
async def validate_scan_log(request: Request):
    from .scan_logs import validate_log
    value=await body(request)
    keys(value,('content','format','inputs'))
    require(isinstance(value['inputs'],dict),'Inputs must be an object')
    keys(value['inputs'],('catalog','offset_ms','bagging_x','min_observations'))
    return validate_log(value)


@app.post("/v1/cases", status_code=201)
async def add_case(request: Request):
    value = await body(request)
    keys(value, ("asset_id", "title", "annotation", "inputs"))
    require(isinstance(value["annotation"], dict), "Annotation must be an object")
    require(isinstance(value["title"], str) and 0 < len(value["title"]) <= 200, "Case title is required")
    asset = record("assets", value["asset_id"])
    validate_inputs(value["inputs"])
    require(value["inputs"]["events"][-1]["t_ms"] + value["inputs"]["offset_ms"] <= asset["duration_ms"], "Payment is outside video")
    # Per-case validation; pair membership is validated when freezing the full suite.
    annotation = dict(value["annotation"])
    annotation.pop("pair_id", None)
    validate_suite({"schema_version": "1.0", "suite_id": "validation", "input_track": "VP", "evidence_kind": "staged",
        "policy": {"tolerance_ms": 1000, "cooldown_ms": 2000, "abstention_routes_to_review": True}, "cases": [annotation]})
    require(value["annotation"]["rights_valid"], "Confirm permission to use this recording before registration")
    value["id"] = value["annotation"]["id"]
    value["asset_sha256"] = asset["sha256"]
    try:
        with db() as conn:
            conn.execute("INSERT INTO cases VALUES (?,?)", (value["id"], canonical(value)))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Case ID exists; use a new ID for corrected annotations") from None
    return value


@app.post("/v1/suites", status_code=201)
async def freeze(request: Request):
    value = await body(request)
    keys(value, ("name", "case_ids", "policy"))
    require(isinstance(value["name"], str) and 0 < len(value["name"]) <= 200, "Suite name is required")
    require(isinstance(value["case_ids"], list) and 0 < len(value["case_ids"]) <= 70, "Select 1–70 cases")
    entries = [record("cases", i) for i in value["case_ids"]]
    require(all(e["annotation"]["review_status"] in {"reviewed", "adjudicated"} for e in entries), "Review all cases before freezing")
    identifier = uuid.uuid4().hex
    # Bind the evaluator suite ID to media, transaction and preprocessing bytes as well as labels.
    suite = {"schema_version": "1.0", "suite_id": digest(entries), "input_track": "VP", "evidence_kind": "staged",
             "policy": value["policy"], "cases": [e["annotation"] for e in entries]}
    validate_suite(suite)
    frozen = {"id": identifier, "name": value["name"], "suite": suite, "entries": entries, "hash": digest(suite)}
    with db() as conn:
        conn.execute("INSERT INTO suites VALUES (?,?)", (identifier, canonical(frozen)))
    return frozen


@app.post("/v1/runs", status_code=202)
async def start_run(request: Request):
    value = await body(request)
    keys(value, ("suite_id", "idempotency_key"), ("imported",))
    require(isinstance(value["idempotency_key"], str) and 1 <= len(value["idempotency_key"]) <= 200, "Invalid idempotency key")
    frozen = record("suites", value["suite_id"])
    if value.get("imported") is not None:
        score(frozen["suite"], value["imported"])
    request_hash = digest(value)
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT id,request_hash FROM runs WHERE request_key=?", (value["idempotency_key"],)).fetchone()
        if old:
            if old["request_hash"] != request_hash:
                raise HTTPException(409, "Idempotency key was used for another request")
            return {"id": old["id"]}
        if conn.execute("SELECT count(*) FROM runs WHERE status NOT IN ('completed','partial','failed','canceled')").fetchone()[0] >= 10:
            raise HTTPException(429, "Queue is full")
        identifier = uuid.uuid4().hex
        now = time.time()
        conn.execute("INSERT INTO runs(id,suite_id,status,created,updated,request_key,request_hash,data) VALUES (?,?,?,?,?,?,?,?)",
            (identifier, value["suite_id"], "queued", now, now, value["idempotency_key"], request_hash, canonical(value)))
    return {"id": identifier}


@app.get("/v1/runs/{identifier}")
def get_run(identifier: str):
    run=run_record(identifier)
    if read_only() and run['data'].get('task')!='rpc_perception':
        raise HTTPException(404,'Public image run not found')
    return run


@app.post("/v1/runs/{identifier}/cancel")
def cancel(identifier: str):
    run_record(identifier)
    with db() as conn:
        conn.execute("UPDATE runs SET status='canceled',updated=? WHERE id=? AND status NOT IN ('completed','partial','failed','canceled')",
                     (time.time(), identifier))
    return run_record(identifier)


@app.get("/v1/media/{identifier}")
def media(identifier: str):
    record("assets", identifier)
    return FileResponse(DATA / "media" / (identifier + ".mp4"), media_type="video/mp4")


@app.post("/v1/comparisons")
async def comparison(request: Request):
    value = await body(request)
    keys(value, ("baseline", "candidate"))
    before, after = run_record(value["baseline"]), run_record(value["candidate"])
    require(before["suite_id"] == after["suite_id"], "Runs must use the exact same frozen suite")
    require(before["result"] is not None and after["result"] is not None, "Both runs need completed scoring")
    return compare(record("suites", before["suite_id"])["suite"], before["result"]["predictions"], after["result"]["predictions"])


@app.get("/v1/runs/{identifier}/export")
def export(identifier: str):
    run = get_run(identifier)
    require(run["result"] is not None, "Run has no scored results")
    if run["result"].get("kind") == "rpc_perception":
        return Response(json.dumps(run["result"], indent=2, allow_nan=False), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="rpc-perception-{identifier[:8]}.json"'})
    frozen = record("suites", run["suite_id"])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in (("suite", frozen["suite"]), ("predictions", run["result"]["predictions"]),
                            ("report", run["result"]["report"]), ("execution", run["result"]["execution"]),
                            ("input-manifest", frozen)):
            archive.writestr(name + ".json", json.dumps(value, indent=2))
        archive.writestr("README.txt", "Private evaluation bundle. Media is excluded; no publication rights are implied.\n"
            "Install CheckoutCheck 0.1.0, extract this archive, then run:\npython -m checkoutcheck verify /path/to/extracted-bundle\n"
            "This verifies deterministic scoring. Re-running vision additionally requires the hash-matched original media.\n")
    return Response(buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="checkoutcheck-{identifier[:8]}.zip"'})


def registered_video(identifier):
    from .retail_video import load_manifest as load_videos
    if not (DATA/'retailaction/manifest.json').is_file():
        raise HTTPException(404,'Real video dataset is not installed')
    manifest=load_videos(DATA/'retailaction')
    entry=next((v for v in manifest['videos'] if v['id']==identifier),None)
    if entry is None:raise HTTPException(404,'Video is not in the registered dataset')
    return manifest,entry


@app.get('/v1/videos')
def video_state():
    from .retail_video import load_manifest as load_videos
    path=DATA/'retailaction'
    if not (path/'manifest.json').is_file():return {'available':False,'videos':[]}
    manifest=load_videos(path)
    return {'available':True,'manifest':manifest,'read_only':read_only(),'videos':[{**v,'analyzed':(path/'analysis'/f"{v['id']}.json").is_file()} for v in manifest['videos']]}


@app.get('/v1/videos/{identifier}/media')
def original_video(identifier: str):
    _,entry=registered_video(identifier)
    path=DATA/'retailaction'/entry['path']
    require(hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256'],'Original video checksum mismatch')
    return FileResponse(path,media_type='video/mp4')


@app.get('/v1/videos/{identifier}/analysis')
def video_analysis(identifier: str):
    manifest,entry=registered_video(identifier)
    path=DATA/'retailaction/analysis'/f'{identifier}.json'
    if not path.is_file():raise HTTPException(404,'Run the video diagnostics first')
    result=json.loads(path.read_text())
    require(result['source_sha256']==entry['sha256'] and result['dataset_hash']==manifest['hash'],'Analysis belongs to another video source')
    return result


@app.post('/v1/videos/{identifier}/analyze')
async def run_video_analysis(identifier: str):
    registered_video(identifier)
    return await asyncio.to_thread(process,[sys.executable,'-m','checkoutcheck.retail_video','--directory',str(DATA/'retailaction'),'--analyze',identifier],30)


@app.get('/v1/videos/{identifier}/export')
def export_video_analysis(identifier: str):
    result=video_analysis(identifier)
    return Response(json.dumps(result,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="{identifier}-analysis.json"'})


@app.get('/v1/cool')
def cool_evidence():
    root=DATA/'outputs/cool'
    if not all((root/(name+'.json')).is_file() for name in ('stock','cool','comparison','deployment')):
        return {'available':False}
    return {'available':True,'comparison':json.loads((root/'comparison.json').read_text()),
            'deployment':json.loads((root/'deployment.json').read_text())}


@app.get('/v1/cool/{name}')
def cool_export(name: str):
    if name not in ('stock','cool','comparison','deployment'):
        raise HTTPException(404,'Benchmark artifact not found')
    path=DATA/'outputs/cool'/(name+'.json')
    if not path.is_file():raise HTTPException(404,'Benchmark artifact not installed')
    return FileResponse(path,media_type='application/json',filename=name+'.json')


@app.get('/licenses/{name}')
def source_license(name: str):
    if name not in ('RetailAction-LICENSE.txt','RetailAction-NOTICE.txt','RPC-NOTICE.txt'):
        raise HTTPException(404,'License not found')
    return FileResponse(ROOT/'docs/licenses'/name,media_type='text/plain')


@app.get('/demo', response_class=HTMLResponse)
def product_demo():
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>CheckoutCheck product demo</title><link rel="stylesheet" href="/style.css"></head><body><article class="prose"><h1>CheckoutCheck product demo</h1><p>Problem, working application, agent decisions, AWS architecture and measured COOL results. 4 minutes 5 seconds. Indian English male computer narration.</p><video controls preload="metadata" width="960" src="/demo.mp4"></video><p><a href="/">Open the application</a> · <a href="https://github.com/ankitlade12/checkoutcheck">Source and technical report</a></p><h2>Source credits and licenses</h2><p>RPC photographs: Wei et al., <a href="https://rpc-dataset.github.io/">RPC dataset</a>, <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a>. Application overlays added. <a href="/licenses/RPC-NOTICE.txt">RPC notice</a>.</p><p>RetailAction footage: Standard Cognition, publisher-anonymized originals, displayed within the application. <a href="/licenses/RetailAction-LICENSE.txt">Standard.AI Dataset License (copy)</a> · <a href="/licenses/RetailAction-NOTICE.txt">Notice</a>. Copyright © Standard Corp. All Rights Reserved.</p><p>Original presentation and narration: CheckoutCheck, CC BY-NC-SA 4.0; third-party footage retains its separate license. Software code is MIT licensed.</p></article></body></html>'''


@app.get('/demo.mp4')
def product_demo_video():
    path=DATA/'outputs/checkoutcheck-product-demo.mp4'
    if not path.is_file():raise HTTPException(404,'Product demo not installed')
    return FileResponse(path,media_type='video/mp4')


app.mount("/", StaticFiles(directory=ROOT / "apps" / "web", html=True), name="web")
