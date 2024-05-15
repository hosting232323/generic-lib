# Generic Lib

Build command: `python -m build`

## Setup Project

```bash
python -m venv venv

.\venv\Scripts\activate

pip install generic_lib-x.x.x.tar.gz

setup_project
```

## Api

```python
from api import send_mail
```

## Database api

```python
from database_api import Session, set_database
from database_api.operations import create, update, delete, get_by_id
```
