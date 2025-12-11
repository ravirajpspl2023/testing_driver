import threading

import sys
import ctypes
from ctypes.util import find_library
from ctypes import *
import multiprocessing as mp
import time 
from functools import partial
from typing import  Dict, Any
from humac_driver.machines.fanuc_driver.Fwlib32_h import *
from humac_driver.machines.fanuc_driver.Exceptions import *
import logging
from humac_driver.const import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
extradlls=[]
fwlib = None
if sys.platform =="win32":
    try:
        fwlib = find_library(f"{WIN_BASE_PATH_LIB}/{FILE_NAME_WIN}")
        fwlib =ctypes.windll.LoadLibrary(fwlib)
        for extradll in EXTRA_LIB:
            extradll = find_library(f"{WIN_BASE_PATH_LIB}/{extradll}")
            extradlls.append(ctypes.windll.LoadLibrary(extradll))
    except OSError as e:
        logging.error(f"{FILE_NAME_WIN}:{e}")
        fwlib= None
if sys.platform == 'linux':
    try:
        # fwlib = find_library(f"{BASE_PATH_LIB}/{FILE_NAME_LIN}")
        file_path = f"{LIN_BASE_PATH_LIB}/{FILE_NAME_LIN}"
        fwlib = ctypes.CDLL(file_path)
        for extradll in extradlls:
            extradll=f"{LIN_BASE_PATH_LIB}/{extradll}"
            extradlls.append(ctypes.CDLL(extradll))
    except OSError as e:
        logging.error(f"{FILE_NAME_LIN}:{e}")
        fwlib= None

class GcodeThread(threading.Thread):
    def __init__(self, GcodeProgram : mp.Queue, handle=None):
        super().__init__()
        self.GcodeProgram = GcodeProgram
        self.lock = threading.Lock()
        self.handle = handle
        self._stop_event = threading.Event()

    def get_gcode_program(self,handle):
        data = {"ts": time.time_ns() // 1_000_000}
        start_time= time.perf_counter()
        fanuc = fwlib.cnc_rdblkcount
        fanuc.restype = c_short
        block_count = c_long()
        result = fanuc(handle,byref(block_count))
        end_time = time.perf_counter()
        data.update({'block_count':block_count.value})
        data['time'] = end_time-start_time
        return data

    def run(self):
        while not self._stop_event.is_set():
            if self.handle:
                gcode_data = self.get_gcode_program(self.handle)
                with self.lock:
                    self.GcodeProgram.put(gcode_data)
            time.sleep(0.01)  # Polling interval

    def stop(self):
        self._stop_event.set()