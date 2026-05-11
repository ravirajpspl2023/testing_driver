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
                # name_str = f"//DATA_SV/{CNC.PROGRAME_NAME}"  # or "DATA_SV/lb44.nc" try kara
                name_bytes = buf.value.rstrip(b'\x00') + b'\x00'
                logging.info(f"Encoded program path: {name_bytes}")

                name_ptr = ctypes.create_string_buffer(name_bytes)

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


    
    def get_all_program_names(self):
        pdf_in = IDBPDFADIR()
        pdf_in.path = b"//DATA_SV/" 
        pdf_in.req_num = 0               
        pdf_in.size_kind = 1             
        pdf_in.type = 1                  
        
        num_to_read = c_short(10)
        pdf_out = (ODBPDFADIR * 10)()    
        
        programs_list = []
        
        while True:
            ret = fwlib.cnc_rdpdf_alldir(self.handle, byref(num_to_read), byref(pdf_in), byref(pdf_out))
            
            if ret == 0:
                if num_to_read.value == 0:
                    break
                    
                for i in range(num_to_read.value):
                    # FIX: Use shift-jis and errors='replace' to handle special characters
                    try:
                        name = pdf_out[i].d_f.split(b'\x00')[0].decode('shift-jis', errors='replace')
                        comment = pdf_out[i].comment.split(b'\x00')[0].decode('shift-jis', errors='replace')
                    except Exception as e:
                        name = "Unknown_Name"
                        comment = f"Decode Error: {e}"
                    path_sv = f"//DATA_SV/{name}"  # Ensure null-terminated string
                    paths = [name,path_sv]
                    for path in paths:
                        name_ptr = ctypes.create_string_buffer(path.encode('shift-jis'))
                        logging.info(f'pointer : {name_ptr.value}')
                        ret_upstart = fwlib.cnc_upstart4(self.handle, 0, name_ptr)  # No extra arg
                        logging.info(f'upstart result is {ret_upstart}')
                        if ret_upstart != 0:
                            err = ODBERR()
                            fwlib.cnc_getdtailerr(self.handle, ctypes.byref(err))
                            logging.error(f"Error {ret_upstart}: Detail {err.err_no} (1:Path Error, 2:File Not Found)")
                        ret_end = fwlib.cnc_upend4(self.handle)
                        logging.info(f"upend4 result: {ret_end}")

                    file_info = {
                        "name": name,
                        "type": "File" if pdf_out[i].data_kind == 1 else "Folder",
                        "size": pdf_out[i].size,
                        "comment": comment,
                    }
                    programs_list.append(file_info)
                    logging.info(f"Found: {file_info['name']} - {file_info['comment']}")
                
                pdf_in.req_num += num_to_read.value
            else:
                logging.error(f"Error reading directory: {ret}")
                break
        logging.info(f"Found programs: {programs_list}")

    def check_execution_vs_main(self):
        # 1. Get Selected Main Program
        main_buf = ctypes.create_string_buffer(244)
        
        fwlib.cnc_pdf_rdmain(self.handle, byref(main_buf))
        main_path = main_buf.value.decode('shift-jis').split('\x00')[0]

        # 2. Get Currently Executing Program
        exe_buf = ctypes.create_string_buffer(244)
        fwlib.cnc_exeprgname(self.handle, byref(exe_buf))
        exe_path = exe_buf.value.decode('shift-jis').split('\x00')[0]

        logging.info(f"Main Selected: {main_path}")
        logging.info(f"Actually Running: {exe_path}")


    def get_hint_from_exec_block(self):
        # Reads the actual lines of code being run
        # Reference: https://www.inventcom.net/fanuc-focas-library/Program/cnc_rdexecprog
        blk_count = ctypes.c_short(1)
        data_len = ctypes.c_long(100)
        prog_data = ctypes.create_string_buffer(100)
        
        fwlib.cnc_rdexecprog(self.handle, byref(data_len), byref(blk_count), prog_data)
        logging.info(f"Execution Hint: {prog_data.value.decode('shift-jis', errors='replace')}")

    def search_text_in_dataserver(self):
        """
        Searches for a specific word in a list of files on the DATA_SV drive.
        Returns the filename if found, else None.
        """
        file_list = [{'name': '1-52R6_S1.tap', 'type': 'File', 'size': 1978000, 'comment': ''}, {'name': '10-25R5_S1.tap', 'type': 'File', 'size': 449500, 'comment': ''}, {'name': '2-52R6_S1.tap', 'type': 'File', 'size': 2243000, 'comment': ''}, {'name': '3-52R6_S1.tap', 'type': 'File', 'size': 1839000, 'comment': ''}, {'name': '4-52R6_S1.tap', 'type': 'File', 'size': 985000, 'comment': ''}, {'name': '5-52R6_S1.tap', 'type': 'File', 'size': 416500, 'comment': ''}, {'name': '6-52R6_S1.tap', 'type': 'File', 'size': 776000, 'comment': ''}, {'name': '7-25R5_S1.tap', 'type': 'File', 'size': 1695500, 'comment': ''}, {'name': '8-25R5_S1.tap', 'type': 'File', 'size': 1977000, 'comment': ''}, {'name': '9-25R5_S1.tap', 'type': 'File', 'size': 133500, 'comment': ''}]

        # RULE: The search buffer MUST NOT contain spaces or lowercase letters.
        # We search for the unique ID (N17778) first.
        search_text = "N17778\x00"
        search_buf = create_string_buffer(search_text.encode('ascii'))

        for file in file_list:
            # RULE: prog_name must be a full path string (NULL terminated)
            path_str = f"//DATA_SV/{file['name']}\x00"
            prog_name_ptr = create_string_buffer(path_str.encode('ascii'))
            
            logging.info(f"Searching in: {path_str}")

            # 1. Initiate the Search
            # Arguments must be explicitly cast to c_ulong to ensure 4-byte alignment
            ret = fwlib.cnc_pdf_searchword(
                self.handle,
                prog_name_ptr,    # prog_name: char*
                c_ulong(0),       # line_no: 0 (start from top)
                c_ulong(1),       # type: 1 (Word search)
                c_ulong(1),       # direct: 1 (Search downwards)
                c_ulong(1),       # repeat: 1 (First occurrence)
                search_buf        # buffer: char*
            )

            if ret == 0: # EW_OK
                # 2. Retrieve the Result (Asynchronous Polling)
                found_line_no = c_long()
                
                # The CNC takes time to scan; we must loop until it's finished.
                timeout = time.time() + 5  # 5 second safety timeout
                while time.time() < timeout:
                    # result = [handle, pointer to line number]
                    res = fwlib.cnc_pdf_searchresult(self.handle, byref(found_line_no))
                    
                    if res == 0: # EW_OK (Found!)
                        logging.info(f"MATCH FOUND! File: {file['name']} at Line: {found_line_no.value}")
                        return file['name']
                    
                    elif res == -1: # EW_BUSY
                        time.sleep(0.05) # Wait 50ms and try again
                        continue
                    
                    else: # Any other error (like EW_NUMBER if not found)
                        logging.info(f"No match in {file['name']} (Result code: {res})")
                        break
            else:
                # If you still get code 5 here, it means the CNC rejected your path or string format.
                logging.error(f"Could not start search in {file['name']}, Error Code: {ret}")

        logging.info("Search completed. No matches found in any file.")
        return None

    def get_cnc_program_details_ascii(self):
    # Prepare the data dictionary with a timestamp
        data = {"ts": time.time_ns() // 1_000_000}
        
        start_time = time.perf_counter()
        
        # 1. Setup the cnc_rdproginfo function
        # Arguments: handle, type (1=ASCII), length (31), buffer
        fanuc_info = fwlib.cnc_rdproginfo
        fanuc_info.restype = c_short
        
        # Initialize the Union structure
        odbnc = ODBNC() 
        
        # 2. Call the API in ASCII mode (type=1, length=31)
        # Reference: https://www.inventcom.net/fanuc-focas-library/Program/cnc_rdproginfo
        result = fanuc_info(self.handle, 1, 31, byref(odbnc))


        
        if result == 0:
            # Get the raw bytes and decode to string
            ascii_data = odbnc.asc.decode('ascii').strip('%').strip()
            
            # The data comes back as "reg\nunreg\nused\nunused"
            # We split it into a list for easier use
            parts = ascii_data.split('\n')
            
            data.update({
                "registered_programs": parts[0] if len(parts) > 0 else "0",
                "available_programs":  parts[1] if len(parts) > 1 else "0",
                "used_memory":         parts[2] if len(parts) > 2 else "0",
                "unused_memory":       parts[3] if len(parts) > 3 else "0",
                "raw_ascii":           ascii_data
            })
        else:
            data['error'] = result

        # 3. Add the execution time
        data['execution_time_s'] = time.perf_counter() - start_time
        
        # Since you asked for the function not to return data (perhaps to log or store instead)
        # You can print it or assign it to a class variable
        logging.info(f"Program Info (ASCII): {data}")

    def get_dnc_diagnosis(self,):
        """
        Reads DNC diagnosis data to see what the CNC is expecting.
        """
        dgndt = ODBDNCDGN()
        ret = fwlib.cnc_rddncdgndt(self.handle, ctypes.byref(dgndt))
        
        if ret == 0:
            # Decode the file name (Shift-JIS is standard for Fanuc)
            try:
                file_name = dgndt.nc_file.decode('shift-jis').strip('\x00')
            except:
                file_name = str(dgndt.nc_file)
                
            logging.info(f"--- DNC Diagnosis ---")
            logging.info(f"CNC Requested File: {file_name}")
            logging.info(f"Control Word: {dgndt.ctrl_word}")
            logging.info(f"Total Size Transferred: {dgndt.total_size}")
            # return dgndt
        else:
            logging.error(f"Failed to read diagnosis. Error: {ret}")
            return None

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
            ds_file_out = (OUT_DSFILE * 10)() 

            ds_file_in.path = b"" 
            ds_file_in.req_num = 10
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
                # local_dir = "./humac"
                # if not os.path.exists(local_dir):
                #     os.makedirs(local_dir)

                for i in range(ds_info_out.total):
                    filename = ds_file_out[i].file.decode('ascii').strip('\x00')   
                    logging.info(f"Starting download for: {filename}")
                    # --- START DOWNLOAD FLOW ---
                    # 2. Start the transfer for this specific file
                    # Format usually requires //DATA_SV/ prefix
                    remote_full_path = f"//DATA_SV/{filename}".encode('shift-jis',errors='replace').rstrip(b'\x00')
                    end_line_path = remote_full_path + b'\x00'
                    logging.info(f"full path : {end_line_path}")
                    buf_path = ctypes.create_string_buffer(end_line_path)  # Null-terminated path
                    ret_upstart = fwlib.cnc_upstart4(self.handle, 1, buf_path)  # Start transfer

                    err = ODBERR()
                    fwlib.cnc_getdtailerr(self.handle, ctypes.byref(err))
                    logging.error(f"Detail Error for {filename}: err_no={err.err_no}, err_dtl={err.err_dtno}")

                    logging.info(f"Upstart result for {filename}: {ret_upstart}")

                    while True:
                        time.sleep(0.2)
                        buf = create_string_buffer(CNC.MAX_BLOCK)
                        length = c_long(CNC.MAX_BLOCK) 

                        ret_upload = fwlib.cnc_upload4(self.handle, byref(length), buf)     
                        logging.info(f"Upload result: {ret_upload}, bytes read: {length.value}")
                        if ret_upload == 0  and length.value > 0:
                            block = buf.raw[:length.value].decode('utf-8', errors='ignore').strip('\x00')
                            logging.info(f"blocks : {block}")
                        elif ret_upload == -2:
                            
                            break

                        elif ret_upload != 0 and ret_upload != -2:
                            logging.error(f"Upload failed with code: {ret_upload}")
                            break

                    end_ref = fwlib.cnc_upend4(self.handle) 
                    logging.info(f"Upend result for {filename}: {end_ref}")

                    full_path = ctypes.create_string_buffer(remote_full_path)
                    line_no = ctypes.c_ulong(0)
                    ret = fwlib.cnc_pdf_searchword(self.handle,full_path,)        
            else:
                logging.error(f"Failed to list files. Error code: {ret}")

    def get_current_ds_path(self):
        # 19-16EM-S2.tap

        file_name = f"19-16em-s2.tap\x00".encode('ascii')  # Null-terminated string
        path_buffer = ctypes.create_string_buffer(file_name)
        
        ret = fwlib.cnc_dsget_req(self.handle, path_buffer,0)
        
        if ret == 0:
            actual_path = path_buffer.value.decode('ascii')
            logging.info(f"path : {actual_path}")
            return actual_path
        else:
            logging.error(f"error : {ret}")
            return None

    
    def disconnect(self,):
        if self.handle != -16 or self.handle is None:
            fwlib.cnc_freelibhndl(self.handle)
        self.block_thread.stop()
        


