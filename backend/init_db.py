#!/usr/bin/env python3
"""初始化 mammoth_agent 数据库和表结构。"""
import asyncio
import sys
from pathlib import Path

import asyncpg

DB_HOST = "127.0.0.1"
DB_PORT = 5434
DB_USER = "oakclaw"
DB_PASSWORD = "oakclaw_password"
DB_NAME = "mammoth_agent"


async def init_db():
    conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database="oakclaw"
    )
    exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", DB_NAME)
    if not exists:
        await conn.execute(f'CREATE DATABASE "{DB_NAME}"')
        print(f"✓ 数据库 {DB_NAME} 已创建")
    else:
        print(f"✓ 数据库 {DB_NAME} 已存在")
    await conn.close()

    sys.path.insert(0, str(Path(__file__).parent))
    from database import engine
    from models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✓ 表结构已就绪 (sessions, messages)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
