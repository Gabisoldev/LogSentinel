import re
import hashlib
from datetime import datetime
from collections import Counter

# Padrões comuns de log: [2024-01-15 10:23:45] ERROR: mensagem

PATTERNS = [
    re.compile(
        r"^\[?(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\]?"
        r"\s*[-:]?\s*(?P<lvl>DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)"
        r"\b[:\s-]*(?P<msg>.*)$",
        re.I,
    ),
    re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}(?:,\d+)?)"
        r"\s+(?P<lvl>DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)"
        r"\s+(?P<msg>.*)$",
        re.I,
    ),
    re.compile(
        r"^(?P<lvl>DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)"
        r"\b[:\s-]+(?P<msg>.*)$",
        re.I,
    ),
]


LEVEL_MAP = {
    "WARN": "WARNING",
    "FATAL": "CRITICAL",
}

# Palavras-chave que elevam severidade
CRITICAL_KEYWORDS = [
    "out of memory", "oom", "segfault", "panic", "fatal",
    "connection refused", "timeout", "deadlock", "corrupt",
    "unauthorized", "denied", "crash",
]

def normalize_level(lvl: str) -> str:
    lvl = lvl.upper()
    return LEVEL_MAP.get(lvl, lvl)

def make_signature(level: str, message: str) -> str:
    """Agrupa eventos por padrão: remove números, IDs e valores voláteis."""
    normalized = re.sub(r"\d+", "N", message.lower())
    normalized = re.sub(r"[0-9a-f]{8,}", "HEX", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.md5(f"{level}:{normalized}".encode()).hexdigest()[:16]

def parse_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None

    for pattern in PATTERNS:
        m = pattern.match(line)
        if m:
            groups = m.groupdict()
            level = normalize_level(groups["lvl"])
            message = (groups.get("msg") or "").strip()

            # Promove para CRITICAL se contém palavra-chave crítica
            lower_msg = message.lower()
            if level == "ERROR" and any(k in lower_msg for k in CRITICAL_KEYWORDS):
                level = "CRITICAL"

            return {
                "timestamp": groups.get("ts") or datetime.utcnow().isoformat(),
                "level": level,
                "message": message or line,
                "signature": make_signature(level, message or line),
                "raw": line,
            }

    # Fallback: heurística — se contém "error", "exception", "fail"
    lower = line.lower()
    if any(k in lower for k in ["error", "exception", "failed", "fail"]):
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "ERROR",
            "message": line,
            "signature": make_signature("ERROR", line),
            "raw": line,
        }
    return None

def analyze_file(content: str) -> dict:
    """Analisa conteúdo bruto e retorna eventos + estatísticas."""
    events = []
    for line in content.splitlines():
        parsed = parse_line(line)
        if parsed:
            events.append(parsed)

    levels = Counter(e["level"] for e in events)
    signatures = Counter(e["signature"] for e in events)

    # Top grupos de eventos suspeitos
    top_groups = []
    for sig, count in signatures.most_common(10):
        sample = next(e for e in events if e["signature"] == sig)
        top_groups.append({
            "signature": sig,
            "count": count,
            "level": sample["level"],
            "sample_message": sample["message"][:200],
        })

    return {
        "events": events,
        "total_lines": len(content.splitlines()),
        "total_events": len(events),
        "counts": {
            "ERROR": levels.get("ERROR", 0),
            "WARNING": levels.get("WARNING", 0),
            "CRITICAL": levels.get("CRITICAL", 0),
            "INFO": levels.get("INFO", 0),
        },
        "top_groups": top_groups,
    }