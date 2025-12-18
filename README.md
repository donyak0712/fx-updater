# fx-updater

Flask API service that updates USD->UAH exchange rates in Google Sheets.
Used as a data source for Power BI currency conversion.

## API

**GET** `/update`

Query params:
- `update_from` (YYYY-MM-DD) - start date (default: today)
- `update_to` (YYYY-MM-DD) - end date (default: today)
- `token` - simple auth token

Example:
`http://<HOST>/update?update_from=2019-03-01&update_to=2019-03-06&token=<TOKEN>`

Response:
JSON with status, rows written, and errors (if any).

## Setup (local)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
flask --app app run
