import multiprocessing as mp
import threading
from humac_driver.const import *
import xml.etree.ElementTree as ET
from multiprocessing import Queue
import requests
from humac_driver.database.db_client import DbClientFactory
import datetime
import os
from time import time_ns,sleep ,time
import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
class MTConnecte(mp.Process):
    def __init__(self,config,program_event:Queue):
        super().__init__(name=config['edgid'], daemon=True)
        
        # Only store simple picklable data
        self.config = config
        self.ip = config['ip']
        self.port = config['port']
        self.timeout = config['timeout']
        self.edgeid = config['edgid']
        self.machineid = config['machineid']
        self.program_event = program_event
        self.lock = threading.Lock()
        logging.info(f"Starting MTconnecte {self.edgeid}") 
        self.url = f"http://{self.ip}:{self.port}/current"
        self.current_date = datetime.date.today()
        self.downloaded_program = None
        self.last_downloaded = 0
        self.program_state = None
        self.redis=  DbClientFactory.get_client("block")
        self.start()  # Safe now

    def fetch_cnc_data(self,url):
        """Fetch data from the CNC machine."""
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()  # Raise exception for bad status codes
            return response.text
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching data from CNC")
            return None
    
    def parse_mtconnect_xml(self, xml_content):
        """MTConnect XML madhu useful data kadhayche"""
        root = ET.fromstring(xml_content)
        results = {}

        for item in root.iter():
            attribs = item.attrib
            if 'dataItemId' in attribs or 'name' in attribs:
                if attribs.get('name', 'unknown') == "Program":
                    results ={
                        'ts': time_ns() // 1_000_000,
                        'name': attribs.get('name', 'unknown'),
                        'id': attribs.get('dataItemId', ''),
                        'value': item.text.strip() if item.text else 'UNAVAILABLE'
                    }
                elif attribs.get('name','unknown') == "RunStatus":
                    self.program_state = item.text.strip() if item.text else "UNAVAILABLE"
                        

        return results

        

    def run(self) -> None:
        pid = os.getpid()
        try:
            while True:
                    xml_current = self.fetch_cnc_data(self.url)
                    if xml_current :
                        result =self.parse_mtconnect_xml(xml_current)

                        if self.downloaded_program != result.get('value') :
                            self.downloaded_program =  result.get('value')
                            self.last_downloaded = time()
                            self.program_event.put(result)
                            logging.info("program download")
                        elif time()-self.last_downloaded >= 14400:
                            self.last_downloaded = time()
                            self.program_event.put(result)
                            logging.info("program ideal for 4 hr")
                        elif datetime.date.today() != self.current_date:
                            self.current_date = datetime.date.today()
                            self.program_event.put(result)
                            logging.info("date_change")
                        if self.program_state == "ACTIVE" :
                            # self.program_previous_state = self.program_state
                            data = {"ts": time_ns() // 1_000_000 , 
                                    "program_No": self.downloaded_program, 
                                    "edgeid": self.edgeid}
                            self.redis.xadd("block",data)
                            # logging.info(f"state : {data}")
                    sleep(2)
                
        except (Exception, KeyboardInterrupt) as e:
            logging.info(f"[PID {pid}] Connection failed {self.edgeid}: {e}")


    def terminate(self) -> None:
        logging.info(f"Terminating MTConnecte {self.edgeid}")
        super().terminate()