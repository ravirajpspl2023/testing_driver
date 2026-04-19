import sys
import ctypes
from ctypes.util import find_library
from ctypes import *
import time 
from functools import partial
from typing import  Dict, Any
from humac_driver.machines.fanuc_driver.Fwlib32_h import *
from humac_driver.machines.fanuc_driver.Exceptions import *
from humac_driver.machines.fanuc_driver.Gblock_thread import BlockThread
import threading
import datetime
import logging
from  multiprocessing  import Queue
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


class FocasDriver(object):
    def __init__(self,config,block_queue=Queue ,event_queue=Queue):
        self.ip = config['ip']
        self.port = config['port']
        self.timeout = config['timeout']
        self.handle = None
        self.previous_program_number = None
        self.edgeid = config['edgid']
        self.previous_date = None
        self.lock = threading.Lock()
        self.block_thread = BlockThread(config,block_queue) 
        self.event_queue = event_queue
    
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
            elapsed = time.time() - start_time

            if result == -16:
                time.sleep(10)  # Wait a moment before retrying
                self.connect()
            logging.info(f"Connection {self.ip} result: {result} | Handle: {handle.value} | RequTime:{elapsed:.2f}s")
        return handle.value

    def get_cnc_programe(self, handle):
        try:
            data = {"ts": time.time_ns() // 1_000_000}
            start_time = time.perf_counter()
            program_content = []

            fanuc = fwlib.cnc_pdf_rdmain
            fanuc.restype = c_short
            buf = ctypes.create_string_buffer(244)
            result = fanuc(handle,byref(buf))
            
            if result == 0 :
                # logging.info(f"result: {result} value: {buf.value}")
                # # Correct path – try without extra '/' or with 'MEMORY/' if DATA_SV fails
                # name_str = f"//DATA_SV/{CNC.PROGRAME_NAME}"  # or "DATA_SV/lb44.nc" try kara
                name_bytes = buf.value.rstrip(b'\x00') + b'\x00'
                logging.info(f"Encoded program path: {name_bytes}")
                
                name_ptr = ctypes.create_string_buffer(name_bytes)
                
                # cnc_upstart4
                ret_upstart = fwlib.cnc_upstart4(handle, 0, name_ptr)  # No extra arg
                logging.info(f'upstart result is {ret_upstart}')
                
                if ret_upstart != 0:
                    logging.error(f"Upstart failed: {ret_upstart}")
                    return data
                chunk = 0
                while True:
                    time.sleep(0.5)  # Avoid tight loop
                    MAX_BLOCK = 4096  # Increase size (safe)
                    buf = create_string_buffer(MAX_BLOCK)
                    length = c_long(MAX_BLOCK)  # Reset each time
                    ret_upload = fwlib.cnc_upload4(handle, byref(length), buf)     
                    logging.info(f"Upload result: {ret_upload}, bytes read: {length.value}")

                    if ret_upload == 0:  # Success, data present
                        if length.value > 0:
                            block = buf.raw.decode('utf-8').strip('\x00')
                            program_content.append(block)
                            # logging.info(f"Block read: {block}")  # Partial log
                        else:
                            # length 0 pan 0 return → possible end or empty
                            logging.warning("Zero bytes read but return 0 – possible end?")
                            break
                    else:
                        logging.error(f"Upload error: {ret_upload}")
                        break
                    if len(program_content) >= 3 and ret_upload != -2:
                        chunk += 1  
                        with self.lock:
                            data['name'] = CNC.PROGRAME_NAME
                            data['program'] = program_content
                            data['edgeid'] = self.edgeid
                            data['chunk'] = chunk
                            self.event_queue.put(data)
                        program_content = []

                ret_end = fwlib.cnc_upend4(handle)
                logging.info(f"upend4 result: {ret_end}")

            data['name'] = CNC.PROGRAME_NAME
            data['program'] = program_content
            data['time'] = round(time.perf_counter() - start_time, 4)
        
        except Exception as e:
            logging.error(f"Error in get_cnc_programe: {e}")
        
        return data
    
    def get_cnc_program_detais(self,handle):
        data = {"ts": time.time_ns() // 1_000_000}
        # self.getProgramName(handle)
        start_time= time.perf_counter()
        fanuc = fwlib.cnc_rdprgnum
        fanuc.restype = c_short
        odbpro = ODBPRO()
        result = fanuc(handle,byref(odbpro))
        data.update(odbpro.__dict__)
        data['time'] = time.perf_counter()-start_time
        return data
           
    def _get_poll_methods(self):

        return [
            # self.get_cnc_sysinfo,
            # self.get_cnc_state,
            self.get_cnc_programe,
            # self.get_torque_servo,
        ]
    
    def _run_function(self, func):
        """Helper function jo pickle ho sakta hai"""
        return func()
    
    def poll(self, handle) -> Dict[str, Any]:
            results = {}
            start_time= time.perf_counter()
            for method in self._get_poll_methods():
                results[method.__name__] = method(handle)
            results['poll_time'] = round(time.perf_counter() - start_time,4)
            return results
    
            # methods = self._get_poll_methods()
            # method_names = [m.__name__ for m in methods]
            # logging.info(method_names)
            # partial_funcs = [partial(method, handle) for method in methods]

            # with mp.Pool(processes=len(methods)) as pool:
            #     results = pool.map(self._run_function, partial_funcs)
            
            # return dict(zip(method_names, results))

    
    def disconnect(self,):
        if self.handle != -16 or self.handle is None:
            fwlib.cnc_freelibhndl(self.handle)
        self.block_thread.stop()
        


