from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
import discord
from discord.ext import tasks
import os
import time
import asyncio

DISABLE_HEADLESS = True

BOT_TOKEN = ""
BOT_CHANNEL = 0

# create client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# create selenium webdriver
options = Options()
options.add_argument('--headless')
if (DISABLE_HEADLESS):
    driver = webdriver.Firefox()
else:
    driver = webdriver.Firefox(options=options)
    
auto_search_keywords = []

def get_search_data(keywords, state):
    # load the page using the search terms
    search = ""
    for word in keywords:
        search += word + "+"
    search = search[:-1]
    
    url = "https://www.ebay.ca/sch/i.html?_nkw=" + search + "&_in_kw=4&rt=nc&LH_BIN=1"
    
    driver.get(url)
    time.sleep(3)
    
    # get listing info
    body = driver.find_element(By.XPATH, "/html/body")
    list_text = body.text.split("\n")
    list_listings = []
    extra_listing_indices = []
    i = 0
    while (i < len(list_text) and not list_text[i].startswith("Related Searches")):
        # check for keywords in string
        text = list_text[i].lower()
        contains_keywords = True
        for word in keywords:
            if (not word in text):
                contains_keywords = False
                break
        if (contains_keywords and not list_text[i].startswith("Related:") and not " results for " in list_text[i]):
            # keywords have been found, so set as the listing title
            if (list_text[i].startswith("NEW LISTING")):
                list_listings.append({"title" : list_text[i][11:]})
            else:
                list_listings.append({"title" : list_text[i]})
            i += 1
            
            if (i < len(list_text)):
                # check for keywords in the next string
                text = list_text[i].lower()
                contains_keywords = True
                for word in keywords:
                    if (not word in text):
                        contains_keywords = False
                        break
                # loop to search for listing data until the end of the list of text is reached or until a new listing title is found
                while (i < len(list_text) and (not list_text[i].startswith("Related Searches")) and (not contains_keywords or (contains_keywords and list_text[i] == "- " + list_listings[-1]["title"]))):
                    # get state
                    if (list_text[i] == "Pre-Owned" or list_text[i] == "Brand New" or list_text[i] == "New (Other)"):
                        # failsafe to ensure the original value is not overwritten by another value erroneously detected by the code
                        if (not "state" in list_listings[-1]):
                            list_listings[-1]["state"] = list_text[i]
                    
                    # get price
                    if (list_text[i].startswith("C $")):
                        # failsafe to ensure the original value is not overwritten by another value erroneously detected by the code
                        if (not "price" in list_listings[-1]):
                            list_listings[-1]["price"] = ""
                            j = 3
                            while (j < len(list_text[i]) and (list_text[i][j].isdecimal() or list_text[i][j] == ".")):
                                list_listings[-1]["price"] += list_text[i][j]
                                j += 1
                            
                            list_listings[-1]["price"] = float(list_listings[-1]["price"])
                        else:
                            # if another price is found while price is already defined, the new price is referring to a listing non-specific to the keywords, which as a result, was ignored
                            # in this case, we continue to ignore it, so we take note of the index of the listing as we must remove it from the list of links later
                            extra_listing_indices.append(len(list_listings) + len(extra_listing_indices))
                    
                    # get shipping price
                    if ("shipping" in list_text[i]):
                        # failsafe to ensure the original value is not overwritten by another value erroneously detected by the code
                        if (not "shipping" in list_listings[-1]):
                            if (list_text[i].startswith("Free")):
                                list_listings[-1]["shipping"] = "0"
                            if (list_text[i].startswith("+C $")):
                                list_listings[-1]["shipping"] = ""
                                j = 4
                                while (j < len(list_text[i]) and (list_text[i][j].isdecimal() or list_text[i][j] == ".")):
                                    list_listings[-1]["shipping"] += list_text[i][j]
                                    j += 1
                        
                            list_listings[-1]["shipping"] = float(list_listings[-1]["shipping"])
                    
                    i += 1
                    
                    # check for keywords in the next string
                    text = list_text[i].lower()
                    contains_keywords = True
                    for word in keywords:
                        if (not word in text):
                            contains_keywords = False
                            break
        else:
            i += 1

    # get listing links
    links = driver.find_elements(By.TAG_NAME, "a")
    list_links = []
    for link in links:
        if (not link.get_attribute("href") == None and link.get_attribute("href").startswith("https://www.ebay.ca/itm/")):
            list_links.append(link.get_attribute("href")[: link.get_attribute("href").find("?")])
            
    # clean the list to get each unique listing link
    list_unique_links = []
    for i in list_links:
        if (not i in list_unique_links):
            list_unique_links.append(i)
            
    # remove (usually) irrelevant listings
    for i in extra_listing_indices:
        list_unique_links[i] = None
    while (None in list_unique_links):
        list_unique_links.remove(None)
            
    # attach listing links to listing info
    i = 0
    for link in list_unique_links:
        list_listings[i]["link"] = link
        i += 1
    
    # remove any listings that have entries in the blacklist, if it exists
    if (os.path.exists("blacklist.txt")):
        blacklist = open("blacklist.txt", "r", encoding="utf-8")
        data = blacklist.readlines()
        for text in data:
            i = 0
            while (i < len(list_listings)):
                title = text.strip("\n")
                if (title == list_listings[i]["title"]):
                    list_listings.pop(i)
                else:
                    i += 1
        blacklist.close()
        
    # remove any listings that don't match the specified state
    i = 0
    while (i < len(list_listings)):
        if ((state == "BRANDNEW" and (list_listings[i]["state"] == "New (Other)" or list_listings[i]["state"] == "Pre-Owned")) or (state == "NEW" and list_listings[i]["state"] == "Pre-Owned")):
            list_listings.pop(i)
        else:
            i += 1
    
    return list_listings
        
@client.event
async def on_ready():
    auto_search.start()
    
    print("We have logged in as {0.user}".format(client))

@client.event
async def on_message(message):
    global auto_search_keywords
    
    if message.author == client.user:
        return
    
    if message.content.startswith("-help"):
        n = []
        n.append("```-search BRANDNEW/NEW/ANY {keyword} {keyword} ... -> Display the current cheapest item on Ebay whose listing name contains all keywords, and whose condition is at least as good as the specified one.")
        n.append("-autosearch BRANDNEW/NEW/ANY {keyword} {keyword} ... -> Set the autosearch function to search for items on Ebay whose listing name contains all keywords, and whose condition is at least as good as the specified one. Leave blank to disable.")
        n.append("-blacklist {name} -> Blacklist a listing name, preventing any listing with that name from being considered.```")
        
        m = ""
        for i in n:
            m += i + "\n\n"
        
        m = m[:-2]
        await message.channel.send(m)
        print(m)
    
    if message.content.startswith("-search"):
        keywords = message.content.split()
        keywords.pop(0)
        if (len(keywords) == 0):
            m = "`Error: Condition and keywords must be specified for the search. (refer to -help)`"
        else:
            state = keywords.pop(0)
            if (state != "BRANDNEW" and state != "NEW" and state != "ANY"):
                m = "`Error: Invalid condition. (refer to -help)`"
            else:
                if (len(keywords) == 0):
                    m = "`Error: Keywords must be specified for the search.`"
                else:
                    list_listings = get_search_data(keywords, state)
                    
                    search = ""
                    for word in keywords:
                        search += word + " "
                    search = search[:-1]
                    
                    if (len(list_listings) > 0):
                        # determine cheapest listing
                        min = list_listings[0]["price"] + list_listings[0]["shipping"]
                        min_index = 0
                        i = 1
                        while (i < len(list_listings)):
                            if (min > list_listings[i]["price"] + list_listings[i]["shipping"]):
                                min = list_listings[i]["price"] + list_listings[i]["shipping"]
                                min_index = i
                            i += 1
                        
                        # put together output message
                        m = "`The cheapest listing for '" + search + "' currently available is titled '{}' ({})".format(list_listings[min_index]["title"], list_listings[min_index]["state"])
                        if (list_listings[min_index]["shipping"] == 0):
                            n = " with a price of ${0:.2f} (free shipping)`".format(min)
                        else:
                            n1 = " with a price of ${0:.2f}".format(min)
                            n2 = " (${0:.2f} with".format(list_listings[min_index]["price"])
                            n3 = " ${0:.2f} shipping)`".format(list_listings[min_index]["shipping"])
                            n = n1 + n2 + n3
                        m += n
                        
                        m += "\n" + list_listings[min_index]["link"]
                    
                    else:
                        m = "`No results found for '" + search + "'`"
            
        await message.channel.send(m)
        print(m)
    
    if message.content.startswith("-autosearch"):
        keywords = message.content.split()
        keywords.pop(0)
        
        if (len(keywords) == 0):
            if (len(auto_search_keywords) == 0):
                m = "`Autosearch is off.`"
            else:
                auto_search_keywords.clear()
                m = "`Autosearch has now been disabled.`"
        else:
            state = keywords[0]
            if (state != "BRANDNEW" and state != "NEW" and state != "ANY"):
                m = "`Error: Invalid condition. (refer to -help)`"
            else:
                if (len(keywords) == 1):
                    m = "`Error: Keywords must be specified for the autosearch.`"
                else:
                    auto_search_keywords = keywords.copy()
                    keywords.pop(0)
                    
                    search = ""
                    for word in keywords:
                        search += word + " "
                    search = search[:-1]
                    
                    m = "`Now autosearching with the keywords: '" + search + "' (" + state + ")`"
        
        await message.channel.send(m)
        print(m)
    
    if message.content.startswith("-blacklist"):
        if (not os.path.exists("blacklist.txt")):
            await message.channel.send("`The file blacklist.txt does not exist, creating it...`")
            print("`The file blacklist.txt does not exist, creating it...`")
            try:
                blacklist = open("blacklist.txt", "w", encoding="utf-8")
                blacklist.close()
            except:
                await message.channel.send("`Something has gone wrong while attempting to create blacklist.txt.`")
                print("`Something has gone wrong while attempting to create blacklist.txt.`")
            
        if (os.path.exists("blacklist.txt")):
            if (len(message.content.split()) == 1):
                blacklist = open("blacklist.txt", "r")
                data = blacklist.readlines()
                m = ""
                for i in data:
                    m += i
                blacklist.close()
                if m == "":
                    m = "`The blacklist is currently empty.`"
            else:
                blacklist = open("blacklist.txt", "a", encoding="utf-8")
                if len(message.content[11:]) > 0:
                    blacklist.write(message.content[11:])
                    blacklist.write("\n")
                    m = "`" + message.content[11:] + " has been added to the blacklist.`"
                    blacklist.close()
                else:
                    m = "`Incorrect formatting. (-blacklist {name})`"
            
            await message.channel.send(m)
            print(m)
            
@tasks.loop()
async def auto_search():
    while not client.is_closed():
        if (len(auto_search_keywords) > 0):
            keywords = auto_search_keywords.copy()
            state = keywords.pop(0)
            
            list_listings = get_search_data(keywords, state)
            
            search = ""
            for word in keywords:
                search += word + " "
            search = search[:-1]
            
            if (len(list_listings) > 0):
                # determine cheapest listing
                min = list_listings[0]["price"] + list_listings[0]["shipping"]
                min_index = 0
                i = 1
                while (i < len(list_listings)):
                    if (min > list_listings[i]["price"] + list_listings[i]["shipping"]):
                        min = list_listings[i]["price"] + list_listings[i]["shipping"]
                        min_index = i
                    i += 1
                
                # put together output message
                m = "`The cheapest listing for '" + search + "' currently available is titled '{}' ({})".format(list_listings[min_index]["title"], list_listings[min_index]["state"])
                if (list_listings[min_index]["shipping"] == 0):
                    n = " with a price of ${0:.2f} (free shipping)`".format(min)
                else:
                    n1 = " with a price of ${0:.2f}".format(min)
                    n2 = " (${0:.2f} with".format(list_listings[min_index]["price"])
                    n3 = " ${0:.2f} shipping)`".format(list_listings[min_index]["shipping"])
                    n = n1 + n2 + n3
                m += n
                
                m += "\n" + list_listings[min_index]["link"]
            
            else:
                m = "`No results found for '" + search + "'`"
            
            await client.get_channel(BOT_CHANNEL).send(m)
            print(m)
            await asyncio.sleep(3600)
        
        else:
            await asyncio.sleep(60)
            
client.run(BOT_TOKEN)
