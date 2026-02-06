import sqlite3
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import contextmanager


class DatabaseManager:
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.env = self.config.get("env", "local")
        self.db_config = self.config["database"][self.env]
        self.connection = None
        
    def _load_config(self) -> Dict[str, Any]:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def connect(self):
        if self.db_config["type"] == "sqlite":
            db_path = Path(self.db_config["path"])
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(str(db_path), check_same_thread=False)
            self.connection.row_factory = sqlite3.Row
        elif self.db_config["type"] == "mysql":
            import pymysql
            self.connection = pymysql.connect(
                host=self.db_config["host"],
                port=self.db_config["port"],
                user=self.db_config["user"],
                password=self.db_config["password"],
                database=self.db_config["database"],
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor
            )
        else:
            raise ValueError(f"Unsupported database type: {self.db_config['type']}")
        
        return self.connection
    
    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None
    
    @contextmanager
    def get_connection(self):
        try:
            if not self.connection:
                self.connect()
            yield self.connection
        finally:
            pass
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if query.strip().upper().startswith("SELECT"):
                    if self.db_config["type"] == "sqlite":
                        return [dict(row) for row in cursor.fetchall()]
                    else:
                        return cursor.fetchall()
                else:
                    conn.commit()
                    return []
            finally:
                cursor.close()
    
    def execute_many(self, query: str, params_list: List[tuple]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(query, params_list)
                conn.commit()
            finally:
                cursor.close()
    
    def init_tables(self):
        if self.db_config["type"] == "sqlite":
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS weight_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                measured_at TIMESTAMP NOT NULL,
                weight_kg REAL NOT NULL,
                raw_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        else:
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS weight_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                measured_at DATETIME NOT NULL,
                weight_kg DECIMAL(5,2) NOT NULL,
                raw_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_user_measured (user_id, measured_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        
        self.execute_query(create_table_sql)
        
        if self.db_config["type"] == "sqlite":
            create_oura_table_sql = """
            CREATE TABLE IF NOT EXISTS oura_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                measured_at TIMESTAMP NOT NULL,
                activity_score INTEGER,
                sleep_score INTEGER,
                readiness_score INTEGER,
                steps INTEGER,
                total_sleep_duration INTEGER,
                raw_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        else:
            create_oura_table_sql = """
            CREATE TABLE IF NOT EXISTS oura_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                measured_at DATETIME NOT NULL,
                activity_score INT,
                sleep_score INT,
                readiness_score INT,
                steps INT,
                total_sleep_duration INT,
                raw_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_user_measured (user_id, measured_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        
        self.execute_query(create_oura_table_sql)
        
    def insert_weight_data(self, user_id: str, measured_at: str, weight_kg: float, raw_data: str):
        query = """
        INSERT INTO weight_data (user_id, measured_at, weight_kg, raw_data)
        VALUES (?, ?, ?, ?)
        """ if self.db_config["type"] == "sqlite" else """
        INSERT INTO weight_data (user_id, measured_at, weight_kg, raw_data)
        VALUES (%s, %s, %s, %s)
        """
        
        self.execute_query(query, (user_id, measured_at, weight_kg, raw_data))
    
    def get_weight_data(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if user_id:
            query = """
            SELECT * FROM weight_data 
            WHERE user_id = ? 
            ORDER BY measured_at DESC 
            LIMIT ?
            """ if self.db_config["type"] == "sqlite" else """
            SELECT * FROM weight_data 
            WHERE user_id = %s 
            ORDER BY measured_at DESC 
            LIMIT %s
            """
            return self.execute_query(query, (user_id, limit))
        else:
            query = """
            SELECT * FROM weight_data 
            ORDER BY measured_at DESC 
            LIMIT ?
            """ if self.db_config["type"] == "sqlite" else """
            SELECT * FROM weight_data 
            ORDER BY measured_at DESC 
            LIMIT %s
            """
            return self.execute_query(query, (limit,))
    
    def insert_oura_data(self, user_id: str, measured_at: str, activity_score: Optional[int], 
                        sleep_score: Optional[int], readiness_score: Optional[int], 
                        steps: Optional[int], total_sleep_duration: Optional[int], raw_data: str):
        query = """
        INSERT INTO oura_data (user_id, measured_at, activity_score, sleep_score, readiness_score, steps, total_sleep_duration, raw_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """ if self.db_config["type"] == "sqlite" else """
        INSERT INTO oura_data (user_id, measured_at, activity_score, sleep_score, readiness_score, steps, total_sleep_duration, raw_data)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        self.execute_query(query, (user_id, measured_at, activity_score, sleep_score, readiness_score, steps, total_sleep_duration, raw_data))
    
    def get_oura_data(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if user_id:
            query = """
            SELECT * FROM oura_data 
            WHERE user_id = ? 
            ORDER BY measured_at DESC 
            LIMIT ?
            """ if self.db_config["type"] == "sqlite" else """
            SELECT * FROM oura_data 
            WHERE user_id = %s 
            ORDER BY measured_at DESC 
            LIMIT %s
            """
            return self.execute_query(query, (user_id, limit))
        else:
            query = """
            SELECT * FROM oura_data 
            ORDER BY measured_at DESC 
            LIMIT ?
            """ if self.db_config["type"] == "sqlite" else """
            SELECT * FROM oura_data 
            ORDER BY measured_at DESC 
            LIMIT %s
            """
            return self.execute_query(query, (limit,))
