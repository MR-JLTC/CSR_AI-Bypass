import os
import sys
import json
import requests
import sqlite3
from typing import Dict, Optional
import platform
from colorama import Fore, Style, init
import logging
import re
import traceback

try:
    from check_user_authorized import generate_cursor_checksum
except ImportError:
    generate_cursor_checksum = None

# Initialize colorama
init()

# Setup logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define emoji constants
EMOJI = {
    "USER": "👤",
    "USAGE": "📊",
    "PREMIUM": "⭐",
    "BASIC": "📝",
    "SUBSCRIPTION": "💳",
    "INFO": "ℹ️",
    "ERROR": "❌",
    "SUCCESS": "✅",
    "WARNING": "⚠️",
    "TIME": "🕒",
    "RESET": "🔄"
}

# Dummy get_config and get_display_width (Keep these for compatibility if needed by other parts of the system)
def get_config(translator=None):
    # Dummy implementation for compatibility
    return {"proxy": None}

def get_display_width(text):
    # Handles basic ANSI color codes (simplified, assumes no complex unicode/bidi)
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    return len(text)

class Config:
    """Config"""
    NAME_LOWER = "cursor"
    NAME_CAPITALIZE = "Cursor"
    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

class UsageManager:
    """Usage Manager"""
    
    @staticmethod
    def get_proxy():
        """get proxy"""
        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
        if proxy:
            return {"http": proxy, "https": proxy}
        return None

    @staticmethod
    def get_storage_path() -> Optional[str]:
        """Get the path to storage.json based on OS. FIXES 'token_not_found' error."""
        system = platform.system()
        # Get actual user's home directory (especially important for sudo/frozen executables)
        if sys.platform == "linux" and os.environ.get('SUDO_USER'):
            actual_home = os.path.join("/home", os.environ['SUDO_USER'])
        else:
            actual_home = os.path.expanduser("~")
            
        if system == "Windows":
            # Windows path: %APPDATA%\Cursor\User\globalStorage\storage.json
            appdata = os.getenv("APPDATA", "")
            if not appdata:
                logger.error("APPDATA environment variable not found on Windows.")
                return None
            return os.path.join(appdata, "Cursor", "User", "globalStorage", "storage.json")
        elif system == "Darwin":
            # macOS path: ~/Library/Application Support/Cursor/User/globalStorage/storage.json
            return os.path.join(actual_home, "Library", "Application Support", "Cursor", "User", "globalStorage", "storage.json")
        elif system == "Linux":
            # Linux path: ~/.config/cursor/User/globalStorage/storage.json
            return os.path.join(actual_home, ".config", "cursor", "User", "globalStorage", "storage.json")
        return None
        
    @staticmethod
    def get_cursor_session_token(translator=None) -> Optional[str]:
        """
        Get Cursor session token (WorkosSessionToken) from storage.json.
        """
        logger.info("Attempting to retrieve Cursor session token.")
        storage_path = UsageManager.get_storage_path()
            
        if not storage_path or not os.path.exists(storage_path):
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('info.storage_not_found') if translator else 'Storage file not found'}: {storage_path}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{EMOJI['WARNING']} Please ensure you have run Cursor at least once.{Style.RESET_ALL}")
            return None

        try:
            with open(storage_path, "r", encoding="utf-8") as f:
                storage_data = json.load(f)

            # The key is case-sensitive: 'cursorAuth/WorkosSessionToken'
            token = storage_data.get('cursorAuth/WorkosSessionToken')

            if token:
                logger.info("Session token retrieved successfully.")
                return token
            else:
                print(f"{Fore.YELLOW}{EMOJI['WARNING']} {translator.get('info.token_not_found') if translator else 'WorkosSessionToken not found in storage.json.'}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}{EMOJI['WARNING']} Make sure you are **logged into the Cursor application** and try again.{Style.RESET_ALL}")
                return None

        except json.JSONDecodeError:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('info.read_token_error') if translator else 'Error reading token: storage.json is corrupted or unreadable.'}{Style.RESET_ALL}")
            return None
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('info.read_token_error') if translator else 'Error reading token'}: {str(e)}{Style.RESET_ALL}")
            return None

    @staticmethod
    def get_usage(token: str) -> Optional[Dict]:
        """get usage. FIXES '401 Unauthorized' by using Cookie header."""
        url = f"https://www.{Config.NAME_LOWER}.com/api/usage"
        headers = Config.BASE_HEADERS.copy()
        
        # The /api/usage endpoint typically requires the token as a cookie.
        # This fixes the 401 error.
        cookie_value = f"Workos{Config.NAME_CAPITALIZE}SessionToken={token}"
        headers.update({"Cookie": cookie_value})
        
        try:
            proxies = UsageManager.get_proxy()
            response = requests.get(url, headers=headers, timeout=10, proxies=proxies)
            response.raise_for_status()
            data = response.json()
            
            # get Premium usage and limit
            gpt4_data = data.get("gpt-4", {})
            premium_usage = gpt4_data.get("numRequestsTotal", 0)
            max_premium_usage = gpt4_data.get("maxRequestUsage", 999)
            
            # get Basic usage, but set limit to "No Limit"
            gpt35_data = data.get("gpt-3.5-turbo", {})
            basic_usage = gpt35_data.get("numRequestsTotal", 0)
            
            return {
                'premium_usage': premium_usage, 
                'max_premium_usage': max_premium_usage, 
                'basic_usage': basic_usage, 
                'max_basic_usage': "No Limit"  # set Basic limit to "No Limit"
            }
        except requests.RequestException as e:
            logger.error(f"Get usage info failed: {str(e)}")
            return None
        except Exception as e:
            # catch all other exceptions
            logger.error(f"Get usage info failed: {str(e)}")
            return None

    @staticmethod
    def get_subscription_info(token: str) -> Optional[Dict]:
        """Get user subscription information."""
        url = f"https://www.{Config.NAME_LOWER}.com/api/user"
        headers = Config.BASE_HEADERS.copy()
        
        cookie_value = f"Workos{Config.NAME_CAPITALIZE}SessionToken={token}"
        headers.update({"Cookie": cookie_value})
        
        try:
            proxies = UsageManager.get_proxy()
            response = requests.get(url, headers=headers, timeout=10, proxies=proxies)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Get subscription info failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Get subscription info failed: {str(e)}")
            return None

    @staticmethod
    def reset_server_usage(translator=None) -> bool:
        """
        Attempts to reset the server-side usage limit using the session token.
        This relies on an undocumented/reverse-engineered API endpoint.
        """
        token = get_token()  # Use the global get_token function
        if not token:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.no_token_available') if translator else 'Cannot perform server-side reset without a session token. Please ensure you are logged in.'}{Style.RESET_ALL}")
            return False

        if not generate_cursor_checksum:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.checksum_function_not_found') if translator else 'Checksum generation function not found. Cannot proceed.'}{Style.RESET_ALL}")
            return False

        # New API endpoint and headers based on check_user_authorized.py
        API_URL = "https://api2.cursor.sh/aiserver.v1.DashboardService/ResetUsageTrial"
        checksum = generate_cursor_checksum(token, translator)

        headers = {
            'accept-encoding': 'gzip',
            'authorization': f'Bearer {token}',
            'connect-protocol-version': '1',
            'content-type': 'application/proto',
            'user-agent': 'connect-es/1.6.1',
            'x-cursor-checksum': checksum,
            'x-cursor-client-version': '0.48.7', # This might need updating in the future
            'x-cursor-timezone': 'Asia/Shanghai', # This can be generalized if needed
            'x-ghost-mode': 'false',
            'Host': 'api2.cursor.sh'
        }

        print(f"\n{Fore.CYAN}{EMOJI['RESET']} {translator.get('reset.attempting_server_reset') if translator else 'Attempting server-side usage reset...'}{Style.RESET_ALL}")
        
        try:
            response = requests.post(API_URL, headers=headers, data=b'', proxies=UsageManager.get_proxy(), timeout=15)

            if response.status_code == 200 or response.status_code == 204:
                print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {translator.get('reset.server_reset_success') if translator else 'Server usage reset request successful. You MUST restart Cursor for changes to fully apply.'}{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.server_reset_failed') if translator else 'Server usage reset request failed.'}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}{EMOJI['INFO']} Status: {response.status_code}. Response: {response.text[:100]}{Style.RESET_ALL}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.connection_error') if translator else 'Connection error during server reset attempt'}: {str(e)}{Style.RESET_ALL}")
            return False

def get_token_from_config():
    """get path info from config"""
    try:
        from config import get_config
        config = get_config()
        if not config:
            return None
            
        system = platform.system()
        if system == "Windows" and config.has_section('WindowsPaths'):
            return {
                'storage_path': config.get('WindowsPaths', 'storage_path'),
                'sqlite_path': config.get('WindowsPaths', 'sqlite_path'),
                'session_path': os.path.join(os.getenv("APPDATA"), "Cursor", "Session Storage")
            }
        elif system == "Darwin" and config.has_section('MacPaths'):  # macOS
            return {
                'storage_path': config.get('MacPaths', 'storage_path'),
                'sqlite_path': config.get('MacPaths', 'sqlite_path'),
                'session_path': os.path.expanduser("~/Library/Application Support/Cursor/Session Storage")
            }
        elif system == "Linux" and config.has_section('LinuxPaths'):
            return {
                'storage_path': config.get('LinuxPaths', 'storage_path'),
                'sqlite_path': config.get('LinuxPaths', 'sqlite_path'),
                'session_path': os.path.expanduser("~/.config/Cursor/Session Storage")
            }
    except Exception as e:
        logger.error(f"Get config path failed: {str(e)}")
    
    return None

def get_token_from_storage(storage_path):
    """get token from storage.json"""
    if not os.path.exists(storage_path):
        return None
        
    try:
        with open(storage_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # try to get accessToken
            if 'cursorAuth/accessToken' in data:
                return data['cursorAuth/accessToken']
            
            # try other possible keys
            for key in data:
                if 'token' in key.lower() and isinstance(data[key], str) and len(data[key]) > 20:
                    return data[key]
    except Exception as e:
        logger.error(f"get token from storage.json failed: {str(e)}")
    
    return None

def get_token_from_sqlite(sqlite_path):
    """get token from sqlite"""
    if not os.path.exists(sqlite_path):
        return None
        
    try:
        conn = sqlite3.connect(sqlite_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM ItemTable WHERE key LIKE '%token%'")
        rows = cursor.fetchall()
        conn.close()
        
        for row in rows:
            try:
                value = row[0]
                if isinstance(value, str) and len(value) > 20:
                    return value
                # try to parse JSON
                data = json.loads(value)
                if isinstance(data, dict) and 'token' in data:
                    return data['token']
            except:
                continue
    except Exception as e:
        logger.error(f"get token from sqlite failed: {str(e)}")
    
    return None

def get_token_from_session(session_path):
    """get token from session"""
    if not os.path.exists(session_path):
        return None
        
    try:
        # try to find all possible session files
        for file in os.listdir(session_path):
            if file.endswith('.log'):
                file_path = os.path.join(session_path, file)
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        # find token pattern
                        token_match = re.search(r'"token":"([^"]+)"', content)
                        if token_match:
                            return token_match.group(1)
                except:
                    continue
    except Exception as e:
        logger.error(f"get token from session failed: {str(e)}")
    
    return None

def get_token():
    """get Cursor token"""
    # get path from config
    paths = get_token_from_config()
    if not paths:
        return None
    
    # try to get token from different locations
    token = get_token_from_storage(paths['storage_path'])
    if token:
        return token
        
    token = get_token_from_sqlite(paths['sqlite_path'])
    if token:
        return token
        
    token = get_token_from_session(paths['session_path'])
    if token:
        return token
    
    return None

def format_subscription_type(subscription_data: Dict) -> str:
    """format subscription type"""
    if not subscription_data:
        return "Free"
    
    # handle new API response format
    if "membershipType" in subscription_data:
        membership_type = subscription_data.get("membershipType", "").lower()
        subscription_status = subscription_data.get("subscriptionStatus", "").lower()
        
        if subscription_status == "active":
            if membership_type == "pro":
                return "Pro"
            elif membership_type == "free_trial":
                return "Free Trial"
            elif membership_type == "pro_trial":
                return "Pro Trial"
            elif membership_type == "team":
                return "Team"
            elif membership_type == "enterprise":
                return "Enterprise"
            elif membership_type:
                return membership_type.capitalize()
            else:
                return "Active Subscription"
        elif subscription_status:
            return f"{membership_type.capitalize()} ({subscription_status})"
    
    # compatible with old API response format
    subscription = subscription_data.get("subscription")
    if subscription:
        plan = subscription.get("plan", {}).get("nickname", "Unknown")
        status = subscription.get("status", "unknown")
        
        if status == "active":
            if "pro" in plan.lower():
                return "Pro"
            elif "pro_trial" in plan.lower():
                return "Pro Trial"
            elif "free_trial" in plan.lower():
                return "Free Trial"
            elif "team" in plan.lower():
                return "Team"
            elif "enterprise" in plan.lower():
                return "Enterprise"
            else:
                return plan
        else:
            return f"{plan} ({status})"
    
    return "Free"

def get_email_from_storage(storage_path):
    """get email from storage.json"""
    if not os.path.exists(storage_path):
        return None
        
    try:
        with open(storage_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # try to get email
            if 'cursorAuth/cachedEmail' in data:
                return data['cursorAuth/cachedEmail']
            
            # try other possible keys
            for key in data:
                if 'email' in key.lower() and isinstance(data[key], str) and '@' in data[key]:
                    return data[key]
    except Exception as e:
        logger.error(f"get email from storage.json failed: {str(e)}")
    
    return None

def get_email_from_sqlite(sqlite_path):
    """get email from sqlite"""
    if not os.path.exists(sqlite_path):
        return None
        
    try:
        conn = sqlite3.connect(sqlite_path)
        cursor = conn.cursor()
        # try to query records containing email
        cursor.execute("SELECT value FROM ItemTable WHERE key LIKE '%email%' OR key LIKE '%cursorAuth%'")
        rows = cursor.fetchall()
        conn.close()
        
        for row in rows:
            try:
                value = row[0]
                # if it's a string and contains @, it might be an email
                if isinstance(value, str) and '@' in value:
                    return value
                
                # try to parse JSON
                try:
                    data = json.loads(value)
                    if isinstance(data, dict):
                        # check if there's an email field
                        if 'email' in data:
                            return data['email']
                        # check if there's a cachedEmail field
                        if 'cachedEmail' in data:
                            return data['cachedEmail']
                except:
                    pass
            except:
                continue
    except Exception as e:
        logger.error(f"get email from sqlite failed: {str(e)}")
    
    return None

def display_account_info(translator=None):
    """display account info"""
    print(f"\n{Fore.CYAN}{'─' * 70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{EMOJI['USER']} {translator.get('account_info.title') if translator else 'Cursor Account Information'}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'─' * 70}{Style.RESET_ALL}")
    
    # get token
    token = get_token()
    if not token:
        print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('account_info.token_not_found') if translator else 'Token not found. Please login to Cursor first.'}{Style.RESET_ALL}")
        return
    
    # get path info
    paths = get_token_from_config()
    if not paths:
        print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('account_info.config_not_found') if translator else 'Configuration not found.'}{Style.RESET_ALL}")
        return
    
    # get email info - try multiple sources
    email = get_email_from_storage(paths['storage_path'])
    
    # if not found in storage, try from sqlite
    if not email:
        email = get_email_from_sqlite(paths['sqlite_path'])
    
    # get subscription info
    subscription_info = UsageManager.get_subscription_info(token)
    
    # if not found in storage and sqlite, try from subscription info
    if not email and subscription_info:
        # try to get email from subscription info
        if 'customer' in subscription_info and 'email' in subscription_info['customer']:
            email = subscription_info['customer']['email']
    
    # get usage info - silently handle errors
    try:
        usage_info = UsageManager.get_usage(token)
    except Exception as e:
        logger.error(f"Get usage info failed: {str(e)}")
        usage_info = None
    
    # Prepare left and right info
    left_info = []
    right_info = []
    
    # Left side shows account info
    if email:
        left_info.append(f"{Fore.GREEN}{EMOJI['USER']} {translator.get('account_info.email') if translator else 'Email'}: {Fore.WHITE}{email}{Style.RESET_ALL}")
    else:
        left_info.append(f"{Fore.YELLOW}{EMOJI['WARNING']} {translator.get('account_info.email_not_found') if translator else 'Email not found'}{Style.RESET_ALL}")
    
    # Add an empty line
    # left_info.append("")
    
    # Show subscription type
    if subscription_info:
        subscription_type = format_subscription_type(subscription_info)
        left_info.append(f"{Fore.GREEN}{EMOJI['SUBSCRIPTION']} {translator.get('account_info.subscription') if translator else 'Subscription'}: {Fore.WHITE}{subscription_type}{Style.RESET_ALL}")
        
        # Show remaining trial days
        days_remaining = subscription_info.get("daysRemainingOnTrial")
        if days_remaining is not None and days_remaining > 0:
            left_info.append(f"{Fore.GREEN}{EMOJI['TIME']} {translator.get('account_info.trial_remaining') if translator else 'Remaining Pro Trial'}: {Fore.WHITE}{days_remaining} {translator.get('account_info.days') if translator else 'days'}{Style.RESET_ALL}")
    else:
        left_info.append(f"{Fore.YELLOW}{EMOJI['WARNING']} {translator.get('account_info.subscription_not_found') if translator else 'Subscription information not found'}{Style.RESET_ALL}")
    
    # Right side shows usage info - only if available
    if usage_info:
        right_info.append(f"{Fore.GREEN}{EMOJI['USAGE']} {translator.get('account_info.usage') if translator else 'Usage Statistics'}:{Style.RESET_ALL}")
        
        # Premium usage
        premium_usage = usage_info.get('premium_usage', 0)
        max_premium_usage = usage_info.get('max_premium_usage', "No Limit")
        
        #  make sure the value is not None
        if premium_usage is None:
            premium_usage = 0
        
        # handle "No Limit" case
        if isinstance(max_premium_usage, str) and max_premium_usage == "No Limit":
            premium_color = Fore.GREEN  # when there is no limit, use green
            premium_display = f"{premium_usage}/{max_premium_usage}"
        else:
            # calculate percentage when the value is a number
            if max_premium_usage is None or max_premium_usage == 0:
                max_premium_usage = 999
                premium_percentage = 0
            else:
                premium_percentage = (premium_usage / max_premium_usage) * 100
            
            # select color based on usage percentage
            premium_color = Fore.GREEN
            if premium_percentage > 70:
                premium_color = Fore.YELLOW
            if premium_percentage > 90:
                premium_color = Fore.RED
            
            premium_display = f"{premium_usage}/{max_premium_usage} ({premium_percentage:.1f}%)"
        
        right_info.append(f"{Fore.YELLOW}{EMOJI['PREMIUM']} {translator.get('account_info.premium_usage') if translator else 'Fast Response'}: {premium_color}{premium_display}{Style.RESET_ALL}")
        
        # Slow Response
        basic_usage = usage_info.get('basic_usage', 0)
        max_basic_usage = usage_info.get('max_basic_usage', "No Limit")
        
        # make sure the value is not None
        if basic_usage is None:
            basic_usage = 0
        
        # handle "No Limit" case
        if isinstance(max_basic_usage, str) and max_basic_usage == "No Limit":
            basic_color = Fore.GREEN  # when there is no limit, use green
            basic_display = f"{basic_usage}/{max_basic_usage}"
        else:
            # calculate percentage when the value is a number
            if max_basic_usage is None or max_basic_usage == 0:
                max_basic_usage = 999
                basic_percentage = 0
            else:
                basic_percentage = (basic_usage / max_basic_usage) * 100
            
            # select color based on usage percentage
            basic_color = Fore.GREEN
            if basic_percentage > 70:
                basic_color = Fore.YELLOW
            if basic_percentage > 90:
                basic_color = Fore.RED
            
            basic_display = f"{basic_usage}/{max_basic_usage} ({basic_percentage:.1f}%)"
        
        right_info.append(f"{Fore.BLUE}{EMOJI['BASIC']} {translator.get('account_info.basic_usage') if translator else 'Slow Response'}: {basic_color}{basic_display}{Style.RESET_ALL}")
    else:
        # if get usage info failed, only log in log, not show in interface
        # you can choose to not show any usage info, or show a simple prompt
        # right_info.append(f"{Fore.YELLOW}{EMOJI['INFO']} {translator.get('account_info.usage_unavailable') if translator else 'Usage information unavailable'}{Style.RESET_ALL}")
        pass  # not show any usage info
    
    # Calculate the maximum display width of left info
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    def get_display_width(s):
        """Calculate the display width of a string, considering Chinese characters and emojis"""
        # Remove ANSI color codes
        clean_s = ansi_escape.sub('', s)
        width = 0
        for c in clean_s:
            # Chinese characters and some emojis occupy two character widths
            if ord(c) > 127:
                width += 2
            else:
                width += 1
        return width
    
    max_left_width = 0
    for item in left_info:
        width = get_display_width(item)
        max_left_width = max(max_left_width, width)
    
    # Set the starting position of right info
    fixed_spacing = 4  # Fixed spacing
    right_start = max_left_width + fixed_spacing
    
    # Calculate the number of spaces needed for right info
    spaces_list = []
    for i in range(len(left_info)):
        if i < len(left_info):
            left_item = left_info[i]
            left_width = get_display_width(left_item)
            spaces = right_start - left_width
            spaces_list.append(spaces)
    
    # Print info
    max_rows = max(len(left_info), len(right_info))
    
    for i in range(max_rows):
        # Print left info
        if i < len(left_info):
            left_item = left_info[i]
            print(left_item, end='')
            
            # Use pre-calculated spaces
            spaces = spaces_list[i]
        else:
            # If left side has no items, print only spaces
            spaces = right_start
            print('', end='')
        
        # Print right info
        if i < len(right_info):
            print(' ' * spaces + right_info[i])
        else:
            print()  # Change line
    
    print(f"{Fore.CYAN}{'─' * 70}{Style.RESET_ALL}")

def main(translator=None):
    """main function"""
    try:
        display_account_info(translator)
        # Add an option to run the new reset feature if run standalone
        if __name__ == "__main__":
             print(f"\n{Fore.CYAN}{EMOJI['RESET']} Test Server Usage Reset{Style.RESET_ALL}")
             UsageManager.reset_server_usage(translator)
    except Exception as e:
        print(f"{Fore.RED}{EMOJI['ERROR']} An error occurred: {e}{Style.RESET_ALL}")
        print(traceback.format_exc())

if __name__ == "__main__":
    # Create a minimal translator object for testing if run directly
    class MinimalTranslator:
        def get(self, key, **kwargs):
            # Simplified translation/string replacement
            messages = {
                'info.storage_not_found': 'Storage file not found',
                'info.token_not_found': 'WorkosSessionToken not found in storage.json. Are you logged in?',
                'info.read_token_error': 'Error reading token',
                'reset.no_token_available': 'Cannot perform server-side reset without a session token. Please ensure you are logged in.',
                'reset.attempting_server_reset': 'Attempting server-side usage reset with session token...',
                'reset.server_reset_success': 'Server usage reset request successful (Status 200/204). You MUST restart Cursor for changes to fully apply.',
                'reset.server_reset_failed': 'Server usage reset request failed.',
                'reset.connection_error': 'Connection error during server reset attempt',
                'reset.workos_token_not_found': 'WorkosSessionToken not found. Attempting to find a general token...',
                'reset.checksum_function_not_found': 'Checksum generation function not found. Cannot proceed.',
                'info.user_account': 'User Account Information'
            }
            msg = messages.get(key, f"<{key}>")
            return msg.format(**kwargs)

    main(MinimalTranslator())