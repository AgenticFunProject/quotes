# Quotes

A quotes API built with Python, FastAPI, and SQLite.

## Requirements

- Python 3.11+

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
uvicorn app.main:app --reload
```

The API will be available at <http://localhost:8000>.

Interactive docs: <http://localhost:8000/docs>

The service uses SQLite by default, creates its tables on startup in `db.sqlite`,
and seeds reference rates and surcharge rules used by `POST /quotes`.

## Example

```bash
curl -X POST http://localhost:8000/quotes \
  -H 'Content-Type: application/json' \
  -d '{
    "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
    "equipment": [{"type": "20FT", "quantity": 1}],
    "cargoWeightKg": 18000
  }'
```

## Test

```bash
pytest
```
