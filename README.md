# Intent Analyzer Sidecar

This is a standalone repository for the Intent Analyzer service, part of the Agent Guardrail project.

## Overview

The Intent Analyzer uses a BART-MNLI model to classify user and conversation intents into a hierarchical taxonomy. This helps in detecting risky intents like exploitation, system control, or unauthorized file access.

## Getting Started

### Prerequisites

- Python 3.9+
- Docker (optional)

### Running with Docker

```bash
docker build -t intent-analyzer .
docker run -p 8001:8001 intent-analyzer
```

### Running Locally

```bash
pip install -r requirements.txt
python main.py
```

## API Endpoints

- `POST /intent`: Analyze text or messages.
- `GET /health`: Health check.

## Testing

Run the test suite using:
```bash
./tests/run_tests.sh
```
