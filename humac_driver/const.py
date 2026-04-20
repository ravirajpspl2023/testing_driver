
#driver file config
WIN_BASE_PATH_LIB= "C:/Users/DELL/Desktop/test_fanuc/humac_driver/lib"
LIN_BASE_PATH_LIB ="./humac_driver/lib"
EXTRA_LIB = []
FILE_NAME_WIN = "Fwlib64.dll"
FILE_NAME_LIN = "libfwlib32-linux-armv7.so.1.0.5"

#mqtt details
MQTT_HOST = "216.48.182.104"
MQTT_PORT = 1883
TOPIC_PRO = "pspl-iot/telemetry_cnc/programe"
TOPIC_BLK = "pspl-iot/telemetry_cnc/block"

config = {
        "machines":[
           {"fanuc":{"ip":"192.168.0.2", "port":8193,"timeout":5,"edgid" :"e420004" , "machineid":"CNC004"}},
         #   {"hass":{"ip":"192.168.0.2", "port":8082,"timeout":5,"edgid" :"ed4200022" , "machineid":"SACNC02"}},
        ]
    }
