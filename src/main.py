import asyncio
from src.core.database import init_db
from src.utils.logger import get_logger

logger = get_logger(__name__)

async def amain():
    logger.info("Starting KUK2RD backend initialization...")
    await init_db()
    logger.info("Backend initialized.")

def main():
    """CLI entrypoint"""
    asyncio.run(amain())

if __name__ == "__main__":
    main()
