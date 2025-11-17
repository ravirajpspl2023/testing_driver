
import multiprocessing as mp
from humac_driver.machines.machine import Machine
import time 
import logging
from functools import partial
from typing import  Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class HumacDriver(object):
    def __init__(self, config):
        self.config = config
        self.machines_list = config.get('machines',None)
        self.machines = []
        self.connecte_with_machine()
        # self.waiting()

    def connecte_with_machine(self,):
        if self.machines_list:
            for machi in self.machines_list:
                m=Machine(ip = machi.get('ip'),port =machi.get('port'),timeout=machi.get('timeout'),edgeId=machi.get('edgid'))
                self.machines.append(m)
    def waiting(self,):
        if self.machines:
            for m in self.machines:
                m.join()

