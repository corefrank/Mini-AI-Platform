"""首次启动时初始化表和测试账号。重复运行保留已有设置。"""
import os

from sqlalchemy import select

from .common import jwt_secret, passwords
from .db import Base, ModelConfig, Session, User, engine

DEFAULT_MODELS = [
    ("GPT-4o mini", "openai/gpt-4o-mini"),
    ("Gemini 2.5 Flash-Lite", "google/gemini-2.5-flash-lite"),
]


def seed():
    jwt_secret()
    password = os.getenv("DEMO_PASSWORD", "")
    if not 10 <= len(password) <= 128 or password.startswith("replace"):
        raise RuntimeError("请在 .env 中设置 DEMO_PASSWORD（10–128 字符）")
    Base.metadata.create_all(engine)
    with Session.begin() as db:
        for name, role in [("admin", "admin"), ("alice", "user"), ("bob", "user")]:
            if not db.scalar(select(User).where(User.username == name)):
                db.add(User(username=name, role=role, password_hash=passwords.hash(password)))
        for label, model in DEFAULT_MODELS:
            if not db.scalar(select(ModelConfig).where(ModelConfig.label == label)):
                db.add(ModelConfig(label=label, model=model, temperature=0.2, max_tokens=1200))


if __name__ == "__main__":
    seed()
