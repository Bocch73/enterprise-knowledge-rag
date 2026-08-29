"""Cross-platform development server entry point."""

import argparse

import uvicorn


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Enterprise Knowledge RAG API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--reload", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run Uvicorn with a database-compatible event loop on every platform."""
    arguments = parse_arguments()
    uvicorn.run(
        "app.main:app",
        host=arguments.host,
        port=arguments.port,
        reload=arguments.reload,
        loop="app.core.event_loop:create_selector_event_loop",
    )


if __name__ == "__main__":
    main()
