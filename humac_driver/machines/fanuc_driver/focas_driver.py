import sys
import ctypes
from ctypes.util import find_library
from ctypes import *
import time 
from functools import partial
from typing import  Dict, Any
from humac_driver.machines.fanuc_driver.Fwlib32_h import *
from humac_driver.machines.fanuc_driver.Exceptions import *
from humac_driver.machines.fanuc_driver.gcode_thread import GcodeThread
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
        self.handle = None
        self.gcode_thread = GcodeThread(ip, port, timeout) 
    
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
    
    def get_cnc_sysinfo(self,handle):
        data = {"ts": time.time_ns() // 1_000_000}
        start_time= time.perf_counter()
        fanuc = fwlib.cnc_sysinfo
        fanuc.restype = c_short
        machine =  ODBSYS()
        result = fanuc(handle,byref(machine))
        data.update(machine.__dict__)

        fanuc = fwlib.cnc_getpath
        fanuc.restype = c_short
        current_path = ctypes.c_short()
        max_paths    = ctypes.c_short()
        result = fwlib.cnc_getpath(handle, ctypes.byref(current_path), ctypes.byref(max_paths))
        CNC.MAX_PATH = max_paths
        CNC.CURRENT_PATH = current_path
        logging.info(f"current_path: {current_path.value},max_path: {max_paths.value}")

        fanuc = fwlib.cnc_sysinfo_ex
        fanuc.restype = c_short
        system = ODBSYSEX()
        result = fanuc(handle,byref(system))
        data.update(system.__dict__)
        end_time = time.perf_counter()
        data['time'] = end_time-start_time
        return data
    
    def get_cnc_state(self,handle):
        data = {"ts": time.time_ns() // 1_000_000}
        start_time= time.perf_counter()

        fanuc = fwlib.cnc_statinfo
        fanuc.restype = c_short
        state_info = ODBST()
        result = fanuc(handle,byref(state_info))
        data.update(state_info.__dict__)

        # fanuc = fwlib.cnc_statinfo2
        # fanuc.restype = c_short
        # new_info = ODBST2()
        # result = fanuc(handle,byref(new_info))
        # data['new_info'] = new_info.__dict__

        end_time = time.perf_counter()
        data['time'] = end_time-start_time
        return data
    
    def get_torque_servo(self,handle):
        data = {"ts": time.time_ns() // 1_000_000}
        start_time= time.perf_counter()
        length = 4 + 2 * CNC.MAX_AXIS
        fanuc = fwlib.cnc_loadtorq
        fanuc.restype = c_short
        motor_torque = ODBLOAD()
        result = fanuc(handle,0,CNC.ALL_AXES,length,byref(motor_torque))
        data.update({'axis':motor_torque.__dict__})

        result = fanuc(handle,1,CNC.ALL_AXES,length,byref(motor_torque))
        data.update({'spindle':motor_torque.__dict__})

        end_time = time.perf_counter()
        data['time'] = end_time-start_time
        return data
    
    def get_gcode_program(self,handle):
        data = {"ts": time.time_ns() // 1_000_000}
        # start_time= time.perf_counter()
        # fanuc = fwlib.cnc_rdblkcount
        # fanuc.restype = c_short
        # block_count = c_long()
        # result = fanuc(handle,byref(block_count))
        # end_time = time.perf_counter()
        # data.update({'block_count':block_count.value})
        # data['time'] = end_time-start_time
        # data = []
        # # if not self.GcodeProgram.empty():
        # #     with self.gcode_thread.lock:
        # #         for _ in range(self.GcodeProgram.qsize()):
        # #             data.append(self.GcodeProgram.get())

        return data
           
    def _get_poll_methods(self):
        return [
            self.get_cnc_sysinfo,
            self.get_cnc_state,
            # self.get_torque_servo,
            # self.get_gcode_program
        ]
    
    def _run_function(self, func):
        """Helper function jo pickle ho sakta hai"""
        return func()
    
    def poll(self, handle) -> Dict[str, Any]:
            results = {}
            start_time= time.perf_counter()
            for method in self._get_poll_methods():
                results[method.__name__] = method(handle)

            results['poll_time'] = time.perf_counter() - start_time
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
        self.gcode_thread.stop()
        


