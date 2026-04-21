from multiprocessing import Process, Event
import ast
from humac_driver.database.redis_client import RedisConnection
import paho.mqtt.client as mqtt
import logging
from humac_driver.const import *
import time
import json
import socket

class MqttPublisher(Process):
    def __init__(self,stream):
        super().__init__(name=stream)
        self.stream = stream
        self.logger = logging.getLogger(f"{self.name}_pub")
        self.redis=  RedisConnection(stream).connect()
        self.group_name = "HumacDriver"
        self.mqtt_client = f"{MQTT_CLI}_{stream}"
        self._stop_event = Event()
        if self.stream == "program":
            self.mqtt_topic = TOPIC_PRO
        if self.stream == "block":
            self.mqtt_topic = TOPIC_BLK
        self.password = None
        self.client = None
        self.start()

    def _check_host_connectivity(self,):
        """Check if the host and port are connectable."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                result = sock.connect_ex((MQTT_HOST, MQTT_PORT))
                if result == 0:
                    return True
                else:
                    return False
        except socket.gaierror:
            return False
        except Exception as e:
            return False
    
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.logger.info(f"{self.stream} mqtt client connected {reason_code}")
        else:
            self.logger.error(f"{self.stream} mqtt client failed to connect with code {reason_code}")
    
    def on_message(self, client, userdata, message, properties=None):
        self.logger.info(f"Received message on topic {message.topic}: {message.payload.decode()}")
    
    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        # self.client.loop_stop()
        self.logger.warning(f"Disconnected from {self.client._host}:{self.client._port}")
        self.connected = False

    def _publish(self,payload):
        try:
            if self.client:
                result = self.client.publish(self.mqtt_topic, json.dumps(payload),qos=1)
                result.wait_for_publish()
                return True
        except Exception as e:
            self.logger.error(f"Failed to publish message: {e}")
            return False

    def _connect(self):
        try:
            self.client = mqtt.Client( mqtt.CallbackAPIVersion.VERSION2,
                                   client_id= self.mqtt_client, clean_session=True,reconnect_on_failure=True)
            if MQTT_PASS is not None:
                self.password = MQTT_PASS.encode('utf-8')
            self.client.username_pw_set(MQTT_PASS, self.password)
            self.client.reconnect_delay_set(1,15)
            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.on_disconnect = self.on_disconnect
            try:
                self.client.connect(MQTT_HOST, MQTT_PORT,keepalive=15)
                self.client.loop_start()
            except Exception as e:
                logging.error(f"mqtt client connection error: {e}")   
        except Exception as e:
            self.logger.error(f"MQTT connection error: {e}")

    def run(self):
        try: 
            while not self._check_host_connectivity():
                time.sleep(10)
            self._connect()
            self.logger.info(f"{self.name} publisher started")
            while not self._stop_event.is_set():
                try:
                    msgs = self.redis.xreadgroup(self.group_name,f"{self.stream}_consumer",{self.stream: ">"},count=1,block=1000)
                    if msgs:
                        for stream, messages in msgs:
                            for msg_id, fields in messages:
                                # if fields.get('program'):
                                #     fields['program'] = json.loads(fields.get('program'))
                                data={}
                                for key, value in fields.items():
                                    str_key = key.decode() if isinstance(key, bytes) else key
                                    str_val = value.decode() if isinstance(value, bytes) else value
                                    data[str_key] = ast.literal_eval(str_val)

                                self.logger.info(f"fields:{data}")
                                while not self._publish(data):
                                    time.sleep(10)
                                self.redis.xack(self.stream, self.group_name, msg_id)
                                self.redis.xdel(self.stream, msg_id)
                    else:
                        time.sleep(0.1)
                        
                except Exception as e:
                    self.logger.error(f"Error in read/publish loop: {e}")
                    time.sleep(1.0)

        except KeyboardInterrupt:
            self.logger.warning("Received KeyboardInterrupt in run")
        except Exception as e:
            self.logger.error(f"Critical error in {self.name}: {e}")
        finally:
            self.stop()
            self.logger.info(f"Process {self.name} stopped cleanly")

    def terminate(self):
        self._stop_event.set()