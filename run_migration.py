from alembic.config import Config
from alembic import command
from app.core.config import settings
import os

# Ensure PYTHONPATH includes current dir for app.models
os.environ["PYTHONPATH"] = os.getcwd()

alembic_cfg = Config("alembic.ini")
try:
    command.upgrade(alembic_cfg, "head")
    print("Migration successful!")
except Exception as e:
    import traceback
    traceback.print_exc()
