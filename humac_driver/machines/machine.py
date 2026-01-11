import multiprocessing as mp
import threading
from humac_driver.machines.fanuc_driver.focas_driver import FocasDriver
from humac_driver.mqtt_client import MqttSender
from multiprocessing import Queue
import os
import time
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
class Machine(mp.Process):
    def __init__(
        self,
        ip: str,
        edgeId :str,
        port: int = 8193,
        timeout: float = 0.5,
        daemon: bool = False,
    ):
        super().__init__(name=edgeId, daemon=daemon)
        
        # Only store simple picklable data
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.event_queue = Queue(maxsize=1024000)
        self.lock = threading.Lock()
        self.mqtt_sender = MqttSender()
        self.edgeid = edgeId
        self.driver = None
        logging.info(f"Starting machine with {edgeId}") 
        self.start()  # Safe now
    def run(self) -> None:
        pid = os.getpid()
        self.driver = FocasDriver(self.ip,self.port,self.timeout,self.mqtt_sender)
        try:
            handle = self.driver.connect()
            while True:
                result = self.driver.poll(handle)
                if result.get('get_cnc_programe',{}).get('program',None):
                    with self.lock:
                        self.event_queue.put_nowait(result)
                start_time = time.time()
                while time.time() - start_time < 1:
                    pass
        except Exception or  KeyboardInterrupt as e :
            logging.info(f"[PID {pid}] Connection failed {self.edgeid}: {e}")
        self.driver.disconnect()
        self.mqtt_sender.stop()

    def terminate(self) -> None:
        logging.info(f"Terminating machine {self.edgeid}")
        self.driver.disconnect()
        self.mqtt_sender.stop()
        super().terminate()
    

