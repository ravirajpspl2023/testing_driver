
import multiprocessing as mp
from humac_driver.machines.machine import Machine
from humac_driver.machines.HASS.HASS_Driver import HassDriver
import logging
from functools import partial
from typing import  Dict, Any
from humac_driver.const import *
from humac_driver.mqtt_publisher import MqttPublisher

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class HumacDriver(object):
    def __init__(self,):
        self.machines_list = config.get('machines',None)
        self.machines = []
        self.streams = ['program','block','trigger']
        self.connecte_with_machine()
        # self.waiting()

    def connecte_with_machine(self,):
        if self.machines_list:
            for machi in self.machines_list:
                for machine,config in machi.items():
                    if machine == 'fanuc':
                        m=Machine(config=config)
                        self.machines.append(m)
                    elif machine == 'hass':
                        m=HassDriver(config)
                        self.machines.append(m)
        for stream in self.streams:
            mqtt_publisher = MqttPublisher(stream)
            self.machines.append(mqtt_publisher)
                
                
    def waiting(self,):
        if self.machines:
            for m in self.machines:
                m.join()
    
    def stop_all_machines(self,):
        if self.machines:
            for m in self.machines:
                m.terminate()
