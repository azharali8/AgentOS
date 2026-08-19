import logging
from backend.app.config.settings import settings

def setup_logging():
    level = logging.DEBUG if settings.APP_ENV == "development" else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    return logging.getLogger("AgentOS")

logger = setup_logging()
