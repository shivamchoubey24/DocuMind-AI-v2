import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Configure a single, consistent log format across the app.

    In production this stream is typically captured by the container
    orchestrator (Docker/K8s) and shipped to a log aggregator.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Quiet down noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)


logger = logging.getLogger("documind")
