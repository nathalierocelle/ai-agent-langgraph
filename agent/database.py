import os
from langchain_community.utilities.sql_database import SQLDatabase

def setup_db():
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rental.db")
    return SQLDatabase.from_uri(f"sqlite:///{db_path}")