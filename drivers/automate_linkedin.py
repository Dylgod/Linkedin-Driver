"""
This is a script to automate Linkedin. This script is a part of a larger automation framework
and not meant for public use. I am not responsible for any misuse of this script.
This is strictly a showcase piece.

In order to function this script needs the following env variables:
- Supabase url and key

What it does/has:
- Signs in to Linkedin and stores cookies
- Searches for jobs relevant to given profile
- Applies for jobs using built-in Question-Answer bank
- Self trains unknown questions using Supabase API
- Built-in captcha detection and solving (recaptcha V3, V2, hcaptcha, CF Turnstile)
- Requires Google Chrome and downloads it if unavailable
- Downloads and/or updates chromedriver when needed
- local db logging system for easy debugging





"""

from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException
from selenium.common.exceptions import ElementNotInteractableException
from selenium.common.exceptions import NoSuchWindowException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import Select
from urllib.request import urlretrieve
from urllib.error import ContentTooShortError
from tkinter import *
import secrets
import random
import uuid as cap_uuid
import requests
import tempfile
import subprocess
import platform
# from pydub import AudioSegment # <- Enable after ffmpeg update
import time
import json
import re
import os, sys
import datetime
import argparse
import psutil
from psutil import NoSuchProcess, AccessDenied
import sqlite3
from supabase import create_client, Client
from twocaptcha import TwoCaptcha

# Pycharm auto format setting
# @formatter:off

# Prevent duplicate scripts
dupe_check = []
for proc in psutil.process_iter():
    if 'shy_drivers' in proc.name():
        dupe_check.append(proc.name())

if len(dupe_check)>2:
    sys.exit()

# True for PROD, False for TEST
WE_ARE_SUBMITTING = True

# final print statement -> gets changed throughout and prints this if no error occurs
finalprint = "Finished! Check your email"

# For Logging
logslist = []

# dont touch this
supa_retry_VAR = 0

class OSType(object):
    LINUX = "linux"
    MAC = "mac"
    WIN = "win"

class ChromeType(object):
    GOOGLE = "google-chrome"
    MSEDGE = "edge"

# These are for various questions and the edge case that there are profile sections missing,
# they will be made with these dates.
todaysdate = datetime.datetime.now().strftime("%m/%d/%Y")
todaysmonth = datetime.datetime.now().strftime("%B")
todaysyear = datetime.datetime.now().strftime("%Y")
lastyear = int(todaysyear) - 1
fouryearsago = int(todaysyear) - 4
eightyearsago = int(todaysyear) - 8

if WE_ARE_SUBMITTING:
    parser = argparse.ArgumentParser(prog='automate_linkedin.py', description="Enter id of profile w/ path to db")
    parser.add_argument('--uuid', type=str, help='Supabase uuid', required=True)
    parser.add_argument('--id', type=int, help='SQLlite id', required=True)
    parser.add_argument('--path', type=str, help='Path to database', required=True)
    parser.add_argument('--jobs', type=int, help='Number of jobs', required=False, default=15)

    args = parser.parse_args()
    uuid = args.uuid

def os_name():
    if "linux" in sys.platform:
        return OSType.LINUX
    elif "darwin" in sys.platform:
        return OSType.MAC
    elif "win32" in sys.platform:
        return OSType.WIN
    else:
        raise Exception("Could not determine the OS type!")

# Change current working directory for proper storage of local db on MacOS
if os_name() == 'mac':
    os.chdir(os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'shy-apply'))

def send_question_post(answer_type=None, question_text=None, platform=None):
    """
    Sends never before seen question to supabase log.
    answer_type: str, (radio, checkbox, ...)
    platform: str, (Indeed, Linkedin, ...)
    """
    if answer_type is None:
        a_type = 'Unknown'
    else:
        a_type = answer_type
    if question_text == '' or question_text == " " or question_text is None:
        question = 'None'
    else:
        question = question_text
    if platform is None:
        plat = 'Unknown'
    else:
        plat = platform

    questiondict = {'questions' : []}
    questiondict['questions'].append({"type":a_type, "question":question, "platform":plat})

    try:
        package = json.dumps(questiondict)
    except Exception:
        raise Exception

    try:
        x = requests.post(url='https://www.shyapply.com/api/questions', data=package, headers={"Content-Type": "application/json"})
        if x.status_code != 200:
            raise Exception
    except Exception:
        raise Exception

def errlog(severity=1, location=None, element="no_element", description=None, log=None):
    """
    Builds SQL query for db. Logs are collected and written in finally block at cleanup time.
    """
    global logslist
    try:
        location = web.current_url
    except Exception:
        location = None
    error_log = "INSERT INTO logs (log_date, log_severity, log_location, log_action, log_description, log_notes) VALUES ('{}', {}, '{}', '{}', '{}', '{}')".format(str(int(time.time())), severity, location, element, type(description).__name__, log)
    logslist.append(error_log)

def log_then_exit():
    """
    Writes current collection of logs to db in the event of a critical error.
    """
    if len(logslist) != 0:
        try:
            if WE_ARE_SUBMITTING:
                db = sqlite3.connect(r'{}'.format(args.path))
            else:
                db = sqlite3.connect(os.path.join(profile_dict['shy_dir'], 'shyapply.db'))
            db.row_factory = sqlite3.Row
            db_cursor = db.cursor()
            for log in logslist:
                db_cursor.execute(log)
                db.commit()
            db.close()
        except Exception:
            pass

    sys.exit()

def frontend_top_msg(String):

    if WE_ARE_SUBMITTING:
        try:
            db = sqlite3.connect(r'{}'.format(args.path))
        except Exception:
            try:
                db = sqlite3.connect(os.path.join(profile_dict['shy_dir'], 'shyapply.db'))
            except Exception:
                return

        update_top_msg = f'UPDATE messages SET mes_top = "{str(String)}" WHERE mes_id = 1'
        db.row_factory = sqlite3.Row
        db_cursor = db.cursor()
        db_cursor.execute(update_top_msg)
        db.commit()
        db.close()
    else:
        print(String)

def frontend_bot_msg(String):

    if WE_ARE_SUBMITTING:
        try:
            db = sqlite3.connect(r'{}'.format(args.path))
        except Exception:
            try:
                db = sqlite3.connect(os.path.join(profile_dict['shy_dir'], 'shyapply.db'))
            except Exception:
                return

        update_bot_msg = f'UPDATE messages SET mes_bottom = "{str(String)}" WHERE mes_id = 1'
        db.row_factory = sqlite3.Row
        db_cursor = db.cursor()
        db_cursor.execute(update_bot_msg)
        db.commit()
        db.close()
    else:
        print(String)

def application_success_log(jobtext):
    try:
        if len(jobtext) > 30:
            truncated_text = jobtext[:30] + "..."
            errlog(severity=0,element="SUCCESS",log=str(truncated_text))
        else:
            errlog(severity=0,element="SUCCESS",log=str(jobtext))
    except Exception:
        errlog(severity=0,element="SUCCESS",log="Application submitted")

def bot_typer(WebElement, string):
    """
    Types the string into the given WebElement if possible.
    Does not type if the WebElement's value matches the string.
    Clears the value before entering if the value does not equal the string.

    Types char by char at varying speeds at avg 65 wpm.
    """
    try:
        if WebElement.get_attribute('value') == string:
            pass
        else:
            WebElement.send_keys(Keys.BACKSPACE)

            if os_name() == 'mac':
                WebElement.send_keys(Keys.COMMAND + "a")
            elif os_name() == 'win':
                WebElement.send_keys(Keys.CONTROL + "a")

            WebElement.send_keys(Keys.DELETE)
            for char in str(string):
                WebElement.send_keys(char)
                delay = secrets.randbelow(1)
                delay2 = random.uniform(0.05, 0.25)
                time.sleep(delay + delay2)
    except Exception:
        WebElement.send_keys(Keys.BACKSPACE)

        if os_name() == 'mac':
            WebElement.send_keys(Keys.COMMAND + "a")
        elif os_name() == 'win':
            WebElement.send_keys(Keys.CONTROL + "a")

        WebElement.send_keys(Keys.DELETE)
        for char in str(string):
            WebElement.send_keys(char)
            delay = secrets.randbelow(1)
            delay2 = random.uniform(0.05, 0.25)
            time.sleep(delay + delay2)

def isnumbersonly(number: str | int):
    """
    Does not account for numbers represented by letters.
    example: qqqqqq returns true.
    """
    acceptable_numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
    if str(number) == "":
      return False
    else:
      for digit in str(number):
         if digit in acceptable_numbers:
            continue
         else:
            return False

    return True

def confirm_window_handle(web):

    if web.current_window_handle == anchor_handle:
        errlog(element='anchor_handle', description='anchor_handle', log='driver was on wrong tab')
        tabs = web.window_handles
        for o in tabs:
            web.switch_to.window(o)
            if web.current_window_handle != anchor_handle:
                break
    else:
        return

def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath("..")

    return os.path.join(base_path, relative_path)

def supa_retry(ping):
    """
    In the event of an outage, tries to reconnect every 3 minutes.
    timeout = 5 tries
    """
    global supa_retry_VAR
    global tokens
    global finalprint

    if ping == "ping":
        try:
            response = supabase.table('subs').select('tokens').eq("id", uuid).execute()
            response_dict = response.model_dump()
            tokens = response_dict['data'][0]['tokens']
            supa_retry_VAR = 0
            if tokens <= 0:
                finalprint = "Not enough tokens!"
                frontend_top_msg("Shy Apply stopped.")
                frontend_bot_msg("Not enough tokens!")
                try:
                    sys.exit()
                except Exception:
                    try:
                        web.quit()
                    except Exception:
                        pass
        except Exception:
            supa_retry_VAR += 1
            if supa_retry_VAR < 5:
                barrens_chat(String='Could not connect to Shy Apply servers. Retrying in 3 minutes', seconds=180)
                supa_retry("ping")
            else:
                finalprint = "Could not connect to Shy Apply"
                frontend_top_msg("Shy Apply stopped.")
                frontend_bot_msg("Could not connect to Shy Apply")
                error_log = "INSERT INTO logs (log_date, log_severity, log_location, log_action, log_description, log_notes) VALUES ({}, 1, supa_retry(ping), 'response', 'no description' ,supa_retry_VAR = 5)".format(str(int(time.time())))
                logslist.append(error_log)
                try:
                    log_then_exit()
                except Exception:
                    try:
                        web.quit()
                    except Exception:
                        pass

    if ping == "update":
        # updates tokens
        try:
            tokens_minus_one = tokens - 1
        except NameError:
            supa_retry("ping")
            tokens_minus_one = tokens - 1
        try:
            supabase.table('subs').update({'tokens': tokens_minus_one}).eq("id", uuid).execute()
            supa_retry_VAR = 0
        except Exception:
            supa_retry_VAR += 1
            if supa_retry_VAR < 5:
                barrens_chat(String='Could not connect to Shy Apply servers. Retrying in 3 minutes', seconds=180)
                supa_retry("update")
            else:
                finalprint = "Could not connect to Shy Apply"
                frontend_top_msg("Shy Apply stopped.")
                frontend_bot_msg("Could not connect to Shy Apply")
                error_log = "INSERT INTO logs (log_date, log_severity, log_location, log_action, log_description, log_notes) VALUES ({}, 1, supa_retry(update), 'response', 'no description' ,supa_retry_VAR = 5)".format(str(int(time.time())))
                logslist.append(error_log)
                try:
                    log_then_exit()
                except Exception:
                    try:
                        web.quit()
                    except Exception:
                        pass

    if ping != "ping" and ping != "update":
        finalprint = "update token error"
        frontend_top_msg("Shy Apply stopped.")
        frontend_bot_msg("update token error")
        try:
            sys.exit()
        except Exception:
            try:
                web.quit()
            except Exception:
                pass

def cf_manual_solver(web, error=None) -> None:
    """
    Attempts to find cloudflare challenge iframe and clicks the checkbox if found.
    """
    captcha_frame_regex = re.compile(r'cf-chl-widget-.{3,6}')
    try:
        # Usually it's item with index 0
        matching_elements = web.find_elements(By.XPATH, "//*[contains(@id, 'cf-chl-widget-')]")
        # print(f'Matches found: {matching_elements}')
        for element in matching_elements:
            element_id = element.get_attribute("id")
            if captcha_frame_regex.match(element_id) and 'Cloudflare security challenge' in element.accessible_name:
                # print(f"Matched Element ID: {element_id} - {element.accessible_name}")
                cf_captcha_frame = element
                break

        try:
            # Switch to captcha iframe
            WebDriverWait(web, 15.0).until(EC.frame_to_be_available_and_switch_to_it(cf_captcha_frame))
            captcha_checkbox = web.find_element(By.CLASS_NAME, 'ctp-checkbox-label')
            captcha_checkbox.uc_click()
            # Back to default content
            web.switch_to.default_content()
            time.sleep(1)
        except Exception as err:
            if error is not None:
                raise NoSuchElementException
    except Exception as e:
        errlog(element="captcha_frame_regex", description=e)
        if error is not None:
            raise NoSuchElementException

def captcha_checkbox_and_solve(web, error=None):
    """
    Clicks reCAPTCHA V3 chkbox and if detected, solves it using 2captcha service.
    """
    try:
        recaptcha_iframe = web.find_element(By.XPATH, '//iframe[contains(@title, "reCAPTCHA")]')
        web.switch_to.frame(recaptcha_iframe)
    except Exception as e:
        errlog(element='recaptcha_iframe', description=e, log="Possibly no captcha present.")
        if error is not None:
            raise NoSuchElementException
        else:
            return

    try:
        checkbox = web.find_element(By.ID, "recaptcha-anchor")
        checkbox.uc_click()
        time.sleep(2)
    except Exception as e:
        errlog(element='checkbox', description=e)

    try:
        ischecked = WebDriverWait(web, 5).until(EC.presence_of_element_located((By.XPATH, "//*[contains(@class, 'checkbox-checked')]")))
        web.switch_to.default_content()
        return
    except Exception:
        pass

    web.switch_to.default_content()

    try:
        recaptchaV3_iframe = web.find_element(By.XPATH, '//iframe[contains(@title, "recaptcha challenge")]')
        web.switch_to.frame(recaptchaV3_iframe)
    except Exception as e:
        errlog(element='recaptchaV3_iframe', description=e)
        if error is not None:
            raise NoSuchElementException
        else:
            return

    if error is not None:
        solve_audio_capcha(web, error='error')
    else:
        solve_audio_capcha(web)

    try:
        web.find_element(By.XPATH, '//div[normalize-space()="Multiple correct solutions required - please solve more."]')
        solve_audio_capcha(web)
    except Exception:
        pass

    web.switch_to.default_content()

def clean_temp(temp_files):
    """
    Used with solve_audio_capcha to clean temporary files involving downloaded mp3 files.
    """
    for path in temp_files:
        if os.path.exists(path):
            os.remove(path)

def solve_audio_capcha(web, error=None) -> None:
    """
    Called if reCAPTCHA V3 is detected.
    Downloads audio challenge and solves with 2captcha service.
    """

    try:
        # Geberate capcha downlaod -> the headset btn
        headset_captcha_btn = web.find_element(By.XPATH, '//*[@id="recaptcha-audio-button"]')
        headset_captcha_btn.uc_click()
        time.sleep(1.5)
    except Exception as e:
        errlog(element="headset_captcha_btn",description=e)
        if error is not None:
            raise NoSuchElementException
        else:
            return

    try:
        # Locate audio challenge download link
        download_link = web.find_element(By.CLASS_NAME, 'rc-audiochallenge-tdownload-link')
    except Exception as e:
        errlog(element="download_link", description=e, log="Failed to download audio file")
        if error is not None:
            raise NoSuchElementException
        else:
            return

    # Create temporary directory and temporary files
    tmp_dir = tempfile.gettempdir()

    id_ = cap_uuid.uuid4().hex

    mp3_file, wav_file = os.path.join(tmp_dir, f'{id_}_tmp.mp3'), os.path.join(tmp_dir, f'{id_}_tmp.wav')

    tmp_files = {mp3_file, wav_file}

    with open(mp3_file, 'wb') as f:
        link = download_link.get_attribute('href')
        audio_download = requests.get(url=link, allow_redirects=True)
        f.write(audio_download.content)
        f.close()

    # DELETE THIS AFTER FFMPEG INTEGRATION!
    if os.path.exists(wav_file):
        clean_temp(tmp_files)
        errlog(element="solve_audio_capcha", log="captcha given in wav format. update ffmpeg!")
        return

    # DOES NOT WORK UNTIL FFMPEG INTEGRATION --UPDATE
    # Convert WAV to MP3 format for compatibility with speech recognizer APIs
    # if os.path.exists(wav_file):
    #     try:
    #         AudioSegment.from_wav(wav_file).export(mp3_file, format='mp3')
    #     except Exception as e:
    #         errlog(element="AudioSegment", description=e, log="Failed to convert wav into mp3")
    #         clean_temp(tmp_files)
    #         if error is not None:
    #             raise NoSuchElementException
    #         else:
    #             return

    # Use 2Captcha's sudio service to get text from file
    try:
        solver = TwoCaptcha('4db1a5f4e11e2ba041312b7cf6f07310')
        result = solver.audio(mp3_file, lang = 'en')
    except Exception as e:
        # invalid parameters passed
        errlog(element="result", description=e, log="Failed to solve audio")
        clean_temp(tmp_files)
        if error is not None:
            raise NoSuchElementException
        else:
            return

    # Clean up all temporary files
    clean_temp(tmp_files)

    # Write transcribed text to iframe's input box
    try:
        response_textbox = web.find_element(By.ID, 'audio-response')
        bot_typer(response_textbox, str(result['code']))
        time.sleep(1.448)
        try:
            verify_btn1 = web.find_element(By.ID, 'recaptcha-verify-button')
            verify_btn1.uc_click()
        except Exception:
            try:
                verify_btn2 = web.find_element(By.XPATH, '//button[contains(text(), "Verify")]')
                verify_btn2.uc_click()
            except Exception as error:
                errlog(element="verify_btn2", description=error, log="No Verify Btn")
    except Exception as e:
        errlog(element="response_textbox", description=e, log="captcha failed")

def captcha_still_there_check(web, timeoutVAR):
    """
    Verifies the existence of a captcha after solve attempt.
    """
    bot_typer_str = '"' + profile_dict['job_title'] + '"'

    if timeoutVAR < 3:
        try:
            still_there = web.find_elements(By.XPATH, '//*[contains(text(), "Verify you are human")]')
            if len(still_there) >= 1:
                errlog(log="captcha detected in whatwhere")
                try:
                    cf_manual_solver(web, error='error')
                except Exception:
                    captcha_checkbox_and_solve(web)
            else:
                return
        except Exception:
            return

        retryVAR = timeoutVAR + 1
        captcha_still_there_check(web, retryVAR)

    elif timeoutVAR == 3:
        beforeURL = web.current_url
        if bot_typer_str in beforeURL:
            newURL = str(beforeURL).replace(bot_typer_str, profile_dict['job_title'])
            web.get(newURL)
        else:
            errlog(log="could not bypass captcha in whatwhere")

def get_dependencies():
    """
    Checks if Google Chrome is installed and if not, attempts to silently install.
    Completely silent on windows and prompts the user for creds on MacOS.
    """

    PATTERN = {
        ChromeType.GOOGLE: r"\d+\.\d+\.\d+",
        ChromeType.MSEDGE: r"\d+\.\d+\.\d+",
    }

    def os_architecture():
        if platform.machine().endswith("64"):
            return 64
        else:
            return 32

    def os_type():
        return "%s%s" % (os_name(), os_architecture())

    def linux_browser_apps_to_cmd(*apps):
        """Create 'browser --version' command from browser app names."""
        ignore_errors_cmd_part = " 2>/dev/null" if os.getenv(
            "WDM_LOG_LEVEL") == "0" else ""
        return " || ".join(
            "%s --version%s" % (i, ignore_errors_cmd_part) for i in apps
        )

    def windows_browser_apps_to_cmd(*apps):
        """Create analogue of browser --version command for windows."""
        powershell = determine_powershell()
        first_hit_template = "$tmp = {expression}; if ($tmp) {{echo $tmp; Exit;}};"
        script = "$ErrorActionPreference='silentlycontinue'; " + " ".join(
            first_hit_template.format(expression=e) for e in apps
        )
        return '%s -NoProfile "%s"' % (powershell, script)

    def get_latest_chrome():
        global finalprint

        if os_name() == 'win':
            if os.path.exists(profile_dict['shy_dir']):
                download_link = r"https://dl.google.com/chrome/install/latest/chrome_installer.exe"

                dl_destination = os.path.join(profile_dict['shy_dir'], 'chrome_installer.exe')

                install_chrome = f""" {dl_destination} /silent /install"""

                try:
                    frontend_top_msg("Setting up...")
                    frontend_bot_msg('Installing dependencies - 5 percent')
                    get_chrome = urlretrieve(download_link, dl_destination)
                    frontend_bot_msg('Installing dependencies - 15 percent')
                except ContentTooShortError as e:
                    finalprint = "Error - Please install Google Chrome."
                    frontend_top_msg("Dependencies not found")
                    frontend_bot_msg("Error - Please install Google Chrome.")
                    errlog(element='get_chrome', description=e, log='Download interupted.')
                    log_then_exit()
                except Exception as e:
                    finalprint = "Error - Please install Google Chrome."
                    frontend_top_msg("Dependencies not found")
                    frontend_bot_msg("Error - Please install Google Chrome.")
                    errlog(element='get_chrome', description=e, log='Tried to download google chrome but couldnt')
                    log_then_exit()

                if os.path.exists(dl_destination):
                    frontend_bot_msg('Installing dependencies - 30 percent')
                    try:
                        subprocess.run(["powershell","& {" + install_chrome + "}"])
                        frontend_bot_msg('Installing dependencies - 45 percent')
                        percentage_count = 49
                        try:
                            fail_stack = 1
                            while fail_stack < 12:
                                time.sleep(5)
                                if get_browser_version_from_os("google-chrome") is None:
                                    frontend_bot_msg(f'Installing dependencies - {str(percentage_count)} percent')
                                    fail_stack += 1
                                    percentage_count += 5
                                else:
                                    frontend_top_msg("Booting up Shy Apply")
                                    frontend_bot_msg("Dependencies found! Starting...")
                                    break

                                if fail_stack == 12:
                                    errlog(element='fail_stack', log='fail_stack = 5. Download Failed')
                                    finalprint = "Error - Please install Google Chrome."
                                    frontend_top_msg("Dependencies not found")
                                    frontend_bot_msg("Error - Please install Google Chrome.")
                                    log_then_exit()

                        except Exception as e:
                            errlog(element='fail_stack', description=e, log='Failure in while loop')

                    except Exception as e:
                        errlog(element='install_chrome', description=e, log='Tried to install google chrome but couldnt')
                        finalprint = "Error - Please install Google Chrome."
                        frontend_top_msg("Dependencies not found")
                        frontend_bot_msg("Error - Please install Google Chrome.")
                        log_then_exit()

                    try:
                        os.unlink(dl_destination)
                    except PermissionError:
                        errlog(element='dl_destination', description=e, log='could not uninstall due to PermissionError')
                    except FileNotFoundError:
                        pass
                    except Exception as e:
                        errlog(element='install_chrome', description=e, log='could not uninstall due to unknown error')

        elif os_name() == 'mac':
            frontend_top_msg("Missing Dependencies")
            frontend_bot_msg("Need Google Chrome")
            log_then_exit()

    def get_browser_version_from_os(browser_type):
        """Return installed browser version."""
        cmd_mapping = {
            ChromeType.GOOGLE: {
                OSType.LINUX: linux_browser_apps_to_cmd(
                    "google-chrome",
                    "google-chrome-stable",
                    "chrome",
                    "chromium",
                    "chromium-browser",
                    "google-chrome-beta",
                    "google-chrome-dev",
                    "google-chrome-unstable",
                ),
                OSType.MAC: r"/Applications/Google\ Chrome.app"
                            r"/Contents/MacOS/Google\ Chrome --version",
                OSType.WIN: windows_browser_apps_to_cmd(
                    r'(Get-Item -Path "$env:PROGRAMFILES\Google\Chrome'
                    r'\Application\chrome.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES (x86)\Google\Chrome'
                    r'\Application\chrome.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:LOCALAPPDATA\Google\Chrome'
                    r'\Application\chrome.exe").VersionInfo.FileVersion',
                    r'(Get-ItemProperty -Path Registry::"HKCU\SOFTWARE'
                    r'\Google\Chrome\BLBeacon").version',
                    r'(Get-ItemProperty -Path Registry::"HKLM\SOFTWARE'
                    r'\Wow6432Node\Microsoft\Windows'
                    r'\CurrentVersion\Uninstall\Google Chrome").version',
                ),
            },
            ChromeType.MSEDGE: {
                OSType.LINUX: linux_browser_apps_to_cmd(
                    "microsoft-edge",
                    "microsoft-edge-stable",
                    "microsoft-edge-beta",
                    "microsoft-edge-dev",
                ),
                OSType.MAC: r"/Applications/Microsoft\ Edge.app"
                            r"/Contents/MacOS/Microsoft\ Edge --version",
                OSType.WIN: windows_browser_apps_to_cmd(
                    # stable edge
                    r'(Get-Item -Path "$env:PROGRAMFILES\Microsoft\Edge'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES (x86)\Microsoft'
                    r'\Edge\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-ItemProperty -Path Registry::"HKCU\SOFTWARE'
                    r'\Microsoft\Edge\BLBeacon").version',
                    r'(Get-ItemProperty -Path Registry::"HKLM\SOFTWARE'
                    r'\Microsoft\EdgeUpdate\Clients'
                    r'\{56EB18F8-8008-4CBD-B6D2-8C97FE7E9062}").pv',
                    # beta edge
                    r'(Get-Item -Path "$env:LOCALAPPDATA\Microsoft\Edge Beta'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES\Microsoft\Edge Beta'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES (x86)\Microsoft\Edge Beta'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-ItemProperty -Path Registry::"HKCU\SOFTWARE\Microsoft'
                    r'\Edge Beta\BLBeacon").version',
                    # dev edge
                    r'(Get-Item -Path "$env:LOCALAPPDATA\Microsoft\Edge Dev'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES\Microsoft\Edge Dev'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-Item -Path "$env:PROGRAMFILES (x86)\Microsoft\Edge Dev'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-ItemProperty -Path Registry::"HKCU\SOFTWARE\Microsoft'
                    r'\Edge Dev\BLBeacon").version',
                    # canary edge
                    r'(Get-Item -Path "$env:LOCALAPPDATA\Microsoft\Edge SxS'
                    r'\Application\msedge.exe").VersionInfo.FileVersion',
                    r'(Get-ItemProperty -Path Registry::"HKCU\SOFTWARE'
                    r'\Microsoft\Edge SxS\BLBeacon").version',
                    # highest edge
                    r"(Get-Item (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft"
                    r"\Windows\CurrentVersion\App Paths\msedge.exe')."
                    r"'(Default)').VersionInfo.ProductVersion",
                    r"[System.Diagnostics.FileVersionInfo]::GetVersionInfo(("
                    r"Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows"
                    r"\CurrentVersion\App Paths\msedge.exe')."
                    r"'(Default)').ProductVersion",
                    r"Get-AppxPackage -Name *MicrosoftEdge.* | Foreach Version",
                    r'(Get-ItemProperty -Path Registry::"HKLM\SOFTWARE\Wow6432Node'
                    r'\Microsoft\Windows\CurrentVersion\Uninstall'
                    r'\Microsoft Edge").version',
                ),
            },
        }
        try:
            cmd_mapping = cmd_mapping[browser_type][os_name()]
            pattern = PATTERN[browser_type]
            quad_pattern = r"\d+\.\d+\.\d+\.\d+"
            quad_version = read_version_from_cmd(cmd_mapping, quad_pattern)
            if quad_version and len(str(quad_version)) >= 9:  # Eg. 115.0.0.0
                return quad_version
            version = read_version_from_cmd(cmd_mapping, pattern)
            return version
        except Exception:
            # get_latest_chrome()
            pass

    def read_version_from_cmd(cmd, pattern):
        with subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                shell=True,
        ) as stream:
            stdout = stream.communicate()[0].decode()
            version = re.search(pattern, stdout)
            version = version.group(0) if version else None
        return version

    def determine_powershell():
        """Returns "True" if runs in Powershell and "False" if another console."""
        cmd = "(dir 2>&1 *`|echo CMD);&<# rem #>echo powershell"
        with subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                shell=True,
        ) as stream:
            stdout = stream.communicate()[0].decode()
        return "" if stdout == "powershell" else "powershell"

    def set_shell_env_WINDOWS(str ,path): # Key: SHYAPPLY_FFMPEG
        ffmpeg_set_env = os.getenv(str)
        if ffmpeg_set_env is None:
            os.environ[str] = path
            print(os.environ.get(str))

    def set_zshell_env_MACOS(path): # Key: SHYAPPLY_FFMPEG
        set_env_PATH = """
        (echo; echo 'eval "$({0})"') >> {1}/.zprofile
        eval "$({0})"
        """.format(path,os.path.expanduser("~"))

        with open(os.path.join(os.path.expanduser("~"),".zprofile")) as file:
            f = file.read()
            if path not in f:
                subprocess.run(set_env_PATH, shell=True)


    try:
        if get_browser_version_from_os("google-chrome") is None:
            get_latest_chrome()
        else:
            frontend_top_msg("Booting up Shy Apply")
            frontend_bot_msg("Dependencies found! Starting...")
    except Exception as e:
        frontend_top_msg("Dependencies not found")
        errlog(log=e)
        frontend_bot_msg("Failed to install dependencies")

def check_if_captcha_redirect(web):
    """
    Checks for a webpage redirect to a captcha screen.
    This can occur after searching in job search screen.
    """
    try:
        iframe_check = web.find_elements(By.XPATH, '//iframe')
        if len(iframe_check) > 0:
            cf_manual_solver(web)
    except Exception:
        pass

    try:
        recaptcha_iframe = web.find_element(By.XPATH, '//iframe[contains(@title, "reCAPTCHA")]')
        captcha_checkbox_and_solve(web)
    except Exception:
        pass

def is_process_stopped():
    """
    Checks 'ai_running' in db and returns true if 1, false 0.
    return value sent to 'check_if_running'
    """

    ai_table = {

        'ai':
            [
                'ai_id',
                'ai_running',
                'ai_last_run'
            ]
    }

    if WE_ARE_SUBMITTING:
        db = sqlite3.connect(r'{}'.format(args.path))
    else:
        db = sqlite3.connect(os.path.join(profile_dict['shy_dir'], 'shyapply.db'))
    db.row_factory = sqlite3.Row
    db_cursor = db.cursor()
    # db_cursor.execute('SELECT * from {} WHERE {} = {}'.format(table, __id, args.id))
    db_cursor.execute('SELECT * from ai WHERE ai_id = 1')
    logs_result = db_cursor.fetchall()
    db.close()

    ai_result = []

    try:
        for row in logs_result:
            logs_dict = {item: row[item].strip() if isinstance(row[item], str) else row[item] for item in ai_table['ai']}
            ai_result.append(logs_dict)
    except Exception as e:
        errlog(description=e,log='Potential issue with is_process_stopped')

    if ai_result[0]['ai_running'] == 0:
        frontend_top_msg("Shy Apply stopped.")
        frontend_bot_msg('Free time taken back!')
        return True
    else:
        return False

def check_if_running():
    """
    evaluates bool from 'is_process_stopped' and if 0, terminates script.
    A value of 1 means the frontend is still running.
    a value of 0 means stop button was pressed or the session terminated.
    """
    try:
        proc_list = []
        for proc in psutil.process_iter():
            if platform_proc_name in proc.name().lower():
                proc_list.append("shyapply")
                break
        if len(proc_list) == 0:
            errlog(element="proc.name()", log='Application terminated by user.')
            frontend_bot_msg('Application closed...')
            log_then_exit()
        elif len(proc_list) > 0:
            if is_process_stopped() == True:
                errlog(element="Stop button", log='Stop button pressed by user.')
                frontend_top_msg('Ready To Search')
                finalprint = "Click 'Start' to automate your job search"
                frontend_bot_msg("Click 'Start' to automate your job search")
                log_then_exit()
    except Exception as e:
        errlog(description=e ,element="psutil", log="error in reading process list")
        finalprint = "Error in reading process list"
        log_then_exit()

def start_warning(seconds=15, proc_interval = 3):
    """
    A user indecisiveness check. Displays a countdown visible to the user.
    'proc_interval' is how often the script calls 'check_if_running'.
    'Seconds' must be divisible by 'proc_interval' to get a process check at 0 seconds.
    """
    timer = seconds
    proc_int = proc_interval

    frontend_top_msg("Preparing to launch")

    while timer > 0:

        if timer >= 60:
            mins_left = round(timer // 60, 1)
            if mins_left == 1:
                mins_left_string = str(round(timer // 60, 1)) + " minute"
            elif mins_left > 1:
                mins_left_string = str(round(timer // 60, 1)) + " minutes"

            secs_left = timer - (round(timer // 60, 1) * 60)
            if secs_left == 1:
                secs_left_string = str(timer - (round(timer // 60, 1) * 60)) + " second"
            elif secs_left > 1:
                secs_left_string = str(timer - (round(timer // 60, 1) * 60)) + " seconds"
            elif secs_left == 0:
                secs_left_string = '' # Convert this into None if adding any string after
        elif timer < 60:
            mins_left_string = None
            if timer == 1:
                secs_left_string = str(timer) + " second"
            elif timer > 1:
                secs_left_string = str(timer) + " seconds"

        if mins_left_string is None:
            time_left = f"Starting in {secs_left_string}"
        else:
            time_left = f"Starting in {mins_left_string} {secs_left_string}"

        frontend_bot_msg(time_left)
        time.sleep(1)
        timer -= 1

        if proc_int == 0:
            check_if_running()
            proc_int = proc_interval
        else:
            proc_int -= 1

def barrens_chat(String, seconds, proc_interval = 60):
    """
    A timeout to speed cap script to dodge certain bot detection methods.
    980 seconds roughly equateds to 3 applications per hour.
    """
    timer = seconds
    proc_int = proc_interval

    frontend_bot_msg(String)

    while timer > 0:
        time.sleep(3)
        timer -= 3

        if proc_int == 0:
            check_if_running()
            proc_int = proc_interval
        else:
            proc_int -= 1


# Allows for seamless testing on Windows and MacOS with no changes.
possible_proc_names = ['shy apply', 'shy-apply', 'shyapply', 'odetodionysus']
if os_name() == 'mac':
    for proc in psutil.process_iter():
        if any(word in proc.name().lower() for word in possible_proc_names):
            platform_proc_name = proc.name().lower()
            break

elif os_name() == 'win':
    for proc in psutil.process_iter():
        if any(word in proc.name().lower() for word in possible_proc_names):
            platform_proc_name = proc.name().lower()
            break

# Indecisivness Check for users.
if WE_ARE_SUBMITTING:
    start_warning()

# --------------------------------------------TURN OFF----------------------------------------------------------
if not WE_ARE_SUBMITTING:
    # This test profile has login info removed.
    # To test be sure to add your own information.

    # Test Profile 1
    profile_dict = {
        'consent_background_check': 1,
        'degree': 'CCAC',
        'edu_level': 4,
        'email_notifications': 1,
        'end_year': 2012,
        'first_name': 'Dylan',
        'indeed': 1,
        'indeed_pass': 'INDEED_PASSWORD_GOES_HERE',
        'indeed_user': 'INDEED_USERNAME/EMAIL_GOES_HERE',
        'job_city': 'Las Vegas',
        'job_remote': 1,
        'job_salary': 115000,
        'job_state_iso': 'NV',
        'job_state_long': 'Nevada',
        'job_title': 'Software Engineer',
        'last_name': 'Taylor',
        'linkedin': 1,
        'linkedin_url': 'www.linkedin.com/in/dylan-taylor-11b5b32ba',
        'linkedin_pass': 'LINKEDIN_PASSWORD_GOES_HERE',
        'linkedin_user': 'LINKEDIN_USERNAME/EMAIL_GOES_HERE',
        'major': 'Computer Science',
        'no_sponsorship': 1,
        'personal_address': '2420 Enchantment Cir',
        'personal_city': 'Las Vegas',
        'personal_email': 'dylan@dylgod.com',
        'personal_phone': 1231231231,
        'personal_state_iso': 'NV',
        'personal_state_long': 'Nevada',
        'personal_zip': '89074',
        'previous_work_job_title': 'Software Engineer',
        'previous_work_company': 'Shy Apply',
        'resume_file': 'Dylan Taylor 2024.pdf',
        'resume_path': r"C:\Users\USERNAME\path\to\resume",
        'school': 'NV Cyber Charter School',
        'shy_dir': r'C:\Users\USERNAME\AppData\Local\shy-apply',
        'sms_notifications': 1,
        'work_legal': 1,
        'ziprecruiter': 0,
        'ziprecruiter_pass': 'ZIPRECRUITER_PASSWORD_GOES_HERE',
        'ziprecruiter_user': 'ZIPRECRUITER_PASSWORD_GOES_HERE',
        'glassdoor': 0,
        'glassdoor_pass': 'GLASSDOOR_PASSWORD_GOES_HERE',
        'glassdoor_user': 'GLASSDOOR_PASSWORD_GOES_HERE',
        'yearsofexp': '5'
    }

    # Required for Test mode on MacOS
    if os_name() == 'mac':
        profile_dict.update({'shy_dir': os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'shy-apply')})

# --------------------------------------------TURN ON-----------------------------------------------------------
if WE_ARE_SUBMITTING:
    url: str = os.environ["SUPABASE_URL"]
    key: str = os.environ["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)

    try:
        response = supabase.table('subs').select('tokens').eq("id",uuid).execute()
    except Exception:
        supa_retry("ping")

    response_dict = response.model_dump()
    tokens = response_dict['data'][0]['tokens']
    if tokens <= 0:
        finalprint = "Not enough tokens!"
        frontend_top_msg("Shy Apply stopped.")
        frontend_bot_msg("Not enough tokens!")
        log_then_exit()

    def set_last_run():
        """
        After significant progress in script's runtime, writes current time into ai_last_run db row.
        This is a measure to help non-technical users avoid bans and/or contamination of their ip through
        many repeated consecutive uses.

        Limits script usage to once per hour.

        """
        global finalprint

        fields = {

            'ai' :
                [
                    'ai_id',
                    'ai_running',
                    'ai_last_run'
                ]
            ,
            'auth' :
                [
                    'auth_id',
                    'auth_linkedin_username',
                    'auth_linkedin_pass',
                    'auth_indeed_username',
                    'auth_indeed_pass',
                    'auth_ziprecruiter_username',
                    'auth_ziprecruiter_pass',
                    'auth_glassdoor_username',
                    'auth_glassdoor_pass'
                ]
            ,
            'education' :
                [
                    'edu_id',
                    'edu_level',
                    'edu_high_school',
                    'edu_high_school_start',
                    'edu_high_school_end',
                    'edu_high_school_achievements',
                    'edu_university_achievements',
                    'edu_college',
                    'edu_certifications'
                ]
            ,
            'experience' :
                [
                    'exp_id',
                    'exp_jobs'
                ]
            ,
            'logs' :
                [
                    'log_id',
                    'log_date',
                    'log_severity',
                    'log_location',
                    'log_action',
                    'log_description',
                    'log_notes',
                    'log_created'
                ]
            ,
            'personal' :
                [
                    "per_consent_background",
                    "per_allow_email",
                    "per_first_name",
                    "per_last_name",
                    "per_linkedin_url",
                    "per_no_sponsorship",
                    "per_address",
                    "per_city",
                    "per_email",
                    "per_phone",
                    "per_state_iso",
                    "per_state",
                    "per_zip",
                    "per_resume_path",
                    "per_allow_sms",
                    "per_work_legal",
                ]
            ,
            'platforms' :
                [
                    'plat_id',
                    'plat_linkedin',
                    'plat_linkedin_use_google',
                    'plat_linkedin_use_apple',
                    'plat_indeed',
                    'plat_indeed_use_google',
                    'plat_indeed_use_apple',
                    'plat_ziprecruiter',
                    'plat_ziprecruiter_use_google',
                    'plat_glassdoor',
                    'plat_glassdoor_use_google',
                    'plat_glassdoor_use_facebook'
                ]
            ,
            'profiles' :
                [
                    'pro_id',
                    'pro_created',
                    'pro_last_edited',
                    'pro_complete'
                ]
            ,
            'system' :
                [
                    'sys_id',
                    'sys_database_version',
                    'sys_local_appdata',
                    'sys_roaming_appdata',
                    'sys_os',
                    'sys_arch',
                    'sys_shy_directory',
                    'sys_home_directory',
                    'sys_last_ran'
                ]
            ,
            'work' :
                [
                    'work_id',
                    'work_city',
                    'work_state',
                    'work_state_iso',
                    'work_country',
                    'work_country_iso',
                    'work_title',
                    'work_annual_salary',
                    'work_monthly_salary',
                    'work_hourly_wage',
                    'work_remote',
                    'work_years_of_experience'
                ]
        }

        def sql_query_ai(table):
            """
            Port of sql_query_table function.
            Only queries ai table for logging the last time the script was run.
            """
            logslist = []
            __id = 'ai_id' # first 3 letters in id_list entries are all different

            db = sqlite3.connect(r'{}'.format(args.path))
            db.row_factory = sqlite3.Row
            db_cursor = db.cursor()
            if table == 'ai' or table == 'system':
                db_cursor.execute('SELECT * from {} WHERE {} = 1'.format(table, __id))
            else:
                db_cursor.execute('SELECT * from {} WHERE {} = {}'.format(table, __id, args.id))
            logs_result = db_cursor.fetchall()
            db.close()

            try:
                for row in logs_result:
                    logs_dict = {item: row[item].strip() if isinstance(row[item], str) else row[item] for item in fields[table]}
                    logslist.append(logs_dict)
            except NameError:
                frontend_top_msg("Shy Apply stopped.")
                frontend_bot_msg("Failed to query SQL table")
                sys.exit()

            return logslist

        ai = sql_query_ai('ai')

        if ai[0]['ai_last_run'] is not None:
            epoch_timenow = int(time.time())
            time_last_run = int(ai[0]['ai_last_run'])

            try:
                if epoch_timenow - time_last_run < 3600:
                    pass
                elif epoch_timenow - time_last_run >= 3600:
                    update_time = f'UPDATE ai SET ai_last_run = {str(int(time.time()))} WHERE ai_id = 1'
                    try:
                        db = sqlite3.connect(r'{}'.format(args.path))
                        db.row_factory = sqlite3.Row
                        db_cursor = db.cursor()
                        db_cursor.execute(update_time)
                        db.commit()
                        db.close()
                    except Exception as err:
                        errlog(element='update_time + db', description=err, log='something went wrong with db write. (wrong path, read-write same time, db not present)')
            except Exception as e:
                errlog(severity=12, element="ai_last_run", description=e, log='something went wrong with time comparison')

        elif ai[0]['ai_last_run'] is None:
            update_time = f'UPDATE ai SET ai_last_run = {str(int(time.time()))} WHERE ai_id = 1'
            try:
                db = sqlite3.connect(r'{}'.format(args.path))
                db.row_factory = sqlite3.Row
                db_cursor = db.cursor()
                db_cursor.execute(update_time)
                db.commit()
                db.close()
            except Exception as e:
                errlog(element='update_time + db', description=e, log='something went wrong with db write. (wrong path, read-write same time, db not present)')

    def generate_profile_dict():
        global finalprint

        # Local db structure
        fields = {

            'ai' :
                [
                    'ai_id',
                    'ai_running',
                    'ai_last_run'
                ]
            ,
            'auth' :
                [
                    'auth_id',
                    'auth_linkedin_username',
                    'auth_linkedin_pass',
                    'auth_indeed_username',
                    'auth_indeed_pass',
                    'auth_ziprecruiter_username',
                    'auth_ziprecruiter_pass',
                    'auth_glassdoor_username',
                    'auth_glassdoor_pass'
                ]
            ,
            'education' :
                [
                    'edu_id',
                    'edu_level',
                    'edu_high_school',
                    'edu_high_school_start',
                    'edu_high_school_end',
                    'edu_high_school_achievements',
                    'edu_university_achievements',
                    'edu_college',
                    'edu_certifications'
                ]
            ,
            'experience' :
                [
                    'exp_id',
                    'exp_jobs'
                ]
            ,
            'logs' :
                [
                    'log_id',
                    'log_date',
                    'log_severity',
                    'log_location',
                    'log_action',
                    'log_description',
                    'log_notes',
                    'log_created'
                ]
            ,
            'personal' :
                [
                    "per_consent_background",
                    "per_allow_email",
                    "per_first_name",
                    "per_last_name",
                    "per_linkedin_url",
                    "per_no_sponsorship",
                    "per_address",
                    "per_city",
                    "per_email",
                    "per_phone",
                    "per_state_iso",
                    "per_state",
                    "per_zip",
                    "per_resume_path",
                    "per_allow_sms",
                    "per_work_legal",
                ]
            ,
            'platforms' :
                [
                    'plat_id',
                    'plat_linkedin',
                    'plat_linkedin_use_google',
                    'plat_linkedin_use_apple',
                    'plat_indeed',
                    'plat_indeed_use_google',
                    'plat_indeed_use_apple',
                    'plat_ziprecruiter',
                    'plat_ziprecruiter_use_google',
                    'plat_glassdoor',
                    'plat_glassdoor_use_google',
                    'plat_glassdoor_use_facebook'
                ]
            ,
            'profiles' :
                [
                    'pro_id',
                    'pro_created',
                    'pro_last_edited',
                    'pro_complete'
                ]
            ,
            'system' :
                [
                    'sys_id',
                    'sys_database_version',
                    'sys_local_appdata',
                    'sys_roaming_appdata',
                    'sys_os',
                    'sys_arch',
                    'sys_shy_directory',
                    'sys_home_directory',
                    'sys_last_ran'
                ]
            ,
            'work' :
                [
                    'work_id',
                    'work_city',
                    'work_state',
                    'work_state_iso',
                    'work_country',
                    'work_country_iso',
                    'work_title',
                    'work_annual_salary',
                    'work_monthly_salary',
                    'work_hourly_wage',
                    'work_remote',
                    'work_years_of_experience'
                ]
        }

        def sql_query_table(table):
            """
            Queries local sql db using unique 3 character identifier for tables.
            ai table = ai_
            auth table = aut
            ...
            """
            logslist = []
            id_list = ['ai_id' ,'auth_id', 'edu_id', 'exp_id', 'log_id', 'per_id', 'plat_id', 'pro_id', 'sys_id', 'work_id']
            __id = [i for i in id_list if table[:3] in i][0] # first 3 letters in id_list entries are all different

            db = sqlite3.connect(r'{}'.format(args.path))
            db.row_factory = sqlite3.Row
            db_cursor = db.cursor()
            if table == 'ai' or table == 'system':
                db_cursor.execute('SELECT * from {} WHERE {} = 1'.format(table, __id))
            else:
                db_cursor.execute('SELECT * from {} WHERE {} = {}'.format(table, __id, args.id))
            logs_result = db_cursor.fetchall()
            db.close()

            try:
                for row in logs_result:
                    logs_dict = {item: row[item].strip() if isinstance(row[item], str) else row[item] for item in fields[table]}
                    logslist.append(logs_dict)
            except NameError:
                frontend_top_msg("Shy Apply stopped.")
                frontend_bot_msg("Failed to query SQL table")
                sys.exit()

            return logslist

        ai = sql_query_table('ai')
        auth = sql_query_table('auth')
        education = sql_query_table('education')
        experience = sql_query_table('experience')
        personal = sql_query_table('personal')
        platforms = sql_query_table('platforms')
        system = sql_query_table('system')
        work = sql_query_table('work')

        if ai[0]['ai_last_run'] is not None:
            epoch_timenow = int(time.time())
            time_last_run = int(ai[0]['ai_last_run'])

            try:
                if epoch_timenow - time_last_run < 3600:
                    learn_more_link = r"https://www.shyapply.com/guide"
                    errlog(severity=12, element="ai_last_run", log='Did not wait the hour cooldown before running. This is to prevent getting blocked by bot detection services.')
                    finalprint = f"""Shy Apply needs an hour cooldown before running.\nThis is to prevent getting blocked by bot detection services.\nLearn more here {learn_more_link}"""
                    frontend_top_msg("Shy Apply stopped.")
                    frontend_bot_msg(finalprint)
                    log_then_exit()
                elif epoch_timenow - time_last_run >= 3600:
                    pass
            except Exception as e:
                errlog(severity=12, element="ai_last_run",description=e, log='something went wrong with time comparison')

        elif ai[0]['ai_last_run'] is None:
            pass

        try:
            edu_college = json.loads(education[0]["edu_college"]) # TypeError if they skipped College fields.

            if edu_college[0]['edu_university'] is None:
                edu_degree = "None"
            else:
                edu_degree = edu_college[0]['edu_university']

            if edu_college[0]['edu_university_degree'] is None:
                edu_major = "None"
            else:
                edu_major = edu_college[0]['edu_university_degree']
        except Exception: # TypeError
            edu_degree = 'None'
            edu_major = 'None'

        try:
            if work[0]['work_years_of_experience'] is None:
                yearsofexp = "3"
            else:
                yearsofexp = str(work[0]['work_years_of_experience'])
        except Exception:
            yearsofexp = '3'

        try:
            past_job_dict = json.loads(experience[0]["exp_jobs"]) # TypeError if they skipped Job fields.
            past_work_company = past_job_dict[0]['exp_company']
            past_work_title = past_job_dict[0]['exp_title']
        except Exception: # TypeError
            past_work_company = 'none'
            past_work_title = 'none'

        if education[0]["edu_high_school_end"] is None:
            edu_end_year = fouryearsago
        else:
            edu_end_year = education[0]["edu_high_school_end"]

        if education[0]["edu_high_school"] is None:
            edu_school = "None"
        else:
            edu_school = education[0]["edu_high_school"]

        if auth[0]["auth_linkedin_username"] is None:
            auth_linkedin_username = "none"
        else:
            auth_linkedin_username = auth[0]["auth_linkedin_username"]

        if auth[0]["auth_linkedin_pass"] is None:
            auth_linkedin_pass = "none"
        else:
            auth_linkedin_pass = auth[0]["auth_linkedin_pass"]

        if auth[0]["auth_indeed_username"] is None:
            auth_indeed_username = "none"
        else:
            auth_indeed_username = auth[0]["auth_indeed_username"]

        if auth[0]["auth_indeed_pass"] is None:
            auth_indeed_pass = "none"
        else:
            auth_indeed_pass = auth[0]["auth_indeed_pass"]

        if auth[0]["auth_ziprecruiter_username"] is None:
            auth_ziprecruiter_username = "none"
        else:
            auth_ziprecruiter_username = auth[0]["auth_ziprecruiter_username"]

        if auth[0]["auth_ziprecruiter_pass"] is None:
            auth_ziprecruiter_pass = "none"
        else:
            auth_ziprecruiter_pass = auth[0]["auth_ziprecruiter_pass"]

        if auth[0]["auth_glassdoor_username"] is None:
            auth_glassdoor_username = "none"
        else:
            auth_glassdoor_username = auth[0]["auth_glassdoor_username"]

        if auth[0]["auth_glassdoor_pass"] is None:
            auth_glassdoor_pass = "none"
        else:
            auth_glassdoor_pass = auth[0]["auth_glassdoor_pass"]

        if platforms[0]["plat_indeed"] is None:
            indeed_on = 0
        else:
            indeed_on = platforms[0]["plat_indeed"]

        if platforms[0]["plat_linkedin"] is None:
            linkedin_on = 0
        else:
            linkedin_on = platforms[0]["plat_linkedin"]

        if platforms[0]["plat_ziprecruiter"] is None:
            ziprecruiter_on = 0
        else:
            ziprecruiter_on = platforms[0]["plat_ziprecruiter"]

        if platforms[0]["plat_glassdoor"] is None:
            glassdoor_on = 0
        else:
            glassdoor_on = platforms[0]["plat_glassdoor"]

        resume_file_basename = os.path.basename(personal[0]["per_resume_path"])

        profile_dict = {
            "consent_background_check": personal[0]["per_consent_background"],
            "degree": edu_degree,
            "edu_level" : education[0]["edu_level"],
            "email_notifications": personal[0]["per_allow_email"],
            "end_year" : edu_end_year,
            "first_name": personal[0]["per_first_name"],
            "indeed": indeed_on,
            "indeed_pass": auth_indeed_pass,
            "indeed_user": auth_indeed_username,
            "job_city": work[0]["work_city"],
            "job_remote": work[0]["work_remote"],
            "job_salary": work[0]["work_annual_salary"],
            "job_state_iso": work[0]["work_state_iso"],
            "job_state_long": work[0]["work_state"],
            "job_title": work[0]["work_title"],
            "last_name": personal[0]["per_last_name"],
            "linkedin": linkedin_on,
            "linkedin_pass": auth_linkedin_pass,
            "linkedin_url": personal[0]["per_linkedin_url"],
            "linkedin_user": auth_linkedin_username,
            "major": edu_major,
            "no_sponsorship": personal[0]["per_no_sponsorship"],
            "personal_address": personal[0]["per_address"],
            "personal_city": personal[0]["per_city"],
            "personal_email": personal[0]["per_email"],
            "personal_phone": personal[0]["per_phone"],
            "personal_state_iso": personal[0]["per_state_iso"],
            "personal_state_long": personal[0]["per_state"],
            "personal_zip": personal[0]["per_zip"],
            "previous_work_job_title": past_work_title,
            "previous_work_company": past_work_company,
            'resume_file': resume_file_basename,
            "resume_path": personal[0]["per_resume_path"],
            "school": edu_school,
            "shy_dir": system[0]["sys_shy_directory"],
            "sms_notifications": personal[0]["per_allow_sms"],
            "work_legal": personal[0]["per_work_legal"],
            "ziprecruiter": ziprecruiter_on,
            "ziprecruiter_pass": auth_ziprecruiter_pass,
            "ziprecruiter_user": auth_ziprecruiter_username,
            "glassdoor": glassdoor_on,
            "glassdoor_pass": auth_glassdoor_pass,
            "glassdoor_user": auth_glassdoor_username,
            "yearsofexp": yearsofexp,
        }

        return profile_dict

    try:
        profile_dict = generate_profile_dict()
    except Exception as e:
        finalprint = "Failed to find Profile"
        frontend_bot_msg("Failed to find Profile")
        frontend_top_msg('Failed to find Profile')
        errlog(element="profile_dict", description=e)
        log_then_exit()

    try:
        if profile_dict['job_salary'] < 30000:
            profile_dict.update({'job_salary': 35000})
        elif profile_dict['job_salary'] >= 1000000:
            profile_dict.update({'job_salary': 100000})
    except Exception:
        errlog(element='profile_dict["job_salary"]', log='could not convert salary')

    possible_proc_names = ['shy apply', 'shy-apply', 'shyapply']
    if os_name() == 'mac':
        for proc in psutil.process_iter():
            if any(word in proc.name().lower() for word in possible_proc_names):
                platform_proc_name = proc.name().lower()
                break

    elif os_name() == 'win':
        for proc in psutil.process_iter():
            if any(word in proc.name().lower() for word in possible_proc_names):
                platform_proc_name = proc.name().lower()
                break

    try:
        if WE_ARE_SUBMITTING:
            get_dependencies()
            barrens_chat(String='Starting', seconds=8)
    except Exception as e:
        frontend_top_msg('Failed to start')
        errlog(description=e, log='Failed to start')
        finalprint = 'Failed to install dependencies'
        frontend_bot_msg('Failed to install dependencies')
        log_then_exit()

# -------------------------------------------------------------------------------------------------------------
num_apps_divisor = 1 # Uncomment to change static num_apps to dynamic
if profile_dict["linkedin"] == 1:
    num_apps_divisor +=1
if profile_dict["indeed"] == 1:
    num_apps_divisor +=1
if profile_dict["ziprecruiter"] == 1:
    num_apps_divisor +=1
if profile_dict["glassdoor"] == 1:
    num_apps_divisor +=1

if WE_ARE_SUBMITTING:
    num_apps = int(args.jobs) // (num_apps_divisor - 1)  # Total applications divided by number of websites selected
else:
    num_apps = 3

yourname = profile_dict['first_name'] + " " + profile_dict['last_name']
citystate = profile_dict["job_city"] + ", " + profile_dict["job_state_long"]
citystate_short = profile_dict["job_city"] + ", " + profile_dict["job_state_iso"]
citystatecountry = profile_dict["job_city"] + ", " + profile_dict["job_state_long"] + ", " + "United States"
choice_resumepath = profile_dict['resume_path']
years_experience = profile_dict['yearsofexp']

LinkedIn_skill_summary = "With my experience in problem-solving and leadership, I am confident that I would be an excellent addition to your organization. I have worked in a variety of roles for many years, developing my skills in communication, conflict resolution, and working with diverse teams."

LinkedIn_cover_letter = f"""Dear Hiring Manager,

I am writing to express my interest in a position at your company. With my experience in problem-solving and leadership, I am confident that I would be an excellent addition to your team.

I have worked in a variety of roles for many years, developing my skills in communication, conflict resolution, and working with diverse teams. In my current role, I have taken the lead on various projects, utilizing my expertise to drive successful results. My experience has given me the skills to be an asset in the position you are offering.

I am eager to bring my enthusiasm and motivation to your company, and I am confident that I have the qualifications that you are seeking.

Thank you for your time and consideration. I look forward to discussing my qualifications with you further.

Sincerely,
{profile_dict['first_name'] + " " + profile_dict['last_name']}"""

LinkedIn_text_check = {
    'involved in any investigations, official complaints or cases, whether criminal or civil': 'I have never been involved with any complaints or investigations.',
    'Is content written by artificial intelligence bad for SEO? Answer by entering': '3',
    'please provide links/urls to your portfolios or work samples.': profile_dict['linkedin_url'], "How many times did you play 18 holes of golf": "150.0", "How many golf clubs do you own?": "12", "What is your typical total strokes for an 18-hole round of golf?": "My average is around 88 for 18. Best I ever did was 82.",
    'List additional skills, qualifications, and certifications': 'Problem-solving and leadership experience\nCommunication \nConflict Resolution',
    'Please explain how you meet the minimum qualifications': LinkedIn_cover_letter,
    'Please list 2-3 dates and times or ranges of times': 'I am available Monday through Friday from 10 AM to 5 PM',
    'What is your desired annual salary or hourly rate?': profile_dict['job_salary'],
    'What type of content are you consuming right now': "Currently, I'm immersing myself in a variety of different content such as books about business leadership, podcasts about personal development, and blogs that offer insight into the latest trends in technology and entrepreneurship. I'm always looking for new ways to expand my knowledge and find inspiration in the stories of others.",
    'If Yes, list name, relationship, and location:': 'N/A', 'If you were referred by a current employee,': 'n/a',
    'What is the best time of day to reach you?': '10am to 5pm',
    'Please type in a language that you speak': 'I grew up speaking English',
    "let us know why you'd like to work here": 'I am looking for a job that will allow me to use my skills and experience to help a company grow and succeed. I believe that I have the right qualities and attitude to make a positive contribution to your organization and I am excited by the prospect of being part of your team.',
    'How many years experience do you have': years_experience,
    'How did you hear about this position?': 'I found the job listing on LinkedIn',
    'How many years of working experience': years_experience, 'What software languages are you most proficient in?':'Rust, Javascript, Python, HTML, C',
    'What is your mailing street address?': profile_dict['personal_address'],"your expected salary and currency": str(profile_dict['job_salary'])+" USD",
    'Your message to the hiring manager': LinkedIn_cover_letter,
    'What is your preferred first name?': profile_dict['first_name'], 'How many years of work experience': years_experience,
    'experience do you currently have?': years_experience, 'What are your salary expectations': profile_dict['job_salary'],
    'What are you salary requirements?': profile_dict['job_salary'], 'If Employee, please provide name': 'n/a',
    'Where do you currently reside': citystatecountry, 'How many years of experience': years_experience,
    'Notice Required (# of Days)': '14', 'Are you a current or former': 'n/a', 'Website, blog or portfolio': profile_dict['linkedin_url'],
    "Reference's Email Address:": 'see resume', 'What is your target salary': profile_dict['job_salary'],
    'How did you hear about us?': 'I found the job listing on LinkedIn', "Reference's Organization:": 'see resume',
    'How many years experience': years_experience, 'What is your desired pay': profile_dict['job_salary'],
    'Please provide your NMLS': 'see resume', 'If you were referred to': 'n/a', "Reference's Telephone:": 'see resume',
    'LinkedIn Profile (URL)': profile_dict['linkedin_url'], 'Minimum Hourly Rate:': '1',
    'Electronic Signature': yourname, 'your preferred name': yourname, 'Salary Expectations': profile_dict['job_salary'],
    'Referred by (Email)': profile_dict['personal_email'],'Why would you like to join': 'I believe that this is an amazing career opportunity and I personally believe in the future of the company',
    'Have you worked for': 'I have not been previously employed at the company.', 'Comments(optional)': 'n/a',
    'on a scale of 1-10': '7', 'Referred by (Name)': profile_dict['first_name'], 'If Yes, list name:': 'N/A',
    'Do you know anyone': 'I do not know anyone.', "Reference's Name:": 'see resume','Compensation Expectations:':profile_dict['job_salary'],
    'Link to Portfolio': 'links in resume', 'How many years of': years_experience,"your current location": citystate,
    'legal first name?': profile_dict['first_name'], 'legal last name?': profile_dict['last_name'],
    'Zip/ Postal Code': profile_dict['personal_zip'], 'Street address': profile_dict["personal_address"],
    'Desired Salary': profile_dict['job_salary'], 'Send us a link': 'links in resume', 'Postal Code': profile_dict["personal_zip"], '(optional)': 'skip',
    'Your Name:': yourname, 'CellPhone': profile_dict['personal_phone'], 'Address': profile_dict["personal_address"],"notice period":"Two weeks",
    "expected salary": profile_dict['job_salary'],'Website': profile_dict['linkedin_url'], 'Amount': profile_dict['job_salary'], 'State': profile_dict["job_state_iso"],
    'City': citystatecountry, 'Portfolio':profile_dict['linkedin_url']}

LinkedIn_radio_check = {
    'If you believe you belong to any of the categories of protected veterans listed above': 'I DO NOT WISH TO IDENTIFY AT THIS TIME',
    'By checking this box, you acknowledge and consent to terms of': 'I have read and agree to this statement',
    'Have you completed the following level of education': 'Yes',
    'Have you ever been or are you currently employed': 'No', 'Are you currently or have you ever been employed': 'No',
    'You are considered to have a disability if you': 'Wish To Answer',
    'In your most recent mortgage lending positions': 'A mix of leads that were provided to me as well as going out myself to bring in new business.',
    'VOLUNTARY SELF-IDENTIFICATION OF DISABILITY': 'Wish To Answer',
    'your citizenship / employment eligibility?': 'U.S. Citizen/Permanent Resident',
    'What is the best time of day to reach you': '10am-5pm', 'in accordance with local law/regulations?': 'Yes',
    'What is the highest level of education': "Bachelor's", 'Is this in line with your expectations': 'Yes',
    'How did you hear about this position': 'Other', 'It is okay to send me text messages': 'No',
    'Have you ever been in the Military': 'No', 'Do you have the following license': 'Yes',
    'Have you previously been employed': 'No', 'need sponsorship from an employer': 'No',
    'Are you able to pass a drug test': 'Yes', 'Have you previously worked for': 'No',
    'Do you have a criminal record': 'No', 'Are you comfortable commuting': 'Yes',
    'Notice Required (Negotiable?)': 'No', 'What is your desired salary': 'Annually',
    'What Computer/s do you own?': 'Windows Based - Sony/Lenovo/HP/Dell, etc (Newer or top of the line)',
    'legal authorization to work': 'Yes', 'Are you Hispanic or Latino?': 'No', 'Can you start immediately?': 'Yes',
    'Do you have the following': 'Yes', 'Select Disability Status': 'No', 'Are you legally eligible': 'Yes',
    'Do you have experience': 'Yes', 'How did you hear about': 'LinkedIn',"have the right to work":"Yes", 'Are you familiar with': 'Yes',
    'Select currency type': 'United States Dollar (USD)', 'Are you comfortable': 'Yes', 'require sponsorship': 'No',
    'ever been convicted': 'No', 'Do you have a valid': 'Yes', 'have you completed': 'Yes', 'authorized to work': 'Yes',
    'are you authorized': 'Yes', 'Can you be on site': 'Yes', 'Have you completed': 'Yes', 'Have you practiced': 'Yes',
    'Are you related to': 'No', 'Do you understand': 'Yes', '18 years or older': 'Yes', 'Did you Graduate?': 'Yes',
    'Two or More Races': 'I prefer not to specify', 'Were you referred': 'No', 'are you eligible': 'Yes',
    'background check': 'Yes', 'reliably commute': 'Yes', 'are you at least': 'Yes', 'Your Citizenship': 'U.S',
    'Will you require': 'No', 'Are you 18 years': 'Yes', 'What percentage': '100', 'Are you willing': 'Yes',
    'Can you commute': 'Yes, I can commute to that location', 'i certify that': 'Yes',
    'Veteran status': 'I prefer not to specify', 'Do you consent': 'Yes', 'via text/SMS?': 'No', 'Can you start': 'Yes',
    'if necessary': 'Yes', 'Referred by:': 'LinkedIn', 'School Type:': 'College/Technical', 'at least 21': 'Yes',
    '(optional)': 'skip', 'Disability': 'Wish To Answer', 'Frequency': 'yearly', 'over 18': 'Yes', 'over 21': 'Yes',
    'H1-B': 'No', 'H-1B': 'No', "Country Code": "United States"}

LinkedIn_number_check = {"(optional)": 'skip', "How many times did you play 18 holes of golf": "10.0", "salary requirements": profile_dict['job_salary'], "desired wage": "1", "How many years": years_experience,
                         "Please enter the amount": profile_dict['job_salary'], "On a scale of 1-10": "8",
                         "Reference's Telephone:": "7205555555"}

LinkedIn_checkbox_check = {
    'I have worked at companies specializing in (select all that apply):':'CX Software,CCaaS,SaaS,UcaaS',
    'The following best describes my hands on development experience with Java and Springboot:':'2-4 years',
    "(optional)": 'skip', "are you available to work": "Day,Night,Overnight",
    "Data rates may apply": "receive text messages",
    'What type of employment are you looking for?':'Full time,C2C,Consulting / Project Based',
    "Which job sites have you been using?": "Indeed,ZipRecruiter,LinkedIn",
    "Are you interested in applying for any other jobs": "Only interested in the position I am applying for",
    "What phone/s do you own?": "iPhone (older or NOT top of the line)",
    "PRIVACY POLICY": "I Agree Terms & Conditions",
    "Select all shifts you are available to work.": "Open to All",
    "Select all days you are available to work": "Open Schedule (Monday - Sunday)"}

LinkedIn_select_check = {
    "We're only assess applications that include a detailed cover letter showing your relevant experience": 'Yes',
    'Are you currently enrolled in an accredited two to four year college or university?': 'No',
    'Will you now or in the future require employment-based visa sponsorship?': 'No',
    'Have you directly utilized and/or provided instruction to others in': 'Yes',
    'Do you currently possess an active TS/SCI CI Polygraph Clearance?': 'Yes',
    'Are you a current NBCUniversal, Comcast or Sky employee?': 'No, I am not a current employee',
    'How long have you received supervision post graduation?': '12+ months',
    'What level of active security clearance do you have?': 'Top Secret',
    'Select the type of employment you are available for.': 'Full Time',
    'What is your desired minimum total compensation?': '$20K-$25K',
    'has adopted a hybrid working approach':'relocate',
    'What is your level of proficiency in English': 'Native or bilingual',
    'Have you used measurement and test equipment': 'Yes', 'Have you accrued professional experience in': 'Yes',
    'Have you gained professional experience in': 'Yes', 'What type of employment are you seeking?': 'Permanent',
    'What is your proficiency in Excel/SQL?': 'Advanced', 'will you require employer sponsorship': 'No',
    'What is your level of proficiency in': 'Professional', 'Are you currently authorized to work': 'Yes',
    'Do you possess direct experience in': 'Yes', 'Do any of your relatives work for': 'No',
    'Where did you find this job post?': 'LinkedIn', 'Have you ever been employed at': 'No',
    'Are you presently residing in': 'Yes', 'Have you worked at DoorDash?': 'I have not worked at DoorDash',
    'confirm your veteran status': 'I do not wish to specify at this time', 'Do you still want to apply?': 'Yes',
    'highest educational degree': 'Bachelors Degree', 'Do you currently reside in': 'Yes',
    'Do you have any experience': 'Yes', 'Are you 18 years or older?': 'Yes', 'Are you 21 years or older?': 'Yes',
    'Do you have any knowledge': 'Yes', 'Are you a former employee': 'No', 'Do you have a minimum of': 'Yes',
    'Do you own a tarot deck?': 'Yes', 'Have you ever supported': 'Yes', 'Do you have experience': 'Yes',
    'Do have any experience': 'Yes', 'Can you work full-time': 'Yes', 'When can you work on a': 'Fully flexible',
    'Do you currently have': 'Yes', 'Current Compensation': 'USD', 'Desired Compensation': 'USD',
    "require any sponsorship": "No","a sponsorship": "No", 'would you be willing': 'Yes', 'Are you willing/able': 'Yes',
    'Are you a US Citizen': 'Yes', 'years of experience': 'Yes', 'Are you comfortable': 'Yes',"previously employed by":"No",
    'Have you passed the': 'Yes', 'Have you worked for': 'No', 'Do you live nearby': 'Yes', 'Preferred Location': 'USA',
    'Are you located in': 'Yes', 'Disability Status': "I don't wish to answer", 'Select your level': 'Native',
    'Are you at least': 'Yes','sponsorship to work':'No','require sponsorship':'No', 'Can you commute': 'Yes', 'Ethnicity/Race': 'I decline to identify',
    'Veteran Status': "I don't wish to answer", 'Are you able': 'Yes', 'Do you have': 'Yes', 'Do you hold': 'Yes',
    '(optional)': 'skip', 'via SMS': 'No', 'Gender': 'Decline To Self Identify',
    'State': profile_dict['job_state_long'], 'Race': 'Decline to answer', 'H-1B': 'No'}

LinkedIn_resume_container = {"resume": "path"}

LinkedIn_date_check = {"(optional)": 'skip', "Today’s Date:": todaysdate, "Date:": todaysdate}

LinkedIn_skip_check = {"(optional)": 'skip',
                       "Data rates may apply": "skip"}  # ---THE SAME KEY MUST BE IN SKIP AND ITS CORRECT CHECK DICT TO SKIP QUESTION


def LinkedIn_Driver(web):

    def search_str(file_path, word): # QUESTION LOGGING
        if os.path.exists(file_path) == False:
            with open(file_path, 'a'): pass

        with open(file_path, 'r') as file:
            # read all content of a file
            content = file.read()
            # check if string present in a file
            if word in content:
                return True
            else:
                return False

    def Resumefill():
        try:
            rescontainerlabel = web.find_element(By.XPATH, '//div[contains(@class, "jobs-document-upload-redesign-card__container")]/p/h3')

            rescontainer = web.find_element(By.XPATH, '//h3[text()="{}"]/ancestor::div[contains(@class, "jobs-document-upload-redesign-card__container")]'.format(rescontainerlabel.text))

            if os.path.basename(choice_resumepath) == rescontainerlabel.text:
                if rescontainer.get_dom_attribute("aria-label") == "Selected":
                    pass
                else:
                    rescontainer.uc_click()
            if os.path.basename(choice_resumepath) != rescontainerlabel.text:
                try:
                    uploadRes = web.find_elements(By.XPATH, "//input[@type='file']")
                    if len(uploadRes)>0:
                        uploadRes[0].send_keys(choice_resumepath)
                except Exception as e:
                    errlog(element="uploadRes",description=e)
        except Exception:
            try:
                uploadRes = web.find_elements(By.XPATH, "//input[@type='file']")
                if len(uploadRes)>0:
                    uploadRes[0].send_keys(choice_resumepath)
            except Exception as e:
                errlog(element="uploadRes[0]",description=e)

    def Linkedin_GoNext():
        time.sleep(1)
        nextcount = 0
        gonext_list = []
        try:
            next = web.find_element(By.XPATH, "//button[@aria-label='Continue to next step']/span[text()='Next']")
            if next:
                gonext_list.append("Next")
        except Exception:
            nextcount+=1
        try:
            reviewtarget = web.find_element(By.XPATH, "//button[@aria-label='Review your application']/span[text()='Review']")
            if reviewtarget:
                gonext_list.append("Review")
        except Exception:
            nextcount+=1
        try:
            submit_application = web.find_element(By.XPATH, "//button[@aria-label='Submit application']/span[text()='Submit application']")
            if submit_application:
                gonext_list.append("Submit")
        except Exception:
            nextcount+=1


        if "Next" in gonext_list:
            frontend_bot_msg("Navigating..")
            next.uc_click()
            time.sleep(2)
            try:
                alert = WebDriverWait(web,7).until(EC.visibility_of_element_located((By.XPATH, '//div[@class="jobs-easy-apply-content"]//descendant::div[@role="alert"]')))
                if alert:
                    errlog(element="alert",log="APPLICATION FAILURE 1")
                    try:
                        alert_text = web.find_elements(By.XPATH, '//div[@class="jobs-easy-apply-content"]//descendant::div[@role="alert"]//ancestor::div[contains(@class,"jobs-easy-apply-form-section__grouping")]')
                        if len(alert_text) > 0:
                            for element in alert_text:
                                errlog(element="alert_text", log=element.text)
                    except Exception as e:
                        errlog(element="alert_text",description=e,log="could not find error text")
                    close_button = web.find_element(By.XPATH, '//button[@aria-label="Dismiss"]')
                    close_button.uc_click()
                    time.sleep(1.5)
                    discard_button = web.find_element(By.XPATH, '//span[text()="Discard"]')
                    discard_button.uc_click()
                    time.sleep(2)
            except TimeoutException:
                LinkedIn_ansfind()
        if "Review" in gonext_list:
            frontend_bot_msg("Reviewing..")
            reviewtarget.uc_click()
            time.sleep(2)
            try:
                alert = WebDriverWait(web,7).until(EC.visibility_of_element_located((By.XPATH, '//div[@class="jobs-easy-apply-content"]//descendant::div[@role="alert"]')))
                if alert:
                    errlog(element="alert",log="APPLICATION FAILURE 2")
                    try:
                        alert_text = web.find_elements(By.XPATH, '//div[@class="jobs-easy-apply-content"]//descendant::div[@role="alert"]//ancestor::div[contains(@class,"jobs-easy-apply-form-section__grouping")]')
                        if len(alert_text) > 0:
                            for element in alert_text:
                                errlog(element="alert_text", log=element.text)
                    except Exception as e:
                        errlog(element="alert_text",description=e,log="could not find error text")
                    close_button = web.find_element(By.XPATH, '//button[@aria-label="Dismiss"]')
                    close_button.uc_click()
                    time.sleep(1.5)
                    discard_button = web.find_element(By.XPATH, '//span[text()="Discard"]')
                    discard_button.uc_click()
                    time.sleep(2)
            except TimeoutException:
                finalscreen()
        if "Submit" in gonext_list:
            frontend_bot_msg("Submitting..")
            try:
                nofollow = web.find_elements(By.XPATH, "//input[@type='checkbox' and @id= 'follow-company-checkbox']")
                for box in nofollow:
                    if box.is_selected()==True:
                        try:
                            boxlbl = box.find_element(By.XPATH, "./following-sibling::label")
                            boxlbl.uc_click()
                        except Exception as e:
                            errlog(element='nofollow', description=e)
                        time.sleep(2)
            except Exception:
                pass
            if WE_ARE_SUBMITTING:
                try:
                    submit_application.uc_click()
                except Exception as e:
                    errlog(element="submit_application", description=e, log='found submit captcha')
                    captcha_checkbox_and_solve(web)
                    time.sleep(2)
                    submit_application = web.find_element(By.XPATH, "//button[@aria-label='Submit application']/span[text()='Submit application']")
                    submit_application.uc_click()
                time.sleep(2)
            else:
                dismiss_scrn = web.find_element(By.XPATH, '//div[@role="dialog"]') # THIS IS FOR DISABLING SUBMIT
                dismissbtn = dismiss_scrn.find_element(By.XPATH, './button[@aria-label="Dismiss"]')
                dismissbtn.uc_click()
                time.sleep(1)
                WebDriverWait(web,10).until(EC.visibility_of_element_located((By.XPATH, '//div[@role="alertdialog"]')))
                close_scrn = web.find_element(By.XPATH, '//div[@role="alertdialog"]')
                closebtn = close_scrn.find_element(By.XPATH, ".//button/span[text()[contains(.,'Discard')]]")
                closebtn.uc_click()
                time.sleep(2)
        if nextcount == 3:
            if WE_ARE_SUBMITTING:
                errlog(element="nextcount",log="nextcount = 3")
                web.close()
            else:
                errlog(element="nextcount",log="nextcount = 3")

    def finalscreen(): # This overlaps with the submit block in Linkedin_gonext for a reason i dont remember. likely back to back review scrns b4 submit?
        time.sleep(1)
        try:
            reviewapp = WebDriverWait(web,20).until(EC.presence_of_element_located((By.XPATH, '//h3[text()[contains(.,"Review your application")]]'))) # This is on submit scrn (confusing name)
            nofollow = web.find_elements(By.XPATH, "//input[@type='checkbox' and @id= 'follow-company-checkbox']")
            for box in nofollow:
                if box.is_selected()==True:
                    try:
                        boxlbl = box.find_element(By.XPATH, "./following-sibling::label")
                        boxlbl.uc_click()
                    except Exception as e:
                        errlog(element="boxlbl",description=e)
                    time.sleep(2)
            Linkedin_GoNext()
        except TimeoutException:
            Linkedin_GoNext()

    def type_finder():#--find question types for testing
        questions = web.find_elements(By.XPATH, "//*[contains(@class, 'jobs-easy-apply-form-section')]")
        qcount = 1
        for i in questions:
            try:
                answer = i.find_element(By.TAG_NAME, "input")
            except NoSuchElementException:
                try:
                    answer = i.find_element(By.TAG_NAME, "textarea")
                except NoSuchElementException:
                    try:
                        answer = i.find_element(By.TAG_NAME, "select")
                    except NoSuchElementException:
                        continue
            answer_type = answer.get_attribute("type")
            answer_type2 = answer.get_attribute("aria-autocomplete")
            frontend_bot_msg("Question" + ' ' + str(qcount) + ' ' + str(answer_type))
            # frontend_bot_msg("Question" + ' ' + str(qcount) + ' ' + str(answer_type) + ' ' + i.text)
            qcount+=1

    def default_workexp():
        work_jobtitle = web.find_element(By.XPATH, "//*[contains(@class, 'jobs-easy-apply-form-section')]//input[preceding-sibling::label[text()='Your title']]")
        bot_typer(work_jobtitle,"Self-Employed")
        time.sleep(2)
        work_company = web.find_element(By.XPATH, "//*[contains(@class, 'jobs-easy-apply-form-section')]//input[preceding-sibling::label[text()='Company']]")
        bot_typer(work_company,"Self-Employed")
        time.sleep(2)
        work_chkbox = web.find_element(By.XPATH, '//input[@type="checkbox"]')
        if work_chkbox.is_selected() == 0:
            work_chkboxlbl = web.find_element(By.XPATH, '//label[text()="I currently work here"]')
            work_chkboxlbl.uc_click()
        else:
            pass
        time.sleep(2)
        work_monthselect = Select(web.find_element(By.XPATH, '//span[preceding-sibling::label[text()="Month of From"]]/select'))
        work_monthselect.select_by_visible_text(todaysmonth)
        time.sleep(2)
        work_yearselect = Select(web.find_element(By.XPATH, '//span[preceding-sibling::label[text()="Year of From"]]/select'))
        work_yearselect.select_by_visible_text(str(lastyear))
        time.sleep(2)
        # work_city = web.find_element(By.XPATH, "//*[contains(@class, 'jobs-easy-apply-form-section')]//div[preceding-sibling::label[text()='City']]/input")#-annoying autofill
        # bot_typer(work_city,"Pittsburgh")#input here
        #Pittsburgh, Pennsylvania, United States
        # time.sleep(1)
        work_company = web.find_element(By.XPATH, "//*[contains(@class, 'jobs-easy-apply-form-section')]//textarea[preceding-sibling::label[text()='Description']]")
        bot_typer(work_company,LinkedIn_cover_letter)
        time.sleep(2)
        savebtn = web.find_element(By.XPATH, '//span[text()="Save"]')
        savebtn.uc_click()

    def default_edu():
        edu_school1 = web.find_element(By.XPATH, "//*[contains(@class, 'jobs-easy-apply-form-section')]//input[preceding-sibling::label[text()='School']]")
        if profile_dict['school'] != "":
            bot_typer(edu_school1,profile_dict['school'])
        else:
            bot_typer(edu_school1,"High School")
        time.sleep(2)
        edu_major = web.find_element(By.XPATH, "//*[contains(@class, 'jobs-easy-apply-form-section')]//input[preceding-sibling::label[text()='Major / Field of study']]")
        if profile_dict['major'] != "":
            bot_typer(edu_major,profile_dict['major'])
        else:
            bot_typer(edu_major,"General Education")
        time.sleep(2)
        edu_monthselect1 = Select(web.find_element(By.XPATH, '//span[preceding-sibling::label[text()="Month of From"]]/select'))#August
        edu_monthselect1.select_by_visible_text("August")
        time.sleep(2)
        edu_yearselect1 = Select(web.find_element(By.XPATH, '//span[preceding-sibling::label[text()="Year of From"]]/select'))#8years ago
        if profile_dict['end_year'] != "":
            edu_yearselect1.select_by_visible_text(str(profile_dict['end_year']-4))
        else:
            edu_yearselect1.select_by_visible_text(str(eightyearsago))
        time.sleep(2)
        edu_monthselect2 = Select(web.find_element(By.XPATH, '//span[preceding-sibling::label[text()="Month of To"]]/select'))#june
        edu_monthselect2.select_by_visible_text("June")
        time.sleep(2)
        edu_yearselect2 = Select(web.find_element(By.XPATH, '//span[preceding-sibling::label[text()="Year of To"]]/select'))#4yearsago
        if profile_dict['end_year'] != "":
            edu_yearselect2.select_by_visible_text(str(profile_dict['end_year']))
        else:
            edu_yearselect2.select_by_visible_text(str(fouryearsago))
        time.sleep(2)
        savebtn = web.find_element(By.XPATH, '//span[text()="Save"]')
        savebtn.uc_click()

    def Linkedin_formfill():#finds the answer type within the question group.
        #print("Linkedin_formfill called")

        def default_skin(i):
            default_radio_answerbank = ["I prefer not","I Don\'t Wish","Prefer not to answer","I prefer not to specify","Decline To Self Identify","Decline to Self Identify","I don't wish to answer","I DO NOT WISH TO IDENTIFY AT THIS TIME","Wish To Answer","I do not want to answer.","I do not wish to disclose","I Do Not Wish to Disclose","I do not want to answer"]

            try:
                answer = i.find_element(By.TAG_NAME, "input")
            except NoSuchElementException:
                try:
                    answer = i.find_element(By.TAG_NAME, "textarea")
                except NoSuchElementException:
                    try:
                        answer = i.find_element(By.TAG_NAME, "select")
                    except NoSuchElementException:
                        pass

            answer_type = answer.get_attribute("type")
            answer_type2 = answer.get_attribute("aria-autocomplete")
            answer_type3 = answer.get_attribute("id")

            # QUESTION LOGGING
            try:
                search_string = i.text
                send_question_post(str(answer_type), str(search_string), 'Linkedin')
            except Exception as e:
                repeatQ = "Likely Repeat Question", str(e)
                errlog(severity=50, element="Linkedin_LOGGING", description=repeatQ, log=str(search_string))

            if answer_type == "text" and "numeric" not in answer_type3:
                bot_typer(answer,"Happy to answer all questions in an interview :)")
                time.sleep(1)
                if answer_type2 == "list":
                    try:
                        i.send_keys(Keys.ENTER) # could be sus. why not answer?
                    except ElementNotInteractableException:
                        pass

            if answer_type == "text" and "numeric" in answer_type3:
                bot_typer(answer,"3")

            if answer_type == "radio":
                valueR_ejector = 0

                for x in default_radio_answerbank:
                    try:
                        prefernot = i.find_element(By.XPATH, './/label[text()[contains(.,\"{}\")]]'.format(x))
                        prefernot2 = i.find_element(By.XPATH, './/label[text()[contains(.,\"{}\")]]//preceding-sibling::input[@type="radio"]'.format(x))
                        if prefernot2.is_selected()==False:
                            prefernot.uc_click()
                        break
                    except NoSuchElementException:
                        valueR_ejector+=1
                        continue

                if valueR_ejector == len(default_radio_answerbank):
                    default_radlbl = i.find_elements(By.XPATH, './/input[@type="radio"]/following-sibling::label')
                    default_rad = i.find_elements(By.XPATH, './/label/preceding-sibling::input[@type="radio"]')
                    if default_rad[0].is_selected()==False:
                        default_radlbl[0].uc_click()
                    else:
                        pass
                    time.sleep(1)

            if answer_type == "textarea":
                bot_typer(answer,"Happy to answer all questions in an interview :)")

            if answer_type == "number":
                bot_typer(answer,"8")

            if answer_type == "checkbox":
                valueC_ejector = 0
                for x in default_radio_answerbank:
                    try:
                        lbl = i.find_element(By.XPATH, './/label[text()[contains(.,\"{}\")]]'.format(x))
                        input = i.find_element(By.XPATH, './/label/preceding-sibling::input[@type="checkbox"]')
                        if input.is_selected()==False:
                            lbl.uc_click()
                        else:
                            pass
                    except NoSuchElementException:
                        valueC_ejector+=1
                        continue

                if valueC_ejector == len(default_radio_answerbank):
                    default_lbl = i.find_elements(By.XPATH, './/input[@type="checkbox"]/following-sibling::label')
                    default_input = i.find_elements(By.XPATH, './/label/preceding-sibling::input[@type="checkbox"]')
                    if default_input[0].is_selected()==False:
                        default_lbl[0].uc_click()
                    else:
                        pass

            if answer_type == "select-one":
                valueS_ejector = 0

                dropdown = Select(i.find_element(By.CSS_SELECTOR, "select")) # rewrite to match x.lower with values.lower for better result
                for x in default_radio_answerbank:
                    try:
                        dropdown.select_by_visible_text(x)
                        break
                    except NoSuchElementException:
                        valueS_ejector+=1
                        continue

                if valueS_ejector == len(default_radio_answerbank):
                    dropdown.select_by_index(1)
                    time.sleep(1)

            if answer_type == "date":
                pass
                #datetype = web.find_element(By.XPATH, "//*[starts-with(@id, '{}')]//input".format(the_id))
                #datetype.send_keys(todaysdate)

            if answer_type == "tel":
                bot_typer(answer, profile_dict['personal_phone'])

        def LinkedInQfill_select(i):
            # def salary_man(number):#FIND QUESTION AND TEST -> MUST GO ABOVE DICTS
            #     values = i.options #list of all possible values
            #     values_after = []

            #     for value in values:
            #         s1=re.sub("[$_]","",value)
            #         s2=re.sub("[-]"," ",s1)
            #         s3=re.sub("[Kk]","000",s2)
            #         s4=s3.strip().split(" ")
            #         values_after.append(int(s4[0]))

            #     final_index = values_after.index(min(values_after, key=lambda x:abs(x-number)))
            #     return values[final_index]

            sel_ans_cons = {}
            defaultejecter = 0
            iterator_text = i.text
            for key,value in LinkedIn_select_check.items():
                if key.lower() in iterator_text.lower() and "(optional)" not in iterator_text.lower():
                    sel_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in LinkedIn_skip_check.keys():
                    sel_ans_cons.update(key="skip")
                    break
            if len(sel_ans_cons)>0:
                first_val = list(sel_ans_cons.values())[0]
                if first_val != "skip":
                    try:
                        answer = Select(i.find_element(By.XPATH, ".//select"))
                        answer.select_by_visible_text(first_val)
                        time.sleep(1)
                    except Exception:
                        defaultejecter +=1
            if len(sel_ans_cons) == 0 or defaultejecter == 1:
                #print("LinkedInQfill_select FAILED")
                #print(iterator_text)
                default_skin(i)
                time.sleep(1)

        def LinkedInQfill_number(i):
            num_ans_cons = {}
            defaultejecter = 0
            iterator_text = i.text
            for key,value in LinkedIn_number_check.items():
                if key.lower() in iterator_text.lower() and "(optional)" not in iterator_text.lower():
                    num_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in LinkedIn_skip_check.keys():
                    num_ans_cons.update(key="skip")
                    break
            if len(num_ans_cons)>0:
                first_val = list(num_ans_cons.values())[0]
                if first_val != "skip":
                    try:
                        bot_typer(answer,first_val)
                        time.sleep(1)
                    except Exception:
                        defaultejecter +=1
            if len(num_ans_cons) == 0 or defaultejecter == 1:
                #print("LinkedInQfill_number FAILED")
                #print(iterator_text)
                default_skin(i)
                time.sleep(1)

        def LinkedInQfill_chkbox(i):#find question group element. split total string by \n to find question at first index. use that with relative locator + string matching to find answers.Split dict values by "," for multi answer.
            chkbox_ans_cons = {}
            defaultejecter = 0
            iterator_text = i.text
            for key,value in LinkedIn_checkbox_check.items():
                if key.lower() in iterator_text.lower() and "(optional)" not in iterator_text.lower():
                    chkbox_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in LinkedIn_skip_check.keys():
                    chkbox_ans_cons.update(key="skip")
                    break
            if len(chkbox_ans_cons)>0:
                first_val = list(chkbox_ans_cons.values())[0]
                if first_val != "skip":
                    valueslist = first_val.split(",")
                    try:
                        boxchecker = 0
                        for o in valueslist:
                            try:
                                lbl = i.find_element(By.XPATH, './/label[text()[contains(.,\"{}\")]]'.format(o))
                                lbl.uc_click()
                                time.sleep(0.5)
                            except Exception:
                                boxchecker+=1
                                continue
                        if boxchecker == len(valueslist):
                            defaultejecter+=1
                        time.sleep(1)
                    except Exception:
                        defaultejecter +=1
            if len(chkbox_ans_cons) == 0 or defaultejecter == 1:
                #print("LinkedInQfill_chkbox FAILED")
                default_skin(i)
                time.sleep(1)

        def LinkedInQfill_date(i):#----Currently does nothing
            radio_ans_cons = {}
            defaultejecter = 0
            iterator_text = i.text
            for key,value in LinkedIn_radio_check.items():
                if key.lower() in iterator_text.lower() and "(optional)" not in iterator_text.lower():
                    radio_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in LinkedIn_skip_check.keys():
                    radio_ans_cons.update(key="skip")
                    break
            if len(radio_ans_cons)>0:
                first_val = list(radio_ans_cons.values())[0]
                if first_val != "skip":
                    try:
                        datetype = web.find_element(By.XPATH, "//*[starts-with(@id, '{}')]//input")
                        datetype.send_keys(first_val)
                        time.sleep(1)
                    except Exception:
                        defaultejecter +=1
            if len(radio_ans_cons) == 0 or defaultejecter == 1:
                #print("LinkedInQfill_radio FAILED")
                #print(iterator_text)
                default_skin(i)
                time.sleep(1)

        def LinkedInQfill_radio(i):#find question group element. split total string by \n to find question at first index. use that with relative locator + string matching to find answer bubble. currently clicks on the label might have to offset with actionchains later if stops working.
            radio_ans_cons = {}
            defaultejecter = 0
            iterator_text = i.text
            for key,value in LinkedIn_radio_check.items():
                if key.lower() in iterator_text.lower() and "(optional)" not in iterator_text.lower():
                    radio_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in LinkedIn_skip_check.keys():
                    radio_ans_cons.update(key="skip")
                    break
            if len(radio_ans_cons)>0:
                first_val = list(radio_ans_cons.values())[0]
                if first_val != "skip":
                    try:
                        rad_lbl = i.find_element(By.XPATH, './/label[text()[contains(.,\"{}\")]]'.format(first_val))
                        Qfill_rad = i.find_element(By.XPATH, './/label[text()[contains(.,\"{}\")]]//preceding-sibling::input[@type="radio"]'.format(first_val))
                        if Qfill_rad.is_selected()==False:
                            rad_lbl.uc_click()
                        time.sleep(1)
                    except Exception:
                        defaultejecter +=1
            if len(radio_ans_cons) == 0 or defaultejecter == 1:
                #print("LinkedInQfill_radio FAILED")
                #print(iterator_text)
                default_skin(i)
                time.sleep(1)

        def LinkedInQfill_text(i):
            text_ans_cons = {}
            defaultejecter = 0
            iterator_text = i.text

            for key,value in LinkedIn_text_check.items():
                if key.lower() in iterator_text.lower():
                    text_ans_cons.update(key=value)
                    break
                if key.lower() in iterator_text.lower() and key in LinkedIn_skip_check.keys():
                    text_ans_cons.update(key="skip")
                    break
            if len(text_ans_cons)>0:
                first_val = list(text_ans_cons.values())[0]
                if first_val != "skip":
                    try:
                        bot_typer(answer,first_val)
                        time.sleep(1)
                    except Exception:
                        defaultejecter +=1
            if len(text_ans_cons)== 0 or defaultejecter == 1:
                #print("LinkedInQfill_text FAILED")
                #print(iterator_text)
                default_skin(i)
                time.sleep(1)

        questions = web.find_elements(By.XPATH, "//*[contains(@class, 'jobs-easy-apply-form-section')]")
        if len(questions) != 0:
            num_questions = str(len(questions))
            current_question = 1

            for i in questions:
                try:
                    answer = i.find_element(By.TAG_NAME, "input")
                except NoSuchElementException:
                    try:
                        answer = i.find_element(By.TAG_NAME, "textarea")
                    except NoSuchElementException:
                        try:
                            answer = i.find_element(By.TAG_NAME, "select")
                        except NoSuchElementException:
                            continue

                frontend_bot_msg("Answering: question "+ str(current_question) + " of " + num_questions)

                answer_type = answer.get_attribute("type")
                answer_type2 = answer.get_attribute("aria-autocomplete")

                if answer_type == "text":#complete
                    LinkedInQfill_text(i)
                    time.sleep(1)
                    if answer_type2 == "list":
                        try:
                            i.send_keys(Keys.ENTER)
                        except Exception as e:
                            errlog(element="answer_type2",description=e)
                if answer_type == "textarea":#complete
                    LinkedInQfill_text(i)
                    time.sleep(1)
                if answer_type == "radio":#complete
                    LinkedInQfill_radio(i)
                    time.sleep(1)
                if answer_type == "number":
                    LinkedInQfill_number(i)
                    time.sleep(1)
                if answer_type == "checkbox":#complete
                    LinkedInQfill_chkbox(i)
                    time.sleep(1)
                if answer_type == "select-one":#complete
                    LinkedInQfill_select(i)
                    time.sleep(1)
                if answer_type == "date":
                    LinkedInQfill_date(i)
                    time.sleep(1)
                if answer_type == "tel":
                    LinkedInQfill_number(i)
                    time.sleep(1)

                current_question = current_question + 1
        else:
            errlog(element='Linkedin_formfill', log='ansfind called when no questions found')

    def LinkedIn_ansfind():
        #print("LinkedIn_ansfind called")
        gonext_Var = 0
        responselist = []
        try:
            workexperience = web.find_element(By.XPATH, '//h3/span[text()="Work experience"]')
            responselist.append("Work")
        except Exception:
            pass
        try:
            resume = web.find_element(By.XPATH, '//h3[text()="Resume"]')
            responselist.append("Resume")
        except Exception:
            pass
        try:
            edu = web.find_element(By.XPATH, '//h3/span[text()="Education"]')
            responselist.append("Edu")
        except Exception:
            pass
        try:
            profilequestion = web.find_element(By.XPATH, '//h3[text()="Screening questions"]/following-sibling::span[text()="LinkedIn Profile"]')
            responselist.append("Profile")
        except Exception:
            pass
        try:
            contactinfo = web.find_element(By.XPATH, '//h3[text()[contains(.,"Contact info")]]')
            responselist.append("Contact")
        except Exception:
            pass
        try:
            homeaddress = web.find_element(By.XPATH, '//h3[text()[contains(.,"Home address")]]')
            responselist.append("Address")
        except Exception:
            pass

        #print(responselist)

        if "Work" in responselist:
            frontend_bot_msg("Adding Work History...")
            try:
                work_jobtitle = web.find_element(By.XPATH, "//*[contains(@class, 'jobs-easy-apply-form-section')]//input[preceding-sibling::label[text()='Your title']]")
                if work_jobtitle:
                    default_workexp()
                    gonext_Var+=1
            except NoSuchElementException:
                gonext_Var+=1
        if "Resume" in responselist:
            frontend_bot_msg("Adding resume...")
            Resumefill()
            try:
                coverletterh1 = web.find_element(By.XPATH, '//h3[text()="Cover letter"]')
                coverletter = web.find_element(By.XPATH, '//h3[text()="Cover letter"]//following-sibling::div//descendant::textarea')
                frontend_bot_msg("Crafting cover letter...")
                bot_typer(coverletter, LinkedIn_cover_letter)
            except Exception:
                pass
            gonext_Var+=1
        if "Edu" in responselist:
            frontend_bot_msg("Adding education...")
            try:
                edu_school2 = web.find_element(By.XPATH, "//*[contains(@class, 'jobs-easy-apply-form-section')]//input[preceding-sibling::label[text()='School']]")
                if edu_school2:
                    default_edu()
                    gonext_Var+=1
            except Exception:
                gonext_Var+=1
        if "Profile" in responselist:
            gonext_Var+=1
        if "Address" in responselist:
            try:
                address_st1 = web.find_element(By.XPATH, '//label[text()="Street address line 1"]/following-sibling::input')
                frontend_bot_msg("Adding address...")
                bot_typer(address_st1,profile_dict['personal_address'])
                time.sleep(1)
            except Exception as e:
                errlog(element="address_st1",description=e)
            try:
                address_cy = web.find_element(By.XPATH, '//label[.//span[text()="City"]]/following-sibling::div/input')
                frontend_bot_msg("Adding city...")
                bot_typer(address_cy,citystatecountry)
                time.sleep(3)
                spanlist = web.find_elements(By.XPATH, '//label[.//span[text()="City"]]/following-sibling::div/input/following-sibling::div[@role="listbox"]/descendant::span')
                for span in spanlist:
                    if profile_dict["job_city"] in span.text and profile_dict["job_state_long"] in span.text:
                        span.uc_click()
                        break
                time.sleep(1)
            except Exception as e:
                errlog(element="address_cy",description=e)
            try:
                address_zp = web.find_element(By.XPATH, '//label[text()="ZIP / Postal Code"]/following-sibling::input')
                frontend_bot_msg("Adding zip code...")
                bot_typer(address_zp,profile_dict['personal_zip'])
                try:
                    alert = WebDriverWait(web,4).until(EC.visibility_of_element_located((By.XPATH, '//div[@class="jobs-easy-apply-content"]//descendant::div[@role="alert"]')))
                    if alert:
                        address_cy.clear()
                        time.sleep(1)
                        bot_typer(address_cy,profile_dict["job_state_long"]+", "+"United States")
                        time.sleep(3)
                        spanlist = web.find_elements(By.XPATH, '//label[.//span[text()="City"]]/following-sibling::div/input/following-sibling::div[@role="listbox"]/descendant::span')
                        for span in spanlist:
                            if profile_dict["job_state_long"] in span.text and "United States" in span.text:
                                span.uc_click()
                                break
                except TimeoutException:
                    pass
                time.sleep(1)
            except Exception as e:
                errlog(element="address_zp",description=e)
            gonext_Var+=1
        if "Contact" in responselist:
            frontend_bot_msg("Adding contact information...")
            try:
                contact_fn = web.find_element(By.XPATH, '//label[text()="First name"]/following-sibling::input')
                bot_typer(contact_fn,profile_dict['first_name'])
                time.sleep(1)
            except Exception:
                pass

            try:
                contact_ln = web.find_element(By.XPATH, '//label[text()="Last name"]/following-sibling::input')
                bot_typer(contact_ln,profile_dict['last_name'])
                time.sleep(1)
            except Exception:
                pass

            try:
                try:
                    contact_mpn = web.find_element(By.XPATH, '//label[text()="Mobile phone number"]/following-sibling::input')
                except NoSuchElementException:
                    contact_mpn = web.find_element(By.XPATH, '//label[text()="Phone"]/following-sibling::input')
                bot_typer(contact_mpn,profile_dict['personal_phone'])
                time.sleep(1)
            except Exception:
                pass

            try:
                try:
                    contact_pn = web.find_element(By.XPATH, '//label[contains(@for, "phoneNumber-country")]/following-sibling::select')
                except NoSuchElementException:
                    contact_pn = web.find_element(By.XPATH, '//label[text()="Phone country code"]/following-sibling::select')
                pncountry = Select(contact_pn)
                if pncountry.first_selected_option.text != "United States (+1)":
                    try:
                        pncountry.select_by_visible_text("United States (+1)")
                        time.sleep(1)
                    except Exception:
                        try:
                            pncountry.select_by_visible_text("1")
                        except Exception:
                            try:
                                pncountry.select_by_index(1)
                            except Exception:
                                pass
                else:
                    pass
            except Exception:
                pass

            try:
                try:
                    contact_em = web.find_element(By.XPATH, '//label/span[contains(text(), "Email")]//parent::label//following-sibling::select')
                except NoSuchElementException:
                    contact_em = web.find_element(By.XPATH, '//label[text()="Email address"]/following-sibling::select')
                contact_em_select = Select(contact_em)
                if contact_em_select.first_selected_option.text == "Select an option":
                    try:
                        contact_em_select.select_by_visible_text(profile_dict['personal_email'])
                    except Exception:
                        try:
                            contact_em_select.select_by_index(1)
                        except Exception:
                            pass
                else:
                    pass
            except Exception:
                pass

            try:
                try:
                    contact_addy = web.find_element(By.XPATH, '//label[text()="Address"]/following-sibling::input')
                except NoSuchElementException:
                    contact_addy = web.find_element(By.XPATH, '//label[text()="Address"]/following-sibling::input')
                bot_typer(contact_addy,profile_dict['personal_address'])
                time.sleep(1)
            except Exception:
                pass

            try:
                Resumefill()
            except Exception as e:
                errlog(element="Resumefill()",description=e)
            time.sleep(1)
            gonext_Var+=1
        if len(responselist)==0:
            Linkedin_formfill()
            gonext_Var+=1
        if gonext_Var > 0:
            time.sleep(3)
            #print("Linkedin_GoNext called")
            Linkedin_GoNext()

    def Linkedin_signin():
        global finalprint
        frontend_bot_msg("Signing into Linkedin")

        try:
            sign_in_with_email_btn = web.find_element(By.XPATH, '//a[contains(text(), "Sign in with email")]')
            sign_in_with_email_btn.uc_click()
            time.sleep(2)
        except Exception:
            try:
                top_right_sign_in_btn = web.find_element(By.LINK_TEXT, "Sign in")
                top_right_sign_in_btn.uc_click()
                time.sleep(2)
            except Exception as e:
                errlog(element='sign_in_with_email_btn & top_right_sign_in_btn', description=e, log='Linkedin updated signin buttons')

        try: # Top half might be old code - couldnt find main_user anywhere
            notsignedin = WebDriverWait(web,10).until(EC.presence_of_element_located((By.ID, "session_key")))
            if notsignedin:
                try:
                    start_URL = web.current_url
                    main_user = web.find_element(By.ID, "session_key") #main screen username
                    bot_typer(main_user,profile_dict['linkedin_user'])
                    time.sleep(2.56)
                    main_pw = web.find_element(By.ID, "session_password") #main screen password
                    bot_typer(main_pw,profile_dict['linkedin_pass'])
                    time.sleep(0.34)
                    main_submit = web.find_element(By.XPATH, '//button[@type="submit"]') #main screen submit/ also works for backup screen
                    main_submit.uc_click()
                    time.sleep(2)
                    after_URL = web.current_url
                except Exception as e:
                    errlog(element="main_user?",description=e)
                    start_URL = "https://www.linkedin.com"
                    after_URL = "https://www.shyapply.com"

                if start_URL == after_URL:
                    try:
                        main_pw_alert = web.find_element(By.XPATH, '//input[@id = "session_password"]//parent::div//parent::div//following-sibling::p[@role="alert"]',timeout=5)
                        frontend_top_msg('Linkedin sign-in failed')
                        frontend_bot_msg("Linkedin Invalid-Email/Password")
                        finalprint = "Linkedin Invalid-Email/Password"
                    except NoSuchElementException:
                        try:
                            main_user_alert = web.find_element(By.XPATH, '//input[@id = "session_key"]//parent::div//parent::div//following-sibling::p[@role="alert"]',timeout=5)
                            frontend_top_msg('Linkedin sign-in failed')
                            frontend_bot_msg("Linkedin Invalid-Email/Password")
                            finalprint = "Linkedin Invalid-Email/Password"
                        except NoSuchElementException:
                            frontend_top_msg('Linkedin sign-in failed')
                            frontend_bot_msg("Linkedin log-in failure")
                            finalprint = "Linkedin log-in failure"
                elif start_URL != after_URL:
                    try:
                        element = WebDriverWait(web,10).until(EC.presence_of_element_located((By.CLASS_NAME, 'global-nav__content')))
                        frontend_bot_msg("Successfully signed in")
                        time.sleep(2)
                    except TimeoutException:
                        try:
                            notsignedin2 = WebDriverWait(web,5).until(EC.presence_of_element_located((By.NAME, "session_key")))
                            frontend_top_msg('Linkedin sign-in failed')
                            frontend_bot_msg("Linkedin log-in failure")
                            finalprint = "Linkedin log-in failure"
                        except TimeoutException:
                            try:
                                html_body = web.find_element(By.XPATH, '/html/body')
                                if "Let's do a quick security check" in html_body.text: # ERROR CODE 7-8-9 FOR CAPCHAS
                                    cf_manual_solver(web)
                                elif "Cloudflare" in html_body.text:
                                    cf_manual_solver(web)
                                elif "capcha" in html_body.text.lower():
                                    cf_manual_solver(web)
                            except Exception as e:
                                errlog(element="capcha?",description=e)
        except TimeoutException:
            try:
                notsignedin2 = WebDriverWait(web,10).until(EC.presence_of_element_located((By.NAME, "session_key")))
                if notsignedin2:
                    try:
                        start_URL2 = web.current_url
                        backup_user = web.find_element(By.NAME, "session_key")
                        bot_typer(backup_user,profile_dict['linkedin_user'])
                        time.sleep(2.56)
                        backup_pw = web.find_element(By.NAME, "session_password")
                        bot_typer(backup_pw,profile_dict['linkedin_pass'])
                        time.sleep(0.34)
                        backup_submit = web.find_element(By.XPATH, '//button[@type="submit"]')
                        backup_submit.uc_click()
                        time.sleep(2)
                        after_URL2 = web.current_url
                    except Exception as e:
                        errlog(element="backup_user?",description=e)
                        start_URL2 = "https://www.linkedin.com"
                        after_URL2 = "https://www.shyapply.com"

                    if start_URL2 == after_URL2:
                        try:
                            backup_alert = web.find_element(By.XPATH, '//input[@name="session_password"]//following-sibling::div[@role="alert"]')
                            frontend_top_msg('Linkedin sign-in failed')
                            frontend_bot_msg("Linkedin Invalid-Email/Password")
                            finalprint = "Linkedin Invalid-Email/Password"
                        except NoSuchElementException:
                            frontend_top_msg('Linkedin sign-in failed')
                            frontend_bot_msg("Linkedin log-in failure")
                            finalprint = "Linkedin log-in failure"
                    elif start_URL2 != after_URL2:
                        try:
                            element = WebDriverWait(web,10).until(EC.presence_of_element_located((By.CLASS_NAME, 'global-nav__content')))
                            frontend_bot_msg("Successfully signed in")
                            time.sleep(2)
                        except TimeoutException:
                            try:
                                html_body = web.find_element(By.XPATH, '/html/body')
                                if "Let's do a quick security check" in html_body.text:
                                    cf_manual_solver(web)
                                if "Cloudflare" in html_body.text:
                                    cf_manual_solver(web)
                            except Exception as e:
                                errlog(element="ERROR Code 7",description=e)
            except TimeoutException:
                try:
                    html_body = web.find_element(By.XPATH, '/html/body')
                    if "Let's do a quick security check" in html_body.text:
                        cf_manual_solver(web)
                    if "Cloudflare" in html_body.text:
                        cf_manual_solver(web)
                except Exception as e:
                    errlog(element="ERROR Code 7",description=e)

    def LinkedWhat_Where(x=None): # If need to remove quotes later REFER to Indeed What_Where
        frontend_bot_msg("Scanning Linkedin")

        if not x:
            try:
                topbar = web.find_element(By.CLASS_NAME, 'global-nav__content')
                jobsnavbutton = topbar.find_element(By.XPATH, './/span[@title="Jobs"]')
                jobsnavbutton.uc_click()
                time.sleep(2)
            except Exception as e:
                errlog(element="topbar",description=e)
        try:
            search_parent = web.find_element(By.XPATH, '//div[@class="jobs-search-box__inner"]')
            jobtitleinput = search_parent.find_element(By.XPATH,
                                                       '//input[@aria-label="Search by title, skill, or company"]')
            if not x:
                bot_typer_str = '"' + profile_dict['job_title'] + '"'
                bot_typer(jobtitleinput, bot_typer_str)
            else:
                bot_typer(jobtitleinput, profile_dict['job_title'])

            time.sleep(2)
            frontend_bot_msg("Scanning Linkedin.")
        except Exception as e:
            errlog(element="search_parent?",description=e)
        try:
            locationinput = search_parent.find_element(By.XPATH, '//input[@aria-label="City, state, or zip code"]')
            if profile_dict["job_remote"]==True:
                bot_typer(locationinput,"remote")
            else:
                bot_typer(locationinput,profile_dict['job_city'])
            time.sleep(1)
            locationinput.send_keys(Keys.ENTER)#there is no submit btn to change to
            time.sleep(1)
            frontend_bot_msg("Scanning Linkedin..")
        except Exception as e:
            errlog(element="locationinput",description=e)

        try:
            EzapplyfilterB1 = WebDriverWait(web,20).until(EC.element_to_be_clickable((By.XPATH, '//button[@aria-label="Easy Apply filter."]')))
            if EzapplyfilterB1:
                time.sleep(3)
                EzapplyfilterB2 = web.find_element(By.XPATH, '//button[@aria-label="Easy Apply filter."]')
                if EzapplyfilterB2.get_attribute("aria-checked") != "true":
                    EzapplyfilterB2.uc_click()
                time.sleep(3)
        except TimeoutException as e:
            errlog(element="ERROR Code 7",description=e)

        try:
            distance = WebDriverWait(web,20).until(EC.element_to_be_clickable((By.XPATH, '//button[contains(@aria-label, "Distance filter.")]')))
            if distance:
                distancefilter = web.find_element(By.XPATH, '//button[contains(@aria-label, "Distance filter.")]')
                distancefilter.uc_click()
                time.sleep(1)
                slider = web.find_element(By.ID, 'distance-filter-bar-slider')
                if slider.get_attribute("value")=="5":
                    slider.send_keys(Keys.LEFT)
                else:
                    while int(slider.get_attribute("value"))<4:
                        slider.send_keys(Keys.RIGHT)
                time.sleep(1)
                try:
                    filter_confirm = web.find_element(By.XPATH, '//button[@data-control-name="filter_show_results"]')
                    filter_confirm.uc_click()
                except Exception as e:
                    errlog(element="filter_confirm",description=e)
                time.sleep(2)
        except TimeoutException as e:
            try:
                if profile_dict['job_remote']==False:
                    errlog(severity=3,element="distance",description=e)
            except Exception as err:
                errlog(severity=2,element="profile_dict['job_remote']==False",description=err)

        frontend_bot_msg("Scanning Linkedin...")

    def LinkedIn_main():
        global LinkedIn_Job_count
        global LinkedIn_quote_bool
        global finalprint

        def Linkedfinder():#----this is the true scroll function
            try:
                footer = web.find_element(By.XPATH, "//*[contains(@class, 'global-footer')]")
                web.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center', inline: 'nearest', duration: '10000'})", footer)
            except Exception as e:
                errlog(element="footer",description=e)

        try: # THIS IS FOR CLOSING DMS TO ENSURE CLEAN UI BEFORE START
            msgboxclose = web.find_elements(By.XPATH, '//div[@role="dialog"]//descendant::button/span[text()[contains(., "Close your conversation")]]')
            if len(msgboxclose)>0:
                for msg in msgboxclose:
                    msgboxclosebtn = msg.find_element(By.XPATH, 'parent::button')
                    msgboxclosebtn.uc_click()
                    time.sleep(2)
        except Exception as e:
            errlog(element="msgboxclosebtn",description=e)

        Linkedfinder()
        time.sleep(3)

        WebDriverWait(web,20).until(EC.presence_of_element_located((By.CLASS_NAME, "job-card-container")))
        target = web.find_elements(By.CLASS_NAME, "job-card-container")

        for i in reversed(target):

            if WE_ARE_SUBMITTING:
                try:
                    response = supabase.table('subs').select('tokens').eq("id",uuid).execute()
                    response_dict = response.model_dump()
                    tokens = response_dict['data'][0]['tokens']
                    if tokens <= 0:
                        finalprint = "Not enough tokens!"
                        frontend_top_msg("Shy Apply stopped.")
                        frontend_bot_msg("Not enough tokens!")
                        try:
                            sys.exit()
                        except Exception:
                            try:
                                web.quit()
                            except Exception:
                                pass
                except Exception as e:
                    errlog(element="LinkedIn_main() supabase",description=e)
                    supa_retry("ping")

                check_if_running()

            try:
                frontend_top_msg("Found Opportunity!")
                frontend_bot_msg("Reading job description..")
            except Exception as e:
                errlog(element="emergency_log", log="emergency_log is broken", description=e)

            time.sleep(2)
            i.uc_click()
            time.sleep(2)
            try:
                company_details = i.find_element(By.XPATH, "./descendant::span[contains(@class, 'primary-description')]")
                jobtext = company_details.text
            except Exception as e:
                errlog(element="company_details",description=e)
            try:
                ezapplyBtns = web.find_elements(By.XPATH, '//button[contains(@aria-label, "Easy Apply to")]')
                ezapplyB = [btn for btn in ezapplyBtns if "Easy Apply" in btn.text]
                if len(ezapplyB)>0:
                    try:
                        ezapplyB[0].uc_click()
                    except Exception as e:
                        errlog(element="ezapplyBtns",description=e)
                elif len(ezapplyB)==0:
                    continue
            except Exception as e:
                errlog(element="ezapplyBtns",description=e)
                continue

            try:
                safety_reminder = WebDriverWait(web,5).until(EC.presence_of_element_located((By.XPATH, '//h2[@id="header" and contains(text(), "Job search safety reminder")]')))
                try:
                    safety_cont_btn = web.find_element(By.XPATH, '//button[contains(@aria-label, "Easy Apply to")]//ancestor::div[@class="jobs-s-apply"]')
                    safety_cont_btn.uc_click()
                    time.sleep(1)
                except Exception as e:
                    errlog(element="safety_cont_btn", description=e)
                    close_button = web.find_element(By.XPATH, '//button[@aria-label="Dismiss"]')
                    close_button.uc_click()
                    time.sleep(1)
                    continue
            except TimeoutException:
                pass

            try:
                WebDriverWait(web,10).until(EC.presence_of_element_located((By.XPATH, '//h2[@id="jobs-apply-header"]')))
                time.sleep(1)
            except TimeoutException as e:
                errlog(element="jobs-apply-header",description=e)
                pass
            try:
                if len(jobtext) > 30:
                    truncated_text = "Applying: "+ jobtext[:30] + "..."
                    frontend_top_msg(truncated_text)
                else:
                    emergency_logtext = "Applying: "+jobtext
                    frontend_top_msg(emergency_logtext)
            except Exception as e:
                errlog(element="truncated_text",description=e)
                frontend_top_msg(str(profile_dict['job_title']))
            LinkedIn_ansfind()
            if WE_ARE_SUBMITTING:
                try:
                    aftermsg = WebDriverWait(web,5).until(EC.presence_of_element_located((By.XPATH, '//button[@aria-label="Dismiss"]'))) # This could be stronger
                    if aftermsg:
                        time.sleep(4)
                        close_button = web.find_element(By.XPATH, '//button[@aria-label="Dismiss"]')
                        close_button.uc_click()
                        LinkedIn_Job_count+=1
                        frontend_bot_msg("Application submitted")
                        try:
                            application_success_log(jobtext)
                        except Exception as e:
                            errlog(element="jobtext", description=e, log="could not find jobtext")
                        if WE_ARE_SUBMITTING:
                            tokens_minus_one = tokens - 1
                            try:
                                supabase.table('subs').update({'tokens': tokens_minus_one}).eq("id",uuid).execute()
                            except Exception:
                                supa_retry("update")
                            time.sleep(2)
                            frontend_top_msg("Searching for best Listing")
                            barrens_chat("Scanning Linkedin", 950)
                except (TimeoutException, ElementNotInteractableException) as e:
                    errlog(element="aftermsg",description=e)
            else:
                LinkedIn_Job_count+=1
            if LinkedIn_Job_count >= num_apps:
                break
        if LinkedIn_Job_count < num_apps:
            try:
                current_page = web.find_element(By.XPATH, '//li[contains(@class, "number active selected")]')
                nextpage_count = int(current_page.text) + 1
            except Exception as e:
                errlog(element="current_page",description=e)
            try:
                next_numpage = web.find_element(By.XPATH, "//button[@aria-label='Page {}']".format(nextpage_count))
                time.sleep(3)
                next_numpage.uc_click()
                time.sleep(3)
                LinkedIn_main()
            except NoSuchElementException:
                # print("Error - next_numpage fail...aborting")
                if LinkedIn_quote_bool == True:
                    LinkedWhat_Where("no quotes")
                    time.sleep(5)
                    LinkedIn_quote_bool = False
                    LinkedIn_main()
                else:
                    LinkedIn_Job_count=num_apps

    global LinkedIn_Job_count
    global LinkedIn_quote_bool
    LinkedIn_Job_count = 0
    LinkedIn_quote_bool = True

    try:
        web.get("https://www.linkedin.com/")
        time.sleep(5)
        check_if_running()
        Linkedin_signin()
    except Exception as e:
        errlog(element="outer Linkedin_signin()",description=e)

    try:
        element = WebDriverWait(web,20).until(EC.presence_of_element_located((By.CLASS_NAME, 'global-nav__content')))
        if element:
            LinkedWhat_Where()
            try:
                set_last_run()
            except Exception:
                pass
    except TimeoutException as e:
        errlog(element="outer LinkedWhat_Where()",description=e)

    try:
        jobcontainerfind = WebDriverWait(web,20).until(EC.presence_of_element_located((By.CLASS_NAME, "job-card-container")))
        if jobcontainerfind:
            LinkedIn_main()
    except TimeoutException as e:
        errlog(element="outer jobcontainerfind",description=e)
    # print("Final LinkedIn job_count = "+str(LinkedIn_Job_count))
    return LinkedIn_Job_count

LinkedIn_resume_container.update({"resume": choice_resumepath})

education_levels = {
    1: "High School",
    2: "GED",
    3: "High School",
    4: "Associates",
    5: "Associates",
    6: "Bachelors",
    7: "Masters",
    8: "Doctoral"
}

edu_level = profile_dict['edu_level']
LinkedIn_select_check.update({"What is the highest level of education you have completed?": education_levels[edu_level]})

try:
    if os_name() == 'win':
        userdata = profile_dict["shy_dir"] + "\\browser"
    elif os_name() == 'mac':
        userdata = profile_dict["shy_dir"] + "/browser"

    try:
        proc_list = []
        for proc in psutil.process_iter():
            if platform_proc_name in proc.name().lower():
                proc_list.append("shyapply")
                break
        if len(proc_list) > 0:
            if WE_ARE_SUBMITTING:
                if not is_process_stopped():
                    web = Driver(browser='chrome', uc=True, user_data_dir=userdata, headless=True, headed=False) # headless=True, headed=True -> for Linux
                else:
                    finalprint = 'Red button pressed. Shy Apply Stopped!'
                    frontend_bot_msg(finalprint)
                    sys.exit()
            else:
                web = Driver(browser='chrome', uc=True, user_data_dir=userdata, headless=False, headed=True) # headless=True, headed=True -> for Linux

            web.set_window_size(1920, 1080)
        elif len(proc_list) == 0:
            sys.exit()
    except Exception as e:
        errlog(element="web",description=e, log='probably client closed prior to driver start')

    website_init = []
    if profile_dict["linkedin"] == True:
        website_init.append("LinkedIn")
    if profile_dict["ziprecruiter"] == True:
        website_init.append("ZipRecruiter")
    if profile_dict["glassdoor"] == True:
        website_init.append("Glassdoor")
    if profile_dict["indeed"] == True:
        website_init.append("Indeed")

    for site in website_init:
    # Other websites were removed for this showcase.
        if WE_ARE_SUBMITTING:
            try:
                response = supabase.table('subs').select('tokens').eq("id",uuid).execute()
                response_dict = response.model_dump()
                tokens = response_dict['data'][0]['tokens']
                if tokens <= 0:
                    finalprint = "Not enough tokens!"
                    frontend_top_msg("Shy Apply stopped.")
                    frontend_bot_msg("Not enough tokens!")
                    sys.exit()
            except Exception as e:
                errlog(element="response",description=e)
                supa_retry("ping")

        if site == "LinkedIn":
            try:
                proc_list = []
                for proc in psutil.process_iter():
                    if platform_proc_name in proc.name().lower():
                        proc_list.append("shyapply")
                        break
                if len(proc_list) > 0:
                    if is_process_stopped() == False:
                        frontend_top_msg("Initializing LinkedIn...")
                        LinkedIn_Driver(web)
            except Exception as e:
                errlog(element="linkedin website_init",description=e)

finally:
    # Final logging occurs here. Logging is not in the moment but pooled together and handled here in one lump sum.
    # errlog function crafts and stores sql queries in logslist and then executed below.
    if len(logslist) != 0:
        try:
            if WE_ARE_SUBMITTING:
                db = sqlite3.connect(r'{}'.format(args.path))
            else:
                db = sqlite3.connect(os.path.join(profile_dict['shy_dir'], 'shyapply.db'))
            db.row_factory = sqlite3.Row
            db_cursor = db.cursor()
            for log in logslist:
                db_cursor.execute(log)
                db.commit()
            db.close()
        except Exception:
            pass

    if WE_ARE_SUBMITTING:
        try:
            web.quit()
        except Exception:
            pass

        # Safety Precaution to kill ghost processes.
        # This has never happened with Seleniumbase and is borderline deprecated.
        term_proc_list = ['chromedriver', 'uc_driver', 'shy_drivers', 'odetodionysus']
        for proc in psutil.process_iter():
            try:
                if "chrome" in proc.name().lower():
                    try:
                        process_info = psutil.Process(proc.pid).cmdline()
                        if os_name() == 'win':
                            if '--user-data-dir=' + profile_dict["shy_dir"] + "\\browser" in process_info:
                                proc.kill()
                        elif os_name() == 'mac':
                            if '--user-data-dir=' + profile_dict["shy_dir"] + "/browser" in process_info:
                                proc.kill()
                    except (NoSuchProcess, ProcessLookupError, AccessDenied):
                        pass
            except (NoSuchProcess, ProcessLookupError, AccessDenied):
                pass
            try:
                if any(word in proc.name().lower() for word in term_proc_list):
                    try:
                        proc.kill()
                    except (NoSuchProcess,ProcessLookupError, AccessDenied):
                        pass
            except (NoSuchProcess, ProcessLookupError, AccessDenied):
                pass

    else:
        # Pauses script on error or completion during End-to-End Test for easy debug
        print("Enter to EXIT")
        x = input()
        try:
            web.quit()
        except Exception:
            pass

    try:
        frontend_top_msg("Shy Apply finished.")
        frontend_bot_msg(finalprint)
    except Exception:
        pass
