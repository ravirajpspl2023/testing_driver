from humac_driver.Driver_Initilization import HumacDriver
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if __name__ == "__main__":
    start_time = time.perf_counter()
    
    try:
        driver = HumacDriver()
        if driver.machines:
            for m in driver.machines:
                m.join()
        end_time = time.perf_counter()
        logging.info(f'time required for completion is : {end_time-start_time}s')
    except KeyboardInterrupt or Exception as e:
        logging.info(f"Main process interrupted: {e}")
        driver.stop_all_machines()
    