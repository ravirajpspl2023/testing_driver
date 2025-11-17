import sys
import os
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


class FocasDriver(object):
    def __init__(self,ip,port,timeout=10):
        self.ip = ip
        self.port = port
        self.timeout = timeout   
    
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
            elapsed = time.time() - start_time
            logging.info(f"Connection {self.ip} result: {result} | Handle: {handle.value} | RequTime:{elapsed:.2f}s")
            return handle.value
        return None

    def getProgramName(self, handle):
        data = {"ts":time.time_ns() // 1_000_000 }
        start_time= time.perf_counter()
        func = fwlib.cnc_exeprgname
        func.restype = c_short
        executingProgram = ExecutingProgram()
        result = func(handle, byref(executingProgram))
        # FocasExceptionRaiser(result, context=self)
        data["programName"] = executingProgram.name
        data["oNumber"] = executingProgram.oNumber
        end_time = time.perf_counter()
        data['time'] = end_time-start_time
        return data

    def getBlockNumber(self, handle):
        data = {"ts":time.time_ns() // 1_000_000 }
        start_time= time.perf_counter()
        dynamic = DynamicResult()
        func = fwlib.cnc_rddynamic2
        func.restype = c_short
        result = func(handle,
                      -1,
                      sizeof(DynamicResult),
                      byref(dynamic))
        # FocasExceptionRaiser(result, context=self)
        data["blockNumber"] = dynamic.sequenceNumber
        end_time = time.perf_counter()
        data['time'] = end_time-start_time
        return data

    def getActiveTool(self, handle):
        data = {"ts":time.time_ns() // 1_000_000 }
        start_time= time.perf_counter()
        func = fwlib.cnc_modal
        func.restype = c_short
        modalData = ModalData()
        result = func(handle, 108, 1, byref(modalData))
        # FocasExceptionRaiser(result, context=self)
        data["activeTool"] = modalData.modal.aux.aux_data
        end_time = time.perf_counter()
        data['time'] = end_time-start_time
        return data

                
    def _get_poll_methods(self):
        return [
            self.getProgramName,
            self.getBlockNumber,
            self.getActiveTool
        ]
    
    def _run_function(self, func):
        """Helper function jo pickle ho sakta hai"""
        return func()
    
    def poll(self, handle) -> Dict[str, Any]:
            methods = self._get_poll_methods()
            method_names = [m.__name__ for m in methods]
            logging.info(method_names)
            partial_funcs = [partial(method, handle) for method in methods]

            with mp.Pool(processes=len(methods)) as pool:
                results = pool.map(self._run_function, partial_funcs)
            
            return dict(zip(method_names, results))

    
    def disconnect(self, handle):
        fwlib.cnc_freelibhndl(handle)
            

    # def student_info(self, id):
    #     start_time = time.perf_counter()
    #     time.sleep(1)
    #     end_time = time.perf_counter()

    #     return {"time": end_time-start_time}

    # def student_performance(self, id):
    #     start_time= time.perf_counter()
    #     time.sleep(2)
    #     end_time = time.perf_counter()
    #     return {'time': end_time-start_time}

    # def student_background_details(self, id):
    #     start_time= time.perf_counter()
    #     time.sleep(3)
    #     end_time = time.perf_counter()
    #     return {'time': end_time-start_time}

    # def _get_poll_methods(self):
    #     return [
    #         self.student_info,
    #         self.student_performance,
    #         self.student_background_details
    #     ]

    # def _run_function(self, func):
    #     """Helper function jo pickle ho sakta hai"""
    #     return func()

    # def poll(self, id) -> Dict[str, Any]:
    #     methods = self._get_poll_methods()
    #     method_names = [m.__name__ for m in methods]
    #     partial_funcs = [partial(method, id) for method in methods]

    #     with mp.Pool(processes=len(methods)) as pool:
    #         results = pool.map(self._run_function, partial_funcs)

    #     return dict(zip(method_names, results))
        


