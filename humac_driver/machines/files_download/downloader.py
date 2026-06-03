import boto3
from botocore.config import Config
import os
import json
import time
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from botocore.exceptions import ClientError, EndpointConnectionError
from humac_driver.machines.utils import load_config
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class S3Downloader:
    def __init__(self,):
        self.config = load_config()
        self.s3_client = None
        self.connect()
        
    def connect(self):
        """Connect with retry"""
        try:
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=self.config['s3']['endpoint_url'],
                aws_access_key_id=self.config['s3']['aws_access_key_id'],
                aws_secret_access_key=self.config['s3']['aws_secret_access_key'],
                region_name=self.config['s3']['region_name'],
                config=Config(signature_version="s3v4", retries={'max_attempts': 3})
            )
            logging.info("✅ Connected to S3 successfully")
        except Exception as e:
            logging.error(f"Failed to connect to S3: {e}")
            raise

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=30))
    def download_new_files(self):
        try:
            machine_id = self.config['s3']['machineid']
            today_date = time.strftime("%Y-%m-%d")
            prefix = f"{machine_id}_{today_date}/"
            response = self.s3_client.list_objects_v2(Bucket=self.config['s3']['bucket'], Prefix=prefix)
            
            if 'Contents' not in response:
                logging.info(f"No files in bucket folder: {machine_id}")
                return []
            # self.logger.info(f"Contents: {response['Contents']}")
            current_keys = [obj['Key'] for obj in response['Contents']]
            last_state = self._load_state()
            new_keys = [k for k in current_keys if k not in last_state.get('last_keys', [])]

            if new_keys:
                logging.info(f"Found {len(new_keys)} new files")
                for key in new_keys:
                    self._download_single_file(key)
                self._save_state(current_keys)
            else:
                logging.debug("No new files")

            return new_keys
        except (ClientError, EndpointConnectionError) as e:
            logging.warning(f"Connection issue: {e}. Reconnecting...")
            self.connect()
            raise
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            raise

    def _download_single_file(self, key):
        local_path = os.path.join(self.config['local']['download_folder'], os.path.basename(key))
        try:
            self.s3_client.download_file(self.config['s3']['bucket'], key, local_path)
            logging.info(f"✅ Downloaded: {key}")
        except Exception as e:
            logging.error(f"Failed to download {key}: {e}")

    def _load_state(self):
        path = self.config['local']['state_file']
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
        return {"last_keys": []}

    def _save_state(self, keys):
        path = self.config['local']['state_file']
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump({"last_keys": keys, "last_updated": time.time()}, f)