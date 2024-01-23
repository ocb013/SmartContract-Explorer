from flask import Flask, render_template, request, jsonify
from flask.helpers import send_file
import pymysql.cursors
import os
import zipfile
import io


app = Flask(__name__)

# DB Settings
db_config = {
    'host': os.getenv('MYSQL_HOST'),
    'user': os.getenv('MYSQL_NAME'),
    'password': os.getenv('MYSQL_PASSWORD'),
    'db': os.getenv('MYSQL_DATABASE'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
}

@app.route('/')
def index():
    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            # SQL Without filters

            sql = f"SELECT id, contract_address, verified_code, tokens_balances, tokens_list, contract_name, contract_usd_balance, contract_eth_balance, notes, chain FROM processed_contract_info LIMIT 50"
            cursor.execute(sql)
            result = cursor.fetchall()
            
    finally:
        conn.close()

    return render_template('index.html', data=result)

@app.route('/get_text_data/<chain>')
def get_text_data(chain):
    file_path = f'/root/files/last_blocks/last_processed_block_{chain.lower()}.txt'
    
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            text_data = file.read()
        return text_data
    else:
        return "File not found"

@app.route('/apply_filters', methods=['GET'])
def apply_filters():
    verified_code = request.args.get('verified_code')
    eth_balance_operator = request.args.get('eth_balance_operator')
    eth_balance_value = request.args.get('eth_balance_value')
    usd_balance_operator = request.args.get('usd_balance_operator')
    usd_balance_value = request.args.get('usd_balance_value')
    chain_name = request.args.get('chain_name')
    
    page = int(request.args.get('page', 1))
    records_per_page = 50

    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            sql = "SELECT id, contract_address, verified_code, tokens_balances, tokens_list, contract_name, contract_usd_balance, contract_eth_balance, notes, chain FROM processed_contract_info WHERE 1"

            params = []

            if verified_code != 'all':
                sql += " AND verified_code = %s"
                params.append(int(verified_code))

            if eth_balance_operator and eth_balance_value:
                if eth_balance_operator == 'ge':
                    sql += " AND contract_eth_balance >= %s"
                elif eth_balance_operator == 'le':
                    sql += " AND contract_eth_balance <= %s"
                else:
                    sql += " AND contract_eth_balance = %s"
                params.append(float(eth_balance_value))
                    
            if usd_balance_operator and usd_balance_value:
                if usd_balance_operator == 'ge':
                    sql += " AND contract_usd_balance >= %s"
                elif usd_balance_operator == 'le':
                    sql += " AND contract_usd_balance <= %s"
                else:
                    sql += " AND contract_usd_balance = %s"
                params.append(float(usd_balance_value))
                
            if chain_name != 'all':
                sql += " AND chain = %s"
                params.append(chain_name)
                
            start_index = (page - 1) * records_per_page
            
            sql += f" LIMIT {start_index}, {records_per_page}"

            cursor.execute(sql, tuple(params))
            result = cursor.fetchall()
    finally:
        conn.close()

    return jsonify(result)

@app.route('/download_zip', methods=['GET'])
def download_zip():
    conn = pymysql.connect(**db_config)
    verified_code = request.args.get('verified_code')
    eth_balance_operator = request.args.get('eth_balance_operator')
    eth_balance_value = request.args.get('eth_balance_value')
    usd_balance_operator = request.args.get('usd_balance_operator')
    usd_balance_value = request.args.get('usd_balance_value')
    chain_name = request.args.get('chain_name')
    
    try:
        with conn.cursor() as cursor:
            sql = "SELECT source_code, contract_address FROM processed_contract_info WHERE 1"
            
            params = []

            if verified_code != 'all':
                sql += " AND verified_code = %s"
                params.append(int(verified_code))

            if eth_balance_operator and eth_balance_value:
                if eth_balance_operator == 'ge':
                    sql += " AND contract_eth_balance >= %s"
                elif eth_balance_operator == 'le':
                    sql += " AND contract_eth_balance <= %s"
                else:
                    sql += " AND contract_eth_balance = %s"
                params.append(float(eth_balance_value))
                    
            if usd_balance_operator and usd_balance_value:
                if usd_balance_operator == 'ge':
                    sql += " AND contract_usd_balance >= %s"
                elif usd_balance_operator == 'le':
                    sql += " AND contract_usd_balance <= %s"
                else:
                    sql += " AND contract_usd_balance = %s"
                params.append(float(usd_balance_value))
                
            if chain_name != 'all':
                sql += " AND chain = %s"
                params.append(chain_name)

            cursor.execute(sql, tuple(params))
            result = cursor.fetchall()

            # Создаем временный буфер в памяти
            zip_buffer = io.BytesIO()

            # Создаем Zip-архив
            with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
                for item in result:
                    contract_address = item['contract_address']
                    contract_code = item['source_code']

                    # Добавляем файл в архив
                    zip_file.writestr(f"{contract_address}.sol", contract_code)

            zip_buffer.seek(0)

    finally:
        conn.close()

    # Отправим файл пользователю для скачивания
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='contracts.zip'
    )


@app.route('/add_note', methods=['POST'])
def add_note():
    contract_id = request.form['contract_id']
    note_text = request.form['note_text']

    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE processed_contract_info SET notes = %s WHERE id = %s"
            cursor.execute(sql, (note_text, contract_id))
            conn.commit()
    finally:
        conn.close()

    return 'Note added successfully'

@app.route('/delete_note', methods=['POST'])
def delete_note():
    contract_id = request.form['contract_id']

    conn = pymysql.connect(**db_config)
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE processed_contract_info SET notes = NULL WHERE id = %s"
            cursor.execute(sql, (contract_id,))
            conn.commit()
    finally:
        conn.close()

    return 'Note deleted successfully'


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')