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
from humac_driver.database.db_client import DbClientFactory
from multiprocessing import Queue
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

class BlockThread(threading.Thread):
    def __init__(self,config):
        super().__init__()
        self.ip = config['ip']
        self.port = config['port']
        self.timeout = config['timeout']
        self.edgeid = config['edgid']
        self.handle = None
        self._stop_event = threading.Event()
        self.redis=  DbClientFactory.get_client("block")
        self.drive = "DATA_SV"
        self.previous_block = -1
        self.blk_no = c_long()
        self.start()

    def connect(self,):
        start_time = time.time()
        logging.info(f"connection start {self.ip} | WithTimeOut:{self.timeout} ")
        if fwlib:
            if sys.platform == 'linux':
                fwlib.cnc_startupprocess.restype = c_short
                fwlib.cnc_startupprocess.argtypes = [c_short, c_char_p]
                log_file = b"focas.log"
                init_ret = fwlib.cnc_startupprocess(3, log_file)
                if init_ret != 0:
                    logging.error(f"FOCAS init failed with code: {init_ret}")
            
            func = fwlib.cnc_allclibhndl3
            func.argtypes = [
                c_char_p,           # IP address (string)
                c_ushort,           # Port number
                c_long,             # Timeout
                ctypes.POINTER(c_ushort)  # Handle pointer
            ]
            func.restype = c_short
            
            ip_bytes = self.ip.encode('utf-8')
            handle = c_ushort(0)            
            result = func(ip_bytes, self.port, self.timeout, byref(handle)) 
           # FocasExceptionRaiser(result, context=self)
           
            if result != 0 :
                time.sleep(10)  # Wait a moment before retrying
                self.connect() 
            elapsed = time.time() - start_time
            self.handle = handle.value
            logging.info(f"Connection {self.ip} result: {result} | Handle: {handle.value} | RequTime:{elapsed:.2f}s")
        return
    
    def get_gcode_program(self):

        func = fwlib.cnc_exeprgname
        func.restype = c_short
        programe = ODBEXEPRG()
        result = func(self.handle, byref(programe))
        programe.__dict__

        fanuc = fwlib.cnc_rdblkcount
        result = fanuc(self.handle,byref(self.blk_no))
        
        # fanuc = fwlib.cnc_rdactpt
        # fanuc.restype = c_short
        # result = fanuc(self.handle,byref(self.prog_no),byref(self.blk_no))

        if result != 0 :
            self.connect()
            time.sleep(1)
    def program_name(self,device_name="DATA_SV"):
        host_number = ctypes.c_short(0)                     # short *host sathi
        file_name_buffer = ctypes.create_string_buffer(256)
        ret = fwlib.cnc_rddsdncfile(
                self.handle, 
                device_name.encode('utf-8'), 
                ctypes.byref(host_number), 
                file_name_buffer
            )
        if ret == 0:
                dnc_file = file_name_buffer.value.decode('utf-8', errors='ignore').rstrip('\x00').split('/')[-1]  # Get the file name without path
                return dnc_file
        
        return None

    def run(self):
        self.connect()
        start_time = time.perf_counter()
        while not self._stop_event.is_set():
            if self.handle: 
                self.get_gcode_program()
                if self.previous_block != self.blk_no.value:
                    gcode_data = {"ts": time.time_ns() // 1_000_000}
                    gcode_data['time'] = round(time.perf_counter()-start_time, 4)
                    start_time= time.perf_counter()
                    gcode_data['block_No'] = self.blk_no.value
                    gcode_data['program_No'] = CNC.PROGRAME_NAME
                    # gcode_data['program_No'] = self.program_name()
                    gcode_data['edgeid'] = self.edgeid
                    self.previous_block = self.blk_no.value
                    # logging.info(f"{gcode_data}")
                    self.redis.xadd("block",gcode_data)

    def stop(self):
        if self.handle != -16 or self.handle is not None:
            fwlib.cnc_freelibhndl(self.handle)
        self._stop_event.set()