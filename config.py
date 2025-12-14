import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Configurações do banco de dados
    DB_SERVER = os.getenv('DB_SERVER', 'localhost')
    DB_NAME = os.getenv('DB_NAME', 'DMD')
    DB_USER = os.getenv('DB_USER', 'sa')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'arte171721')
    
    # Outras configurações
    DEBUG = True