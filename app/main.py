from flask import Flask, request
from selenium import webdriver
import os
import gspread
from gspread.exceptions import GSpreadException

from spider import Spider
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"

app = Flask(__name__)

def get_urls():
    try:
        gc = gspread.service_account(filename='credentials.json')
    except GSpreadException as e:
        raise e("Error Authenticating Google Sheets")
    
    try:
        sh = gc.open_by_key("1Vnx-43twBuSptmzWOkBAgft0VtRR1PXeNJqfzXp_X50")
    except GSpreadException as e:
        raise e("Error Opening Spread Sheet")
    else:
        worksheet = sh.worksheet("input")
        input_list = worksheet.get_all_records()
        return [input_data['url'] for input_data in input_list if input_data['scrape'] == 'enable']

@app.route('/scrape', methods=['POST']) 
def run():
    req_data = request.get_json()
    
    email = None
    if 'email' in req_data:
        email = req_data['email']
    password = None
    if 'password' in req_data:
        password = req_data['password']
    
    url_list = get_urls()

    if email and password and url_list:
        spidy = Spider()
        url_list = spidy.modify_urls(url_list)
        spidy.crawl(url_list=url_list, email=email, password=password)
        return ''' Done '''
    else:
        return ''' ERROR in email or password or while fetching urls '''



if __name__ == "__main__":
    app.run(debug=True,host='0.0.0.0',port=int(os.environ.get('PORT', 8080)))