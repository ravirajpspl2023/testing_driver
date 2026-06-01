import sys
import ctypes
from ctypes.util import find_library
from ctypes import *
import json
import time 
from functools import partial
from typing import  Dict, Any
from humac_driver.machines.fanuc_driver.Fwlib32_h import *
from humac_driver.machines.fanuc_driver.Exceptions import *
from humac_driver.machines.fanuc_driver.Gblock_thread import BlockThread
from humac_driver.database.redis_client import RedisConnection
import threading
import datetime
import logging
from  multiprocessing  import Queue
from humac_driver.const import *
from ftplib import FTP
import os

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
    def __init__(self,config):
        self.ip = config['ip']
        self.port = config['port']
        self.timeout = config['timeout']
        self.handle = None
        self.previous_program_number = None
        self.edgeid = config['edgid']
        self.redis=  RedisConnection("program").connect()
        self.previous_date = None
        self.lock = threading.Lock()
        self.block_thread = BlockThread(config) 
        self.connect()
    
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

            if result != 0 :
                time.sleep(10)  # Wait a moment before retrying
                self.connect()
            logging.info(f"Connection {self.ip} result: {result} | Handle: {handle.value} | RequTime:{elapsed:.2f}s")

            self.handle = handle.value

    def get_cnc_programe(self,):
        try:
            data = {"ts": time.time_ns() // 1_000_000,
                    "name": CNC.PROGRAME_NAME,
                    "edgeid": self.edgeid}
            
            fanuc = fwlib.cnc_pdf_rdmain
            fanuc.restype = c_short
            buf = ctypes.create_string_buffer(244)
            result = fanuc(self.handle,byref(buf))

            if result == 0 :
                # logging.info(f"result: {result} value: {buf.value}")
                # # Correct path – try without extra '/' or with 'MEMORY/' if DATA_SV fails
                name_str = f"//DATA_SV/{CNC.PROGRAME_NAME}"  # or "DATA_SV/lb44.nc" try kara
                name_bytes = buf.value.rstrip(b'\x00') + b'\x00'
                # path = f"//CNC_MEM/USER/1"
                name_ptr = ctypes.create_string_buffer(name_bytes)
                logging.info(f"Encoded program path: {name_ptr.value}")

                # cnc_upstart4
                ret_upstart = fwlib.cnc_upstart4(self.handle, 0, name_ptr)  # No extra arg
                logging.info(f'upstart result is {ret_upstart}')

                if ret_upstart != 0:
                    logging.error(f"Upstart failed: {ret_upstart}")
                    return
                
                program_content = []
                chunk = 0
                while True:
                    time.sleep(0.2)

                    buf = create_string_buffer(CNC.MAX_BLOCK)
                    length = c_long(CNC.MAX_BLOCK) 

                    ret_upload = fwlib.cnc_upload4(self.handle, byref(length), buf)     
                    logging.info(f"Upload result: {ret_upload}, bytes read: {length.value}")
                    if ret_upload == 0  and length.value > 0:
                        block = buf.raw[:length.value].decode('utf-8', errors='ignore').strip('\x00')
                        program_content.append(block)
                        if len(program_content) >=6:
                            chunk += 1
                            data['chunk'] = chunk
                            data['program'] = json.dumps(program_content)
                            self.redis.xadd("program",data)
                            logging.info(f"chunk {chunk} sent to Redis ")
                            program_content = []
                    elif ret_upload == -2:
                        if program_content:
                            chunk += 1
                            data['chunk'] = chunk
                            data['program'] = json.dumps(program_content)
                            self.redis.xadd("program",data)
                            logging.info(f"Final program chunk {chunk} sent to Redis ")
                        break
                    elif ret_upload == -1 :
                        logging.warning(f"Upload busy, retrying... (Code: {ret_upload})")
                        time.sleep(0.5)  # Wait before retrying
                        continue

                    elif ret_upload != 0 and ret_upload != -2:
                        logging.error(f"Upload failed with code: {ret_upload}")
                        break

                ret_end = fwlib.cnc_upend4(self.handle)
                logging.info(f"upend4 result: {ret_end}")

            # data['name'] = CNC.PROGRAME_NAME
            # data['program'] = program_content
            # data['time'] = round(time.perf_counter() - start_time, 4)
        
        except Exception as e:
            logging.error(f"Error in get_cnc_programe: {e}")
        
    
    def get_cnc_program_detais(self,):
        data = {"ts": time.time_ns() // 1_000_000}
        # self.getProgramName(handle)
        start_time= time.perf_counter()
        fanuc = fwlib.cnc_rdprgnum
        fanuc.restype = c_short
        odbpro = ODBPRO()
        result = fanuc(self.handle,byref(odbpro))
        data.update(odbpro.__dict__)

        if data.get('mdata') == 0:
            func = fwlib.cnc_exeprgname
            func.restype = c_short
            programe = ODBEXEPRG()
            result = func(self.handle, byref(programe))
            programe.__dict__
            data['mdata'] = CNC.PROGRAME_NAME

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
    
    def poll(self,) -> Dict[str, Any]:
            
            for method in self._get_poll_methods():
                # results[method.__name__] = method()
                method()
    
            # methods = self._get_poll_methods()
            # method_names = [m.__name__ for m in methods]
            # logging.info(method_names)
            # partial_funcs = [partial(method, handle) for method in methods]

            # with mp.Pool(processes=len(methods)) as pool:
            #     results = pool.map(self._run_function, partial_funcs)
            
            # return dict(zip(method_names, results))


    def list_dataserver_files(self):
        # Initialize structures
            blk_count = ctypes.c_short(1)
            data_len = ctypes.c_long(1000)
            prog_data = ctypes.create_string_buffer(1000)
            
            fwlib.cnc_rdexecprog(self.handle, byref(data_len), byref(blk_count), prog_data)
            logging.info(f"Execution Hint: {prog_data.value.decode('ascii', errors='replace')}")

        # 1. Initialize structures for listing
            ds_file_in = IN_DSFILE()
            ds_info_out = OUT_DSINFO()
            ds_file_out = (OUT_DSFILE * 20)() 

            ds_file_in.path = b"" 
            ds_file_in.req_num = 20
            ds_file_in.size_type = 1 
            ds_file_in.detail = 0    

            # Call listing function
            ret = fwlib.cnc_rddsfile(
                self.handle, 
                b"DATA_SV", 
                ctypes.byref(ds_file_in), 
                ctypes.byref(ds_info_out), 
                ctypes.byref(ds_file_out)
            )

            if ret == 0:
                logging.info(f"Total files on Data Server: {ds_info_out.total}")

                for i in range(ds_info_out.total):
                    filename = ds_file_out[i].file.decode('ascii').strip('\x00')   
                    logging.info(f"Starting download for: {filename}")

                    if filename == '10-16R2_S2.tap':

                        # --- START DOWNLOAD FLOW ---
                        # 2. Start the transfer for this specific file
                        
                        remote_full_path = f"//DATA_SV/{filename}".encode('shift-jis',errors='replace').rstrip(b'\x00')
                        end_line_path = remote_full_path + b'\x00'
                        logging.info(f"full path : {end_line_path}")
                        buf_path = ctypes.create_string_buffer(end_line_path)  # Null-terminated path
                        ret_upstart = fwlib.cnc_fileread_start(self.handle, 0 , buf_path)  # Start transfer

                        err = ODBERR()
                        fwlib.cnc_getdtailerr(self.handle, ctypes.byref(err))
                        logging.error(f"Detail Error for {filename}: err_no={err.err_no}, err_dtl={err.err_dtno}")

                        logging.info(f"Upstart result for {filename}: {ret_upstart}")

                        while True:
                            time.sleep(0.2)
                            buf = create_string_buffer(CNC.MAX_BLOCK)
                            length = c_long(CNC.MAX_BLOCK) 
                            ret_upload = fwlib.cnc_fileread(self.handle, byref(length), buf)     
                            logging.info(f"Upload result: {ret_upload}, bytes read: {length.value}")
                            if ret_upload == 0  and length.value > 0:
                                block = buf.raw[:length.value].decode('utf-8', errors='ignore').strip('\x00')
                                logging.info(f"blocks : {block}")
                            elif ret_upload == -2:
                                logging.info(f"Upload completed for {filename}")
                                break

                            elif ret_upload != 0 and ret_upload != -2:
                                logging.error(f"Upload failed with code: {ret_upload}")
                                break

                        end_ref = fwlib.cnc_fileread_end(self.handle) 
                        logging.info(f"Upend result for {filename}: {end_ref}")

            else:
                logging.error(f"Failed to list files. Error code: {ret}")

    def upload_program(self,):
            # --- Step 1: NC Program prepare करा ---
        
        program_content = (
            "\n"
            "<PROG123>\n"
            "M3 S1200\n"
            "G0 Z0\n"
            "G0 X0 Y0\n"
            "G1 F500 X120. Y-30.\n"
            "M30\n"
            "%"
        )

        # String → bytes convert करा
        prg_bytes = program_content.encode('ascii')
        total_len = len(prg_bytes)
        logging.info(f"Total program size: {total_len} bytes")

        # --- Step 2: cnc_dwnstart4 ---
        folder_path = "//DATA_SV/HUMAC.NC"
        dir_bytes = folder_path.encode('shift-jis', errors='replace') + b'\x00'

        start_ret = fwlib.cnc_dwnstart4(self.handle, 0, dir_bytes)
        logging.info(f"cnc_dwnstart4 result: {start_ret}")

        if start_ret != 0:
            logging.error(f"cnc_dwnstart4 failed: {start_ret}")
            return start_ret

        # --- Step 3: Chunk करून cnc_download4 ला पाठवा ---
        CHUNK_SIZE = 1024   # Max 1024 bytes per call (safe for Ethernet)
        EW_OK      = 0
        EW_BUFFER  = 10
        sent       = 0      # किती bytes पाठवले

        while sent < total_len:

            # पुढचा chunk काढा (max CHUNK_SIZE bytes)
            chunk = prg_bytes[sent : sent + CHUNK_SIZE]
            chunk_len = len(chunk)

            # ctypes c_long — in/out parameter
            n = ctypes.c_long(chunk_len)

            ret = fwlib.cnc_download4(
                self.handle,
                ctypes.byref(n),   # length pointer
                chunk              # data pointer
            )

            logging.info(
                f"cnc_download4 | offset={sent} "
                f"| tried={chunk_len} | accepted={n.value} "
                f"| ret={ret}"
            )

            if ret == EW_BUFFER:
                # CNC चा buffer full आहे — same chunk पुन्हा try करा
                logging.warning(f"EW_BUFFER at offset={sent}, retrying...")
                continue  # sent वाढवायचा नाही, same chunk पुन्हा

            elif ret == EW_OK:
                # n.value = CNC ने actually accept केलेले bytes
                sent += n.value
                logging.info(f"Sent {sent}/{total_len} bytes")

            else:
                # Real error
                logging.error(f"cnc_download4 error: {ret} at offset={sent}")
                fwlib.cnc_dwnend4(self.handle)  # cleanup
                return ret

        logging.info("All data sent successfully!")

        # --- Step 4: cnc_dwnend4 ---
        end_ret = fwlib.cnc_dwnend4(self.handle)
        logging.info(f"cnc_dwnend4 result: {end_ret}")

    def disconnect(self,):
        if self.handle != -16 or self.handle is None:
            fwlib.cnc_freelibhndl(self.handle)
        self.block_thread.stop()
        


