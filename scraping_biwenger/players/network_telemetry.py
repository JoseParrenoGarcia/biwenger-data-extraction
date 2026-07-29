from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary

CORE_HOSTS = {
    "biwenger.as.com",
    "cdn.biwenger.com",
}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_getattr(obj: object, attr: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def _call_or_value(value: Any) -> Any:
    try:
        return value() if callable(value) else value
    except Exception:
        return None


def _url_pattern(url: str) -> str:
    parts = urlsplit(url or "")
    path = parts.path or ""
    path = re.sub(r"/\d+(?=/|$)", "/:id", path)
    path = re.sub(r"/[0-9a-f]{8,}(?=/|$)", "/:token", path, flags=re.I)
    return f"{parts.netloc}{path}"


def _url_host(url: str) -> str:
    return urlsplit(url or "").netloc


def _is_core_host(host: str) -> bool:
    return host in CORE_HOSTS


@dataclass
class _ActionFrame:
    action: str
    player_slug: str
    metadata: dict[str, Any]
    started_at: float = field(default_factory=time.perf_counter)


class PlayerRunNetworkTelemetry:
    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.telemetry_path = self.run_dir / "network_telemetry.jsonl"
        self.summary_path = self.run_dir / "network_summary.json"
        self._action_stack: list[_ActionFrame] = []
        self._request_contexts: dict[int, dict[str, Any]] = {}
        self._action_stats: dict[str, dict[str, Any]] = defaultdict(self._new_action_stats)
        self._overall_stats = self._new_action_stats()
        self._core_action_stats: dict[str, dict[str, Any]] = defaultdict(self._new_action_stats)
        self._core_overall_stats = self._new_action_stats()
        self._fh = self.telemetry_path.open("a", encoding="utf-8")
        self._attached = False
        self._closed = False
        self._summary_written = False

    @staticmethod
    def _new_action_stats() -> dict[str, Any]:
        return {
            "action_invocations": 0,
            "action_duration_s_total": 0.0,
            "request_count": 0,
            "response_count": 0,
            "failed_request_count": 0,
            "download_count": 0,
            "resource_types": Counter(),
            "methods": Counter(),
            "statuses": Counter(),
            "url_patterns": Counter(),
        }

    def attach(self, page: object) -> None:
        if self._attached:
            return
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_request_failed)
        page.on("download", self._on_download)
        self._attached = True

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._summary_written:
            self._write_summary()
        if not self._fh.closed:
            self._fh.close()

    def push_action(self, action: str, *, player_slug: str = "", **metadata: Any) -> _ActionFrame:
        frame = _ActionFrame(action=action, player_slug=player_slug, metadata=metadata)
        self._action_stack.append(frame)
        self._write_event(
            {
                "type": "action_started",
                "recorded_at": _utc_timestamp(),
                "action": action,
                "player_slug": player_slug,
                "metadata": metadata,
            }
        )
        return frame

    def pop_action(self, frame: _ActionFrame) -> None:
        if not self._action_stack:
            return
        top = self._action_stack.pop()
        if top is not frame:
            return
        duration_s = time.perf_counter() - frame.started_at
        for bucket in (self._action_stats[frame.action], self._core_action_stats[frame.action]):
            bucket["action_invocations"] += 1
            bucket["action_duration_s_total"] += duration_s
        self._write_event(
            {
                "type": "action_finished",
                "recorded_at": _utc_timestamp(),
                "action": frame.action,
                "player_slug": frame.player_slug,
                "duration_s": round(duration_s, 6),
                "metadata": frame.metadata,
            }
        )

    def current_action(self) -> dict[str, Any]:
        if not self._action_stack:
            return {"action": "unscoped", "player_slug": "", "metadata": {}}
        frame = self._action_stack[-1]
        return {
            "action": frame.action,
            "player_slug": frame.player_slug,
            "metadata": frame.metadata,
        }

    def _event_base(self, *, event_type: str, context: dict[str, Any], url: str = "") -> dict[str, Any]:
        return {
            "type": event_type,
            "recorded_at": _utc_timestamp(),
            "action": context["action"],
            "player_slug": context["player_slug"],
            "metadata": context["metadata"],
            "url": url,
            "url_pattern": _url_pattern(url) if url else "",
        }

    def _record_common(
        self,
        context: dict[str, Any],
        *,
        method: str,
        resource_type: str,
        url: str,
        core_only: bool = False,
    ) -> None:
        buckets = (
            (self._core_overall_stats, self._core_action_stats[context["action"]])
            if core_only
            else (self._overall_stats, self._action_stats[context["action"]])
        )
        for bucket in buckets:
            bucket["request_count"] += 1
            bucket["resource_types"][resource_type or "unknown"] += 1
            bucket["methods"][method or "UNKNOWN"] += 1
            bucket["url_patterns"][_url_pattern(url)] += 1

    def _on_request(self, request: object) -> None:
        if self._closed:
            return
        context = self.current_action()
        request_id = id(request)
        method = _call_or_value(_safe_getattr(request, "method", "UNKNOWN")) or "UNKNOWN"
        resource_type = _call_or_value(_safe_getattr(request, "resource_type", "unknown")) or "unknown"
        url = _call_or_value(_safe_getattr(request, "url", "")) or ""
        host = _url_host(url)
        is_core_request = _is_core_host(host)
        self._request_contexts[request_id] = {
            **context,
            "method": method,
            "resource_type": resource_type,
            "url": url,
            "url_host": host,
            "is_core_request": is_core_request,
        }
        self._record_common(context, method=method, resource_type=resource_type, url=url)
        if is_core_request:
            self._record_common(
                context,
                method=method,
                resource_type=resource_type,
                url=url,
                core_only=True,
            )
        self._write_event(
            {
                **self._event_base(event_type="request", context=context, url=url),
                "method": method,
                "resource_type": resource_type,
                "url_host": host,
                "is_core_request": is_core_request,
            }
        )

    def _on_response(self, response: object) -> None:
        if self._closed:
            return
        request = _call_or_value(_safe_getattr(response, "request"))
        context = self._request_contexts.get(id(request), self.current_action())
        status = _call_or_value(_safe_getattr(response, "status"))
        url = context.get("url", "") or _call_or_value(_safe_getattr(response, "url", "")) or ""
        is_core_request = bool(context.get("is_core_request"))
        for bucket in (self._overall_stats, self._action_stats[context["action"]]):
            bucket["response_count"] += 1
            bucket["statuses"][str(status if status is not None else "unknown")] += 1
        if is_core_request:
            for bucket in (self._core_overall_stats, self._core_action_stats[context["action"]]):
                bucket["response_count"] += 1
                bucket["statuses"][str(status if status is not None else "unknown")] += 1
        self._write_event(
            {
                **self._event_base(event_type="response", context=context, url=url),
                "method": context.get("method", "UNKNOWN"),
                "resource_type": context.get("resource_type", "unknown"),
                "status": status,
                "url_host": context.get("url_host", _url_host(url)),
                "is_core_request": is_core_request,
            }
        )

    def _on_request_failed(self, request: object) -> None:
        if self._closed:
            return
        context = self._request_contexts.get(id(request), self.current_action())
        url = context.get("url", "") or _call_or_value(_safe_getattr(request, "url", "")) or ""
        failure = _call_or_value(_safe_getattr(request, "failure")) or {}
        is_core_request = bool(context.get("is_core_request", _is_core_host(_url_host(url))))
        if isinstance(failure, dict):
            failure_text = failure.get("errorText", "")
        else:
            failure_text = str(failure)
        for bucket in (self._overall_stats, self._action_stats[context["action"]]):
            bucket["failed_request_count"] += 1
        if is_core_request:
            for bucket in (self._core_overall_stats, self._core_action_stats[context["action"]]):
                bucket["failed_request_count"] += 1
        self._write_event(
            {
                **self._event_base(event_type="request_failed", context=context, url=url),
                "method": context.get("method", "UNKNOWN"),
                "resource_type": context.get("resource_type", "unknown"),
                "failure_text": failure_text,
                "url_host": context.get("url_host", _url_host(url)),
                "is_core_request": is_core_request,
            }
        )

    def _on_download(self, download: object) -> None:
        if self._closed:
            return
        context = self.current_action()
        url = _call_or_value(_safe_getattr(download, "url", "")) or ""
        host = _url_host(url)
        is_core_request = _is_core_host(host)
        suggested_filename = _call_or_value(_safe_getattr(download, "suggested_filename", "")) or ""
        for bucket in (self._overall_stats, self._action_stats[context["action"]]):
            bucket["download_count"] += 1
        if is_core_request:
            for bucket in (self._core_overall_stats, self._core_action_stats[context["action"]]):
                bucket["download_count"] += 1
        self._write_event(
            {
                **self._event_base(event_type="download", context=context, url=url),
                "suggested_filename": suggested_filename,
                "url_host": host,
                "is_core_request": is_core_request,
            }
        )

    def _write_event(self, payload: dict[str, Any]) -> None:
        if self._closed or self._fh.closed:
            return
        self._fh.write(json.dumps(payload, ensure_ascii=True) + "\n")
        self._fh.flush()

    def _summarize_bucket(self, bucket: dict[str, Any]) -> dict[str, Any]:
        action_invocations = bucket["action_invocations"]
        total_duration = bucket["action_duration_s_total"]
        avg_duration = total_duration / action_invocations if action_invocations else 0.0
        return {
            "action_invocations": action_invocations,
            "action_duration_s_total": round(total_duration, 6),
            "action_duration_s_avg": round(avg_duration, 6),
            "request_count": bucket["request_count"],
            "response_count": bucket["response_count"],
            "failed_request_count": bucket["failed_request_count"],
            "download_count": bucket["download_count"],
            "resource_types": dict(bucket["resource_types"]),
            "methods": dict(bucket["methods"]),
            "statuses": dict(bucket["statuses"]),
            "top_url_patterns": [
                {"url_pattern": url_pattern, "count": count}
                for url_pattern, count in bucket["url_patterns"].most_common(20)
            ],
        }

    def _write_summary(self) -> None:
        if self._summary_written:
            return
        summary = {
            "generated_at": _utc_timestamp(),
            "core_hosts": sorted(CORE_HOSTS),
            "overall": self._summarize_bucket(self._overall_stats),
            "core_overall": self._summarize_bucket(self._core_overall_stats),
            "actions": {
                action: self._summarize_bucket(bucket)
                for action, bucket in sorted(self._action_stats.items(), key=lambda item: item[0])
            },
            "core_actions": {
                action: self._summarize_bucket(bucket)
                for action, bucket in sorted(self._core_action_stats.items(), key=lambda item: item[0])
            },
        }
        self.summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        self._summary_written = True


_PAGE_TELEMETRY: WeakKeyDictionary[object, PlayerRunNetworkTelemetry] = WeakKeyDictionary()


def attach_page_network_telemetry(page: object, telemetry: PlayerRunNetworkTelemetry) -> None:
    _PAGE_TELEMETRY[page] = telemetry
    telemetry.attach(page)


@contextmanager
def network_action(page: object, action: str, *, player_slug: str = "", **metadata: Any):
    try:
        telemetry = _PAGE_TELEMETRY.get(page)
    except TypeError:
        telemetry = None
    if telemetry is None:
        yield
        return
    frame = telemetry.push_action(action, player_slug=player_slug, **metadata)
    try:
        yield
    finally:
        telemetry.pop_action(frame)
