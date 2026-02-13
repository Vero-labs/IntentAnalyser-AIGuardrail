"""
Intent Analyzer Sidecar v4.0
Tri-Axis Scope Enforcement Pipeline.
Three orthogonal classifiers: Action (verbs), Domain (knowledge spaces), Risk Signals (anomalies).
Detection produces structured facts. Enforcement applies rules to facts.
"""

from app.main import app
import logging
import os

# Ensure we are using the production-grade v3 app
# The actual logic is now maintained in the app/ directory.

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)
