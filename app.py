import os
import datetime as dt
from flask import Flask, request, jsonify
import requests
import time
from requests.exceptions import RequestException, HTTPError, Timeout

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"

app = Flask(__name__)

def parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()

def daterange(d1: dt.date, d2: dt.date):
    cur = d1
    while cur <= d2:
        yield cur
        cur += dt.timedelta(days=1)

def require_auth(req) -> bool:
    expected = os.getenv("API_TOKEN", "")
    if not expected:
        return True  # локальная отладка
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.replace("Bearer ", "", 1).strip()
        return token == expected
    return req.args.get("token", "") == expected

def fetch_usd_uah_rate(day: dt.date, retries: int = 4, backoff: float = 0.8) -> float:
    params = {"valcode": "USD", "date": day.strftime("%Y%m%d"), "json": ""}

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(NBU_URL, params=params, timeout=20)

            # если НБУ "тупит" — повторяем
            if r.status_code in (502, 503, 504):
                raise HTTPError(f"{r.status_code} from NBU", response=r)

            r.raise_for_status()
            data = r.json()
            if not data:
                raise ValueError(f"No NBU USD rate for {day.isoformat()}")
            return float(data[0]["rate"])

        except (Timeout, HTTPError, RequestException, ValueError) as e:
            last_err = e
            # экспоненциальная пауза
            time.sleep(backoff * attempt)

    raise last_err

def open_rates_worksheet():
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    spreadsheet_id = os.environ["SPREADSHEET_ID"]
    worksheet_name = os.getenv("WORKSHEET_NAME", "rates")

    creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    return sh.worksheet(worksheet_name)

def load_existing_keys(ws):
    values = ws.get_all_values()
    keys = {}
    for i, row in enumerate(values[1:], start=2):
        if len(row) >= 2 and row[0] and row[1]:
            keys[(row[0], row[1])] = i
    return keys

def upsert_rows(ws, rows):
    existing = load_existing_keys(ws)
    to_append = []

    for row in rows:
        key = (row[0], row[1])  # (date, ccy)
        if key in existing:
            r = existing[key]
            ws.update(range_name=f"A{r}:E{r}", values=[row])
        else:
            to_append.append(row)

    if to_append:
        ws.append_rows(to_append, value_input_option="USER_ENTERED")

@app.get("/health")
def health():
    return jsonify({"ok": True})

@app.get("/update")
def update_rates():
    if not require_auth(request):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    today = dt.date.today()
    update_from = request.args.get("update_from", today.isoformat())
    update_to = request.args.get("update_to", today.isoformat())

    d_from = parse_date(update_from)
    d_to = parse_date(update_to)
    if d_from > d_to:
        return jsonify({"ok": False, "error": "update_from must be <= update_to"}), 400

    # защитимся от слишком больших диапазонов (чтобы не словить таймаут)
    if (d_to - d_from).days > 370:
        return jsonify({"ok": False, "error": "Max range is 370 days"}), 400

    ws = open_rates_worksheet()
    updated_at = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    rows = []
    errors = []

    for day in daterange(d_from, d_to):
        try:
            rate = fetch_usd_uah_rate(day)
            rows.append([day.isoformat(), "USD", str(rate), "NBU", updated_at])
        except Exception as e:
            errors.append({"date": day.isoformat(), "error": str(e)})

    if rows:
        upsert_rows(ws, rows)

    status_code = 200 if len(errors) == 0 else 207  # 207 = Multi-Status (частично успешно)
    return jsonify({
        "ok": len(errors) == 0,
        "rows_written": len(rows),
        "errors_count": len(errors),
        "errors": errors[:20],
        "from": d_from.isoformat(),
        "to": d_to.isoformat()
    }), status_code
