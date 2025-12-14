import pyodbc
import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseManager:
    def __init__(self, config=None):
        if config:
            self.server = config.get('DB_SERVER')
            self.database = config.get('DB_NAME')
            self.username = config.get('DB_USER')
            self.password = config.get('DB_PASSWORD')
        else:
            self.server = os.getenv('DB_SERVER')
            self.database = os.getenv('DB_NAME')
            self.username = os.getenv('DB_USER')
            self.password = os.getenv('DB_PASSWORD')
    
    def get_connection(self):
        try:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={self.server};"
                f"DATABASE={self.database};"
                f"UID={self.username};"
                f"PWD={self.password}"
            )
            conn = pyodbc.connect(conn_str)
            return conn
        except Exception as e:
            print(f"Erro na conexão: {str(e)}")
            return None
    
    def execute_query(self, query, params=None):
        conn = self.get_connection()
        if not conn:
            return None
        
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # Para SELECT
            if query.strip().upper().startswith('SELECT'):
                columns = [column[0] for column in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                return results
            else:
                # Para INSERT, UPDATE, DELETE
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            print(f"Erro na query: {str(e)}")
            return None
        finally:
            conn.close()