from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.core.database import init_db
from src.utils.logger import get_logger
from src.api.routes import router

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting KUK2RD backend initialization...")
    await init_db()
    logger.info("Backend initialized.")
    yield
    logger.info("Shutting down KUK2RD backend...")

app = FastAPI(
    title="KUK2RD API",
    description="Knowledge Extraction System API",
    version="0.1.0",
    lifespan=lifespan
)

app.include_router(router)

def main():
    """CLI entrypoint"""
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()
