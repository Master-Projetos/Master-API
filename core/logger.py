import logging


class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: '\033[36m',
        logging.INFO: '\033[32m',
        logging.WARNING: '\033[33m',
        logging.ERROR: '\033[31m',
        logging.CRITICAL: '\033[41m',
    }
    RESET = '\033[0m'

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        record.levelname = f'{color}{record.levelname}{self.RESET}'
        return super().format(record)


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(
        ColorFormatter(
            '%(asctime)s - %(levelname)s - %(filename)s - %(funcName)s - %(message)s'
        )
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler])
