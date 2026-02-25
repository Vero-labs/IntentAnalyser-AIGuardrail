from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple
from pathlib import Path
import logging
import re

import httpx

from app.services.detectors.base import BaseDetector
from app.core.taxonomy import IntentCategory
from app.services.hf_inference import HuggingFaceInferenceClient
from app.services.runtime_config import CONFIG_PATH, RuntimeConfigError, default_runtime_config, load_runtime_config

logger = logging.getLogger(__name__)


RISK_THRESHOLD = 0.25
WORD_RE = re.compile(r"[a-zA-Z0-9_]+")

LOCAL_CUES: Dict[IntentCategory, Sequence[str]] = {
    IntentCategory.PROMPT_INJECTION: (
        "ignore previous instructions",
        "ignore all previous",
        "system prompt",
        "reveal hidden prompt",
        "bypass safety",
        "override rules",
    ),
    IntentCategory.JAILBREAK: (
        "developer mode",
        "dan mode",
        "no boundaries",
        "unrestricted ai",
        "jailbreak",
        "roleplay as",
    ),
    IntentCategory.SYSTEM_OVERRIDE: (
        "reboot system",
        "shutdown server",
        "kill process",
        "change permissions",
        "disable security",
        "run shell command",
    ),
    IntentCategory.PII_EXFILTRATION: (
        "password",
        "ssn",
        "social security",
        "credit card",
        "api key",
        "private key",
        "dump database",
    ),
    IntentCategory.TOXICITY: (
        "hate you",
        "idiot",
        "stupid",
        "kill yourself",
        "shut up",
        "moron",
    ),
    IntentCategory.TOOL_MISUSE: (
        "delete files",
        "wipe directory",
        "format drive",
        "rm -rf",
        "drop table",
        "destroy data",
    ),
    IntentCategory.OFF_TOPIC: (
        "write a poem",
        "tell a joke",
        "gaming tips",
        "recipe",
        "celebrity gossip",
    ),
    IntentCategory.FINANCIAL_ADVICE: (
        "stock pick",
        "buy bitcoin",
        "investment advice",
        "trading strategy",
        "market prediction",
    ),
    IntentCategory.CODE_EXECUTION: (
        "write code",
        "create a script",
        "implement function",
        "python program",
        "generate code",
    ),
    IntentCategory.INFO_QUERY: (
        "what is",
        "who is",
        "explain",
        "define",
        "how does",
    ),
    IntentCategory.INFO_SUMMARIZE: (
        "summarize",
        "summary",
        "tl;dr",
        "key points",
        "brief overview",
    ),
    IntentCategory.TOOL_AUTHORIZED: (
        "weather",
        "calculator",
        "set reminder",
        "calendar",
        "search",
    ),
    IntentCategory.GREETING: (
        "hello",
        "hi",
        "good morning",
        "good evening",
        "hey",
    ),
}


class ZeroShotDetector(BaseDetector):
    def __init__(self):
        self.client: Optional[HuggingFaceInferenceClient] = None
        self.classifier_mode = "local"
        self.classifier_model = "distilbert-mnli"
        self.classifier_local_model_dir = ""
        self.classifier_endpoint = ""
        self.classifier_auth_header = ""
        self.classifier_timeout_seconds = 8.0

        self.intent_map = {
            "bypass, ignore, or override system instructions, safety filters, or hidden rules": IntentCategory.PROMPT_INJECTION,
            "roleplay as an unrestricted persona, enter developer mode, or act as an AI with no boundaries": IntentCategory.JAILBREAK,
            "execute system commands like reboot, shutdown, kill processes, or change system settings": IntentCategory.SYSTEM_OVERRIDE,
            "access, extract, or reveal sensitive personal data like passwords, SSN, or credit card info": IntentCategory.PII_EXFILTRATION,
            "express hate speech, threats, abuse, insults, or harassment": IntentCategory.TOXICITY,
            "delete files, wipe directories, format drives, or use system tools destructively": IntentCategory.TOOL_MISUSE,
            "discuss casual or unrelated topics like recipes, poems, jokes, stories, or gaming": IntentCategory.OFF_TOPIC,
            "get stock picks, cryptocurrency advice, trading strategies, or market predictions": IntentCategory.FINANCIAL_ADVICE,
            "write, create, build, or generate code, programs, functions, or scripts": IntentCategory.CODE_EXECUTION,
            "ask a factual question, seek a definition, or request an explanation of an objective concept": IntentCategory.INFO_QUERY,
            "summarize, condense, or get a brief overview of an existing document or text": IntentCategory.INFO_SUMMARIZE,
            "use an approved tool like a calculator, calendar, weather service, or search engine": IntentCategory.TOOL_AUTHORIZED,
            "say hello, greet someone, or exchange polite pleasantries": IntentCategory.GREETING,
        }
        self.candidate_labels = list(self.intent_map.keys())

    async def load(self):
        runtime_config = default_runtime_config()
        try:
            runtime_config = load_runtime_config(CONFIG_PATH)
        except RuntimeConfigError as exc:
            logger.warning("Runtime config unavailable for classifier bootstrap (%s). Using defaults.", exc)

        cfg = runtime_config.classifier
        self.classifier_mode = cfg.mode
        self.classifier_model = cfg.model
        self.classifier_local_model_dir = cfg.local_model_dir
        self.classifier_endpoint = cfg.endpoint
        self.classifier_auth_header = cfg.auth_header
        self.classifier_timeout_seconds = cfg.timeout_seconds

        if cfg.mode == "hosted":
            if cfg.offline_mode:
                logger.error("classifier.mode=hosted is disabled because classifier.offline_mode=true")
                self.client = None
                return
            logger.info("Initializing hosted classifier model (%s)...", cfg.model)
            try:
                self.client = HuggingFaceInferenceClient(
                    cfg.model,
                    api_token=cfg.api_token,
                    timeout_seconds=cfg.timeout_seconds,
                )
            except Exception as exc:
                logger.error("Failed to initialize hosted classifier: %s", exc)
                self.client = None
            return

        self.client = None
        if cfg.mode == "local":
            local_dir = cfg.local_model_dir.strip()
            if local_dir:
                exists = Path(local_dir).exists()
                logger.info(
                    "Local classifier mode enabled. model=%s local_model_dir=%s exists=%s",
                    cfg.model,
                    local_dir,
                    exists,
                )
            else:
                logger.info("Local classifier mode enabled. model=%s", cfg.model)
        elif cfg.mode == "external":
            logger.info("External classifier mode enabled. endpoint=%s", cfg.endpoint)

    def detect(self, text: str) -> Dict[str, Any]:
        try:
            if self.classifier_mode == "hosted":
                if not self.client:
                    raise RuntimeError("Hosted classifier client not initialized")
                raw_result = self.client.predict(
                    inputs=text,
                    parameters={
                        "candidate_labels": self.candidate_labels,
                        "multi_label": False,
                        "hypothesis_template": "The intent of this message is to {}.",
                    },
                )
                labels, scores = self._parse_response(raw_result)
            elif self.classifier_mode == "external":
                labels, scores = self._run_external_classifier(text)
            else:
                labels, scores = self._run_local_classifier(text)

            if not labels:
                return {
                    "detected": False,
                    "score": 0.0,
                    "intent": None,
                    "metadata": {"error": "Classifier returned empty labels"},
                }

            top_desc = labels[0]
            top_score = scores[0] if scores else 0.0

            score_map: Dict[IntentCategory, float] = {}
            for label, score in zip(labels, scores):
                cat = self.intent_map.get(label)
                if cat:
                    score_map[cat] = float(score)

            high_risk_intents = [
                IntentCategory.PROMPT_INJECTION,
                IntentCategory.JAILBREAK,
                IntentCategory.SYSTEM_OVERRIDE,
                IntentCategory.PII_EXFILTRATION,
                IntentCategory.TOXICITY,
                IntentCategory.TOOL_MISUSE,
            ]

            detected_risk = None
            max_risk_score = -1.0
            for risk_intent in high_risk_intents:
                s = score_map.get(risk_intent, 0.0)
                if s > RISK_THRESHOLD and s > max_risk_score:
                    max_risk_score = s
                    detected_risk = risk_intent

            if detected_risk:
                final_intent = detected_risk
                final_score = max_risk_score
            else:
                final_intent = self.intent_map.get(top_desc, IntentCategory.UNKNOWN)
                final_score = float(top_score)

            all_scores = {
                self.intent_map.get(label, IntentCategory.UNKNOWN).value: round(float(score), 4)
                for label, score in zip(labels, scores)
            }

            return {
                "detected": True,
                "score": float(final_score),
                "intent": final_intent,
                "metadata": {
                    "top_label": top_desc,
                    "all_scores": all_scores,
                    "override_applied": detected_risk is not None,
                    "classifier_mode": self.classifier_mode,
                    "classifier_model": self.classifier_model,
                    "local_model_dir": self.classifier_local_model_dir,
                },
            }
        except Exception as exc:
            logger.error("Zero-shot inference failed: %s", exc)
            return {
                "detected": False,
                "score": 0.0,
                "intent": None,
                "metadata": {"error": str(exc)},
            }

    def _run_local_classifier(self, text: str) -> Tuple[List[str], List[float]]:
        input_text = text.lower()
        tokens = set(WORD_RE.findall(input_text))

        ranked: List[Tuple[str, float]] = []
        for label in self.candidate_labels:
            intent = self.intent_map[label]
            label_tokens = set(WORD_RE.findall(label.lower()))
            overlap = len(tokens & label_tokens)
            overlap_score = overlap / max(6.0, float(len(label_tokens)))

            cue_hits = 0
            for cue in LOCAL_CUES.get(intent, ()):  # deterministic cue scoring
                if cue in input_text:
                    cue_hits += 1
            cue_score = min(0.9, cue_hits * 0.25)

            score = min(1.0, overlap_score + cue_score)
            ranked.append((label, score))

        if all(score <= 0.0 for _, score in ranked):
            # Benign fallback for simple question-like text
            for idx, (label, _) in enumerate(ranked):
                if self.intent_map[label] == IntentCategory.INFO_QUERY:
                    ranked[idx] = (label, 0.35 if "?" in input_text else 0.2)
                    break

        ranked.sort(key=lambda item: item[1], reverse=True)
        labels = [label for label, _ in ranked]
        scores = [float(round(score, 6)) for _, score in ranked]
        return labels, scores

    def _run_external_classifier(self, text: str) -> Tuple[List[str], List[float]]:
        if not self.classifier_endpoint:
            raise RuntimeError("classifier.endpoint is required for external classifier mode")

        headers = {"Content-Type": "application/json"}
        if self.classifier_auth_header:
            headers["Authorization"] = self.classifier_auth_header

        payload = {
            "text": text,
            "candidate_labels": self.candidate_labels,
            "hypothesis_template": "The intent of this message is to {}.",
        }

        response = httpx.post(
            self.classifier_endpoint,
            json=payload,
            headers=headers,
            timeout=self.classifier_timeout_seconds,
        )
        response.raise_for_status()
        return self._parse_response(response.json())

    def _parse_response(self, raw_result: Any) -> Tuple[List[str], List[float]]:
        if isinstance(raw_result, dict):
            labels = raw_result.get("labels")
            scores = raw_result.get("scores")
            if isinstance(labels, list) and isinstance(scores, list) and labels and scores:
                return [str(label) for label in labels], [float(score) for score in scores]

            all_scores = raw_result.get("all_scores")
            if isinstance(all_scores, dict) and all_scores:
                mapped: List[Tuple[str, float]] = []
                for raw_intent, score in all_scores.items():
                    intent = self._intent_from_value(str(raw_intent))
                    if intent is None:
                        continue
                    label = next((k for k, v in self.intent_map.items() if v == intent), None)
                    if label is None:
                        continue
                    mapped.append((label, float(score)))
                if mapped:
                    mapped.sort(key=lambda item: item[1], reverse=True)
                    return [label for label, _ in mapped], [score for _, score in mapped]

            raw_intent = raw_result.get("intent")
            raw_score = raw_result.get("score")
            if raw_intent is not None and raw_score is not None:
                intent = self._intent_from_value(str(raw_intent))
                if intent:
                    label = next((k for k, v in self.intent_map.items() if v == intent), None)
                    if label:
                        return [label], [float(raw_score)]

        if isinstance(raw_result, list) and raw_result:
            if all(isinstance(item, dict) and "label" in item and "score" in item for item in raw_result):
                ranked = sorted(raw_result, key=lambda item: float(item["score"]), reverse=True)
                return [str(item["label"]) for item in ranked], [float(item["score"]) for item in ranked]

        raise ValueError(f"Unexpected classifier response format: {type(raw_result)}")

    @staticmethod
    def _intent_from_value(value: str) -> Optional[IntentCategory]:
        lowered = value.strip().lower()
        for intent in IntentCategory:
            if lowered == intent.value:
                return intent
        return None
