from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# pool_pre_ping: test a pooled connection before handing it out. Neon suspends
# an idle compute (free tier: after ~5 min) and closes its connections; without
# the ping, the first request after a quiet spell fails with "server closed
# the connection unexpectedly", masked on the public API as an empty map.
# Cost: one round trip per checkout (~1 ms with the function next to Neon).
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
