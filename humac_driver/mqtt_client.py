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
        # json_data = json.dumps(data)
        result = self.client.publish(TOPIC,data,qos=1)
        result.wait_for_publish()
        logging.info(f"Published data to topic {TOPIC}: {data}")

    def run(self):
         logging.info("Creating mqtt client instance")      
         try:
            self._client_connect()
            self.client.loop_start()
            while self.running:
                if self.connected:
                    result =self.client.publish(TOPIC, {"get_cnc_programe": {"ts": 1767947673360, "name": "O21", "program": ["%\nO0021(FLAT PROGRAM)\nN1 \nG0G91G28Z.0\nG0G90G55X-665.5Y0.0\nG0G43Z200.0\nS1200M03 \nM08\nG0Z5.0 \nG01Z0.0F500\nG01Z-2.0F300 \nG01Y90.0F300 \nG0Z0.0 \nG0Y0.0 \nG01Z-3.5F300 \nG01Y90.0F300 \nG0Z0.0 \nG0Y0.0 \nG01Z-4.5F300 \nG01Y90.0F300 \nG0Z0.0 \nG0Y0.0 \nG01Z-4.99F300\nG01Y15", "0.0F300\nG0G80G40Z200.0 \nM05\nM09\nG0G91G28Z0.0Y0.0 \nM30\n \nG0Z0.0 \nG0Y0.0 \nG01Z-5.0 \nG01Y110.0\nG0Z0.0 \nG0Y0.0 \nG01Z-6.5 \nG01Y120.0\nG0Z0.0 \nG0Y0.0 \nG01Z-6.975 \nG01Y150.0\nG0Z0.0 \nM09\nG0G80G40Z100.0 \nM05\nM09\nG0G91G28Y0.0Z0.0 \nM30\n%0 \nG0Y0.0 \nG01Z-4.99F300\nG01Y15"], "time": 0.0931}, "poll_time": 0.0932}, qos=1)
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