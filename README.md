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

## License

This project is dual-licensed:

- **GNU AGPLv3 (Free/Open Source):** For free use, personal projects, education, and open-source development. Under this license, any modifications or network services (SaaS) built upon this code must also be open-sourced under the AGPLv3. See the `LICENSE` file for details.
  
- **Commercial License (Proprietary/Closed Source):** For businesses and organizations that wish to use, integrate, or modify this software in commercial, closed-source products without open-sourcing their own code. If you require a commercial license, please contact the author/company.
