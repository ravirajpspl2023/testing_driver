from humac_driver.Driver_Initilization import HumacDriver
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if __name__ == "__main__":
    start_time = time.perf_counter()
    config = {
        "machines":[
            {"ip":"192.168.1.190", "port":1883,"timeout":5,"edgid" :"VMC03"},
            {'ip':"192.168.1.196", "port":1883,"timeout":2,"edgid" :"VMC08"},
            {'ip':"193.168.0.4", "port":1883,"timeout":8,"edgid" :"ed4200003"}
        ]
    }
    driver = HumacDriver(config=config)
    if driver.machines:
        for m in driver.machines:
             m.join()
    end_time = time.perf_counter()
    logging.info(f'time requird for complition is : {end_time-start_time}s')
    