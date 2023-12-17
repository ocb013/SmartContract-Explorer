from web3 import Web3
import os
import pymysql
import logging
import time
from requests.exceptions import HTTPError

infura_url = os.getenv("INFURA_URL")
db_host = os.getenv("MYSQL_HOST")
db_user = os.getenv("MYSQL_NAME")
db_password = os.getenv("MYSQL_PASSWORD")
db_name = os.getenv("MYSQL_DATABASE")

log_file = '/root/files/info_log.txt'
block_file = '/root/files/last_processed_block.txt'

logging.basicConfig(filename=log_file, level=logging.INFO)

web3 = Web3(Web3.HTTPProvider(infura_url))

# Checking connection
if web3.is_connected():
    logging.info("Подключение к Infura успешно.")
else:
    logging.error("Failed to connect to Infura.")
    exit(1)

# Read last checked block from the file
try:
    with open(block_file, 'r') as file:
        start_block = int(file.read().strip())
except (FileNotFoundError, ValueError):
    start_block = 0

latest_block_number = web3.eth.block_number
logging.info("Last block: %d", latest_block_number)

connection = pymysql.connect(host=db_host, user=db_user, password=db_password, database=db_name)
cursor = connection.cursor()

try:
    logging.info("Starting a search")
    for block_number in range(start_block, latest_block_number + 1):
        try:
            block = web3.eth.get_block(block_number, True)  # Get info about the block
        except HTTPError as e:
            if e.response.status_code == 429:  # 429 is the HTTP status code for "Too Many Requests"
                logging.info("Infura API rate limit exceeded. Sleeping for a while.")
                time.sleep(86400)  # Sleep for 60 seconds
                continue
            else:
                raise  # Re-raise other HTTPError exceptions

        transactions = block.transactions

        for tx in transactions:
            to_address = tx.get('to')
            if to_address:
                code = web3.eth.get_code(to_address)
                if code and code != '0x':
                    try:
                        # Unique addresses in the table
                        insert_query = "INSERT IGNORE INTO contract_addresses (address) VALUES (%s)"
                        cursor.execute(insert_query, (to_address,))
                        logging.info("Find a new contract: %s", to_address)
                    except pymysql.err.OperationalError as db_error:
                        # Handle database connection error
                        logging.error("Database connection error: %s", str(db_error))
                        logging.info("Reconnecting to the database...")
                        connection.close()
                        connection = connect_to_database()
                        cursor = connection.cursor()
                        logging.info("Reconnected to the database.")
                    
        connection.commit()

        # Rewrite last checked block
        with open(block_file, 'w') as file:
            file.write(str(block_number))

        

except Exception as e:
    logging.error("Error: %s", str(e), exc_info=True)

finally:
    if 'connection' in locals():
        cursor.close()
        connection.close()
