import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SPREADSHEET_ID = "1CnTUu6kBJwEHM-MJ1u0ZiyVwhOmdoYhCbxndz1x2OS4"

creds = Credentials.from_service_account_file(
    "service_account.json",
    scopes=SCOPES
)

gc = gspread.authorize(creds)
sh = gc.open_by_key(SPREADSHEET_ID)

ws = sh.worksheet("rates")

ws.update(range_name="A1:E1", values=[["date", "ccy", "rate_to_uah", "source", "updated_at"]])

print("✅ Google Sheets connected")
