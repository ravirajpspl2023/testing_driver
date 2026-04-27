import redis
import logging
import time
class RedisConnection:
    def __init__(self,stream_name):
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
        self.group_name = "HumacDriver"
        self.stream_name = stream_name
        self.db = 0
        self.host = "192.168.0.3"
        self.port = 6379

    def create_group(self):
        try:
            self.r.xgroup_create(self.stream_name, self.group_name, id='$', mkstream=True)
            logging.info(f"Created consumer group '{self.group_name}' for stream '{self.stream_name}'")
        except redis.exceptions.ResponseError as e:
            pass
    def connect(self):
        try: 
            self.r = redis.Redis(host=self.host, port=self.port, db=self.db ,decode_responses=True)
            self.r.ping()
            logging.info("Successfully connected to Redis")
            self.create_group()
            return self.r
        except Exception as e:
            logging.error(f"Failed to connect to Redis: {e}")
            time.sleep(5)
            self.r = None
            self.connect()
