"""
Datadog collector - fetches usage metrics via Datadog API.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v1.api.metrics_api import MetricsApi
from datadog_api_client.v1.api.monitors_api import MonitorsApi


class DatadogCollector:
    """Collects usage metrics and monitor status from Datadog."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        app_key: Optional[str] = None,
        site: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("DD_API_KEY")
        self.app_key = app_key or os.environ.get("DD_APP_KEY")
        self.site = site or os.environ.get("DD_SITE", "datadoghq.com")
        self._config: Optional[Configuration] = None

    def _get_config(self) -> Configuration:
        """Get Datadog API configuration."""
        if self._config:
            return self._config

        self._config = Configuration()
        self._config.api_key["apiKeyAuth"] = self.api_key
        self._config.api_key["appKeyAuth"] = self.app_key
        self._config.server_variables["site"] = self.site

        return self._config

    def get_metrics(
        self,
        query: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Query metrics from Datadog.

        Args:
            query: Datadog metrics query (e.g., "avg:system.cpu.user{client:acme}")
            start_date: Start of date range (default: 7 days ago)
            end_date: End of date range (default: now)

        Returns:
            List of metric series with timestamps and values
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.utcnow()

        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())

        with ApiClient(self._get_config()) as api_client:
            api = MetricsApi(api_client)
            response = api.query_metrics(
                _from=start_ts,
                to=end_ts,
                query=query,
            )

            results = []
            for series in response.get("series", []):
                points = series.get("pointlist", [])
                results.append({
                    "metric": series.get("metric", ""),
                    "scope": series.get("scope", ""),
                    "tags": series.get("tag_set", []),
                    "points": [
                        {"timestamp": p[0], "value": p[1]}
                        for p in points
                    ],
                    "avg": sum(p[1] for p in points) / len(points) if points else 0,
                    "max": max(p[1] for p in points) if points else 0,
                    "min": min(p[1] for p in points) if points else 0,
                })

            return results

    def get_monitors(
        self,
        client_tag: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch monitor status, optionally filtered by client tag.

        Args:
            client_tag: Tag to filter monitors (e.g., "client:acme")

        Returns:
            List of monitors with status
        """
        with ApiClient(self._get_config()) as api_client:
            api = MonitorsApi(api_client)

            params = {}
            if client_tag:
                params["monitor_tags"] = client_tag

            response = api.list_monitors(**params)

            return [
                {
                    "id": monitor.get("id"),
                    "name": monitor.get("name", ""),
                    "type": monitor.get("type", ""),
                    "status": monitor.get("overall_state", ""),
                    "message": monitor.get("message", ""),
                    "tags": monitor.get("tags", []),
                    "created": monitor.get("created"),
                    "modified": monitor.get("modified"),
                }
                for monitor in response
            ]

    def get_client_usage(
        self,
        client_tag: str,
        metric_queries: Optional[list[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """
        Get usage summary for a client.

        Args:
            client_tag: Datadog tag for the client (e.g., "client:acme")
            metric_queries: List of metric queries to run
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Summary dict with metrics and monitor status
        """
        if metric_queries is None:
            # Default queries - adjust based on your actual metrics
            metric_queries = [
                f"sum:app.requests.count{{{client_tag}}}",
                f"avg:app.response_time{{{client_tag}}}",
                f"sum:app.errors.count{{{client_tag}}}",
            ]

        metrics_data = {}
        for query in metric_queries:
            try:
                result = self.get_metrics(
                    query=query,
                    start_date=start_date,
                    end_date=end_date,
                )
                metrics_data[query] = result
            except Exception as e:
                metrics_data[query] = {"error": str(e)}

        monitors = self.get_monitors(client_tag=client_tag)

        # Calculate summary stats
        alert_count = sum(1 for m in monitors if m["status"] == "Alert")
        warn_count = sum(1 for m in monitors if m["status"] == "Warn")
        ok_count = sum(1 for m in monitors if m["status"] == "OK")

        return {
            "client_tag": client_tag,
            "metrics": metrics_data,
            "monitors": monitors,
            "monitor_summary": {
                "total": len(monitors),
                "alert": alert_count,
                "warn": warn_count,
                "ok": ok_count,
            },
        }

    def compare_usage(
        self,
        client_tag: str,
        metric_query: str,
        current_start: datetime,
        current_end: datetime,
        previous_start: datetime,
        previous_end: datetime,
    ) -> dict:
        """
        Compare usage between two time periods.

        Returns:
            Dict with current, previous, and change percentage
        """
        current = self.get_metrics(
            query=metric_query,
            start_date=current_start,
            end_date=current_end,
        )

        previous = self.get_metrics(
            query=metric_query,
            start_date=previous_start,
            end_date=previous_end,
        )

        current_avg = current[0]["avg"] if current else 0
        previous_avg = previous[0]["avg"] if previous else 0

        if previous_avg > 0:
            change_pct = ((current_avg - previous_avg) / previous_avg) * 100
        else:
            change_pct = 100 if current_avg > 0 else 0

        return {
            "current": current_avg,
            "previous": previous_avg,
            "change_percent": round(change_pct, 2),
            "trend": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
        }
