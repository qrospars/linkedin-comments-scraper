import csv
import json
import argparse
from time import time
from datetime import datetime
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup as BSoup

from utils import (
    check_post_url,
    login_details,
    load_more,
    extract_emails,
    download_avatars,
    write_data2csv,
    write_high_level_data2csv,
)

BASE_URL = "https://www.linkedin.com/"

def setup_args():
    parser = argparse.ArgumentParser(description="Linkedin Scraping.")
    parser.add_argument("--headless", dest="headless", action="store_true", help="Go headless browsing")
    parser.set_defaults(headless=False)
    parser.add_argument("--show-replies", dest="show_replies", action="store_true", help="Load all replies to comments")
    parser.set_defaults(show_replies=False)
    parser.add_argument("--download-pfp", dest="download_avatars", action="store_true", help="Download profile pictures of commentors")
    parser.set_defaults(download_avatars=False)
    parser.add_argument("--save-page-source", dest="save_page_source", action="store_true", help="Safe page source for debugging")
    parser.set_defaults(save_page_source=False)

    return parser.parse_args()

def setup_config():
    with open("config.json") as f:
        return json.load(f)

def get_driver(headless):
    options = Options()
    options.headless = headless
    options.add_argument(r"user-data-dir=C:\Users\rospa\AppData\Local\Google\Chrome\User Data")
    driver = webdriver.Chrome(options=options, service=Service(ChromeDriverManager().install()))
    driver.maximize_window()
    return driver

def login(driver, username_name, password_name, sign_in_button_xpath):
    linkedin_username, linkedin_password = login_details()

    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, username_name)))
    username = driver.find_element(By.NAME, username_name)
    username.send_keys(linkedin_username)
    password = driver.find_element(By.NAME, password_name)
    password.send_keys(linkedin_password)
    sign_in_button = driver.find_element(By.XPATH, sign_in_button_xpath)
    sign_in_button.click()

def process_page(driver, post_url_data, load_comments_class, load_replies_class, reactions_class, comment_class, headline_class, name_class, avatar_class, show_replies=False, save_page_source=False):
    print("Processing URL:", post_url_data["url"])
    driver.get(post_url_data["url"])

    print("Loading comments :", end=" ", flush=True)
    load_more("comments", load_comments_class, driver)

    if show_replies:
        print("Loading replies :", end=" ", flush=True)
        load_more("replies", load_replies_class, driver)

    if save_page_source:
        with open("page_source.html", "w", encoding='utf-8') as f:
            f.write(driver.page_source)

    bs_obj = BSoup(driver.page_source, "html.parser")

    reactions_count = get_reactions_count(driver, reactions_class)
    comments = get_elements_text(bs_obj, comment_class)
    headlines = get_elements_text(bs_obj, headline_class)
    emails = extract_emails(comments)
    names = get_names(bs_obj, name_class)
    profile_links = get_profile_links(bs_obj, avatar_class)
    avatars = get_avatars(bs_obj, avatar_class)

    return reactions_count, names, profile_links, avatars, headlines, emails, comments

def get_elements_text(bs_obj, css_class):
    elements = bs_obj.find_all("span", {"class": css_class})
    return [element.get_text(strip=True) for element in elements]

def get_names(bs_obj, css_class):
    names = bs_obj.find_all("span", {"class": css_class})
    return [name.get_text(strip=True).split("\n")[0] for name in names]

def get_profile_links(bs_obj, css_class):
    profile_links_set = bs_obj.find_all("a", {"class": css_class})
    return [urljoin(BASE_URL, profile_link["href"]) for profile_link in profile_links_set]

def get_avatars(bs_obj, css_class):
    avatars = []
    profile_links_set = bs_obj.find_all("a", {"class": css_class})
    for a in profile_links_set:
        img_link = a.find("img", src=True)
        avatars.append(img_link['src'] if img_link else "")
    return avatars

def get_reactions_count(driver, reactions_class):
    try:
        reactions_count_element = driver.find_element(By.CLASS_NAME, reactions_class)
        return reactions_count_element.text
    except NoSuchElementException:
        return "0"

def main():
    args = setup_args()
    now = datetime.now()
    unique_suffix = now.strftime("-%m-%d-%Y--%H-%M")
    Config = setup_config()

    post_url_data_list = Config["post_url"]

    # Setup writers
    writer = csv.writer(
        open(
            Config["filename"] + unique_suffix + ".csv",
            "w",
            newline="",
            encoding="utf-8",
        )
    )
    writer.writerow(["Post URL", "Reaction Count", "Name", "Headline", "Profile Picture", "Email", "Comment"])
    
    # High-level CSV writer
    high_level_writer = csv.writer(
        open(
            Config["high_level_filename"] + unique_suffix + ".csv",
            "w",
            newline="",
            encoding="utf-8",
        )
    )
    high_level_writer.writerow(["Post URL", "Author", "Theme", "Reaction Count"]) 

    driver = get_driver(args.headless)
    driver.get(BASE_URL)

    if not Config.get('skip_login', False):
        login(driver, Config["username_name"], Config["password_name"], Config["sign_in_button_xpath"])

    start = time()  # Record the start time

    for post_url_data in post_url_data_list:
        reactions_count, names, profile_links, avatars, headlines, emails, comments = process_page(
            driver, post_url_data, Config["load_comments_class"], Config["load_replies_class"], Config["reactions_class"], 
            Config["comment_class"], Config["headline_class"], Config["name_class"], Config["avatar_class"], args.show_replies, args.save_page_source
        )

        write_data2csv(writer, post_url_data["url"], reactions_count, names, profile_links, avatars, headlines, emails, comments)
        
        # Write to high-level CSV
        write_high_level_data2csv(high_level_writer, post_url_data, reactions_count)
        
        if args.download_avatars:
            download_avatars(avatars, names, Config["dirname"] + unique_suffix)

    print(f"{len(names)} linkedin post comments scraped in: {((time() - start) / 60):.2f} minutes")
    driver.quit()

if __name__ == "__main__":
    main()
