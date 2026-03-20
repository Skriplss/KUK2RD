import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import JSON, String, Integer
from src.utils.logger import get_logger
from src.core.config import settings

logger = get_logger(__name__)

DATABASE_URL = settings.database_url
if "postgresql" in DATABASE_URL and "asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql", "postgresql+asyncpg")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

class KnowledgeObject(Base):
    __tablename__ = "knowledge_objects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    category: Mapped[str] = mapped_column(String, index=True)
    data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="PENDING") # PENDING / APPROVED

async def init_db():
    async with engine.begin() as conn:
        logger.info("Initializing database schema...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema initialized.")

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
