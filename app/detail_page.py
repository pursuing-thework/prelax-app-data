from bs4 import BeautifulSoup
import pandas as pd
from pprint import pprint
import re
import demjson
from utils import Apps

class DetailPage:

    def __init__(self, app, page_source):        
        self.df_change_log = pd.DataFrame()
        self.df_rating_history = pd.DataFrame()
        self._app = {"app_name":app}
        self._soup = BeautifulSoup(page_source, 'lxml')

    def changelog(self):
        l_date = []
        l_status = []
        l_description = []
        for ultag in self._soup.find_all('ul',class_=Apps.CL_UL_TAG):
            for litag in ultag.find_all('li'):
                date        = litag.find('span',class_=Apps.CL_DATE).text.strip() or None
                status      = litag.find('span',class_=Apps.CL_DATE).text.strip() or None
                description = litag.find('span',class_=Apps.CL_DESCRIPTION).text.strip() or None
                
                l_date.append(date)
                l_status.append(status)
                l_description.append(description)
        
        return {"date":l_date,"status":l_status,"description":l_description}
    
    def _clean(self,tooltip, value):
        tooltip = tooltip.strip().replace(".","").replace(" ","_").lower()
        value = value.strip().replace('\n\n\n'," ")
        return (tooltip, value)

    def infotile(self):
        info = dict()
        main_content = self._soup.select(Apps.IT_MAIN_CONTENT)
        for infotiles in main_content:
            data = infotiles.find_all(['div','a'],{'tooltip':True})
            for element in data:
                tooltip, value = self._clean(element['tooltip'], element.text)
                info[tooltip] = value
        return info

    def rating_history(self):
        rate = {}
        ratings = self._soup.select(Apps.RH_RATINGS)
        for rating in ratings:
            votes = rating.find_all("div",class_=Apps.RH_VOTES)
            stars = rating.find_all("div",class_=Apps.RH_STARS)
            
            for vote,star in zip(votes,stars):
                yellow = 0
                for images in star.find_all('img'):
                    if(images['src'].find("yellow") > -1):
                        yellow += 1  
                rate["star_"+str(yellow)] = vote.text.strip()
        
        return rate
    
    def rating_histogram(self):
        pattern = re.compile(Apps.RH_RATING_DATA)
        scripts = self._soup.find_all('script')
        for script in scripts:
            if(pattern.search(str(script.string))):
                data = pattern.search(script.string).groups()[0]
                data = demjson.decode(data)
        values = data[0]['values']
        date = []
        rating_moving_avg = []
        status = []
        for value in values:
            for item in value:
                if(isinstance(item,str)):
                    d = item
                    r,s = None,None
                elif(isinstance(item,int) or isinstance(item,float)):
                    r = item or None
                    s = None
                elif(isinstance(item,dict)):
                    s= item['annotationText'] or None
                else:
                    d,r,s = None,None,None

                date.append(d)
                rating_moving_avg.append(r)
                status.append(s)

        return {"rating_history_date":date,"rating_moving_avg":rating_moving_avg,"rating_status":status}   
    
    def scrape(self):
        change_log = self.changelog()
        info_title = self.infotile()
        ratings = self.rating_history()
        histogram = self.rating_histogram()

        self.df_change_log = self.df_change_log.from_dict({**self._app,**change_log,**info_title, **ratings})
        self.df_rating_history = self.df_rating_history.from_dict({**self._app,**histogram})

        return self