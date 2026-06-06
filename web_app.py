from __future__ import annotations

import csv
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
RUNS_DIR = ROOT / "web_runs"
ALLOWED_FILES = {
    "trades.csv",
    "trades.xlsx",
    "stocks.csv",
    "stocks.xlsx",
    "agent_day_record.csv",
    "agent_day_record.xlsx",
    "agent_session_record.csv",
    "agent_session_record.xlsx",
    "trace.jsonl",
}


@dataclass
class RunJob:
    id: str
    command: List[str]
    output_dir: Path
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    process: Optional[subprocess.Popen] = None

    def public(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds(),
            "returncode": self.returncode,
            "command": self.command,
            "output_dir": str(self.output_dir),
            "stdout_tail": self.stdout[-4000:],
            "stderr_tail": self.stderr[-4000:],
            "error": self.error,
            "files": list_output_files(self.output_dir),
            "summary": summarize_run(self.output_dir),
        }

    def duration_seconds(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.finished_at or time.time()
        return round(end - self.started_at, 2)


JOBS: Dict[str, RunJob] = {}
JOBS_LOCK = threading.Lock()


def main() -> None:
    host = os.getenv("STOCKBRO_HOST", "127.0.0.1")
    port = int(os.getenv("STOCKBRO_PORT", "8765"))
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), StockBroHandler)
    print(f"StockBro console: http://{host}:{port}")
    server.serve_forever()


class StockBroHandler(BaseHTTPRequestHandler):
    server_version = "StockBroWeb/1.0"

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        target_name = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        target = (FRONTEND_DIR / target_name).resolve()
        if target.exists() and target.is_file():
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(target.stat().st_size))
            self.end_headers()
            return
        self._send_error(404, "Not found")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._serve_static("index.html")
        elif path.startswith("/api/runs/") and path.endswith("/trace"):
            self._handle_trace(path, parsed.query)
        elif path.startswith("/api/runs/") and path.endswith("/file"):
            self._handle_file(path, parsed.query)
        elif path == "/api/runs":
            self._send_json({"runs": list_jobs()})
        elif path.startswith("/api/runs/"):
            self._handle_run_detail(path)
        elif path.startswith("/api/defaults"):
            self._send_json(default_payload())
        else:
            self._serve_static(path.lstrip("/"))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/runs":
            self._handle_create_run()
        else:
            self._send_error(404, "Unknown endpoint")

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/runs/"):
            job_id = parsed.path.split("/")[3]
            self._handle_cancel_run(job_id)
        else:
            self._send_error(404, "Unknown endpoint")

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _handle_create_run(self) -> None:
        try:
            body = self._read_json()
            command, output_dir = build_command(body)
            job_id = uuid.uuid4().hex[:12]
            output_dir = output_dir / job_id
            command = replace_output_dir(command, output_dir)
            job = RunJob(id=job_id, command=command, output_dir=output_dir)
            with JOBS_LOCK:
                JOBS[job_id] = job
            thread = threading.Thread(target=run_job, args=(job,), daemon=True)
            thread.start()
            self._send_json(job.public(), status=201)
        except ValueError as exc:
            self._send_error(400, str(exc))

    def _handle_cancel_run(self, job_id: str) -> None:
        job = get_job(job_id)
        if job is None:
            self._send_error(404, "Run not found")
            return
        if job.status == "running" and job.process is not None:
            job.status = "cancelled"
            job.process.terminate()
        self._send_json(job.public())

    def _handle_run_detail(self, path: str) -> None:
        job_id = path.split("/")[3]
        job = get_job(job_id)
        if job is None:
            self._send_error(404, "Run not found")
            return
        self._send_json(job.public())

    def _handle_trace(self, path: str, query: str) -> None:
        job_id = path.split("/")[3]
        job = get_job(job_id)
        if job is None:
            self._send_error(404, "Run not found")
            return
        params = parse_qs(query)
        limit = safe_int(params.get("limit", ["100"])[0], 100, 1, 1000)
        event_type = params.get("event_type", [None])[0]
        events = read_trace(job.output_dir / "trace.jsonl", limit=limit, event_type=event_type)
        self._send_json({"events": events})

    def _handle_file(self, path: str, query: str) -> None:
        job_id = path.split("/")[3]
        job = get_job(job_id)
        if job is None:
            self._send_error(404, "Run not found")
            return
        params = parse_qs(query)
        filename = params.get("name", [""])[0]
        filename = Path(unquote(filename)).name
        if filename not in ALLOWED_FILES:
            self._send_error(400, "File is not downloadable")
            return
        file_path = job.output_dir / filename
        if not file_path.exists():
            self._send_error(404, "File not found")
            return
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
        self.send_header("Content-Length", str(file_path.stat().st_size))
        self.end_headers()
        with file_path.open("rb") as file_obj:
            self.wfile.write(file_obj.read())

    def _serve_static(self, relative_path: str) -> None:
        relative_path = "index.html" if not relative_path else relative_path
        target = (FRONTEND_DIR / relative_path).resolve()
        if FRONTEND_DIR.resolve() not in target.parents and target != FRONTEND_DIR.resolve():
            self._send_error(403, "Forbidden")
            return
        if not target.exists() or not target.is_file():
            self._send_error(404, "Not found")
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()
        with target.open("rb") as file_obj:
            self.wfile.write(file_obj.read())

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON") from exc

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)


def build_command(body: dict) -> tuple[List[str], Path]:
    model = clean_string(body.get("model"), "mock")
    log_level = clean_string(body.get("log_level"), "WARNING").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ValueError("log_level must be DEBUG, INFO, WARNING, or ERROR")

    agents = safe_int(body.get("agents"), 2, 1, 200)
    days = safe_int(body.get("days"), 1, 1, 264)
    sessions = safe_int(body.get("sessions"), 1, 1, 12)
    seed = optional_int(body.get("seed"))
    fee_rate = safe_float(body.get("fee_rate"), 0.001, 0.0, 0.2)
    slippage_rate = safe_float(body.get("slippage_rate"), 0.0005, 0.0, 0.2)
    daily_limit_pct = safe_float(body.get("daily_limit_pct"), 0.10, 0.0, 1.0)
    max_fill = safe_int(body.get("max_fill_per_level"), 10000, 1, 1_000_000)
    ttl = safe_int(body.get("order_ttl_sessions"), 3, 1, 100)
    output_root = RUNS_DIR

    command = [
        sys.executable,
        str(ROOT / "main.py"),
        "--model",
        model,
        "--agents",
        str(agents),
        "--days",
        str(days),
        "--sessions",
        str(sessions),
        "--output-dir",
        "__OUTPUT_DIR__",
        "--log-level",
        log_level,
        "--fee-rate",
        str(fee_rate),
        "--slippage-rate",
        str(slippage_rate),
        "--daily-limit-pct",
        str(daily_limit_pct),
        "--max-fill-per-level",
        str(max_fill),
        "--order-ttl-sessions",
        str(ttl),
    ]
    if seed is not None:
        command.extend(["--seed", str(seed)])
    return command, output_root


def replace_output_dir(command: List[str], output_dir: Path) -> List[str]:
    return [str(output_dir) if value == "__OUTPUT_DIR__" else value for value in command]


def run_job(job: RunJob) -> None:
    job.status = "running"
    job.started_at = time.time()
    job.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.Popen(
            job.command,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        job.process = process
        stdout, stderr = process.communicate()
        job.stdout = stdout or ""
        job.stderr = stderr or ""
        job.returncode = process.returncode
        if job.status == "cancelled":
            return
        job.status = "succeeded" if process.returncode == 0 else "failed"
    except Exception as exc:
        job.error = str(exc)
        job.status = "failed"
    finally:
        job.finished_at = time.time()
        job.process = None


def list_jobs() -> list[dict]:
    with JOBS_LOCK:
        jobs = list(JOBS.values())
    jobs.sort(key=lambda item: item.created_at, reverse=True)
    return [job.public() for job in jobs]


def get_job(job_id: str) -> Optional[RunJob]:
    with JOBS_LOCK:
        return JOBS.get(job_id)


def list_output_files(output_dir: Path) -> list[dict]:
    if not output_dir.exists():
        return []
    files = []
    for file_path in sorted(output_dir.iterdir()):
        if file_path.is_file() and file_path.name in ALLOWED_FILES:
            files.append({
                "name": file_path.name,
                "size": file_path.stat().st_size,
            })
    return files


def summarize_run(output_dir: Path) -> dict:
    return {
        "trades": csv_count(output_dir / "trades.csv"),
        "stock_rows": csv_count(output_dir / "stocks.csv"),
        "agent_days": csv_count(output_dir / "agent_day_record.csv"),
        "agent_sessions": csv_count(output_dir / "agent_session_record.csv"),
        "trace_events": jsonl_count(output_dir / "trace.jsonl"),
        "last_prices": last_csv_row(output_dir / "stocks.csv"),
    }


def csv_count(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = sum(1 for _ in csv.reader(csv_file))
    return max(0, rows - 1)


def jsonl_count(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as jsonl_file:
        return sum(1 for _ in jsonl_file)


def last_csv_row(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    last_row = None
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            last_row = row
    return last_row


def read_trace(path: Path, *, limit: int, event_type: Optional[str]) -> list[dict]:
    if not path.exists():
        return []
    events = []
    with path.open("r", encoding="utf-8") as jsonl_file:
        for line in jsonl_file:
            if not line.strip():
                continue
            event = json.loads(line)
            if event_type and event.get("event_type") != event_type:
                continue
            events.append(event)
    return events[-limit:]


def default_payload() -> dict:
    return {
        "model": "mock",
        "agents": 2,
        "days": 1,
        "sessions": 1,
        "seed": 42,
        "log_level": "WARNING",
        "fee_rate": 0.001,
        "slippage_rate": 0.0005,
        "daily_limit_pct": 0.10,
        "max_fill_per_level": 10000,
        "order_ttl_sessions": 3,
    }


def clean_string(value: Any, default: str) -> str:
    if value is None:
        return default
    value = str(value).strip()
    return value or default


def optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    return int(value)


def safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def safe_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


if __name__ == "__main__":
    main()
