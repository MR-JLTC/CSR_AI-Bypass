import os
import sys
import json
import uuid
import hashlib
import shutil
import sqlite3
import platform
import re
import tempfile
from colorama import Fore, Style, init
from typing import Tuple
import configparser
import traceback
from config import get_config
import glob

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
             return os.path.join(os.path.expanduser("~"), "Documents")
     elif sys.platform == "darwin":
         return os.path.join(os.path.expanduser("~"), "Documents")
     else:  # Linux
         # Get actual user's home directory
         sudo_user = os.environ.get('SUDO_USER')
         if sudo_user:
             return os.path.join("/home", sudo_user, "Documents")
         return os.path.join(os.path.expanduser("~"), "Documents")
     

def get_cursor_paths(translator=None) -> Tuple[str, str]:
    """ Get Cursor related paths"""
    system = platform.system()
    
    # Read config file
    config = configparser.ConfigParser()
    config_dir = os.path.join(get_user_documents_path(), ".cursor-free-vip")
    config_file = os.path.join(config_dir, "config.ini")
    
    # Create config directory if it doesn't exist
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    
    # Default paths for different systems - REFINED
    default_paths = {
        "Darwin": "/Applications/Cursor.app/Contents/Resources/app",
        "Windows": [
            os.path.join(os.getenv("LOCALAPPDATA", ""), "Programs", "Cursor", "resources", "app"),
            os.path.join(os.path.expanduser("~"), "Desktop", "cursor", "resources", "app"),
            os.path.join(os.path.expanduser("~"), "Desktop", "Microsoft VS Code", "resources", "app"),
        ],
        "Linux": ["/opt/Cursor/resources/app", "/usr/share/cursor/resources/app", os.path.expanduser("~/.local/share/cursor/resources/app")]
    }
    
    if system == "Linux":
        # Look for extracted AppImage directories - with usr structure
        extracted_usr_paths = glob.glob(os.path.expanduser("~/squashfs-root/usr/share/cursor/resources/app"))
        # Check current directory for extraction without home path prefix
        current_dir_paths = glob.glob("squashfs-root/usr/share/cursor/resources/app")
        
        # Add all paths to the Linux paths list
        default_paths["Linux"].extend(extracted_usr_paths)
        default_paths["Linux"].extend(current_dir_paths)

        # Print debug info for troubleshooting
        print(f"{Fore.CYAN}{EMOJI['INFO']} Available paths found:{Style.RESET_ALL}")
        for path in default_paths["Linux"]:
            if os.path.exists(path):
                print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {path} (exists){Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}{EMOJI['ERROR']} {path} (not found){Style.RESET_ALL}")
    
    # If config doesn't exist, create it with default paths
    if not os.path.exists(config_file):
        for section in ['MacPaths', 'WindowsPaths', 'LinuxPaths']:
            if not config.has_section(section):
                config.add_section(section)
        
        if system == "Darwin":
            config.set('MacPaths', 'cursor_path', default_paths["Darwin"])
        elif system == "Windows":
            # REFINED: Find first existing Windows path and set it as default
            for path in default_paths["Windows"]:
                if os.path.exists(path):
                    config.set('WindowsPaths', 'cursor_path', path)
                    break
            else:
                # If no path exists, use the first one as default
                config.set('WindowsPaths', 'cursor_path', default_paths["Windows"][0])
        elif system == "Linux":
            # For Linux, try to find the first existing path
            for path in default_paths["Linux"]:
                if os.path.exists(path):
                    config.set('LinuxPaths', 'cursor_path', path)
                    break
            else:
                # If no path exists, use the first one as default
                config.set('LinuxPaths', 'cursor_path', default_paths["Linux"][0])
        
        with open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)
    else:
        config.read(config_file, encoding='utf-8')
    
    # Get path based on system
    if system == "Darwin":
        section = 'MacPaths'
    elif system == "Windows":
        section = 'WindowsPaths'
    elif system == "Linux":
        section = 'LinuxPaths'
    else:
        raise OSError(translator.get('reset.unsupported_os', system=system) if translator else f"不支持的操作系统: {system}")
    
    if not config.has_section(section) or not config.has_option(section, 'cursor_path'):
        raise OSError(translator.get('reset.path_not_configured') if translator else "未配置 Cursor 路徑")
    
    base_path = config.get(section, 'cursor_path')
    
    # For Windows/Linux, try to find the first existing path if the configured one doesn't exist
    if system == "Windows":
        path_list = default_paths[system]
        for path in path_list:
            # Check for a key file like package.json
            if os.path.exists(os.path.join(path, "package.json")):
                base_path = path
                # Update config with the found path
                config.set(section, 'cursor_path', path)
                with open(config_file, 'w', encoding='utf-8') as f:
                    config.write(f)
                break
    elif system == "Linux" and not os.path.exists(base_path):
        for path in default_paths["Linux"]:
            if os.path.exists(path):
                base_path = path
                # Update config with the found path
                config.set(section, 'cursor_path', path)
                with open(config_file, 'w', encoding='utf-8') as f:
                    config.write(f)
                break

    if not os.path.exists(base_path):
        raise OSError(translator.get('reset.path_not_found', path=base_path) if translator else f"找不到 Cursor 路徑: {base_path}")
    
    pkg_path = os.path.join(base_path, "package.json")
    main_path = os.path.join(base_path, "out/main.js")
    
    # Check if files exist
    if not os.path.exists(pkg_path):
        raise OSError(translator.get('reset.package_not_found', path=pkg_path) if translator else f"找不到 package.json: {pkg_path}")
    if not os.path.exists(main_path):
        raise OSError(translator.get('reset.main_not_found', path=main_path) if translator else f"找不到 main.js: {main_path}")
    
    return (pkg_path, main_path)

def get_cursor_machine_id_path(translator=None) -> str:
    """
    Get Cursor machineId file path based on operating system
    Returns:
        str: Path to machineId file
    """
    # Read configuration
    config_dir = os.path.join(get_user_documents_path(), ".cursor-free-vip")
    config_file = os.path.join(config_dir, "config.ini")
    config = configparser.ConfigParser()
    
    if os.path.exists(config_file):
        config.read(config_file)
    
    if sys.platform == "win32":  # Windows
        if not config.has_section('WindowsPaths'):
            config.add_section('WindowsPaths')
            config.set('WindowsPaths', 'machine_id_path', 
                os.path.join(os.getenv("APPDATA"), "Cursor", "machineId"))
        return config.get('WindowsPaths', 'machine_id_path')
        
    elif sys.platform == "linux":  # Linux
        if not config.has_section('LinuxPaths'):
            config.add_section('LinuxPaths')
            config.set('LinuxPaths', 'machine_id_path',
                os.path.expanduser("~/.config/cursor/machineid"))
        return config.get('LinuxPaths', 'machine_id_path')
        
    elif sys.platform == "darwin":  # macOS
        if not config.has_section('MacPaths'):
            config.add_section('MacPaths')
            config.set('MacPaths', 'machine_id_path',
                os.path.expanduser("~/Library/Application Support/Cursor/machineId"))
        return config.get('MacPaths', 'machine_id_path')
        
    else:
        raise OSError(f"Unsupported operating system: {sys.platform}")

    # Save any changes to config file
    with open(config_file, 'w', encoding='utf-8') as f:
        config.write(f)

def get_workbench_cursor_path(translator=None) -> str:
    """Get Cursor workbench.desktop.main.js path"""
    system = platform.system()

    # Read configuration
    config_dir = os.path.join(get_user_documents_path(), ".cursor-free-vip")
    config_file = os.path.join(config_dir, "config.ini")
    config = configparser.ConfigParser()

    if os.path.exists(config_file):
        config.read(config_file)

    # REFINED: Centralized and enhanced path search logic
    if system == "Windows":
        section = 'WindowsPaths'
        main_sub_path = "out\\vs\\workbench\\workbench.desktop.main.js"
        # Known default installation paths for Windows
        default_bases = [
            os.path.join(os.getenv("LOCALAPPDATA", ""), "Programs", "Cursor", "resources", "app"),
            # User's provided paths (likely portable/desktop installs)
            os.path.join(os.path.expanduser("~"), "Desktop", "cursor", "resources", "app"),
            os.path.join(os.path.expanduser("~"), "Desktop", "Microsoft VS Code", "resources", "app"),
        ]
    elif system == "Darwin":
        section = 'MacPaths'
        main_sub_path = "out/vs/workbench/workbench.desktop.main.js"
        default_bases = ["/Applications/Cursor.app/Contents/Resources/app"]
    elif system == "Linux":
        section = 'LinuxPaths'
        main_sub_path = "out/vs/workbench/workbench.desktop.main.js"
        # Default Linux paths + paths for extracted AppImage
        default_bases = [
            "/opt/Cursor/resources/app", 
            "/usr/share/cursor/resources/app", 
            os.path.expanduser("~/.local/share/cursor/resources/app")
        ]
        default_bases.extend(glob.glob(os.path.expanduser("~/squashfs-root/usr/share/cursor/resources/app")))
        default_bases.extend(glob.glob("squashfs-root/usr/share/cursor/resources/app"))
    else:
        raise OSError(translator.get('reset.unsupported_os', system=system) if translator else f"Unsupported operating system: {system}")
        
    # Get the configured base path and add it to the front of the list to check it first
    configured_base_path = None
    if config.has_section(section) and config.has_option(section, 'cursor_path'):
        configured_base_path = config.get(section, 'cursor_path')
        if configured_base_path in default_bases:
            # Move the configured path to the front to check it first
            default_bases.remove(configured_base_path)
        default_bases.insert(0, configured_base_path)
        
    # Remove duplicates while preserving order
    checked_bases = []
    for item in default_bases:
        if item not in checked_bases:
            checked_bases.append(item)

    # Check all potential base paths
    for base_path in checked_bases:
        main_path = os.path.join(base_path, main_sub_path)
        if os.path.exists(main_path):
            # If a working path is found, ensure it is the one stored in config
            if base_path != configured_base_path:
                print(f"{Fore.YELLOW}{EMOJI['INFO']} {translator.get('reset.found_new_path') if translator else 'Found new Cursor path'}: {base_path}{Style.RESET_ALL}")
                
                # Update config with the working base path
                if not config.has_section(section):
                    config.add_section(section)
                config.set(section, 'cursor_path', base_path)
                with open(config_file, 'w', encoding='utf-8') as f:
                    config.write(f)
            return main_path

    # If loop completes, the file was not found in any known location
    raise OSError(translator.get('reset.file_not_found', path=main_sub_path) if translator else f"未找到 Cursor main.js 文件，在所有已知路徑中: {main_sub_path}")
    # --- END REFINEMENT ---

def version_check(version: str, min_version: str = "", max_version: str = "", translator=None) -> bool:
    """Version number check"""
    version_pattern = r"^\d+\.\d+\.\d+$"
    try:
        if not re.match(version_pattern, version):
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.invalid_version_format', version=version)}{Style.RESET_ALL}")
            return False

        def parse_version(ver: str) -> Tuple[int, ...]:
            return tuple(map(int, ver.split(".")))

        current = parse_version(version)

        if min_version and current < parse_version(min_version):
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.version_too_low', version=version, min_version=min_version)}{Style.RESET_ALL}")
            return False

        if max_version and current > parse_version(max_version):
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.version_too_high', version=version, max_version=max_version)}{Style.RESET_ALL}")
            return False

        return True

    except Exception as e:
        print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.version_check_error', error=str(e))}{Style.RESET_ALL}")
        return False

def check_cursor_version(translator) -> bool:
    """Check Cursor version"""
    try:
        pkg_path, _ = get_cursor_paths(translator)
        print(f"{Fore.CYAN}{EMOJI['INFO']} {translator.get('reset.reading_package_json', path=pkg_path)}{Style.RESET_ALL}")
        
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except UnicodeDecodeError:
            # If UTF-8 reading fails, try other encodings
            with open(pkg_path, "r", encoding="latin-1") as f:
                data = json.load(f)
                
        if not isinstance(data, dict):
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.invalid_json_object')}{Style.RESET_ALL}")
            return False
            
        if "version" not in data:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.no_version_field')}{Style.RESET_ALL}")
            return False
            
        version = str(data["version"]).strip()
        if not version:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.version_field_empty')}{Style.RESET_ALL}")
            return False
            
        print(f"{Fore.CYAN}{EMOJI['INFO']} {translator.get('reset.found_version', version=version)}{Style.RESET_ALL}")
        
        # Check version format
        if not re.match(r"^\d+\.\d+\.\d+$", version):
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.invalid_version_format', version=version)}{Style.RESET_ALL}")
            return False
            
        # Compare versions
        try:
            current = tuple(map(int, version.split(".")))
            min_ver = (0, 45, 0)  # Use tuple directly instead of string
            
            if current >= min_ver:
                print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {translator.get('reset.version_check_passed', version=version, min_version='0.45.0')}{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.YELLOW}{EMOJI['INFO']} {translator.get('reset.version_too_low', version=version, min_version='0.45.0')}{Style.RESET_ALL}")
                return False
        except ValueError as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.version_parse_error', error=str(e))}{Style.RESET_ALL}")
            return False
            
    except FileNotFoundError as e:
        print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.package_not_found', path=pkg_path)}{Style.RESET_ALL}")
        return False
    except json.JSONDecodeError as e:
        print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.invalid_json_object')}{Style.RESET_ALL}")
        return False
    except Exception as e:
        print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.check_version_failed', error=str(e))}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}{EMOJI['INFO']} {translator.get('reset.stack_trace')}: {traceback.format_exc()}{Style.RESET_ALL}")
        return False

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

            if sys.platform == "win32":
                # Define replacement patterns
                CButton_old_pattern = r'$(k,E(Ks,{title:"Upgrade to Pro",size:"small",get codicon(){return F.rocket},get onClick(){return t.pay}}),null)'
                CButton_new_pattern = r'$(k,E(Ks,{title:"yeongpin GitHub",size:"small",get codicon(){return F.rocket},get onClick(){return function(){window.open("https://github.com/yeongpin/cursor-free-vip","_blank")}}}),null)'
            elif sys.platform == "linux":
                CButton_old_pattern = r'$(k,E(Ks,{title:"Upgrade to Pro",size:"small",get codicon(){return F.rocket},get onClick(){return t.pay}}),null)'
                CButton_new_pattern = r'$(k,E(Ks,{title:"yeongpin GitHub",size:"small",get codicon(){return F.rocket},get onClick(){return function(){window.open("https://github.com/yeongpin/cursor-free-vip","_blank")}}}),null)'
            elif sys.platform == "darwin":
                CButton_old_pattern = r'M(x,I(as,{title:"Upgrade to Pro",size:"small",get codicon(){return $.rocket},get onClick(){return t.pay}}),null)'
                CButton_new_pattern = r'M(x,I(as,{title:"yeongpin GitHub",size:"small",get codicon(){return $.rocket},get onClick(){return function(){window.open("https://github.com/yeongpin/cursor-free-vip","_blank")}}}),null)'

            CBadge_old_pattern = r'<div>Pro Trial'
            CBadge_new_pattern = r'<div>Pro'

            CToast_old_pattern = r'notifications-toasts'
            CToast_new_pattern = r'notifications-toasts hidden'

            # Replace content
            content = content.replace(CButton_old_pattern, CButton_new_pattern)
            content = content.replace(CBadge_old_pattern, CBadge_new_pattern)
            content = content.replace(CToast_old_pattern, CToast_new_pattern)

            # Write to temporary file
            tmp_file.write(content)
            tmp_path = tmp_file.name

        # Backup original file
        backup_path = file_path + ".backup"
        if os.path.exists(backup_path):
            os.remove(backup_path)
        shutil.copy2(file_path, backup_path)
        
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

def modify_main_js(main_path: str, translator) -> bool:
    """Modify main.js file"""
    try:
        original_stat = os.stat(main_path)
        original_mode = original_stat.st_mode
        original_uid = original_stat.st_uid
        original_gid = original_stat.st_gid

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
            with open(main_path, "r", encoding="utf-8") as main_file:
                content = main_file.read()

            patterns = {
                r"async getMachineId\(\)\{return [^??]+\?\?([^}]+)\}": r"async getMachineId(){return \1}",
                r"async getMacMachineId\(\)\{return [^??]+\?\?([^}]+)\}": r"async getMacMachineId(){return \1}",
            }

            for pattern, replacement in patterns.items():
                content = re.sub(pattern, replacement, content)

            tmp_file.write(content)
            tmp_path = tmp_file.name

        shutil.copy2(main_path, main_path + ".old")
        shutil.move(tmp_path, main_path)

        os.chmod(main_path, original_mode)
        if os.name != "nt":
            os.chown(main_path, original_uid, original_gid)

        print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {translator.get('reset.file_modified')}{Style.RESET_ALL}")
        return True

    except Exception as e:
        print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.modify_file_failed', error=str(e))}{Style.RESET_ALL}")
        if "tmp_path" in locals():
            os.unlink(tmp_path)
        return False

def patch_cursor_get_machine_id(translator) -> bool:
    """Patch Cursor getMachineId function"""
    try:
        print(f"{Fore.CYAN}{EMOJI['INFO']} {translator.get('reset.start_patching')}...{Style.RESET_ALL}")
        
        # Get paths
        pkg_path, main_path = get_cursor_paths(translator)
        
        # Check file permissions
        for file_path in [pkg_path, main_path]:
            if not os.path.isfile(file_path):
                print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.file_not_found', path=file_path)}{Style.RESET_ALL}")
                return False
            if not os.access(file_path, os.W_OK):
                print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.no_write_permission', path=file_path)}{Style.RESET_ALL}")
                return False

        # Get version number
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                version = json.load(f)["version"]
            print(f"{Fore.CYAN}{EMOJI['INFO']} {translator.get('reset.current_version', version=version)}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.read_version_failed', error=str(e))}{Style.RESET_ALL}")
            return False

        # Check version
        if not version_check(version, min_version="0.45.0", translator=translator):
            print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.version_not_supported')}{Style.RESET_ALL}")
            return False

        print(f"{Fore.CYAN}{EMOJI['INFO']} {translator.get('reset.version_check_passed')}{Style.RESET_ALL}")

        # Backup file
        backup_path = main_path + ".bak"
        if not os.path.exists(backup_path):
            shutil.copy2(main_path, backup_path)
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {translator.get('reset.backup_created', path=backup_path)}{Style.RESET_ALL}")

        # Modify file
        if not modify_main_js(main_path, translator):
            return False

        print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {translator.get('reset.patch_completed')}{Style.RESET_ALL}")
        return True

    except Exception as e:
        print(f"{Fore.RED}{EMOJI['ERROR']} {translator.get('reset.patch_failed', error=str(e))}{Style.RESET_ALL}")
        return False

class MachineIDResetter:
    def __init__(self, translator=None):
        self.translator = translator

        # Read configuration
        config_dir = os.path.join(get_user_documents_path(), ".cursor-free-vip")
        config_file = os.path.join(config_dir, "config.ini")
        config = configparser.ConfigParser()
        
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")
        
        config.read(config_file, encoding='utf-8')

        # Check operating system
        if sys.platform == "win32":  # Windows
            appdata = os.getenv("APPDATA")
            if appdata is None:
                raise EnvironmentError("APPDATA Environment Variable Not Set")
            
            if not config.has_section('WindowsPaths'):
                config.add_section('WindowsPaths')
                config.set('WindowsPaths', 'storage_path', os.path.join(
                    appdata, "Cursor", "User", "globalStorage", "storage.json"
                ))
                config.set('WindowsPaths', 'sqlite_path', os.path.join(
                    appdata, "Cursor", "User", "globalStorage", "state.vscdb"
                ))
                
            self.db_path = config.get('WindowsPaths', 'storage_path')
            self.sqlite_path = config.get('WindowsPaths', 'sqlite_path')
            
        elif sys.platform == "darwin":  # macOS
            if not config.has_section('MacPaths'):
                config.add_section('MacPaths')
                config.set('MacPaths', 'storage_path', os.path.abspath(os.path.expanduser(
                    "~/Library/Application Support/Cursor/User/globalStorage/storage.json"
                )))
                config.set('MacPaths', 'sqlite_path', os.path.abspath(os.path.expanduser(
                    "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb"
                )))
                
            self.db_path = config.get('MacPaths', 'storage_path')
            self.sqlite_path = config.get('MacPaths', 'sqlite_path')
            
        elif sys.platform == "linux":  # Linux
            if not config.has_section('LinuxPaths'):
                config.add_section('LinuxPaths')
                # Get actual user's home directory
                sudo_user = os.environ.get('SUDO_USER')
                actual_home = f"/home/{sudo_user}" if sudo_user else os.path.expanduser("~")
                
                config.set('LinuxPaths', 'storage_path', os.path.abspath(os.path.join(
                    actual_home,
                    ".config/cursor/User/globalStorage/storage.json"
                )))
                config.set('LinuxPaths', 'sqlite_path', os.path.abspath(os.path.join(
                    actual_home,
                    ".config/cursor/User/globalStorage/state.vscdb"
                )))
                
            self.db_path = config.get('LinuxPaths', 'storage_path')
            self.sqlite_path = config.get('LinuxPaths', 'sqlite_path')
            
        else:
            raise NotImplementedError(f"Not Supported OS: {sys.platform}")

        # Save any changes to config file
        with open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)

    def generate_new_ids(self):
        """Generate new machine ID"""
        # Generate new UUID
        dev_device_id = str(uuid.uuid4())

        # Generate new machineId (64 characters of hexadecimal)
        machine_id = hashlib.sha256(os.urandom(32)).hexdigest()

        # Generate new macMachineId (128 characters of hexadecimal)
        mac_machine_id = hashlib.sha512(os.urandom(64)).hexdigest()

        # Generate new sqmId
        sqm_id = "{" + str(uuid.uuid4()).upper() + "}"

        self.update_machine_id_file(dev_device_id)

        return {
            "telemetry.devDeviceId": dev_device_id,
            "telemetry.macMachineId": mac_machine_id,
            "telemetry.machineId": machine_id,
            "telemetry.sqmId": sqm_id,
            "storage.serviceMachineId": dev_device_id,  # Add storage.serviceMachineId
        }

    def update_sqlite_db(self, new_ids):
        """Update machine ID in SQLite database"""
        try:
            print(f"{Fore.CYAN}{EMOJI['INFO']} {self.translator.get('reset.updating_sqlite')}...{Style.RESET_ALL}")
            
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ItemTable (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            updates = [
                (key, value) for key, value in new_ids.items()
            ]

            for key, value in updates:
                cursor.execute("""
                    INSERT OR REPLACE INTO ItemTable (key, value) 
                    VALUES (?, ?)
                """, (key, value))
                print(f"{EMOJI['INFO']} {Fore.CYAN} {self.translator.get('reset.updating_pair')}: {key}{Style.RESET_ALL}")

            conn.commit()
            conn.close()
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('reset.sqlite_success')}{Style.RESET_ALL}")
            return True

        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.sqlite_error', error=str(e))}{Style.RESET_ALL}")
            return False

    def update_system_ids(self, new_ids):
        """Update system-level IDs"""
        try:
            print(f"{Fore.CYAN}{EMOJI['INFO']} {self.translator.get('reset.updating_system_ids')}...{Style.RESET_ALL}")
            
            if sys.platform.startswith("win"):
                self._update_windows_machine_guid()
                self._update_windows_machine_id()
            elif sys.platform == "darwin":
                self._update_macos_platform_uuid(new_ids)
                
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('reset.system_ids_updated')}{Style.RESET_ALL}")
            return True
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.system_ids_update_failed', error=str(e))}{Style.RESET_ALL}")
            return False

    def _update_windows_machine_guid(self):
        """Update Windows MachineGuid"""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                "SOFTWARE\\Microsoft\\Cryptography",
                0,
                winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
            )
            new_guid = str(uuid.uuid4())
            winreg.SetValueEx(key, "MachineGuid", 0, winreg.REG_SZ, new_guid)
            winreg.CloseKey(key)
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('reset.windows_machine_guid_updated')}{Style.RESET_ALL}")
        except PermissionError:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.permission_denied')}{Style.RESET_ALL}")
            raise
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.update_windows_machine_guid_failed', error=str(e))}{Style.RESET_ALL}")
            raise
    
    def _update_windows_machine_id(self):
        """Update Windows MachineId in SQMClient registry"""
        try:
            import winreg
            # 1. Generate new GUID
            new_guid = "{" + str(uuid.uuid4()).upper() + "}"
            print(f"{Fore.CYAN}{EMOJI['INFO']} {self.translator.get('reset.new_machine_id')}: {new_guid}{Style.RESET_ALL}")
            
            # 2. Open the registry key
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\SQMClient",
                    0,
                    winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
                )
            except FileNotFoundError:
                # If the key does not exist, create it
                key = winreg.CreateKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\SQMClient"
                )
            
            # 3. Set MachineId value
            winreg.SetValueEx(key, "MachineId", 0, winreg.REG_SZ, new_guid)
            winreg.CloseKey(key)
            
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('reset.windows_machine_id_updated')}{Style.RESET_ALL}")
            return True
            
        except PermissionError:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.permission_denied')}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{EMOJI['WARNING']} {self.translator.get('reset.run_as_admin')}{Style.RESET_ALL}")
            return False
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.update_windows_machine_id_failed', error=str(e))}{Style.RESET_ALL}")
            return False
                    

    def _update_macos_platform_uuid(self, new_ids):
        """Update macOS Platform UUID"""
        try:
            uuid_file = "/var/root/Library/Preferences/SystemConfiguration/com.apple.platform.uuid.plist"
            if os.path.exists(uuid_file):
                # Use sudo to execute plutil command
                cmd = f'sudo plutil -replace "UUID" -string "{new_ids["telemetry.macMachineId"]}" "{uuid_file}"'
                result = os.system(cmd)
                if result == 0:
                    print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('reset.macos_platform_uuid_updated')}{Style.RESET_ALL}")
                else:
                    raise Exception(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.failed_to_execute_plutil_command')}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.update_macos_platform_uuid_failed', error=str(e))}{Style.RESET_ALL}")
            raise

    # --- START OF NEW USAGE RESET METHODS ---

    def _clear_usage_in_storage_json(self) -> bool:
        """Clear usage-related keys in storage.json."""
        try:
            if not os.path.exists(self.db_path):
                return True # Nothing to do

            with open(self.db_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            keys_to_clear = []
            for key in config.keys():
                # Keys that track usage often contain 'usage', 'gpt4', or 'trial'
                if any(term in key.lower() for term in ['usage', 'gpt4', 'trial', 'cursorauth/trial']):
                    keys_to_clear.append(key)
            
            if not keys_to_clear:
                print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('reset.no_usage_keys_storage') if self.translator else 'No usage-related keys found in storage.json.'}{Style.RESET_ALL}")
                return True

            for key in keys_to_clear:
                # Set values to 0 for usage counts or False for boolean flags
                # If the value is a string or dictionary, removing it is safer.
                # Here, we opt for removing to ensure a clean state, as usage data can be complex JSON strings.
                if key in config:
                    del config[key] 
                    print(f"{EMOJI['INFO']} {Fore.CYAN} {self.translator.get('reset.clearing_key') if self.translator else 'Clearing key'}: {key} (storage.json){Style.RESET_ALL}")

            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
                
            return True
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.clear_storage_usage_failed', error=str(e)) if self.translator else f'Failed to clear storage.json usage: {str(e)}'}{Style.RESET_ALL}")
            return False

    def _clear_usage_in_sqlite_db(self) -> bool:
        """Clear usage-related keys in state.vscdb (SQLite)."""
        if not os.path.exists(self.sqlite_path):
            return True # Nothing to do

        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            
            # Delete keys that likely store usage data
            # Use LIKE to match keys containing 'usage', 'gpt4', or 'trial'
            cursor.execute("""
                DELETE FROM ItemTable WHERE 
                key LIKE '%usage%' OR 
                key LIKE '%gpt4%' OR 
                key LIKE '%trial%'
            """)
            
            changes = conn.total_changes
            if changes > 0:
                print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('reset.sqlite_usage_cleared') if self.translator else f'Successfully deleted {changes} usage-related records from state.vscdb.'}{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('reset.no_usage_keys_sqlite') if self.translator else 'No usage-related keys found in state.vscdb.'}{Style.RESET_ALL}")
            
            conn.commit()
            conn.close()
            return True
        
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.clear_sqlite_usage_failed', error=str(e)) if self.translator else f'Failed to clear state.vscdb usage: {str(e)}'}{Style.RESET_ALL}")
            return False

    def reset_usage_counts(self) -> bool:
        """Master function to clear local usage counts in storage.json and state.vscdb."""
        print(f"\n{Fore.CYAN}{EMOJI['RESET']} {self.translator.get('reset.start_usage_clear') if self.translator else 'Starting local usage count clear...'}{Style.RESET_ALL}")
        success_storage = self._clear_usage_in_storage_json()
        success_sqlite = self._clear_usage_in_sqlite_db()
        
        if success_storage and success_sqlite:
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('reset.usage_success') if self.translator else 'Local usage counts successfully reset.'}{Style.RESET_ALL}")
            return True
        else:
            # Report failure if either operation failed
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.usage_failed') if self.translator else 'One or more usage reset steps failed.'}{Style.RESET_ALL}")
            return False
            
    # --- END OF NEW USAGE RESET METHODS ---

    def reset_machine_ids(self):
        """Reset machine ID and backup original file"""
        try:
            print(f"{Fore.CYAN}{EMOJI['INFO']} {self.translator.get('reset.checking')}...{Style.RESET_ALL}")

            if not os.path.exists(self.db_path):
                print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.not_found')}: {self.db_path}{Style.RESET_ALL}")
                return False

            if not os.access(self.db_path, os.R_OK | os.W_OK):
                print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.no_permission')}{Style.RESET_ALL}")
                return False

            print(f"{Fore.CYAN}{EMOJI['FILE']} {self.translator.get('reset.reading')}...{Style.RESET_ALL}")
            with open(self.db_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            backup_path = self.db_path + ".bak"
            if not os.path.exists(backup_path):
                print(f"{Fore.YELLOW}{EMOJI['BACKUP']} {self.translator.get('reset.creating_backup')}: {backup_path}{Style.RESET_ALL}")
                shutil.copy2(self.db_path, backup_path)
            else:
                print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('reset.backup_exists')}{Style.RESET_ALL}")

            print(f"{Fore.CYAN}{EMOJI['RESET']} {self.translator.get('reset.generating')}...{Style.RESET_ALL}")
            new_ids = self.generate_new_ids()

            # Update configuration file
            config.update(new_ids)

            print(f"{Fore.CYAN}{EMOJI['FILE']} {self.translator.get('reset.saving_json')}...{Style.RESET_ALL}")
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)

            # Update SQLite database
            self.update_sqlite_db(new_ids)

            # Update system IDs
            self.update_system_ids(new_ids)

            # --- CALL NEW FEATURE: Reset Usage Counts ---
            self.reset_usage_counts()
            # ------------------------------------------

            # Modify workbench.desktop.main.js
            workbench_path = get_workbench_cursor_path(self.translator)
            modify_workbench_js(workbench_path, self.translator)

            # Check Cursor version and perform corresponding actions
            greater_than_0_45 = check_cursor_version(self.translator)
            if greater_than_0_45:
                print(f"{Fore.CYAN}{EMOJI['INFO']} {self.translator.get('reset.detecting_version')} >= 0.45.0，{self.translator.get('reset.patching_getmachineid')}{Style.RESET_ALL}")
                patch_cursor_get_machine_id(self.translator)
            else:
                print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('reset.version_less_than_0_45')}{Style.RESET_ALL}")

            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('reset.success')}{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}{self.translator.get('reset.new_id')}:{Style.RESET_ALL}")
            for key, value in new_ids.items():
                print(f"{EMOJI['INFO']} {key}: {Fore.GREEN}{value}{Style.RESET_ALL}")

            return True

        except PermissionError as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.permission_error', error=str(e))}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('reset.run_as_admin')}{Style.RESET_ALL}")
            return False
        except Exception as e:
            print(f"{Fore.RED}{EMOJI['ERROR']} {self.translator.get('reset.process_error', error=str(e))}{Style.RESET_ALL}")
            return False

    def update_machine_id_file(self, machine_id: str) -> bool:
        """
        Update machineId file with new machine_id
        Args:
            machine_id (str): New machine ID to write
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get the machineId file path
            machine_id_path = get_cursor_machine_id_path()
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(machine_id_path), exist_ok=True)

            # Create backup if file exists
            if os.path.exists(machine_id_path):
                backup_path = machine_id_path + ".backup"
                try:
                    shutil.copy2(machine_id_path, backup_path)
                    print(f"{Fore.GREEN}{EMOJI['INFO']} {self.translator.get('reset.backup_created', path=backup_path) if self.translator else f'Backup created at: {backup_path}'}{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.YELLOW}{EMOJI['INFO']} {self.translator.get('reset.backup_creation_failed', error=str(e)) if self.translator else f'Could not create backup: {str(e)}'}{Style.RESET_ALL}")

            # Write new machine ID to file
            with open(machine_id_path, "w", encoding="utf-8") as f:
                f.write(machine_id)

            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} {self.translator.get('reset.update_success') if self.translator else 'Successfully updated machineId file'}{Style.RESET_ALL}")
            return True

        except Exception as e:
            error_msg = f"Failed to update machineId file: {str(e)}"
            if self.translator:
                error_msg = self.translator.get('reset.update_failed', error=str(e))
            print(f"{Fore.RED}{EMOJI['ERROR']} {error_msg}{Style.RESET_ALL}")
            return False

def run(translator=None):
    config = get_config(translator)
    if not config:
        return False
    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{EMOJI['RESET']} {translator.get('reset.title')}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    resetter = MachineIDResetter(translator)  # Correctly pass translator
    resetter.reset_machine_ids()

    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    input(f"{EMOJI['INFO']} {translator.get('reset.press_enter')}...")

if __name__ == "__main__":
    from main import translator as main_translator
    run(main_translator)