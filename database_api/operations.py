from sqlalchemy.orm import Session as session_type

from . import Session


def db_session_decorator(func):
  def wrapper(*args, **kwargs):
    if 'session' in kwargs and kwargs['session'] is not None:
      return func(*args, **kwargs)

    with Session() as session:
      response = func(*args, session=session, **kwargs)
      session.commit()
      return response

  wrapper.__name__ = func.__name__
  return wrapper


@db_session_decorator
def create(class_type, params, session: session_type):
  new_instance = class_type(**params)
  session.add(new_instance)
  session.flush()
  session.refresh(new_instance)
  return new_instance


def update(instance, update_params, session=None):
  external_session = session is not None
  if not external_session:
    with Session() as session:
        updated_instance = session.merge(instance)
        for key, value in update_params.items():
          setattr(updated_instance, key, value)
        session.commit()
        session.refresh(updated_instance)
        return updated_instance
  else:
    updated_instance = session.merge(instance)
    for key, value in update_params.items():
      setattr(updated_instance, key, value)
    session.flush()
    session.refresh(updated_instance)
    return updated_instance


def update(instance, update_params):
  with Session() as session:
    updated_instance = session.merge(instance)
    for key, value in update_params.items():
      setattr(updated_instance, key, value)
    session.commit()
    session.refresh(updated_instance)
    return updated_instance


def update_bulk(instances, update_params_list):
  with Session() as session:
    updated_instances = session.merge(instances)
    for updated_instance, update_params in zip(updated_instances, update_params_list):
      for key, value in update_params.items():
        setattr(updated_instance, key, value)
    session.commit()
    return updated_instances


def delete(instance):
  with Session() as session:
    session.delete(instance)
    session.commit()


def delete_bulk(instances):
  with Session() as session:
    for instance in instances:
      session.delete(instance)
    session.commit()


def get_by_id(class_type, instance_id):
  with Session() as session:
    return session.query(class_type).filter(class_type.id == instance_id).first()


def get_by_ids(class_type, instance_ids):
  with Session() as session:
    return session.query(class_type).filter(class_type.id.in_(instance_ids)).all()


def get_all(class_type):
  with Session() as session:
    return session.query(class_type).all()


def get_by_params(class_type, params_list):
  with Session() as session:
    return session.query(class_type).filter(*[getattr(class_type, key) == value for key, value in params_list]).all()