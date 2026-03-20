# KUK2RD Knowledge Extraction System

Converts technical PDF documents into structured intelligent data via LLM extraction and persists them as `CORE DATA`.

## Project Structure
- `src/`: Core backend, parser, services, and CLI/API points.
- `dashboard/`: Streamlit interactive dashboard.
- `data/`: Local storage for raw PDFs and processed files (ignored in git).
- `tests/`: Automated unit and integration tests.

## Getting Started

### Prerequisites
- Docker and Docker Compose
- OpenAI API Key

### Setup
1. Create a `.env` file referencing `.env.example` (or just edit the `.env` placeholder):
```bash
OPENAI_API_KEY=sk-....
```
2. Build and run via Docker Compose:
```bash
docker-compose up --build
```
3. Open the Streamlit dashboard at http://localhost:8501
