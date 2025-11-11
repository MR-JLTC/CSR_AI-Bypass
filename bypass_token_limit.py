import os
import shutil
import platform
import tempfile
import glob
from colorama import Fore, Style, init
import configparser
import sys
from config import get_config
from datetime import datetime

# Initialize colorama
init()

# Define emoji constants
EMOJI = {
    "FILE": "📄",
    "BACKUP": "💾",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "INFO": "ℹ️",
    "RESET": "🔄",
    "WARNING": "⚠️",
}

def get_user_documents_path():
     """Get user Documents folder path"""
     if sys.platform == "win32":
         try:
             import winreg
             with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders") as key:
                 documents_path, _ = winreg.QueryValueEx(key, "Personal")
                 return documents_path
         except Exception as e:
             # fallback
             return os.path.join(os.path.expanduser("~"), "Documents")
     elif sys.platform == "darwin":
         return os.path.join(os.path.expanduser("~"), "Documents")
     else:  # Linux
         # Get actual user's home directory
         sudo_user = os.environ.get('SUDO_USER')
         if sudo_user:
             return os.path.join("/home", sudo_user, "Documents")
         return os.path.join(os.path.expanduser("~"), "Documents")
     

def get_workbench_cursor_path(translator=None) -> str:
    """Search for all workbench.desktop.main.js files and let the user choose one."""
    filename = "workbench.desktop.main.js"
    system = platform.system()
    found_paths = []

    print(f"{Fore.CYAN}{EMOJI['INFO']} Searching for {filename}...{Style.RESET_ALL}")

    # --- Windows paths ---
    if system == "Windows":
        user = os.environ.get("USERNAME", "")
        search_paths = [
            os.path.join("C:\\Users", user, "Desktop"),  # your detected paths are here
            os.path.join("C:\\Users", user, "AppData", "Local", "Programs"),
            os.path.join("C:\\Users", user, "AppData", "Local"),
            "C:\\Program Files",
            "C:\\Program Files (x86)"
        ]
    elif system == "Darwin":  # macOS
        search_paths = ["/Applications/Cursor.app/Contents/Resources/app"]
    elif system == "Linux":
        search_paths = [
            "/opt/Cursor/resources/app",
            "/usr/share/cursor/resources/app",
            "/usr/lib/cursor/app/",
            os.path.expanduser("~/squashfs-root/usr/share/cursor/resources/app")
        ]
    else:
        raise OSError(f"Unsupported OS: {system}")

    # Search recursively
    for base in search_paths:
        if os.path.exists(base):
            for root, dirs, files in os.walk(base):
                if filename in files:
                    path = os.path.join(root, filename)
                    found_paths.append(path)
                    print(f"{Fore.GREEN}{EMOJI['SUCCESS']} Found: {path}{Style.RESET_ALL}")

    # If none found
    if not found_paths:
        print(f"{Fore.RED}{EMOJI['ERROR']} Could not locate {filename} anywhere.{Style.RESET_ALL}")
        raise FileNotFoundError(filename)

    # If multiple found, ask user to choose
    if len(found_paths) > 1:
        print(f"\n{Fore.CYAN}Multiple files found:{Style.RESET_ALL}")
        for i, p in enumerate(found_paths):
            print(f"  [{i+1}] {p}")
        choice = input(f"\n{Fore.YELLOW}Select the file to modify (1-{len(found_paths)}): {Style.RESET_ALL}")
        try:
            index = int(choice) - 1
            if 0 <= index < len(found_paths):
                return found_paths[index]
        except ValueError:
            pass
        print(f"{Fore.RED}{EMOJI['ERROR']} Invalid selection. Using first file by default.{Style.RESET_ALL}")
    
    return found_paths[0]



def modify_workbench_js(file_path: str, translator=None) -> bool:
    """
    Modify file content
    """
    try:
        # Save original file permissions
        original_stat = os.stat(file_path)
        original_mode = original_stat.st_mode
        original_uid = original_stat.st_uid
        original_gid = original_stat.st_gid

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", errors="ignore", delete=False) as tmp_file:
            # Read original content
            with open(file_path, "r", encoding="utf-8", errors="ignore") as main_file:
                content = main_file.read()

            patterns = {
                # 通用按钮替换模式
                r'B(k,D(Ln,{title:"Upgrade to Pro",size:"small",get codicon(){return A.rocket},get onClick(){return t.pay}}),null)': r'B(k,D(Ln,{title:"yeongpin GitHub",size:"small",get codicon(){return A.github},get onClick(){return function(){window.open("https://github.com/yeongpin/cursor-free-vip","_blank")}}}),null)',
                
                # Windows/Linux
                r'M(x,I(as,{title:"Upgrade to Pro",size:"small",get codicon(){return $.rocket},get onClick(){return t.pay}}),null)': r'M(x,I(as,{title:"yeongpin GitHub",size:"small",get codicon(){return $.github},get onClick(){return function(){window.open("https://github.com/yeongpin/cursor-free-vip","_blank")}}}),null)',
                
                # Mac 通用按钮替换模式
                r'$(k,E(Ks,{title:"Upgrade to Pro",size:"small",get codicon(){return F.rocket},get onClick(){return t.pay}}),null)': r'$(k,E(Ks,{title:"yeongpin GitHub",size:"small",get codicon(){return F.rocket},get onClick(){return function(){window.open("https://github.com/yeongpin/cursor-free-vip","_blank")}}}),null)',
                # Badge 替换
                r'<div>Pro Trial': r'<div>Pro',

                r'py-1">Auto-select': r'py-1">Bypass-Version-Pin',
                
                #
                r'async getEffectiveTokenLimit(e){const n=e.modelName;if(!n)return 2e5;':r'async getEffectiveTokenLimit(e){return 9000000;const n=e.modelName;if(!n)return 9e5;',
                # Pro
                r'var DWr=ne("<div class=settings__item_description>You are currently signed in with <strong></strong>.");': r'var DWr=ne("<div class=settings__item_description>You are currently signed in with <strong></strong>. <h1>Pro</h1>");',
                
                # Toast 替换
                r'notifications-toasts': r'notifications-toasts hidden'
            }

            # 使用patterns进行替换
            for old_pattern, new_pattern in patterns.items():
                content = content.replace(old_pattern, new_pattern)

            # Write to temporary file
            tmp_file.write(content)
            tmp_path = tmp_file.name

        # Backup original file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{file_path}.backup.{timestamp}"
        shutil.copy2(file_path, backup_path)
        print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {translator.get('reset.backup_created', path=backup_path)}{Style.RESET_ALL}")
        
        # Move temporary file to original position
        if os.path.exists(file_path):
            os.remove(file_path)
        shutil.move(tmp_path, file_path)

        # Restore original permissions
        os.chmod(file_path, original_mode)
        if os.name != "nt":  # Not Windows
            os.chown(file_path, original_uid, original_gid)

        print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {translator.get('reset.file_modified')}{Style.RESET_ALL}")
        return True

    except Exception as e:
        print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.modify_file_failed', error=str(e))}{Style.RESET_ALL}")
        if "tmp_path" in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass
        return False
    
def run(translator=None):
    config = get_config(translator)
    if not config:
        return False
    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{EMOJI['RESET']} {translator.get('bypass_token_limit.title')}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    modify_workbench_js(get_workbench_cursor_path(translator), translator)

    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    input(f"{EMOJI['INFO']} {translator.get('bypass_token_limit.press_enter')}...")

if __name__ == "__main__":
    from main import translator as main_translator
    run(main_translator)