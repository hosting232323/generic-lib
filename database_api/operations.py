from sqlalchemy.orm import Session as session_type

from . import Session


def db_session_decorator(commit=False):
  def decorator(func):
    def wrapper(*args, **kwargs):
      if 'session' in kwargs and kwargs['session'] is not None:
        return func(*args, **kwargs)

      with Session() as session:
        result = func(*args, session=session, **kwargs)
        if commit:
          session.commit()
        return result

    wrapper.__name__ = func.__name__
    return wrapper

  return decorator


@db_session_decorator(commit=True)
def create(class_type, params, session: session_type = None):
  new_instance = class_type(**params)
  session.add(new_instance)
  session.flush()
  session.refresh(new_instance)
  return new_instance


@db_session_decorator(commit=True)
def create_bulk(class_type, params_list, session: session_type = None):
  new_instances = [class_type(**params) for params in params_list]
  session.add_all(new_instances)
  session.flush()
  return [session.refresh(obj) for obj in new_instances]


@db_session_decorator(commit=True)
def update(instance, update_params: dict, session: session_type = None):
  instance = session.merge(instance)
  for key, value in update_params.items():
    setattr(instance, key, value)
  session.flush()
  session.refresh(instance)
  return instance


@db_session_decorator(commit=True)
def update_bulk(instances, update_params_list: list[dict], session: session_type = None):
  merged_instances = [session.merge(i) for i in instances]
  for instance, update_params in zip(merged_instances, update_params_list):
    for key, value in update_params.items():
      setattr(instance, key, value)
  session.flush()
  for obj in merged_instances:
    session.refresh(obj)
  return merged_instances


@db_session_decorator(commit=True)
def delete(instance, session: session_type = None):
  session.delete(instance)


@db_session_decorator(commit=True)
def delete_bulk(instances, session: session_type = None):
  for instance in instances:
    session.delete(instance)


@db_session_decorator(commit=False)
def get_by_id(class_type, instance_id, session: session_type = None):
  return session.query(class_type).filter(class_type.id == instance_id).first()


@db_session_decorator(commit=False)
def get_by_ids(class_type, instance_ids, session: session_type = None):
  return session.query(class_type).filter(class_type.id.in_(instance_ids)).all()


@db_session_decorator(commit=False)
def get_all(class_type, session: session_type = None):
  return session.query(class_type).all()


@db_session_decorator(commit=False)
def get_by_params(class_type, params_list, session: session_type = None):
  return session.query(class_type).filter(*[getattr(class_type, key) == value for key, value in params_list]).all()
