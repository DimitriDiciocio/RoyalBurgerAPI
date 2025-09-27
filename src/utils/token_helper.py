import secrets  
import datetime  
from ..database import get_db_connection  
import fdb  

def generate_secure_token(length=32):  
    return secrets.token_urlsafe(length)  
