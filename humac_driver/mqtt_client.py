from unittest import result
import paho.mqtt.client as mqtt
from humac_driver.const import *
from multiprocessing import Queue
import json
import time
import logging
import threading
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
class MqttSender(threading.Thread):
    def __init__(self,event_queue=Queue(),block_queue=Queue()):
        threading.Thread.__init__(self)
        self.running = True
        self.event_queue = event_queue
        self.block_queue = block_queue
        self.connected = False
        self.lock = threading.Lock()
        self.start()
        
    def _client_connect(self):
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="VMC-09",
            clean_session=True,
            reconnect_on_failure=True
        )
        self.client.reconnect_delay_set(1,5)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        try:
            self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=15)
        except Exception as e:
            logging.error(f"Connection attempt failed: {e}")
            
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.connected = True
            logging.info(f"MQTT {MQTT_HOST} is connected")
        else:
            logging.error(f"Failed to connect server mqtt return code {reason_code} {MQTT_HOST}")

    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        logging.warning(f"Disconnected from server MQTT broker {MQTT_HOST}")
        self.connected = False
    def publish_data(self, payload):
            try :
                result =self.client.publish(TOPIC_PRO, json.dumps(payload), qos=1)
                result.wait_for_publish()
            except Exception as e:
                logging.error(f"Failed to publish data to mqtt broker: {e}")

    def run(self):
         logging.info("Creating mqtt client instance")      
         try:
            self._client_connect()
            self.client.loop_start()
            while self.running:
                try:
                    if self.connected and not self.event_queue.empty():
                        for i in range(self.event_queue.qsize()):
                            with self.lock:
                                result =self.client.publish(TOPIC_PRO, json.dumps(self.event_queue.get()), qos=1)
                                result.wait_for_publish()

                    if self.connected and not self.block_queue.empty():
                        for i in range(self.block_queue.qsize()):
                            with self.lock:
                                result =self.client.publish(TOPIC_BLK, json.dumps(self.block_queue.get()), qos=1)
                                result.wait_for_publish()
                except Exception as e :
                    if self.connected is False:
                        self._client_connect()
                        time.sleep(5)
                time.sleep(0.1)
         except Exception as e:
            logging.error(f"Failed to connecte mqtt broker: {e}")
         except Exception as e:
             logging.error(e)

    def stop(self):
        if self.client.is_connected():
            self.client.disconnect()
            self.client.loop_stop()
            logging.info("disconnected to mqtt broker")
        self.running = False