import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Suppress SQLAlchemy warnings
import warnings
from sqlalchemy import exc as sa_exc
warnings.filterwarnings('ignore', 
    category=sa_exc.SAWarning, 
    message='Cannot correctly sort tables.*'
)

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')