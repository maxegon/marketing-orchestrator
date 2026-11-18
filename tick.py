#!/usr/bin/env python3
"""Lancia all'ora esatta i workflow marketing delle 4 app (solo libreria standard).

cron-job.org chiama ogni 5 minuti il workflow `tick.yml` di questo repo. tick prende l'ora di creazione della run
(arrotondata ai 5 minuti più vicini, ora di Roma), cerca in `orari.json` i giri di quell'ora e per ognuno chiama
POST /repos/<owner>/<repo>/actions/workflows/<workflow>/dispatches.

Perché: i cron di GitHub sui repo privati arrivavano con 6-9 ore di ritardo (12-18/11/2026). Un repo pubblico non
consuma minuti di Actions, quindi un giro ogni 5 minuti qui è gratis.

Uso:
  python3 tick.py --valida                      controlla orari.json
  python3 tick.py --dry-run                     cosa lancerebbe adesso
  python3 tick.py --dry-run --ora 20:00         cosa lancerebbe alle 20:00
  python3 tick.py                               lancia davvero (serve ORCH_TOKEN)
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zoneinfo

ROME = zoneinfo.ZoneInfo("Europe/Rome")
HERE = os.path.dirname(os.path.abspath(__file__))
ORA_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def load(path=None):
    with open(path or os.path.join(HERE, "orari.json"), encoding="utf-8") as f:
        return json.load(f)


def validate(cfg):
    """Errori in orari.json (lista vuota = ok)."""
    errs, seen = [], set()
    if not cfg.get("owner"):
        errs.append("manca owner")
    for i, j in enumerate(cfg.get("jobs", [])):
        tag = f"jobs[{i}]"
        m = ORA_RE.match(str(j.get("ora", "")))
        if not m:
            errs.append(f"{tag}: ora non valida {j.get('ora')!r} (HH:MM)")
        elif int(m.group(2)) % 5:
            errs.append(f"{tag}: ora {j['ora']} non multipla di 5 minuti (tick gira ogni 5)")
        if not j.get("repo") or not str(j.get("workflow", "")).endswith((".yml", ".yaml")):
            errs.append(f"{tag}: servono repo e workflow (.yml)")
        inp = j.get("inputs", {})
        if not isinstance(inp, dict) or not all(isinstance(v, str) for v in inp.values()):
            errs.append(f"{tag}: inputs deve essere un oggetto di stringhe")
        key = (j.get("ora"), str(j.get("repo")).lower(), j.get("workflow"), json.dumps(inp, sort_keys=True))
        if key in seen:
            errs.append(f"{tag}: doppione di un altro giro")
        seen.add(key)
    return errs


def slot(t):
    """Ora di Roma arrotondata ai 5 minuti più vicini, "HH:MM" (tollera cron-job.org in anticipo o in ritardo di 2 min)."""
    t = t.astimezone(ROME)
    m = int(round((t.hour * 60 + t.minute + t.second / 60) / 5.0)) * 5 % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def due(cfg, hhmm):
    return [j for j in cfg["jobs"] if j["ora"] == hhmm]


def http_dispatch(url, body, token):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
        "User-Agent": "marketing-orchestrator"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:300]


def dispatch(owner, j, token, http=http_dispatch, sleep=time.sleep):
    """True se GitHub ha accettato il lancio (204). Riprova 3 volte su errori di rete e 5xx."""
    url = f"https://api.github.com/repos/{owner}/{j['repo']}/actions/workflows/{j['workflow']}/dispatches"
    body = {"ref": j.get("ref", "main")}
    if j.get("inputs"):
        body["inputs"] = j["inputs"]
    for tentativo in range(3):
        try:
            code, msg = http(url, body, token)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            code, msg = 0, str(e)
        if code == 204:
            return True
        print(f"   tentativo {tentativo + 1}: HTTP {code} {msg}")
        if code and code < 500:
            break  # 401/403/404/422: riprovare non serve
        sleep(5)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ora", help="HH:MM di Roma da usare al posto dell'ora della run")
    ap.add_argument("--adesso", help="istante ISO (default: RUN_CREATED_AT o adesso)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--valida", action="store_true")
    a = ap.parse_args(argv)
    cfg = load()
    errs = validate(cfg)
    if errs or a.valida:
        print("\n".join(errs) or f"orari.json ok: {len(cfg['jobs'])} giri al giorno")
        return 1 if errs else 0
    if a.ora:
        if not ORA_RE.match(a.ora):
            print(f"--ora non valida: {a.ora}")
            return 1
        hhmm = a.ora
    else:
        iso = a.adesso or os.environ.get("RUN_CREATED_AT") or dt.datetime.now(dt.timezone.utc).isoformat()
        hhmm = slot(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")))
    giri = due(cfg, hhmm)
    print(f"Slot {hhmm} (Roma): {len(giri)} giri")
    if not giri:
        return 0
    token = os.environ.get("ORCH_TOKEN", "").strip()
    if not a.dry_run and not token:
        print("::error::ORCH_TOKEN mancante: non lancio nulla")
        return 1
    falliti = 0
    for j in giri:
        desc = f"{j['repo']}/{j['workflow']}" + (f" {j['inputs']}" if j.get("inputs") else "")
        if a.dry_run:
            print(f" [dry-run] {desc}")
        elif dispatch(cfg["owner"], j, token):
            print(f" ok  {desc}")
        else:
            print(f"::error::lancio fallito: {desc}")
            falliti += 1
    return 1 if falliti else 0


if __name__ == "__main__":
    sys.exit(main())
