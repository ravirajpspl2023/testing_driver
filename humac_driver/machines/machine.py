import multiprocessing as mp
import threading
from humac_driver.machines.fanuc_driver.Fwlib32_h import *
from humac_driver.machines.fanuc_driver.focas_driver import FocasDriver
from humac_driver.const import *
import datetime
import os
import time
import logging
logging.basicConfig(level="machine", format='%(levelname)s - %(message)s')
class Machine(mp.Process):
    def __init__(self,config):
        super().__init__(name=config['edgid'], daemon=True)
        
        # Only store simple picklable data
        self.config = config
        self.ip = config['ip']
        self.port = config['port']
        self.timeout = config['timeout']
        self.edgeid = config['edgid']
        self.machineid = config['machineid']
        self.driver = None
        logging.info(f"Starting machine with {self.edgeid}") 
        self.SubPgrogram = []
        self.MainProgram = None
        self.main_program_run_time = 0
        self.current_date = datetime.date.today()
        self.start()  # Safe now
    def run(self) -> None:
        pid = os.getpid()
        self.driver = FocasDriver(self.config)
        try:           
            # programs = self.driver.get_cnc_program_details_ascii()
            # self.driver.get_all_program_names()
            # self.driver.get_current_ds_path()
            # self.driver.get_dnc_diagnosis()
            self.driver.list_dataserver_files()
            self.driver.check_m198_directory()
            # self.driver.check_execution_vs_main()
            # self.driver.get_hint_from_exec_block()

            # self.driver.search_text_in_dataserver()


            while True:
                data = self.driver.get_cnc_program_detais()
                start_time = time.time()
                if self.MainProgram != data.get('mdata'):
                    self.main_program_run_time = time.time()
                    self.MainProgram =data.get('mdata')
                    self.driver.poll()
                    logging.info(f"download main program:{data.get('mdata')}")
                if data.get('data') not in self.SubPgrogram and data.get('mdata') != data.get('data') :
                    self.SubPgrogram.append(data.get('data'))
                    self.driver.poll()
                    logging.info(f"download sub-program:{data.get('data')}")
                if self.current_date !=  datetime.date.today() :
                    self.current_date = datetime.date.today()
                    self.driver.poll()
                    logging.info(f"Date changed: {self.current_date}")
                if time.time()-self.main_program_run_time >= 14400:
                    self.main_program_run_time = time.time()
                    self.driver.poll()
                    logging.info(f'machine is ideal up to 4 h')
                while time.time()-start_time <= 0.5:
                    pass
                
        except Exception or  KeyboardInterrupt as e :
            logging.info(f"[PID {pid}] Connection failed {self.edgeid}: {e}")
        self.driver.disconnect()

    def terminate(self) -> None:
        logging.info(f"Terminating machine {self.edgeid}")
        self.driver.disconnect()
        super().terminate()
    

