import multiprocessing as mp
import threading
from humac_driver.machines.HASS.MT_Connecte import MTConnecte
from humac_driver.database.redis_client import RedisConnection
from humac_driver.const import *
from multiprocessing import Queue
import datetime
import json
import io
import os
from time import time_ns, perf_counter, sleep
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    from smb.SMBConnection import SMBConnection
    SMB_AVAILABLE = True
except ImportError:
    logging.warning("pysmb not installed — run: pip install pysmb")
    SMB_AVAILABLE = False

# SMB config — const.py madhe add karo kiva ithe set karo
SMB_USERNAME = "haas"
SMB_PASSWORD = "123456"
SMB_CLIENT   = "HumacPC"
SMB_SERVER   = "HAASCNC"
SMB_SHARE    = "Data"
SMB_PORT     = 445
CHUNK_LINES  = 100    # Fanuc sarkha buffer size


class HassDriver(mp.Process):
    def __init__(self, config):
        super().__init__(name=config['edgid'], daemon=True)

        self.config       = config
        self.ip           = config['ip']
        self.port         = config['port']
        self.timeout      = config['timeout']
        self.edgeid       = config['edgid']
        self.machineid    = config['machineid']

        # self.event_queue   = Queue(maxsize=204800)
        # self.block_queue   = Queue(maxsize=102400)
        self.program_event = Queue(maxsize=102400)
        self.lock          = threading.Lock()

        self.redis=  RedisConnection("program").connect()

        # self.mqtt_sender = MqttSender(self.machineid, self.event_queue, self.block_queue)
        # self.MT_connecte = MTConnecte(self.config, self.program_event,self.block_queue)
        self.MT_connecte = MTConnecte(self.config, self.program_event)

        self.current_date = datetime.date.today()
        logging.info(f"Starting HASS with {self.edgeid}")
        self.start()

    # ──────────────────────────────────────────────────────
    # SMB download
    # ──────────────────────────────────────────────────────
    def _smb_connect(self):
        """SMB connection open karo. Returns conn kiva None."""
        try:
            conn = SMBConnection(
                SMB_USERNAME, SMB_PASSWORD,
                SMB_CLIENT, SMB_SERVER,
                use_ntlm_v2=True
            )
            if conn.connect(self.ip, SMB_PORT, timeout=self.timeout):
                return conn
            logging.error("SMB connect() returned False")
        except Exception as e:
            logging.error(f"SMB connection error: {e}")
        return None

    def _file_exists(self, conn, filename):
        """SMB share madhe file aahe ka check karo."""
        try:
            for f in conn.listPath(SMB_SHARE, '/'):
                if f.filename == filename:
                    return True
        except Exception as e:
            logging.error(f"SMB listPath error: {e}")
        return False

    def download_program(self, program_filename , ts):
        """
        SMB varun program download karo ani
        CHUNK_LINES lines per chunk event_queue madhe put karo.
        Fanuc get_cnc_programe logic nusaar.

        Returns: True jar successful
        """
        if not SMB_AVAILABLE:
            logging.error("pysmb not available")
            return False

        conn = self._smb_connect()
        if not conn:
            return False

        try:
            # File exist ka?
            if not self._file_exists(conn, program_filename):
                logging.warning(f"File not found on HAAS share: {program_filename}")
                conn.close()
                return False

            logging.info(f"Downloading: {program_filename}")
            start_time = perf_counter()

            # In-memory download
            buf = io.BytesIO()
            conn.retrieveFile(SMB_SHARE, program_filename, buf)
            conn.close()

            buf.seek(0)
            raw = buf.read()

            # Decode
            try:
                content = raw.decode('utf-8')
            except UnicodeDecodeError:
                content = raw.decode('latin-1')

            all_lines  = [l for l in content.splitlines() if l.strip()]
            total      = len(all_lines)
            poll_time  = round(perf_counter() - start_time, 4)

            if total == 0:
                logging.warning("Empty program file")
                return False

            logging.info(f"Downloaded {total} lines in {poll_time}s — chunking...")

            # Chunk karo ani event_queue madhe put karo
            chunk_num = 0
            data = {"ts": ts,
                    "name": program_filename,
                    "edgeid": self.edgeid}
            for start in range(0, total, CHUNK_LINES):
                chunk_lines = all_lines[start: start + CHUNK_LINES]
                chunk_num  += 1
                data['chunk'] = chunk_num
                data['program'] = json.dumps(["\n\r\r".join(chunk_lines)]),  # Fanuc sarkha single string

                # Fanuc-style MQTT payload
                # payload = {
                #     "get_cnc_programe": {
                #         "ts":     ts,
                #         "name":    program_filename,
                #         "program": ["\n\r\r".join(chunk_lines)],  # Fanuc sarkha single string
                #         "edgeid":  self.edgeid,
                #         "chunk":   chunk_num,
                #         "time":    poll_time,
                #     },
                #     "poll_time": poll_time,
                #     "edgeid":    self.edgeid,
                # }
                with self.lock:
                    self.redis.xadd("program",data)
                    # if not self.event_queue.full():
                    #     self.event_queue.put(payload)
                    # else:
                    #     logging.warning(f"event_queue full — chunk {chunk_num} dropped")

                # logging.info(
                #     f"Chunk {chunk_num} queued "
                #     f"(lines {start+1}–{min(start+CHUNK_LINES, total)}/{total})"
                # )
                sleep(0.05)

            logging.info(f"Published {chunk_num} chunks for: {program_filename}")
            return True

        except Exception as e:
            logging.error(f"Download error: {e}")
            try:
                conn.close()
            except Exception:
                pass
            return False

    # ──────────────────────────────────────────────────────
    # Main loop
    # ──────────────────────────────────────────────────────
    def run(self) -> None:
        pid = os.getpid()
        logging.info(f"[PID {pid}] HassDriver running: {self.edgeid}")

        try:
            while True:
                if not self.program_event.empty():
                    event = self.program_event.get()
                    
                    program_filename = event.get('value', '')
                    ts = event.get('ts')
                    trigger_reason   = (
                        "date_change"      if event.get('date_change') else
                        "4hr_idle"         if event.get('idle_reset')  else
                        "new_program"
                    )

                    logging.info(
                        f"Download trigger [{trigger_reason}]: {program_filename}"
                    )

                    if program_filename and program_filename != 'UNAVAILABLE':
                        self.download_program(program_filename,ts)
                    else:
                        logging.warning(f"Invalid program name: {program_filename}")

                sleep(0.1)

        except (Exception, KeyboardInterrupt) as e:
            logging.error(f"[PID {pid}] HassDriver error {self.edgeid}: {e}")

        finally:
            self.mqtt_sender.stop()

    def terminate(self) -> None:
        logging.info(f"Terminating HASS {self.edgeid}")
        self.mqtt_sender.stop()
        super().terminate()