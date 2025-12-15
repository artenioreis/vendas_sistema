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
            if query.strip().upper().startswith('SELECT') or query.strip().upper().startswith('WITH'):
                if cursor.description:
                    columns = [column[0] for column in cursor.description]
                    results = []
                    for row in cursor.fetchall():
                        results.append(dict(zip(columns, row)))
                    return results
                return []
            else:
                # Para INSERT, UPDATE, DELETE
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            print(f"Erro na query: {str(e)}")
            return None
        finally:
            conn.close()

    # --- Métodos de Gestão de Usuários ---

    def get_user_by_username(self, username):
        query = "SELECT * FROM USUARIOS_SISTEMA WHERE username = ?"
        results = self.execute_query(query, (username,))
        return results[0] if results else None

    def get_user_by_id(self, user_id):
        query = "SELECT * FROM USUARIOS_SISTEMA WHERE id = ?"
        results = self.execute_query(query, (user_id,))
        return results[0] if results else None

    def create_user(self, username, password_hash, role, codigo_vendedor=None):
        query = """
        INSERT INTO USUARIOS_SISTEMA (username, password_hash, role, codigo_vendedor)
        VALUES (?, ?, ?, ?)
        """
        return self.execute_query(query, (username, password_hash, role, codigo_vendedor))

    def delete_user(self, user_id):
        query = "DELETE FROM USUARIOS_SISTEMA WHERE id = ?"
        return self.execute_query(query, (user_id,))
    
    def get_all_users(self):
        query = "SELECT * FROM USUARIOS_SISTEMA ORDER BY username"
        return self.execute_query(query)