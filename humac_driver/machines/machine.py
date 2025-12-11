import multiprocessing as mp
from humac_driver.machines.fanuc_driver.focas_driver import FocasDriver
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
        self.edgeid = edgeId
        self.driver = None
        logging.info(f"Starting machine with {edgeId}") 
        self.start()  # Safe now
    def run(self) -> None:
        pid = os.getpid()
        self.driver = FocasDriver(self.ip,self.port,self.timeout)
        try:
            handle = self.driver.connect()
            while True:
                result = self.driver.poll(handle)
                logging.info(result)
        except Exception as e:
            logging.info(f"[PID {pid}] Connection failed {self.edgeid}: {e}")
        self.driver.disconnect()

    def terminate(self) -> None:
        logging.info(f"Terminating machine {self.edgeid}")
        self.driver.disconnect()
        super().terminate()
    

