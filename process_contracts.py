import os
import logging
from time import sleep
import requests
from functools import lru_cache
import pymysql

# Your own vars
db_host = os.getenv("MYSQL_HOST")
db_user = os.getenv("MYSQL_NAME")
db_password = os.getenv("MYSQL_PASSWORD")
db_name = os.getenv("MYSQL_DATABASE")
infura_url = os.getenv("INFURA_URL")
ETHERSCAN_API = os.getenv("ETHERSCAN_API")
COVALENTHQ_API = os.getenv("COVALENTHQ_API")


LAST_CHECKED_ADDRESS_FILE = "/root/files/last_checked_address.txt"
LOG_FILE_PATH = '/root/files/contract_info_log.txt'

ETHERSCAN_BASE_URL = "https://api.etherscan.io/api"
COINGECKO_BASE_URL = 'https://api.coingecko.com/api/v3'

# Set the logs 
logging.basicConfig(filename=LOG_FILE_PATH, level=logging.INFO)

@lru_cache(maxsize=None)
def get_eth_to_usd_rate():
    try:
        url = f'{COINGECKO_BASE_URL}/simple/price'
        params = {"ids": "ethereum", "vs_currencies": "usd"}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data['ethereum']['usd'] if data and 'ethereum' in data else None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching ETH to USD rate: {e}")
        return None

def make_request(url, params=None):
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error making request: {e}")
        return None

def get_contract_info(address: str):
    params = {"apikey": ETHERSCAN_API, "module": "contract", "action": "getabi", "address": address}
    return make_request(ETHERSCAN_BASE_URL, params)

def is_contract_verified(address: str) -> bool:
    try:
        contract_info = get_contract_info(address)
        return contract_info.get("status") == "1" and bool(get_contract_source_code(address))
    except requests.exceptions.RequestException:
        return False

def get_contract_name(address: str):
    contract_info = get_contract_info(address)
    return contract_info.get("ContractName", "Unknown Contract")

def get_balance(address: str):
    try:
        url = f'{ETHERSCAN_BASE_URL}?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API}'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return int(data['result']) / 10**18 if data and data.get('status') == '1' else None
    except requests.exceptions.RequestException:
        return None

def get_contract_source_code(address: str):
    try:
        params = {'address': address, 'apikey': ETHERSCAN_API}
        response = requests.get(f'{ETHERSCAN_BASE_URL}?module=contract&action=getsourcecode', params=params)
        response.raise_for_status()
        data = response.json()
        return data['result'][0]['SourceCode'] if data and data.get('status') == '1' else None
    except requests.exceptions.RequestException:
        return None

def eth_to_usd(balance_eth):
    eth_to_usd_rate = get_eth_to_usd_rate()
    return balance_eth * eth_to_usd_rate if eth_to_usd_rate is not None else None

def get_last_checked_address():
    if os.path.exists(LAST_CHECKED_ADDRESS_FILE):
        with open(LAST_CHECKED_ADDRESS_FILE, "r") as file:
            last_checked_address = file.read().strip()
        return last_checked_address
    else:
        return None

def save_last_checked_address(address):
    with open(LAST_CHECKED_ADDRESS_FILE, "w") as file:
        file.write(address)

def get_token_balances(contract_address, chain_name, ETHERSCAN_API):
    try:
        base_url = "https://api.covalenthq.com/v1/"
        endpoint = f"{chain_name.lower()}/address/{contract_address}/balances_v2/"
        url = f"{base_url}{endpoint}?key={ETHERSCAN_API}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None

def insert_processed_info(data):
    connection = pymysql.connect(host=db_host, user=db_user, password=db_password, db=db_name, charset='utf8mb4',
                                 cursorclass=pymysql.cursors.DictCursor)

    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO processed_contract_info (contract_address, verified_code, tokens_balance, " \
                  "token_list, source_code, contract_name, contract_usd_balance) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(sql, (
                data["contract_address"],
                data["verified_code"],
                data["tokens_balance"],
                data["token_list"],
                data["source_code"],
                data["contract_name"],
                data["contract_usd_balance"]
            ))
        connection.commit()

    finally:
        connection.close()

def process_token_balances(data, contract_address):
    items = data.get('data', {}).get('items', [])

    if not items:
        logging.info("No data about token balances")
        return

    token_list = ";".join([f"{token_info.get('contract_name')}" for token_info in items])
    tokens_balance = ";".join([f"{token_info.get('balance')}" for token_info in items])

    eth_balance = get_balance(contract_address)
    usd_balance = eth_to_usd(eth_balance)

    processed_data = {
        "contract_address": contract_address,
        "contract_name": get_contract_name(contract_address),
        "token_eth_balance": eth_balance,
        "contract_usd_balance": usd_balance,
        "verified_code": is_contract_verified(contract_address),
        "token_list": token_list,
        "tokens_balance": tokens_balance,
        "source_code": get_contract_source_code(contract_address)
    }

    logging.info(processed_data)
    insert_processed_info(processed_data)

def main():
    try:
        last_checked_address = get_last_checked_address()
        connection = pymysql.connect(host=db_host, user=db_user, password=db_password, db=db_name, charset='utf8mb4',
                                     cursorclass=pymysql.cursors.DictCursor)

        with connection.cursor() as cursor:
            sql = "SELECT * FROM contract_addresses"
            if last_checked_address:
                sql += f" WHERE address >= '{last_checked_address}'"
            cursor.execute(sql)
            contracts = cursor.fetchall()

            for contract in contracts:
                contract_address = contract["address"]
                chain_name = "eth-mainnet"

                token_balances = get_token_balances(contract_address, chain_name, COVALENTHQ_API)

                if token_balances and not token_balances.get('error', False):
                    process_token_balances(token_balances, contract_address)
                else:
                    logging.error(f"There is an issue with receiving token balances for address {contract_address}")

                save_last_checked_address(contract_address)
                # Спим 5 секунд перед следующим запросом, чтобы не превысить лимиты
                sleep(5)

    except Exception as e:
        logging.error(f"Error in main function: {e}")
        # Если произошла ошибка, спим 24 часа перед повторным запуском
        sleep(24 * 60 * 60)

    finally:
        connection.close()

if __name__ == "__main__":
    main()
