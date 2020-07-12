from login import Login
from utils import Apps
from detail_page import DetailPage
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common import exceptions
from bs4 import BeautifulSoup 
from urllib.parse import urljoin
from urllib.request import urlparse
from time import sleep
from random import uniform
from datetime import datetime
import os
import codecs
import pandas as pd
from google.cloud import bigquery

class Spider:

    def __init__(self):
        self._ouput = os.path.join(os.getcwd(), 'output')
        self._base_url = "https://www.appbrain.com/dev/"
    
    def _upload(self, df, table_id, job_config, client):
        job = client.load_table_from_dataframe(
            df, table_id, job_config=job_config
        )
        job.result()

    
    def _upload_bigquery(self, download, rating_history):
        client = bigquery.Client()
        table_download_history = "prelax-app-data.app_brain.download_history"
        table_rating_history = "prelax-app-data.app_brain.rating_history"
        
        schema_rating_history = [
            bigquery.SchemaField("rating_history_date",bigquery.enums.SqlTypeNames.TIMESTAMP),
            bigquery.SchemaField("inserted_at",bigquery.enums.SqlTypeNames.TIMESTAMP),
        ]
        schema_download = [
            bigquery.SchemaField("date",bigquery.enums.SqlTypeNames.TIMESTAMP),
            bigquery.SchemaField("status",bigquery.enums.SqlTypeNames.TIMESTAMP),
            bigquery.SchemaField("release_date",bigquery.enums.SqlTypeNames.TIMESTAMP),
            bigquery.SchemaField("latest_date",bigquery.enums.SqlTypeNames.TIMESTAMP),
            bigquery.SchemaField("previous_date",bigquery.enums.SqlTypeNames.TIMESTAMP),
            bigquery.SchemaField("inserted_at",bigquery.enums.SqlTypeNames.TIMESTAMP),
        ]

        job_config = bigquery.LoadJobConfig()
        job_config.write_disposition = bigquery.job.WriteDisposition.WRITE_APPEND
        job_config.source_format = bigquery.job.SourceFormat.PARQUET

        job_config.schema = schema_download
        download['date'] = pd.to_datetime(download['date'])
        download['status'] = pd.to_datetime(download['status'])
        download['release_date'] = pd.to_datetime(download['release_date'])
        download['latest_date'] = pd.to_datetime(download['latest_date'])
        download['previous_date'] = pd.to_datetime(download['previous_date'])
        download['inserted_at'] = pd.to_datetime(download['inserted_at'])
        self._upload(df=download, table_id=table_download_history, job_config=job_config, client=client)

        job_config.schema = schema_rating_history
        rating_history['inserted_at'] = pd.to_datetime(rating_history['inserted_at'])
        rating_history['rating_history_date'] = pd.to_datetime(rating_history['rating_history_date'])
        self._upload(df=rating_history, table_id=table_rating_history, job_config=job_config, client=client)

    def _get_data(self,df):
        df['date'] = pd.to_datetime(df['date'])
        df['status'] = pd.to_datetime(df['status'])
        
        download = df[df.installs.notnull()].sort_values(['app_name','date']).groupby('app_name', as_index=False).tail(2)
        download['rank'] = download.groupby(by=['app_name'])['date'].rank(method="first", ascending=True)
        download["installs"] = download["installs"].str.replace("installs", "")

        download_latest = download[download['rank'] == 2.0].rename(columns={'date': 'latest_date', 'installs': 'latest_installs'})
        download_previous = download[download['rank'] == 1.0].rename(columns={'date': 'previous_date', 'installs': 'previous_installs'})

        download_selected_columns = ['app_name','latest_date','latest_installs','previous_date','previous_installs']
        download_df = download_previous.join(download_latest.set_index('app_name')[['latest_date','latest_installs']], on='app_name')[download_selected_columns]

        release_selected_columns = ['app_name','release_date','release_description']
        release_df = df[df['update'].notnull()].sort_values(['app_name','date']).groupby('app_name', as_index=False).head(1).rename(columns={'date': 'release_date','description':'release_description'})[release_selected_columns]

        data = release_df.join(download_df.set_index('app_name')[['latest_date','latest_installs','previous_date','previous_installs']], on='app_name')
        data['inserted_at'] = pd.to_datetime('today')
        data['app_category'] = data.release_description.str.extract('in(.*)for',expand=False)
        data['app_category'] = data['app_category'].str.strip('app_category')
        data.latest_date.fillna(data.previous_date, inplace=True)
        data.latest_installs.fillna(data.previous_installs, inplace=True)
        data['release_year'] = data['release_date'].dt.year
        data = pd.merge(df,data,how='left',on='app_name')
        return data

    def _d_links(self, url, page_source):
        '''
        Parse the developer account page to find links of detail page for apps

        Args:
        url: str Developer account url
        page_source: bs4.BeautifulSoup The source page

        Returns:
        detail_links: List Detail page links
        '''
        soup = BeautifulSoup(page_source, 'lxml')    
        anchors = soup.find_all("a",attrs={'class': Apps.DETAIL_LINKS}, href=True)
        if anchors:
            detail_links = [urljoin(url,a['href']) for a in anchors]
        else:
            detail_links = None
        return detail_links
    
    def _make_csv(self, apps_dataframes, filename):
        '''
        Makes two CSV files on Changelog and Rating Hostory
        
        Args: 
        apps_dataframes: List containg dataframe objects
        filename: str developer account name 
        '''
        change_log_data = []
        rating_history_data = [] 

        for detail_page in apps_dataframes:
            change_log_data.append(detail_page.df_change_log)
            rating_history_data.append(detail_page.df_rating_history)

        change_log_df = pd.concat(change_log_data, ignore_index=True)
        rating_history_df = pd.concat(rating_history_data, ignore_index=True)
        
        change_log_df['installs'] = change_log_df.description.str.extract('(?P<installs>.*installs)')
        change_log_df['update']   = change_log_df.description.str.extract('(?P<update>Version.*)')

        download_df = self._get_data(change_log_df)
        rating_history_df['inserted_at'] = pd.to_datetime('today')

        # Upload to bigquery
        self._upload_bigquery(download_df, rating_history_df)


    def modify_urls(self, url_list):
        return [self._base_url + urlparse(url).query.split("=")[1].rstrip() + "/" for url in url_list]
    
    def crawl(self, url_list, email, password):

        l = Login()
        driver = l.gmail(email=email, password=password)
        
        try:
            # Iterating over developer account urls
            for url in url_list:
                driver.get(url)

                try:
                    # Wait until table loads
                    WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.ID,Apps.TABLE))
                    )
                except exceptions.TimeoutException as e:
                    pass

                
                try:
                    # Click show more button if exists
                    show_more = driver.find_element_by_xpath(Apps.SHOW_MORE)
                    if show_more:
                        show_more.click()
                except exceptions.NoSuchElementException as e:
                    pass    
                
                # Paring develper account and fetching detail page links for apps
                page_source = driver.page_source
                developer = url.split("/")[-2].replace("+","").replace("%20","")
                filename = developer + Apps.FILE_EXTENSION
                apps_dataframes = []
                detail_links = self._d_links(url, page_source) 
                
                sleep(uniform(1.5,3.1))
                
                if detail_links:
                    # Itrating over detail app pages for developer
                    for link in detail_links:
                        driver.get(link)
                        
                        try:
                            if("mature-warning" in driver.current_url):
                                yes_button = driver.find_element_by_xpath(Apps.MATURE_WARNING)
                                if(yes_button):
                                    yes_button.click()
                        except exceptions.NoSuchElementException as e:
                            pass
                        
                        try:
                            # Wait Until Table Loads
                            main_content = WebDriverWait(driver, 20).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR,Apps.IT_MAIN_CONTENT))
                            )
                        except exceptions.TimeoutException as e:
                            pass
                        
                        if(main_content):
                            app_url = driver.current_url
                            app_name = app_url.split("/")[-1]
                            page_source = driver.page_source

                            try:
                                apps_dataframes.append(DetailPage(app_name,page_source).scrape())
                            except Exception as e:
                                pass

                        sleep(uniform(2.5,6.3))
                        
                    self._make_csv(apps_dataframes, filename)
        except Exception as e:
            raise e("Error getting the requested page")
        finally:
            driver.quit()