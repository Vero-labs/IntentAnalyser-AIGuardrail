import logging
import math
import os
import time
from collections.abc import Sequence
from typing import Any, Optional, Union

import httpx

logger = logging.getLogger(__name__)

Number = Union[int, float]
Vector = list[float]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_number_list(values: Any) -> bool:
    return isinstance(values, list) and bool(values) and all(_is_number(v) for v in values)


def _mean_pool(vectors: list[list[Number]]) -> Vector:
    if not vectors:
        return []
    width = len(vectors[0])
    if width == 0:
        return []
    pooled = [0.0] * width
    for row in vectors:
        if len(row) != width:
            raise ValueError("Cannot mean-pool ragged embeddings")
        for i, value in enumerate(row):
            pooled[i] += float(value)
    inv_n = 1.0 / len(vectors)
    return [v * inv_n for v in pooled]


def coerce_embedding_vector(raw: Any) -> Vector:
    """
    Normalize varied HF embedding output shapes to a flat sentence vector.

    Handles:
      - [f1, f2, ...]
      - [[f1, f2, ...]]
      - [[token1...], [token2...], ...]  -> mean pooled sentence vector
    """
    if _is_number_list(raw):
        return [float(v) for v in raw]

    if isinstance(raw, list) and raw:
        if len(raw) == 1 and _is_number_list(raw[0]):
            return [float(v) for v in raw[0]]

        if all(_is_number_list(item) for item in raw):
            token_matrix: list[list[Number]] = raw
            return _mean_pool(token_matrix)

    raise ValueError(f"Unexpected embedding response shape: {type(raw)}")


def coerce_embedding_batch(raw: Any, expected_count: int) -> list[Vector]:
    if expected_count <= 0:
        return []

    if expected_count == 1:
        return [coerce_embedding_vector(raw)]

    if not isinstance(raw, list):
        raise ValueError("Expected list response for batch embedding inference")

    if len(raw) == expected_count:
        return [coerce_embedding_vector(item) for item in raw]

    if len(raw) == 1 and isinstance(raw[0], list) and len(raw[0]) == expected_count:
        return [coerce_embedding_vector(item) for item in raw[0]]

    raise ValueError(
        f"Embedding batch size mismatch: expected {expected_count}, got {len(raw)}"
    )


def cosine_similarity(lhs: Sequence[float], rhs: Sequence[float]) -> float:
    if not lhs or not rhs or len(lhs) != len(rhs):
        return 0.0

    dot = 0.0
    norm_l = 0.0
    norm_r = 0.0
    for lv, rv in zip(lhs, rhs):
        lf = float(lv)
        rf = float(rv)
        dot += lf * rf
        norm_l += lf * lf
        norm_r += rf * rf

    denom = math.sqrt(norm_l) * math.sqrt(norm_r)
    if denom == 0.0:
        return 0.0
    return dot / denom


class HuggingFaceInferenceClient:
    def __init__(
        self,
        model_id: str,
        api_token: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        base_url: Optional[str] = None,
    ):
        if not model_id:
            raise ValueError("model_id is required")

        self.model_id = model_id
        resolved_base_url = base_url or os.getenv(
            "HF_INFERENCE_BASE_URL",
            "https://router.huggingface.co/hf-inference/models",
        )
        self.url = f"{resolved_base_url.rstrip('/')}/{model_id}"

        timeout = timeout_seconds if timeout_seconds is not None else os.getenv("HF_TIMEOUT_SECONDS", "20")
        retries = max_retries if max_retries is not None else os.getenv("HF_MAX_RETRIES", "2")
        try:
            self.timeout_seconds = float(timeout)
        except (TypeError, ValueError):
            self.timeout_seconds = 20.0
        try:
            self.max_retries = max(0, int(retries))
        except (TypeError, ValueError):
            self.max_retries = 2

        token = (api_token or os.getenv("HUGGINGFACE_API_TOKEN") or os.getenv("HF_TOKEN") or "").strip()
        self.headers: dict[str, str] = {"Content-Type": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        else:
            logger.warning(
                "No Hugging Face token found. Set HUGGINGFACE_API_TOKEN or HF_TOKEN "
                "(or ensure .env is loaded) to avoid HTTP 401 from inference APIs."
            )

    def predict(
        self,
        inputs: Any,
        parameters: Optional[dict[str, Any]] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "inputs": inputs,
            "options": {
                "wait_for_model": True,
                "use_cache": True,
            },
        }
        if parameters:
            payload["parameters"] = parameters
        if options:
            payload["options"].update(options)
        return self._post_json(payload)

    def _post_json(self, payload: dict[str, Any]) -> Any:
        last_err: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.post(
                    self.url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                body: Any = None
                if response.text:
                    try:
                        body = response.json()
                    except ValueError:
                        body = None

                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    sleep_seconds = self._retry_delay_seconds(body, attempt)
                    logger.warning(
                        "HF inference retry (%s/%s) for %s after HTTP %s",
                        attempt + 1,
                        self.max_retries,
                        self.model_id,
                        response.status_code,
                    )
                    time.sleep(sleep_seconds)
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as status_err:
                    if response.status_code == 410:
                        raise RuntimeError(
                            "Hugging Face returned HTTP 410 Gone. "
                            "Use HF_INFERENCE_BASE_URL=https://router.huggingface.co/hf-inference/models "
                            "and verify the model exists."
                        ) from status_err
                    raise RuntimeError(
                        f"HuggingFace inference HTTP {response.status_code} for model "
                        f"'{self.model_id}': {response.text[:300]}"
                    ) from status_err

                if isinstance(body, dict) and body.get("error"):
                    message = str(body["error"])
                    if "loading" in message.lower() and attempt < self.max_retries:
                        sleep_seconds = self._retry_delay_seconds(body, attempt)
                        logger.warning(
                            "HF model loading retry (%s/%s) for %s",
                            attempt + 1,
                            self.max_retries,
                            self.model_id,
                        )
                        time.sleep(sleep_seconds)
                        continue
                    raise RuntimeError(message)

                return body

            except (httpx.RequestError, RuntimeError, ValueError) as err:
                last_err = err
                if attempt >= self.max_retries:
                    break
                sleep_seconds = 1.0 + attempt
                logger.warning(
                    "HF inference transient error (%s/%s) for %s: %s",
                    attempt + 1,
                    self.max_retries,
                    self.model_id,
                    err,
                )
                time.sleep(sleep_seconds)

        raise RuntimeError(
            f"HuggingFace inference failed for model '{self.model_id}': {last_err}"
        )

    @staticmethod
    def _retry_delay_seconds(body: Any, attempt: int) -> float:
        if isinstance(body, dict):
            estimated = body.get("estimated_time")
            if isinstance(estimated, (int, float)) and estimated > 0:
                return min(float(estimated), 20.0)
        return min(2.0 + attempt, 10.0)
