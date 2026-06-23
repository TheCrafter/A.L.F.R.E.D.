import logging
import os

import uvicorn
from dotenv import dotenv_values

from .config import Settings, bootstrap_config
from .server import create_app


def load_settings(*, bootstrap: bool = True) -> Settings:
    if bootstrap:
        # Seed config.toml from the dev .env merged under the real environment
        # (os.environ wins). This migrates an existing .env-based setup into the
        # config file on first run — important because reload reads config.toml,
        # not the dev .env, so the keys must live in the file.
        seed = {**dotenv_values(".env"), **os.environ}
        bootstrap_config(env=seed)
    return Settings()


def main() -> None:
    settings = load_settings()
    # Configure app logging so alfred_brain.* INFO logs (e.g. memory extraction)
    # are emitted — uvicorn only configures its own loggers, leaving ours silent.
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("alfred_brain").setLevel(settings.log_level)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
