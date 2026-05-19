import logging
from pathlib import Path


class LoggerFactory:
    def __init__(self, log_dir: str, level: str = "INFO"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.level = getattr(logging, level.upper(), logging.INFO)

    def get_logger(self, name: str, filename: str) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(self.level)
        logger.propagate = False

        target_path = self.log_dir / filename
        if not any(getattr(handler, "baseFilename", None) == str(target_path) for handler in logger.handlers):
            handler = logging.FileHandler(target_path)
            handler.setLevel(self.level)
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
            logger.addHandler(handler)

        return logger
