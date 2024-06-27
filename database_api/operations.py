from . import Session


def create(class_type, params):
  with Session() as session:
    new_instance = class_type(**params)
    session.add(new_instance)
    session.commit()
    session.refresh(new_instance)
    return new_instance


def update(instance, update_params):
  with Session() as session:
    updated_instance = session.merge(instance)
    for key, value in update_params.items():
      setattr(updated_instance, key, value)
    session.commit()
    session.refresh(updated_instance)
    return updated_instance


def delete(instance):
  with Session() as session:
    session.delete(instance)
    session.commit()


def get_by_id(class_type, instance_id):
  with Session() as session:
    return session.query(class_type).filter(
      class_type.id == instance_id
    ).first()


def create_bulk(class_type, params_list):
    with Session() as session:
        """Create multiple entries in a single session."""
        instances = [class_type(**params) for params in params_list]
        session.bulk_save_objects(instances)
        session.commit()
        return instances
