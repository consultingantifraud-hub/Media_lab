import os, sys
os.environ[DATABASE_URL] = postgresql://media_lab_user:media_lab_password_change_me@127.0.0.1:5432/media_lab
sys.path.insert(0, /opt/media-lab)
from app.db.base import init_db
init_db()
print( Tables created successfully!)
