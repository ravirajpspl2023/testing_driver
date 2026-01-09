import paho.mqtt.client as mqtt
from humac_driver.const import *
import json
import time
import logging
import threading
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
class MqttSender(threading.Thread):
    def __init__(self,):
        threading.Thread.__init__(self)
        self.running = True
        self.connected = False
        self.start()
        
    def _client_connect(self):
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="humac_driver",
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
    
    def publish_data(self,data):
        if not self.connected:
            return
        json_data = json.dumps(data)
        result = self.client.publish(TOPIC,json_data,qos=1)
        result.wait_for_publish()
        logging.info(f"Published data to topic {TOPIC}: {json_data}")

    def run(self):
         logging.info("Creating mqtt client instance")      
         try:
            self._client_connect()
            self.client.loop_start()
            while self.running:
                if self.connected:
                    result =self.client.publish(TOPIC, json.dumps({"status": "running"}), qos=1)
                    result.wait_for_publish()

                time.sleep(1)
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