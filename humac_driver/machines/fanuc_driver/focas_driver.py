import sys
import ctypes
from ctypes.util import find_library
from ctypes import *
import json
import time 
from typing import  Dict, Any
from humac_driver.machines.fanuc_driver.Fwlib32_h import *
from humac_driver.machines.fanuc_driver.Exceptions import *
from humac_driver.machines.fanuc_driver.Gblock_thread import BlockThread
from humac_driver.database.redis_client import RedisConnection
from humac_driver.machines.files_download.downloader import S3Downloader
import threading
import logging
from humac_driver.const import *
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
        self.redis_trig = RedisConnection("trigger").connect()
        self.previous_date = None
        self.lock = threading.Lock()
        self.block_thread = BlockThread(config) 
        self.file_downloader = S3Downloader()
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
                name_str = f"//DATA_SV/11-8R1-S1.tap/O1"  # or "DATA_SV/lb44.nc" try kara
                # name_bytes = buf.value.rstrip(b'\x00') + b'\x00'
                name_bytes = name_str.encode('shift-jis', errors='replace') + b'\x00'  # Shift-JIS encoding for Japanese characters, with null terminator

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
                        if len(program_content) >=4:
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

    def get_machine_program_list(self) -> list[str]:
        """
        DATA_SV drive वरील सर्व programs ची list return करतो.
        Returns: ['O0001.nc', 'PROG002.tap', ...] — फक्त filenames
        """
        ds_file_in  = IN_DSFILE()
        ds_info_out = OUT_DSINFO()
        ds_file_out = (OUT_DSFILE * 20)()

        ds_file_in.path      = b""
        ds_file_in.req_num   = 20
        ds_file_in.size_type = 1
        ds_file_in.detail    = 0

        ret = fwlib.cnc_rddsfile(
            self.handle,
            b"DATA_SV",
            ctypes.byref(ds_file_in),
            ctypes.byref(ds_info_out),
            ctypes.byref(ds_file_out),
        )

        if ret != 0:
            logging.error(f"cnc_rddsfile failed: {ret}")
            return []

        programs = []
        for i in range(ds_info_out.total):
            fname = ds_file_out[i].file.decode("ascii", errors="replace").strip("\x00").strip()
            if fname:
                programs.append(fname)

        # logging.info(f"Machine programs ({len(programs)}): {programs}")
        return programs
    
    def _send_program_to_machine(self, local_filepath: str) -> bool:
        """
        Local file → Machine DATA_SV ला send करतो.
        upload_program() मधील proven logic वापरतो.
        Returns: True if success, False if failed
        """
        filename = os.path.basename(local_filepath)
        try:
            with open(local_filepath, "r") as f:
                content = f.read()
        except Exception as e:
            logging.error(f"Cannot read {local_filepath}: {e}")
            return False

        modified = content.replace("O0001", f"<{filename}>")
        prg_bytes  = modified.encode("ascii", errors="ignore")
        total_len  = len(prg_bytes)
        logging.info(f"Sending {filename} ({total_len} bytes) → DATA_SV")

        folder_path = "//DATA_SV/"
        dir_bytes   = folder_path.encode("shift-jis", errors="replace") + b"\x00"

        # cnc_dwnstart4 — retry if busy
        for attempt in range(5):
            start_ret = fwlib.cnc_dwnstart4(self.handle, 0, dir_bytes)
            if start_ret == 0:
                break
            if start_ret == -1:
                logging.warning(f"cnc_dwnstart4 busy, retry {attempt+1}/5")
                fwlib.cnc_dwnend4(self.handle)
                time.sleep(1)
            else:
                logging.error(f"cnc_dwnstart4 failed: {start_ret}")
                return False
        else:
            logging.error("cnc_dwnstart4 never became ready")
            return False

        # Data chunks पाठवणे
        EW_OK, EW_BUFFER, CHUNK_SIZE = 0, 10, 4096
        sent = 0
        while sent < total_len:
            chunk     = prg_bytes[sent: sent + CHUNK_SIZE]
            n         = ctypes.c_long(len(chunk))
            ret       = fwlib.cnc_download4(self.handle, ctypes.byref(n), chunk)
            time.sleep(0.2)

            if ret in (EW_BUFFER, -1):
                logging.warning(f"EW_BUFFER at offset={sent}, retrying...")
                continue
            elif ret == EW_OK:
                sent += n.value
                logging.info(f"  Progress: {sent}/{total_len} bytes")
            else:
                logging.error(f"cnc_download4 error {ret} at offset={sent}")
                fwlib.cnc_dwnend4(self.handle)
                return False

        end_ret = fwlib.cnc_dwnend4(self.handle)
        logging.info(f"✅ Sent {filename} — dwnend4: {end_ret}")
        return True
    
    def _delete_machine_program(self, filename: str) -> bool:
        """
        Machine च्या DATA_SV वरून एक file delete करतो.
        Returns: True if success
        """
        path = f"//DATA_SV/{filename}".encode("shift-jis", errors="replace").rstrip(b"\x00") + b"\x00"
        ret  = fwlib.cnc_pdf_del(self.handle, path)
        if ret == 0:
            logging.info(f"🗑️  Deleted from machine: {filename}")
            return True
        else:
            logging.error(f"Delete failed for {filename}: ret={ret}")
            return False

    def _load_send_state(self) -> dict:
        """
        State file मधून send pointer load करतो.
        Structure: { "sent_files": ["O001.nc", "O002.nc", ...] }
        'sent_files' म्हणजे आतापर्यंत machine ला successfully send केलेल्या files.
        """
        path = self.file_downloader.config["local"].get(
            "sync_state_file",
            os.path.join(os.path.dirname(self.file_downloader.config["local"]["state_file"]), "sync_state.json")
        )
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return {"sent_files": []}
    
    def _save_send_state(self, sent_files: list):
        path = self.file_downloader.config["local"].get(
            "sync_state_file",
            os.path.join(os.path.dirname(self.file_downloader.config["local"]["state_file"]), "sync_state.json")
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"sent_files": sent_files, "last_updated": time.time()}, f, indent=2)
        logging.info(f"Sync state saved: {len(sent_files)} sent files tracked")

    def extract_sequence_number(self, filename):
        """Extract numeric prefix from filename (e.g., '1-' → 1, '10-' → 10)"""
        try:
            num_part = filename.split('-')[0]
            return int(num_part)
        except (ValueError, IndexError):
            return 999999  # Non-numeric files at the end

    def sync_programs(self):
        """
        Main sync method.

        Example scenario:
          Local folder : [P01, P02, P03, ... P20]  (sorted, S3 वरून downloaded)
          Machine      : [P01, P02, P03, P04, P05, P06]  (6 already present)
          → slots free = 4  →  P07, P08, P09, P10 send करा

          नंतर machine वरून P03 manually delete झाला:
          → slots free = 1  →  P11 send करा  (P07–P10 already sent, त्यांना skip)

        Key idea: 'sent_files' state मध्ये track होतो — कुठल्या files आधीच
                  send केल्या आहेत ते माहीत असतं, त्यामुळे re-send होत नाही.
        """

        self.file_downloader.download_new_files()
        
        MAX_PROGRAMS = 10
        local_folder = self.file_downloader.config["local"]["download_folder"]

        # ── Step 1: Local folder — sorted order (हाच sequence) ──────────────
        try:
            all_local = [
                f for f in os.listdir(local_folder)
                if os.path.isfile(os.path.join(local_folder, f))
            ]
            all_local.sort(key=lambda f: self.extract_sequence_number(f))
        except Exception as e:
            logging.error(f"Cannot read local folder {local_folder}: {e}")
            os.makedirs(self.file_downloader.config['local']['download_folder'], exist_ok=True)
            return
        
        local_set = set(all_local)
        # logging.info(f"Local programs ({len(all_local)}): {all_local}")
        # ── Step 2: Machine वरील programs ────────────────────────────────────
        machine_programs = self.get_machine_program_list()
        machine_set      = set(machine_programs)

        # # ── Step 3: Machine वर आहे पण local मध्ये नाही → DELETE from machine ─
        # to_delete_machine = machine_set - local_set
        # if to_delete_machine:
        #     logging.info(f"Deleting from machine (not in local): {to_delete_machine}")
        #     for fname in to_delete_machine:
        #         self._delete_machine_program(fname)
        #     machine_programs = self.get_machine_program_list()
        #     machine_set      = set(machine_programs)

        # ── Step 3.5: Local मध्ये आहे पण Machine वर नाही आणि आधी send केलेली
        #              नाही → local मधून DELETE (machine = source of truth) ────
        state      = self._load_send_state()
        sent_files = state.get("sent_files", [])  # आतापर्यंत send केलेल्या files
        sent_set   = set(sent_files)
        
        # Local मध्ये आहे, machine वर नाही, आणि पूर्वी send केलेली आहे
        # म्हणजे machine वरून manually delete झाली → local मधूनही काढा
        to_delete_local = local_set - machine_set - (local_set - sent_set)
        # Simplified: local आणि sent आहे पण machine वर नाही
        to_delete_local = (local_set & sent_set) - machine_set

        if to_delete_local:
            logging.info(f"Deleting from local (removed from machine): {to_delete_local}")
            for fname in to_delete_local:
                local_path = os.path.join(local_folder, fname)
                try:
                    os.remove(local_path)
                    logging.info(f"🗑️ Deleted local: {fname}")
                except Exception as e:
                    logging.error(f"Failed to delete local {fname}: {e}")
            # sent_files मधूनही काढा — ते आता relevant नाहीत
            sent_files = [f for f in sent_files if f not in to_delete_local]
            all_local  = sorted([
                f for f in os.listdir(local_folder)
                if os.path.isfile(os.path.join(local_folder, f))
            ])
            local_set = set(all_local)

        # ── Step 4: Slots free आहेत का? ──────────────────────────────────────
        current_count = len(machine_set)
        # logging.info(f"Machine count: {current_count}/{MAX_PROGRAMS}")
        if current_count >= MAX_PROGRAMS:
            logging.info("Machine full (10 programs) — nothing to send")
            self._save_send_state(sent_files)
            return

        slots_free = MAX_PROGRAMS - current_count

        # ── Step 5: Candidate files — local मध्ये आहेत, machine वर नाहीत,
        #            आणि आधी send केलेल्या नाहीत → sorted order मधून पुढचे ──
        #
        #  [P01 P02 P03 ... P10 | P11 P12 ... P20]
        #   ←── already sent ──→  ←── pending ──→
        #
        not_yet_sent = [f for f in all_local if f not in sent_set and f not in machine_set]
        to_send      = not_yet_sent[:slots_free]

        if not to_send:
            logging.info("No pending programs to send — queue exhausted or machine in sync")
            self._save_send_state(sent_files)
            return

        logging.info(f"Sending {len(to_send)} programs → machine: {to_send}")

        for fname in to_send:
            full_path = os.path.join(local_folder, fname)
            success   = self._send_program_to_machine(full_path)
            if success:
                sent_files.append(fname)   # pointer पुढे सरकवा
                data = {"ts": time.time_ns() // 1_000_000,
                        "edgeid": self.edgeid,
                        "filename": fname,
                        'drive': 'DATA_SV',
                        "memory_use": 32412}
                self.redis_trig.xadd('trigger',data)
                
            else:
                logging.error(f"❌ Send failed: {fname} — stopping")
                break

        self._save_send_state(sent_files)
        logging.info("✅ sync_programs() complete")

    def get_selected_dnc_file(self, device_name="DATA_SV"):
        host_number = ctypes.c_short(0)                     # short *host sathi
        file_name_buffer = ctypes.create_string_buffer(256) # char *dncfile (256 bytes cha buffer)
        
        try:
            # Best Practice: Type safety sathi argtypes ani restype आधी define करा
            fwlib.cnc_rddsdncfile.argtypes = [
                ctypes.c_ushort,                 # FlibHndl
                ctypes.c_char_p,                 # dev_name
                ctypes.POINTER(ctypes.c_short),  # *host
                ctypes.c_char_p                  # *dncfile
            ]
            fwlib.cnc_rddsdncfile.restype = ctypes.c_short

            # UPDATE 1 & 2: 'device_name.encode()' pathvla ani host sobat 'ctypes.byref' vaparla
            ret = fwlib.cnc_rddsdncfile(
                self.handle, 
                device_name.encode('utf-8'), 
                ctypes.byref(host_number), 
                file_name_buffer
            )
            
            if ret == 0:
                # UTF-8 decode karne jast safe rahil standard files sathi
                dnc_file = file_name_buffer.value.decode('utf-8', errors='ignore').rstrip('\x00')
                
                # UPDATE 3: host_number chya jagi 'host_number.value' vaparla
                logging.info(f"Selected DNC file on {device_name}: {dnc_file} host : {host_number.value}")
                
                # UI la data denyasathi return statement add kela
                return {"status": "SUCCESS", "file_name": dnc_file, "host": host_number.value}
            else:
                logging.error(f"Focas Error Code: {ret} while reading DNC file.")
                return {"status": "FOCAS_ERROR", "error_code": ret}
                
        except Exception as e:
            logging.error(f"Error reading DNC file: {e}")
            return {"status": "EXCEPTION", "error_msg": str(e)}

    def disconnect(self,):
        if self.handle != -16 or self.handle is None:
            fwlib.cnc_freelibhndl(self.handle)
        self.block_thread.stop()


    # def upload_program(self,):
        
    #     new_program =  self.file_downloader.download_new_files()
    #     if not new_program:
    #         return
        
    #     logging.info(f"New program list: {new_program}")

    #     for program in new_program:
    #         filename = os.path.basename(program)
    #         with open(os.path.join(self.file_downloader.config['local']['download_folder'], filename), 'r') as f:
    #             program_content = f.read()
    #             # String → bytes convert 
    #             new_program = program_content.replace("O0001", f"<{filename}>")
    #             prg_bytes = new_program.encode('ascii', errors='ignore')
    #             total_len = len(prg_bytes)
    #             logging.info(f"Total program size: {total_len} bytes of {filename}")

    #             # --- Step 2: cnc_dwnstart4 ---
    #             folder_path = "//DATA_SV/"
    #             dir_bytes = folder_path.encode('shift-jis', errors='replace') + b'\x00'

    #             while True:
    #                 start_ret = fwlib.cnc_dwnstart4(self.handle, 0, dir_bytes)
    #                 logging.info(f"cnc_dwnstart4 result: {start_ret}")
    #                 if start_ret == 0 :
    #                     logging.info(f"cnc_dwnstart4 result: {start_ret} )")
    #                     break
    #                 if start_ret == -1:
    #                     logging.warning(f"cnc_dwnstart4 busy, retrying... (Code: {start_ret})")
    #                     fwlib.cnc_dwnend4(self.handle)  # cleanup
    #                     time.sleep(1)
    #                     continue
    #                 else:
    #                     logging.error(f"cnc_dwnstart4 failed with code: {start_ret}")
    #                     break
                
    #             EW_OK      = 0
    #             EW_BUFFER  = 10
    #             sent       = 0
    #             BUFFER_SIZE = 4096

    #             while sent < total_len:
    #                 chunk = prg_bytes[sent : sent + BUFFER_SIZE]
    #                 chunk_len = len(chunk)

    #                 # ctypes c_long — in/out parameter
    #                 n = ctypes.c_long(chunk_len)

    #                 ret = fwlib.cnc_download4(
    #                     self.handle,
    #                     ctypes.byref(n),   # length pointer
    #                     chunk              # data pointer
    #                 )
    #                 time.sleep(0.2)  # Small delay to prevent overwhelming the CNC
    #                 logging.info(
    #                     f"cnc_download4 | offset={sent} "
    #                     f"| tried={chunk_len} | accepted={n.value} "
    #                     f"| ret={ret}"
    #                 )

    #                 if ret == EW_BUFFER or ret == -1 :
    #                     logging.warning(f"EW_BUFFER at offset={sent}, retrying...")
    #                     continue  

    #                 elif ret == EW_OK:
    #                     sent += n.value
    #                     logging.info(f"Sent {sent}/{total_len} bytes")
    #                 else:
    #                     logging.error(f"cnc_download4 error: {ret} at offset={sent}")
    #                     fwlib.cnc_dwnend4(self.handle)  # cleanup
    #                     time.sleep(5)  # Wait before next attempt
    #                     break 
    #             end_ret = fwlib.cnc_dwnend4(self.handle)
    #             logging.info(f"Finished processing {filename} with result: {end_ret}")    
    #     logging.info("All data sent successfully!")

    # def list_dataserver_files(self):
    #     # Initialize structures
    #         blk_count = ctypes.c_short(1)
    #         data_len = ctypes.c_long(1000)
    #         prog_data = ctypes.create_string_buffer(1000)
            
    #         fwlib.cnc_rdexecprog(self.handle, byref(data_len), byref(blk_count), prog_data)
    #         logging.info(f"Execution Hint: {prog_data.value.decode('ascii', errors='replace')}")

    #     # 1. Initialize structures for listing
    #         ds_file_in = IN_DSFILE()
    #         ds_info_out = OUT_DSINFO()
    #         ds_file_out = (OUT_DSFILE * 20)() 

    #         ds_file_in.path = b"" 
    #         ds_file_in.req_num = 20
    #         ds_file_in.size_type = 1 
    #         ds_file_in.detail = 0    

    #         # Call listing function
    #         ret = fwlib.cnc_rddsfile(
    #             self.handle, 
    #             b"DATA_SV", 
    #             ctypes.byref(ds_file_in), 
    #             ctypes.byref(ds_info_out), 
    #             ctypes.byref(ds_file_out)
    #         )

    #         if ret == 0:
    #             logging.info(f"Total files on Data Server: {ds_info_out.total}")

    #             for i in range(ds_info_out.total):
    #                 filename = ds_file_out[i].file.decode('ascii').strip('\x00')   
    #                 logging.info(f"Starting download for: {filename}")

    #                 if filename == 'PROG123':
    #                     logging.info(f"Found target file: {filename}")
    #                     file_path = f"//DATA_SV/{filename}"
    #                     del_ret = fwlib.cnc_pdf_del(self.handle, b"//DATA_SV/PROG123")


    #                 if filename == '10-16R2_S2.tap':

    #                     # --- START DOWNLOAD FLOW ---
    #                     # 2. Start the transfer for this specific file
                        
    #                     remote_full_path = f"//DATA_SV/{filename}".encode('shift-jis',errors='replace').rstrip(b'\x00')
    #                     end_line_path = remote_full_path + b'\x00'
    #                     logging.info(f"full path : {end_line_path}")
    #                     buf_path = ctypes.create_string_buffer(end_line_path)  # Null-terminated path
    #                     ret_upstart = fwlib.cnc_fileread_start(self.handle, 0 , buf_path)  # Start transfer

    #                     err = ODBERR()
    #                     fwlib.cnc_getdtailerr(self.handle, ctypes.byref(err))
    #                     logging.error(f"Detail Error for {filename}: err_no={err.err_no}, err_dtl={err.err_dtno}")

    #                     logging.info(f"Upstart result for {filename}: {ret_upstart}")

    #                     while True:
    #                         time.sleep(0.25)
    #                         buf = create_string_buffer(CNC.MAX_BLOCK)
    #                         length = c_long(CNC.MAX_BLOCK) 
    #                         ret_upload = fwlib.cnc_fileread(self.handle, byref(length), buf)     
    #                         logging.info(f"Upload result: {ret_upload}, bytes read: {length.value}")
    #                         if ret_upload == 0  and length.value > 0:
    #                             block = buf.raw[:length.value].decode('utf-8', errors='ignore').strip('\x00')
    #                             logging.info(f"blocks : {block}")
    #                         elif ret_upload == -2:
    #                             logging.info(f"Upload completed for {filename}")
    #                             break

    #                         elif ret_upload != 0 and ret_upload != -2:
    #                             logging.error(f"Upload failed with code: {ret_upload}")
    #                             break

    #                     end_ref = fwlib.cnc_fileread_end(self.handle) 
    #                     logging.info(f"Upend result for {filename}: {end_ref}")

    #         else:
    #             logging.error(f"Failed to list files. Error code: {ret}")











        
