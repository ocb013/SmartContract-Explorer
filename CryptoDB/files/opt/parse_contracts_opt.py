from web3 import Web3
from web3.middleware import geth_poa_middleware
import os
import pymysql
import logging
import time
from requests.exceptions import HTTPError

infura_url = os.getenv("INFURA_URL_OPT")
db_host = os.getenv("MYSQL_HOST")
db_user = os.getenv("MYSQL_NAME")
db_password = os.getenv("MYSQL_PASSWORD")
db_name = os.getenv("MYSQL_DATABASE")

log_file = '/root/files/opt/info_log_opt.txt'
block_file = '/root/files/last_blocks/last_processed_block_opt.txt'

logging.basicConfig(filename=log_file, level=logging.INFO)

def connect_to_database():
    return pymysql.connect(host=db_host, user=db_user, password=db_password, database=db_name)

while True:
    web3 = Web3(Web3.HTTPProvider(infura_url))
    web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    # Переменные для соединения и курсора вынесены за пределы цикла
    connection = None
    cursor = None

    try:
        connection = connect_to_database()
        cursor = connection.cursor()

        if web3.is_connected():
            logging.info("Подключение к Infura успешно.")
        else:   
            logging.error("Не удалось подключиться к Infura.")
            exit(1)

        try:
            with open(block_file, 'r') as file:
                start_block = int(file.read().strip())
        except (FileNotFoundError, ValueError):
            start_block = 0

        latest_block_number = web3.eth.block_number
        logging.info("Last block: %d", latest_block_number)

        for block_number in range(start_block, latest_block_number + 1):
            try:
                block = web3.eth.get_block(block_number, True)
            except HTTPError as e:
                if e.response.status_code == 429:
                    logging.info("Infura API rate limit exceeded. Sleeping for a while.")
                    time.sleep(86400)
                    continue
                else:
                    raise

            transactions = block.transactions

            for tx in transactions:
                to_address = tx.get('to')
                if to_address:
                    try:
                        code = web3.eth.get_code(to_address)
                    except HTTPError as e:
                        if e.response.status_code == 429:
                            logging.info("Infura API rate limit exceeded. Sleeping for a while.")
                            time.sleep(86400)
                            continue
                        else:
                            raise
                    if code and code != '0x':
                        try:
                            insert_query = "INSERT IGNORE INTO contract_addresses_opt (address) VALUES (%s)"
                            cursor.execute(insert_query, (to_address,))
                            logging.info("Find a new contract: %s", to_address)
                        except pymysql.err.OperationalError as db_error:
                            logging.error("Database connection error: %s", str(db_error))
                            logging.info("Reconnecting to the database...")
                            connection.close()
                            connection = connect_to_database()
                            cursor = connection.cursor()
                            logging.info("Reconnected to the database.")

            connection.commit()

            with open(block_file, 'w') as file:
                file.write(str(block_number))

    except Exception as e:
        logging.error("Error: %s", str(e), exc_info=True)

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    time.sleep(86400)
