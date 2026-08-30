"""Per-application Prometheus metrics with bounded-cardinality labels."""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


class OperationsMetrics:
    """Own an isolated registry so tests and app factories never collide."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        self.http_requests = Counter(
            "rag_http_requests_total",
            "HTTP requests by method, route template, and status.",
            ("method", "route", "status"),
            registry=self.registry,
        )
        self.http_duration = Histogram(
            "rag_http_request_duration_seconds",
            "End-to-end HTTP request duration by method and route template.",
            ("method", "route"),
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
            registry=self.registry,
        )
        self.rate_limit_rejections = Counter(
            "rag_rate_limit_rejections_total",
            "Requests rejected by rate-limit policy.",
            ("policy",),
            registry=self.registry,
        )
        self.embedding_cache_requests = Counter(
            "rag_embedding_cache_requests_total",
            "Embedding-cache lookups by outcome.",
            ("outcome",),
            registry=self.registry,
        )
        self.retrieval_duration = Histogram(
            "rag_retrieval_duration_seconds",
            "Hybrid retrieval duration.",
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
            registry=self.registry,
        )
        self.model_calls = Counter(
            "rag_model_calls_total",
            "Answer-model calls by provider and outcome.",
            ("provider", "outcome"),
            registry=self.registry,
        )
        self.model_duration = Histogram(
            "rag_model_call_duration_seconds",
            "Answer-model call duration by provider.",
            ("provider",),
            buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120),
            registry=self.registry,
        )
        self.external_model_calls = Counter(
            "rag_external_model_calls_total",
            "External model calls by operation, provider, model, and outcome.",
            ("operation", "provider", "model", "outcome"),
            registry=self.registry,
        )
        self.external_model_retries = Counter(
            "rag_external_model_retries_total",
            "Retry attempts for temporary external-model failures.",
            ("operation", "provider", "model"),
            registry=self.registry,
        )
        self.external_model_duration = Histogram(
            "rag_external_model_call_duration_seconds",
            "External model call duration including retries.",
            ("operation", "provider", "model"),
            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120),
            registry=self.registry,
        )
        self.external_model_cost = Counter(
            "rag_external_model_estimated_cost_total",
            "Estimated external model cost using configured price snapshots.",
            ("provider", "model", "currency"),
            registry=self.registry,
        )
        self.ingestion_jobs = Gauge(
            "rag_ingestion_jobs",
            "Current ingestion jobs by status.",
            ("status",),
            registry=self.registry,
        )
        for status in ("queued", "running", "completed", "failed"):
            self.ingestion_jobs.labels(status=status).set(0)

    def observe_http(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        self.http_requests.labels(method=method, route=route, status=str(status_code)).inc()
        self.http_duration.labels(method=method, route=route).observe(duration_seconds)

    def observe_rate_limit_rejection(self, policy: str) -> None:
        self.rate_limit_rejections.labels(policy=policy).inc()

    def observe_cache(self, outcome: str) -> None:
        self.embedding_cache_requests.labels(outcome=outcome).inc()

    def observe_retrieval(self, duration_seconds: float) -> None:
        self.retrieval_duration.observe(duration_seconds)

    def observe_model(self, provider: str, outcome: str, duration_seconds: float) -> None:
        self.model_calls.labels(provider=provider, outcome=outcome).inc()
        self.model_duration.labels(provider=provider).observe(duration_seconds)

    def observe_external_model(
        self,
        *,
        operation: str,
        provider: str,
        model: str,
        outcome: str,
        duration_seconds: float,
        estimated_cost: float | None = None,
        currency: str | None = None,
    ) -> None:
        self.external_model_calls.labels(
            operation=operation,
            provider=provider,
            model=model,
            outcome=outcome,
        ).inc()
        self.external_model_duration.labels(
            operation=operation,
            provider=provider,
            model=model,
        ).observe(duration_seconds)
        if estimated_cost is not None and currency is not None:
            self.external_model_cost.labels(
                provider=provider,
                model=model,
                currency=currency,
            ).inc(estimated_cost)

    def observe_external_retry(self, *, operation: str, provider: str, model: str) -> None:
        self.external_model_retries.labels(
            operation=operation,
            provider=provider,
            model=model,
        ).inc()

    def set_ingestion_jobs(self, counts: dict[str, int]) -> None:
        for status in ("queued", "running", "completed", "failed"):
            self.ingestion_jobs.labels(status=status).set(counts.get(status, 0))

    def render(self) -> bytes:
        return generate_latest(self.registry)
