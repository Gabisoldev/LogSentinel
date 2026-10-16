from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from datetime import datetime
import io, csv

from database import init_db, get_db
from parser import analyze_file

app = FastAPI(title="LogSentinel")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

init_db()

# ---------- DASHBOARD ----------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

# ---------- UPLOAD ----------
@app.post("/api/upload")
async def upload_log(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".log", ".txt")):
        raise HTTPException(400, "Apenas arquivos .log ou .txt são aceitos.")

    raw = await file.read()
    try:
        content = raw.decode("utf-8", errors="ignore")
    except Exception:
        raise HTTPException(400, "Não foi possível ler o arquivo.")

    result = analyze_file(content)

    with get_db() as db:
        cur = db.execute(
            """INSERT INTO files (filename, uploaded_at, total_lines,
               error_count, warning_count, critical_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                file.filename,
                datetime.utcnow().isoformat(),
                result["total_lines"],
                result["counts"]["ERROR"],
                result["counts"]["WARNING"],
                result["counts"]["CRITICAL"],
            ),
        )
        file_id = cur.lastrowid

        db.executemany(
            """INSERT INTO events (file_id, timestamp, level, message, raw_line, signature)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (file_id, e["timestamp"], e["level"], e["message"], e["raw"], e["signature"])
                for e in result["events"]
            ],
        )

    return {
        "file_id": file_id,
        "filename": file.filename,
        "summary": result["counts"],
        "total_lines": result["total_lines"],
        "total_events": result["total_events"],
        "top_groups": result["top_groups"],
    }

# ---------- LISTAR ARQUIVOS ----------
@app.get("/api/files")
def list_files():
    with get_db() as db:
        rows = db.execute("SELECT * FROM files ORDER BY uploaded_at DESC").fetchall()
        return [dict(r) for r in rows]

# ---------- EVENTOS COM FILTRO ----------
@app.get("/api/events")
def list_events(
    file_id: int | None = None,
    level: str | None = None,
    search: str | None = None,
    limit: int = Query(500, le=5000),
):
    q = "SELECT * FROM events WHERE 1=1"
    params = []
    if file_id:
        q += " AND file_id = ?"; params.append(file_id)
    if level and level != "ALL":
        q += " AND level = ?"; params.append(level)
    if search:
        q += " AND (message LIKE ? OR raw_line LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    q += " ORDER BY id DESC LIMIT ?"; params.append(limit)

    with get_db() as db:
        rows = db.execute(q, params).fetchall()
        return [dict(r) for r in rows]

# ---------- ESTATÍSTICAS ----------
@app.get("/api/stats")
def stats(file_id: int | None = None):
    with get_db() as db:
        where = "WHERE file_id = ?" if file_id else ""
        params = [file_id] if file_id else []

        by_level = db.execute(
            f"SELECT level, COUNT(*) as count FROM events {where} GROUP BY level",
            params,
        ).fetchall()

        top_sig = db.execute(
            f"""SELECT signature, level, message, COUNT(*) as count
                FROM events {where}
                GROUP BY signature
                ORDER BY count DESC LIMIT 10""",
            params,
        ).fetchall()

        # Timeline por hora
        timeline = db.execute(
            f"""SELECT substr(timestamp, 1, 13) as hour, COUNT(*) as count
                FROM events {where}
                GROUP BY hour ORDER BY hour""",
            params,
        ).fetchall()

        totals = db.execute(
            f"SELECT COUNT(*) as total FROM events {where}", params
        ).fetchone()

    return {
        "by_level": [dict(r) for r in by_level],
        "top_signatures": [dict(r) for r in top_sig],
        "timeline": [dict(r) for r in timeline],
        "total_events": totals["total"],
    }

# ---------- EXPORTAR CSV ----------
@app.get("/api/export")
def export_csv(
    file_id: int | None = None,
    level: str | None = None,
    search: str | None = None,
):
    q = "SELECT id, file_id, timestamp, level, message, signature FROM events WHERE 1=1"
    params = []
    if file_id:
        q += " AND file_id = ?"; params.append(file_id)
    if level and level != "ALL":
        q += " AND level = ?"; params.append(level)
    if search:
        q += " AND message LIKE ?"; params.append(f"%{search}%")

    with get_db() as db:
        rows = db.execute(q, params).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "file_id", "timestamp", "level", "message", "signature"])
    for r in rows:
        writer.writerow([r["id"], r["file_id"], r["timestamp"], r["level"], r["message"], r["signature"]])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=logsentinel_export.csv"},
    )

# ---------- DELETE ----------
@app.delete("/api/files/{file_id}")
def delete_file(file_id: int):
    with get_db() as db:
        db.execute("DELETE FROM events WHERE file_id = ?", (file_id,))
        db.execute("DELETE FROM files WHERE id = ?", (file_id,))
    return {"ok": True}