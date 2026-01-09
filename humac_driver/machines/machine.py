import multiprocessing as mp
from humac_driver.machines.fanuc_driver.focas_driver import FocasDriver
from humac_driver.mqtt_client import MqttSender
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
                    while self.mqtt_sender.connected is False:
                        pass
                    self.mqtt_sender.publish_data({"get_cnc_programe": {"ts": 1767947673360, "name": "O21", "program": ["%\nO0021(FLAT PROGRAM)\nN1 \nG0G91G28Z.0\nG0G90G55X-665.5Y0.0\nG0G43Z200.0\nS1200M03 \nM08\nG0Z5.0 \nG01Z0.0F500\nG01Z-2.0F300 \nG01Y90.0F300 \nG0Z0.0 \nG0Y0.0 \nG01Z-3.5F300 \nG01Y90.0F300 \nG0Z0.0 \nG0Y0.0 \nG01Z-4.5F300 \nG01Y90.0F300 \nG0Z0.0 \nG0Y0.0 \nG01Z-4.99F300\nG01Y15", "0.0F300\nG0G80G40Z200.0 \nM05\nM09\nG0G91G28Z0.0Y0.0 \nM30\n \nG0Z0.0 \nG0Y0.0 \nG01Z-5.0 \nG01Y110.0\nG0Z0.0 \nG0Y0.0 \nG01Z-6.5 \nG01Y120.0\nG0Z0.0 \nG0Y0.0 \nG01Z-6.975 \nG01Y150.0\nG0Z0.0 \nM09\nG0G80G40Z100.0 \nM05\nM09\nG0G91G28Y0.0Z0.0 \nM30\n%0 \nG0Y0.0 \nG01Z-4.99F300\nG01Y15"], "time": 0.0931}, "poll_time": 0.0932})
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
    

