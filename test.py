from ctypes.util import find_library
import ctypes 
from ctypes import *
fwlib = find_library(f"C:/Users/DELL/Desktop/test_fanuc/humac_driver/lib/Fwlib64.dll")
fwlib =ctypes.windll.LoadLibrary(fwlib)

if fwlib:
    ip ="192.168.0.2"
    port= 1993
    timeout = 10
    func = fwlib.cnc_allclibhndl3
    func.argtypes = [
        c_char_p,           # IP address (string)
        c_ushort,           # Port number
        c_long,             # Timeout
        ctypes.POINTER(c_ushort)  # Handle pointer
    ]
    func.restype = c_short
    
    ip_bytes = ip.encode('utf-8')
    handle = c_ushort(0)
    
    # logging.info(f"Connecting to {ip}:{port} with timeout {timeout}")
    
    result = func(ip_bytes, port, timeout, byref(handle))

    print(f"Connection result: {result}, Handle: {handle.value}")
    # fwlib.cnc_startupprocess.restype = c_short
    # fwlib.cnc_startupprocess.argtypes = [c_short, c_char_p]
    # log_file = b"focas.log"
    # init_ret = fwlib.cnc_startupprocess(3, log_file)

# import multiprocessing as mp
# import os
# import sys
# import time
# from typing import List, Optional


# class NameFinder(mp.Process):
#     """
#     A Process that continuously looks for a name in a shared list.
#     The process starts the moment the object is instantiated.
#     """
#     def __init__(
#         self,
#         target_name: str,
#         name_list: List[str],
#         poll_interval: float = 0.5,
#         daemon: bool = True,
#     ):
#         # 1. Call the parent constructor *first*
#         super().__init__(name=f"Finder-{target_name}", daemon=daemon)

#         # 2. Store everything the worker will need
#         self.target_name   = target_name
#         self.name_list     = name_list          # read-only, no copy needed
#         self.poll_interval = poll_interval

#         # 3. **Start the process immediately**
#         self.start()

#     # ------------------------------------------------------------------
#     # This method runs in a *separate OS process* on its own CPU core
#     # ------------------------------------------------------------------
#     def run(self) -> None:
#         pid = os.getpid()
#         print(f"[PID {pid}] NameFinder looking for '{self.target_name}'")

#         while True:
#             if self.target_name in self.name_list:
#                 # Found!  Push the result and exit
               
#                 data={"pid": pid, "found": self.target_name, "list": self.name_list[:]}
#                 print(data)
                
#                 break

#             # Simulate work / give other processes a chance
#             time.sleep(self.poll_interval)

#         print(f"[PID {pid}] Finished searching for '{self.target_name}'")


# def main():
#     print(sys.platform)
#     name = ['shubam','manoj','sjdnsd','bdhhdn','hhbdhd','dshbjh']
#     find = 'bdhhdn'
#     result_q= mp.Queue()
#     result = NameFinder(name_list=name,target_name=find )
#     print('not waiting for complition ... ')
#     result.join()


# if __name__ == "__main__":
#     main()


