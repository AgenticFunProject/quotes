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

## Test

```bash
pytest
```

## Project Structure

```
quotes/
├── app/
│   ├── __init__.py    # FastAPI app instance
│   └── main.py        # Entry point
├── tests/
│   ├── __init__.py
│   └── test_health.py # Smoke tests
├── pyproject.toml     # Project metadata and dependencies
└── README.md
```
