import os
from sqlalchemy import Column, String

from database_api import Session, BaseEntity


SESSION_HOURS = int(os.environ.get('SESSION_HOURS', 5))
DECODE_JWT_TOKEN = os.getenv('DECODE_JWT_TOKEN')
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')


class User(BaseEntity):
  __abstract__ = True

  password = Column(String)
  pass_token = Column(String)
  email = Column(String, unique=True, nullable=False)


def get_user_by_email(email: str) -> User:
  sub_class = User.__subclasses__()[0]
  with Session() as session:
    return session.query(sub_class).filter(sub_class.email == email).first()


def get_user_by_pass_token(pass_token: str) -> User:
  sub_class = User.__subclasses__()[0]
  with Session() as session:
    return session.query(sub_class).filter(sub_class.pass_token == pass_token).first()
