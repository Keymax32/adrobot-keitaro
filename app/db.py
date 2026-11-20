import os
from dotenv import load_dotenv
from sqlalchemy import JSON, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///adrobot.db"), connect_args={"timeout": 30})


class Base(DeclarativeBase):
    pass


class Stream(Base):
    __tablename__ = "streams"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    campaign_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer)
    editable: Mapped[bool]
    version: Mapped[int]
    # Ordered snapshots include local pin flags and archived bindings.
    published: Mapped[list] = mapped_column(JSON)
    draft: Mapped[list] = mapped_column(JSON)

