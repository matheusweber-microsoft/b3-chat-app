import logging
import os
from opencensus.ext.azure.log_exporter import AzureLogHandler

class Logger:
    def __init__(self):
        self.logger = logging.getLogger()
        if not self.logger.handlers:
            log_level = os.getenv('APP_LOG_LEVEL', 'INFO')
            self.logger.setLevel(getattr(logging, log_level))
            handler = AzureLogHandler(connection_string=os.getenv('CONNECTION_STRING_APPLICATION_INSIGHTS'))
            formatter = logging.Formatter('%(filename)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def info(self, message):
        self.logger.info(message)

    def error(self, message):
        self.logger.error(message)

    def warning(self, message):
        self.logger.warning(message)