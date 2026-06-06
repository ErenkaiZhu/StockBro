from __future__ import annotations

import logging
from pathlib import Path

try:
    from colorama import Fore, Style
except ImportError:
    class _NoColor:
        CYAN = ""
        GREEN = ""
        YELLOW = ""
        RED = ""
        BRIGHT = ""
        RESET_ALL = ""

    Fore = _NoColor()
    Style = _NoColor()


class ColoredFormatter(logging.Formatter):
    levelname_color = {
        "DEBUG": Fore.CYAN + Style.BRIGHT,
        "INFO": Fore.GREEN + Style.BRIGHT,
        "WARNING": Fore.YELLOW + Style.BRIGHT,
        "ERROR": Fore.RED + Style.BRIGHT,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        message = super().format(record)
        if record.levelname in self.levelname_color:
            return self.levelname_color[record.levelname] + message + Style.RESET_ALL
        return message


class CustomLogger:
    def __init__(self, log_file: str = "log/test.txt"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("Stocklogger")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        if not self.logger.handlers:
            self._add_handlers()

    def set_level(self, level_name: str) -> None:
        level = getattr(logging, level_name.upper())
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)

    def _add_handlers(self) -> None:
        plain_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        file_handler = logging.FileHandler(self.log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(plain_formatter)
        self.logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(ColoredFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        self.logger.addHandler(console_handler)


log = CustomLogger()
