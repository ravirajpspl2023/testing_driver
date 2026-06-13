import logging
from humac_driver.const import DATABASE_TYPE

class DbClientFactory:
    @staticmethod
    def get_client(stream_name):
        db_type = DATABASE_TYPE.lower()
        if db_type == 'sqlite':
            from humac_driver.database.sqlite_client import SqliteConnection
            return SqliteConnection(stream_name).connect()
        if db_type == 'redis':
            from humac_driver.database.redis_client import RedisConnection
            return RedisConnection(stream_name).connect()
        raise ValueError(f"Unsupported database type: {DATABASE_TYPE}")
