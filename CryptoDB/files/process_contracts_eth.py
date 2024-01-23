import os
import logging
from time import sleep
import requests
import pymysql
from decimal import Decimal
from math import floor
from datetime import datetime

# Secret vars
db_host = os.getenv("MYSQL_HOST")
db_user = os.getenv("MYSQL_NAME")
db_password = os.getenv("MYSQL_PASSWORD")
db_name = os.getenv("MYSQL_DATABASE")
ETHERSCAN_API = os.getenv("ETHERSCAN_API")
COVALENTHQ_API = os.getenv("COVALENTHQ_ETH_API")

LAST_CHECKED_TIME_FILE = "/root/files/last_checked_time_eth.txt"
LOG_FILE_PATH = '/root/files/contract_info_log_eth.txt'

ETHERSCAN_BASE_URL = "https://api.etherscan.io/api"
COINGECKO_BASE_URL = 'https://api.coingecko.com/api/v3'

# Set the logs
logging.basicConfig(filename=LOG_FILE_PATH, level=logging.INFO)


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


def get_last_checked_time():
    if os.path.exists(LAST_CHECKED_TIME_FILE):
        with open(LAST_CHECKED_TIME_FILE, "r") as file:
            last_checked_time_str = file.read().strip()
        try:
            return datetime.strptime(last_checked_time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    else:
        return None
    
def get_last_created_time():
    connection = pymysql.connect(host=db_host, user=db_user, password=db_password, db=db_name, charset='utf8mb4',
                                 cursorclass=pymysql.cursors.DictCursor)

    try:
        with connection.cursor() as cursor:
            sql = "SELECT MAX(created_at) AS last_created_time FROM contract_addresses_eth"
            cursor.execute(sql)
            result = cursor.fetchone()
            last_created_time = result.get("last_created_time")
            return last_created_time
    finally:
        connection.close()


def save_last_checked_time(created_at):
    with open(LAST_CHECKED_TIME_FILE, "w") as file:
        file.write(created_at.strftime("%Y-%m-%d %H:%M:%S"))


def get_smartcontract_balance(smartcontract_address, chain_name, covalenthq_api_key):
        base_url = "https://api.covalenthq.com/v1/"
        endpoint = f"{chain_name.lower()}/address/{smartcontract_address}/balances_v2/"

        url = f"{base_url}{endpoint}?key={covalenthq_api_key}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            return data

        else:
            print(f"Error: {response.status_code}")
            return None

def get_tokens_prices(coingecko_platform_id, tokens_addresses):
    url = f"https://api.coingecko.com/api/v3/simple/token_price/{coingecko_platform_id}"
    vs_currencies = "usd"
    chunk_size = 7  # Maximum of addresses per one request

    try:
        prices_list = []

        address_chunks = [tokens_addresses[i:i + chunk_size] for i in range(0, len(tokens_addresses), chunk_size)]

        for chunk in address_chunks:
            params = {
                'contract_addresses': ','.join(chunk),
                'vs_currencies': vs_currencies
            }

            response = requests.get(url, params=params)
            response.raise_for_status() 
            data = response.json()

            for address in chunk:
                price = data.get(address, {}).get(vs_currencies, 0.0)
                prices_list.append(price)

            sleep(60)
            
        return prices_list

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None


def insert_processed_info(data, chain_value="ETH"):
    connection = pymysql.connect(host=db_host, user=db_user, password=db_password, db=db_name, charset='utf8mb4',
                                 cursorclass=pymysql.cursors.DictCursor)

    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO processed_contract_info (contract_address, verified_code, tokens_balances, " \
                  "tokens_list, source_code, contract_name, contract_usd_balance, contract_eth_balance, notes, chain) " \
                  "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" 

            try:
                if len(data["tokens_balances"]) > 100:
                    data["tokens_balances"] = data["tokens_balances"][:100]

                if len(data["tokens_list"]) > 100:
                    data["tokens_list"] = data["tokens_list"][:100]

                cursor.execute(sql, (
                    data["contract_address"],
                    data["verified_code"],
                    data["tokens_balances"],
                    data["tokens_list"],
                    data["source_code"],
                    data["contract_name"],
                    data["contract_usd_balance"],
                    data["contract_eth_balance"],
                    data.get("notes", None),
                    chain_value
                ))
                connection.commit()
            except pymysql.Error as e:
                logging.error(f"Error inserting data: {e}")
    finally:
        connection.close()


def process_token_balances(data, smartcontract_address):
    items = data.get('data', {}).get('items', [])

    if not items:
        logging.info("No data about token balances")
        return

    filtered_tokens = [token_info for token_info in items if token_info.get('contract_ticker_symbol') != 'ETH']

    tokens_addresses = [token_info.get('contract_address') for token_info in filtered_tokens]
    tokens_symbols = ["ERR" if token_info.get('contract_ticker_symbol') is None else token_info.get('contract_ticker_symbol') for token_info in filtered_tokens]
    tokens_balances = [
        round(int(token_info.get('balance')) / 10 ** int(token_info['contract_decimals']) if token_info.get('contract_decimals') else 18, 2)
        for token_info in filtered_tokens
    ]

    tokens_prices = get_tokens_prices("ethereum", tokens_addresses)

    rounded_tokens_balances = [round(balance) for balance in tokens_balances]

    tokens_list = ";".join(tokens_symbols)
    balances_list = ";".join(map(str, rounded_tokens_balances))

    eth_balance = get_balance(smartcontract_address)
    usd_balance = 0
    
    if tokens_balances and tokens_prices:
        for i in range(len(tokens_addresses)):
            usd_balance += tokens_balances[i] * float(tokens_prices[i])
    else:
        usd_balance = 0
        
    eth_balance_rounded = round(float(eth_balance), 1)    
    usd_balance_rounded = round(float(usd_balance))
    
    processed_data = {
        "contract_address": smartcontract_address,
        "contract_name": get_contract_name(smartcontract_address),
        "contract_eth_balance": eth_balance_rounded,
        "contract_usd_balance": usd_balance_rounded,
        "verified_code": is_contract_verified(smartcontract_address),
        "tokens_list": tokens_list,
        "tokens_balances": balances_list,
        "source_code": get_contract_source_code(smartcontract_address)
    }

    logging.info(processed_data)
    insert_processed_info(processed_data, chain_value="ETH")


def main():
    while True:
        try:
            last_checked_time = get_last_checked_time()

            connection = pymysql.connect(host=db_host, user=db_user, password=db_password, db=db_name, charset='utf8mb4',
                                         cursorclass=pymysql.cursors.DictCursor)

            with connection.cursor() as cursor:
                sql = "SELECT * FROM contract_addresses_eth WHERE created_at > %s "
                cursor.execute(sql, (last_checked_time,))
                contracts = cursor.fetchall()

                processed_any_address = False

                for contract in contracts:
                    smartcontract_address = contract["address"]
                    chain_name = "eth-mainnet"

                    try:
                        token_balances = get_smartcontract_balance(smartcontract_address, chain_name, COVALENTHQ_API)

                        if token_balances and not token_balances.get('error', False):
                            process_token_balances(token_balances, smartcontract_address)
                            processed_any_address = True
                        else:
                            logging.error(
                                f"Проблема с получением балансов токенов для адреса {smartcontract_address}")

                        sleep(15)

                    except Exception as e:
                        logging.error(f"Ошибка при обработке контракта {smartcontract_address}: {e}")
                        
                    last_created_time = contract.get("created_at") 
                    save_last_checked_time(last_created_time)

                if processed_any_address:
                    logging.info("Обработка всех контрактов завершена. Засыпаем на 24 часа.")
                    sleep(24 * 60 * 60)
                else:
                    logging.info("Нет новых контрактов для обработки. Засыпаем на 24 часа.")
                    sleep(24 * 60 * 60)

        finally:
            connection.close()

if __name__ == "__main__":
    main()