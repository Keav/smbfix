import os
import re
import sys
import subprocess
import getpass
import platform
import json
from pathlib import Path
import base64
import shutil

# Define invalid SMB characters
PROBLEM_CHAR_REGEX = re.compile(r"[\x00-\x1F\x7F\uE000-\uF8FF\u0300-\u036F]")
INVALID_CHARACTERS = re.compile(r'[\\/:*?"<>|+\[\]]')  # Keep existing invalid SMB characters
# Windows reserved names (case-insensitive)
RESERVED_NAMES = ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 100)] + [f'LPT{i}' for i in range(1, 100)]
# Define the byte signature of a macOS alias file
ALIAS_HEADER = b'book\x00\x00\x00\x00mark'
stored_passwords = {}
sudo_timestamp_refreshed = False  # Track if we've refreshed the sudo timestamp

# Platform detection
IS_MACOS = platform.system() == "Darwin"  
IS_SYNOLOGY = os.path.exists("/etc/synoinfo.conf")

# ------------------ CREDENTIAL MANAGEMENT ------------------ #

def get_password_file_path():
    """Get path to password storage file."""
    home_dir = str(Path.home())
    config_dir = os.path.join(home_dir, '.config', 'smbfix')
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, 'credentials.enc')

def encrypt_simple(password):
    """Basic encoding of password - not truly secure but better than plaintext."""
    return base64.b64encode(password.encode()).decode()

def decrypt_simple(encoded):
    """Basic decoding of password."""
    try:
        return base64.b64decode(encoded.encode()).decode()
    except:
        return None

def get_stored_password(username):
    """Get password from file if available, otherwise return None."""
    try:
        cred_path = get_password_file_path()
        if os.path.exists(cred_path):
            with open(cred_path, 'r') as f:
                creds = json.load(f)
                if username in creds:
                    decoded = decrypt_simple(creds[username])
                    if decoded:
                        print(f"✅ Found stored credentials for {username}")
                        return decoded
    except Exception as e:
        print(f"⚠️ Could not retrieve stored password: {e}")
        
    return None

def store_password(username, password):
    """Store password in file."""
    try:
        cred_path = get_password_file_path()
        
        # Read existing credentials if file exists
        creds = {}
        if os.path.exists(cred_path):
            with open(cred_path, 'r') as f:
                try:
                    creds = json.load(f)
                except:
                    creds = {}
        
        # Add or update this user's credentials
        creds[username] = encrypt_simple(password)
        
        # Write back to file with restrictive permissions
        with open(cred_path, 'w') as f:
            json.dump(creds, f)
        
        # Set secure permissions
        os.chmod(cred_path, 0o600)
        
        print(f"✅ Stored credentials for {username}")
        return True
    except Exception as e:
        print(f"⚠️ Could not store password: {e}")
        return False

def forget_credentials(username):
    """Remove stored credentials."""
    try:
        cred_path = get_password_file_path()
        if os.path.exists(cred_path):
            with open(cred_path, 'r') as f:
                creds = json.load(f)
            
            if username in creds:
                del creds[username]
                with open(cred_path, 'w') as f:
                    json.dump(creds, f)
                print(f"✅ Removed stored credentials for {username}")
                return True
            else:
                print(f"⚠️ No stored credentials found for {username}")
        else:
            print(f"⚠️ No credential file exists")
    except Exception as e:
        print(f"⚠️ Error removing credentials: {e}")
    
    return False

def get_password(username, prompt_message=None):
    """Get password from storage or prompt user if not stored."""
    global stored_passwords
    
    # Check if already in memory for this session
    if username in stored_passwords:
        return stored_passwords[username]
    
    # Try to get from file storage
    password = get_stored_password(username)
    
    # If not found, prompt user
    if not password:
        prompt_message = prompt_message or f"Password for {username} (will be stored for future use): "
        password = getpass.getpass(prompt_message)
        
        # Store for future use
        if password:
            store_password(username, password)
    
    # Store in memory for this session
    stored_passwords[username] = password
    return password

def refresh_sudo_timestamp(password, force_refresh=False):
    """Initialize/refresh sudo session to avoid repeated password prompts during script execution."""
    global sudo_timestamp_refreshed
    
    if sudo_timestamp_refreshed and not force_refresh:
        return True
    
    if force_refresh:
        print("� Refreshing sudo session...")
    else:
        print("�🔑 Initializing sudo session...")
    
    cmd = 'echo "Sudo session active"'
    result = subprocess.run(
        ["sudo", "-S", "sh", "-c", cmd],
        input=password + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    if result.returncode == 0:
        sudo_timestamp_refreshed = True
        return True
    else:
        print(f"⚠️ Failed to refresh sudo session: {result.stderr}")
        return False

def ensure_sudo_session(current_user):
    """Ensure sudo session is active, refresh if needed."""
    global sudo_timestamp_refreshed
    
    # Test if sudo is still active
    test_result = subprocess.run(
        ["sudo", "-n", "echo", "test"],
        capture_output=True,
        text=True
    )
    
    if test_result.returncode != 0:
        # Sudo session expired, refresh it
        password = get_password(current_user)
        return refresh_sudo_timestamp(password, force_refresh=True)
    
    return True

# ------------------ ENVIRONMENT CHECK ------------------ #

def check_environment():
    """Check if all required modules are available and the environment is correctly set up."""
    required_modules = {
        'os': 'Core functionality for file operations',
        're': 'Regular expressions for pattern matching',
        'sys': 'System-specific parameters and functions',
        'subprocess': 'Subprocess management',
        'getpass': 'Secure password input',
        'platform': 'Platform identification',
        'json': 'JSON handling for credential storage',
        'base64': 'Basic encoding/decoding for credential storage'
    }
    
    print("\n🔍 Checking Python environment...\n")
    print(f"Python version: {platform.python_version()}")
    print(f"Platform: {platform.platform()}")
    print(f"System: {platform.system()} {platform.release()}")
    
    # Check for required modules
    missing = []
    for module, description in required_modules.items():
        try:
            __import__(module)
            print(f"✅ {module}: Found - {description}")
        except ImportError:
            print(f"❌ {module}: Missing - {description}")
            missing.append(module)
    
    # Check for administrative permissions on macOS
    if platform.system() == "Darwin":
        try:
            # Try a simple sudo command to check if sudo access works
            with open(os.devnull, 'w') as DEVNULL:
                subprocess.check_call(["sudo", "-n", "echo", "Testing sudo"], 
                                     stdout=DEVNULL, stderr=DEVNULL)
            print("✅ sudo access: Available - Can execute administrative commands")
        except subprocess.CalledProcessError:
            print("⚠️ sudo access: Requires password - Will prompt during execution")
        except Exception:
            print("⚠️ sudo access: Unknown - May have issues with permission operations")
    
    if missing:
        print("\n❌ Environment check failed. Missing required modules.")
        print("Install missing modules with: pip install " + " ".join(missing))
        return False
    else:
        print("\n✅ Environment check passed. All required modules are available.")
        return True

# ------------------ FILE & FOLDER CLEANUP FUNCTIONS ------------------ #

def is_mac_alias(filepath):
    """Check if a file is a macOS alias by examining its header."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(16)
            return header.startswith(ALIAS_HEADER)
    except Exception:
        return False

def is_reserved_name(name):
    """Check if a name is a Windows reserved name (ignoring extension)."""
    basename = os.path.splitext(name)[0]
    return basename.upper() in RESERVED_NAMES

def clean_filename(entry):
    """Fix filename by replacing invalid characters, removing unnecessary spaces, and ensuring proper formatting."""
    # Log problematic filenames when debugging is needed
    original_entry = entry
    
    if not entry:
        print(f"⚠️ Warning: Empty filename detected, using 'unnamed_file' instead")
        return "unnamed_file"  # Handle empty filenames
    
    # Check if the name actually needs to be cleaned
    has_invalid_chars = (INVALID_CHARACTERS.search(entry) or 
                         PROBLEM_CHAR_REGEX.search(entry) or 
                         "\u00A0" in entry or
                         is_reserved_name(entry) or
                         re.search(r'\.{2,}', entry) or
                         re.search(r'-{2,}', entry) or  # Check for multiple consecutive hyphens
                         re.search(r'[\u2013\u2014\u2015]{2,}', entry) or  # Check for multiple Unicode dashes
                         entry.endswith('.') or  # This check catches trailing periods
                         entry.endswith(' ') or  # Check for trailing spaces
                         entry.startswith(' ') or # Check for leading spaces
                         re.search(r'\s{2,}', entry) or  # Check for multiple consecutive spaces
                         re.search(r'[\s\t\u00A0\u2000-\u200B\u2028\u2029]{2,}', entry) or  # Check for mixed whitespace
                         ' .' in entry or
                         re.search(r'-{2,}\.[a-zA-Z0-9]+$', entry) or  # Check for multiple hyphens before extension
                         re.search(r'-\.[a-zA-Z0-9]+$', entry) or  # Check for hyphen before extension
                         entry.endswith('-') or  # Check for trailing hyphens
                         re.search(r'[^a-zA-Z0-9)]$', entry) or  # Check for trailing special chars (excluding closing parentheses)
                         entry.startswith('-'))  # Check for leading hyphens specifically
    
    if not has_invalid_chars:
        return entry  # Return unchanged if already valid
    
    # Initial replacements for invalid characters
    entry = entry.replace("\u00A0", " ")  # Replace non-breaking spaces
    
    # Smart replacement of invalid characters to avoid creating trailing issues
    # Handle leading asterisk specially - replace with underscore to preserve sorting intent
    if entry.startswith('*'):
        entry = '_' + entry[1:]  # Replace leading * with _ to preserve "sort to top" behavior
        print(f"🔧 Replaced leading asterisk with underscore to preserve sorting in '{original_entry}'")
    
    # Replace all remaining invalid SMB characters and problematic Unicode characters with hyphens
    entry = INVALID_CHARACTERS.sub('-', entry)
    entry = PROBLEM_CHAR_REGEX.sub("-", entry)
    
    # Replace Unicode dashes with regular hyphens
    entry = re.sub(r'[\u2013\u2014\u2015]', '-', entry)
    
    # Collapse multiple consecutive hyphens into a single hyphen
    entry = re.sub(r'-{2,}', '-', entry)
    
    # Remove multiple hyphens immediately before file extensions
    entry = re.sub(r'-{2,}(\.[a-zA-Z0-9]+)$', r'\1', entry)
    # Remove single hyphen immediately before file extensions (e.g., "file-.pdf" -> "file.pdf")
    # Also remove spaces before hyphens before extensions (e.g., "file -.pdf" -> "file.pdf")
    entry = re.sub(r'\s*-(\.[a-zA-Z0-9]+)$', r'\1', entry)
    
    # Remove leading special characters to ensure names start with alphanumeric characters or valid SMB chars
    # Only remove problematic leading characters like hyphens and spaces, but preserve periods (for hidden files)
    original_for_leading = entry
    entry = re.sub(r'^[-\s]+', '', entry)  # Remove leading hyphens and spaces only, preserve periods
    if entry != original_for_leading:
        print(f"🔧 Removed problematic leading character(s) from '{original_for_leading}' -> '{entry}'")
    
    # Remove any trailing hyphens that were just created from invalid character replacement
    if entry.endswith('-') and not original_entry.endswith('-'):
        # We created a trailing hyphen from replacement, remove it
        entry = entry.rstrip('-')
        print(f"🔧 Removed trailing hyphen created by character replacement in '{original_entry}'")
    
    # Handle file extension separately to ensure proper cleanup
    base_name, ext = os.path.splitext(entry)
    
    # Normalize spaces first - handle all types of whitespace
    base_name = re.sub(r'[\s\t\u00A0\u2000-\u200B\u2028\u2029]+', ' ', base_name).strip()
    
    # Check for empty base name after space normalization
    if not base_name and ext:
        print(f"⚠️ Warning: Filename '{original_entry}' became empty after cleaning, using 'file' as base name")
        base_name = "file"
    elif not base_name:
        print(f"⚠️ Warning: Filename '{original_entry}' became empty after cleaning, using 'unnamed_file' instead")
        return "unnamed_file"
    
    # Handle periods in non-hidden files consistently across platforms
    if not base_name.startswith('.'):  # Skip period handling for hidden files
        # Special handling for consecutive dots - be more explicit about the pattern
        # Replace 2 or more consecutive dots with a single dot, but only if not at the end
        # This prevents "file.." from becoming "file." which would then become "file-"
        base_name = re.sub(r'\.{2,}(?=\w)', '.', base_name)  # Only replace if followed by word character
        base_name = re.sub(r'\.{2,}(?=\s)', '.', base_name)  # Only replace if followed by space
        
        # Handle remaining consecutive dots (like "file..eml" -> "file.eml")
        # Split on extension boundary and handle dots in base name only
        if '.' in base_name:
            # Find the last meaningful dot (before potential extension in base_name)
            parts = base_name.split('.')
            if len(parts) > 1:
                # Rejoin with single dots, but handle consecutive dots at boundaries
                cleaned_parts = []
                for i, part in enumerate(parts):
                    if part or i == 0 or i == len(parts) - 1:  # Keep non-empty parts and boundary parts
                        cleaned_parts.append(part)
                base_name = '.'.join(cleaned_parts)
        
        # Then handle spaces around periods
        base_name = re.sub(r' \.$', '', base_name)  # Remove space + period at end
        base_name = re.sub(r' \.', '.', base_name)  # Fix space before period
    
    # Comprehensive trailing special character cleanup
    # Remove all trailing non-alphanumeric characters except closing parentheses
    base_name = re.sub(r'[^a-zA-Z0-9)]+$', '', base_name)
    
    # Check again for empty base name after character cleanup
    if not base_name and ext:
        print(f"⚠️ Warning: Filename '{original_entry}' became empty after character cleanup, using 'file' as base name")
        base_name = "file"
    elif not base_name:
        print(f"⚠️ Warning: Filename '{original_entry}' became empty after character cleanup, using 'unnamed_file' instead")
        return "unnamed_file"
    
    # Handle trailing periods ONLY if they're not part of a valid extension pattern
    # (This check should now be redundant due to the comprehensive cleanup above, but kept for safety)
    if base_name.endswith('.') and not ext:
        base_name = base_name[:-1]  # Just remove the period, don't replace with dash
    elif base_name.endswith('.') and ext:
        # If we have an extension, remove the trailing period from base_name
        base_name = base_name[:-1]
    
    # Handle trailing hyphens (including multiple consecutive ones) before extension (from previous script runs)
    # Also fix trailing hyphens in folder names (which typically have no extension)
    if base_name.endswith('-'):
        # Remove ALL trailing hyphens, not just one
        original_base = base_name
        base_name = base_name.rstrip('-')
        if ext:
            print(f"🔧 Removing trailing hyphen(s) from file '{entry}': '{original_base}' -> '{base_name}'")
        else:
            print(f"🔧 Removing trailing hyphen(s) from folder/file '{entry}': '{original_base}' -> '{base_name}'")
        # base_name = base_name[:-1]  # Remove trailing hyphen
    
    # Ensure no spaces before extension
    entry = base_name + ext
    
    # Remove any remaining spaces before extension
    entry = re.sub(r' (\.[a-zA-Z0-9]+)$', r'\1', entry)
    
    # Final cleanup pass
    entry = entry.strip()
    
    # Handle Windows reserved names by appending an underscore
    if is_reserved_name(entry):
        entry = entry + "_"
    
    return entry

# ------------------ FILE & FOLDER CHECKS ------------------ #

def should_exclude(path):
    """Exclude iPhoto Library, .abbu files/folders, Synology system files, and mail archives."""
    return ("iPhoto Library" in path or 
            ".abbu/" in path or 
            path.lower().endswith(".abbu") or 
            ".photoslibrary/" in path or 
            path.lower().endswith(".photoslibrary") or
            "/@eaDir/" in path or  # Exclude Synology extended attributes directory with leading slash
            "@eaDir" in os.path.basename(path) or  # Exclude @eaDir folder name directly
            path.endswith("@SynoEAStream") or  # Exclude Synology extended attribute files
            ".mbox/" in path or  # Exclude mail archive contents
            path.lower().endswith(".mbox"))  # Exclude mail archive files

def is_rtfd_bundle(path):
    """Check if the path is an RTFD bundle."""
    return path.lower().endswith('.rtfd') and os.path.isdir(path)

def is_locked(path):
    """Check if a file or folder is locked. Only applicable for macOS."""
    if not IS_MACOS:
        return False
        
    result = subprocess.run(['find', path, '-flags', 'uchg'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return bool(result.stdout.strip())

def get_permissions(path):
    """Retrieve file/folder permissions (e.g., 644, 755)."""
    try:
        mode = oct(os.stat(path).st_mode)[-3:]  # Get last 3 digits of permission
        return int(mode)
    except Exception:
        return None

def get_owner(path):
    """Retrieve file owner UID."""
    try:
        return os.stat(path).st_uid
    except Exception:
        return None

# ------------------ FIX FUNCTIONS ------------------ #

def unlock_file(path, current_user, logged_in_user):
    """Unlock a file only if it is locked, using sudo."""
    if not IS_MACOS:
        return False  # Skip for non-macOS systems
        
    if is_locked(path):
        print(f"\n🔓 Unlocking file: {path}")
        
        # Ensure sudo session is active
        if not ensure_sudo_session(current_user):
            print(f"❌ Failed to establish sudo session for unlocking: {path}")
            return False

        cmd = f'chflags -R nouchg "{path}"'
        child = subprocess.run(["sudo", "sh", "-c", cmd],
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if child.returncode != 0:
            print(f"❌ Failed to unlock: {path}")
            return False
        else:
            print(f"✅ Successfully unlocked: {path}")
            return True
    return False  # File was not locked

def fix_ownership(path, current_user):
    """Fix ownership of a file or folder only if incorrect."""
    if not IS_MACOS:  # Skip for non-macOS systems
        return
        
    try:
        if get_owner(path) != os.getuid():
            print(f"🛠️ Changing ownership: {path}")
            
            # Ensure sudo session is active
            if not ensure_sudo_session(current_user):
                print(f"❌ Failed to establish sudo session for ownership change: {path}")
                return
                
            subprocess.run(["sudo", "chown", "-R", f"{current_user}:staff", path], check=True)
            print(f"✅ Ownership fixed: {path}")
    except Exception as e:
        print(f"⚠️ Failed to change ownership: {path} - {e}")

def fix_permissions(path):
    """Ensure minimum permissions of 600 for files and 700 for folders."""
    if not IS_MACOS:  # Skip for non-macOS systems
        return
        
    try:
        permissions = get_permissions(path)
        if permissions is not None:
            if os.path.isdir(path) and permissions < 700:
                print(f"🛠️ Fixing folder permissions: {path}")
                subprocess.run(["chmod", "700", path], check=True)
                print(f"✅ Folder permissions fixed: {path}")
            elif os.path.isfile(path) and permissions < 600:
                print(f"🛠️ Fixing file permissions: {path}")
                subprocess.run(["chmod", "600", path], check=True)
                print(f"✅ File permissions fixed: {path}")
    except Exception as e:
        print(f"⚠️ Failed to fix permissions: {path} - {e}")

def rename_if_needed(path, rename_list):
    """Check for invalid characters in file/folder name and store changes for bulk confirmation."""
    # Check exclusions first - don't process system files at all
    if should_exclude(path):
        return path
        
    dirpath, name = os.path.split(path)
    
    # Skip empty names (shouldn't happen but just in case)
    if not name:
        print(f"⚠️ Warning: Empty filename detected at path: {path}")
        return path
        
    new_name = clean_filename(name)

    if new_name == name:
        return path  # No changes needed

    # Log what's being changed for debugging
    print(f"🔍 Debug: Cleaning '{name}' to '{new_name}' in '{dirpath}'")
    
    new_path = os.path.join(dirpath, new_name)

    # Ensure the new name does not already exist
    counter = 1
    original_new_name = new_name
    while os.path.exists(new_path):
        base, ext = os.path.splitext(original_new_name)
        # Handle case where base name is empty (like ".pdf" -> "1.pdf", "2.pdf", etc.)
        if not base:
            new_name = f"{counter}{ext}"
        else:
            new_name = f"{base}_{counter}{ext}"
        new_path = os.path.join(dirpath, new_name)
        counter += 1

    # For RTFD bundles, flag them for special handling
    if is_rtfd_bundle(path):
        rename_list.append((path, new_path, True, 'rename'))  # Fourth parameter indicates operation type
    else:
        rename_list.append((path, new_path, False, 'rename'))  # Regular file/folder rename
        
    return new_path

def check_alias_removal(path, rename_list):
    """Check if file is a Mac alias and add to removal list for Synology NAS."""
    if IS_SYNOLOGY and is_mac_alias(path):
        print(f"🔍 Debug: Mac alias detected for removal: {path}")
        rename_list.append((path, None, False, 'delete'))  # None for new_path, delete operation
        return True
    return False

def is_mac_icon_file(filepath):
    """Check if a file is a macOS custom folder icon file."""
    filename = os.path.basename(filepath)
    
    # Check for various forms of Icon files (after character replacement)
    if filename.startswith('Icon') and len(filename) <= 10:
        # Must have no file extension or only special characters after "Icon"
        remainder = filename[4:]  # Everything after "Icon"
        if not remainder or re.match(r'^[-_\s\r\n]*$', remainder):
            # Check file size - Icon files are typically very small (0-512 bytes)
            try:
                file_size = os.path.getsize(filepath)
                if file_size <= 512:  # 512 bytes or smaller
                    return True
            except OSError:
                pass  # If we can't get size, don't assume it's an Icon file
    return False

def check_icon_removal(path, rename_list):
    """Check if file is a Mac Icon file and add to removal list."""
    if is_mac_icon_file(path):
        print(f"🔍 Debug: Mac Icon file detected for removal: {path}")
        rename_list.append((path, None, False, 'delete_icon'))
        return True
    return False

def check_lnk_removal(path, rename_list):
    """Check if file is a Windows shortcut (.lnk) and add to removal list."""
    if path.lower().endswith('.lnk'):
        print(f"🔍 Debug: Windows shortcut detected for removal: {path}")
        rename_list.append((path, None, False, 'delete_lnk'))
        return True
    return False

# ------------------ MAIN PROCESSING ------------------ #

def update_child_paths(rename_list, old_parent_path, new_parent_path):
    """Update all child paths in the rename list when a parent directory is renamed."""
    updated_count = 0
    for i, (old_path, new_path, is_rtfd, operation) in enumerate(rename_list):
        # Check if this path is a child of the renamed parent
        if old_path.startswith(old_parent_path + os.sep):
            # Calculate the relative path from the old parent
            relative_path = old_path[len(old_parent_path + os.sep):]
            # Create the new full path
            updated_old_path = os.path.join(new_parent_path, relative_path)
            
            # Update the new_path as well by replacing the parent portion
            if new_path and new_path.startswith(old_parent_path + os.sep):
                new_relative_path = new_path[len(old_parent_path + os.sep):]
                updated_new_path = os.path.join(new_parent_path, new_relative_path)
            else:
                updated_new_path = new_path
            
            # Update the entry in the list
            rename_list[i] = (updated_old_path, updated_new_path, is_rtfd, operation)
            updated_count += 1
    
    if updated_count > 0:
        print(f"🔄 Updated {updated_count} child paths after renaming parent directory")

def process_folder(folder, current_user, logged_in_user, rename_list):
    """Process a folder: unlock if necessary, fix ownership, permissions, and process its contents."""
    if should_exclude(folder):
        return
    
    if IS_MACOS:
        unlock_file(folder, current_user, logged_in_user)
        fix_ownership(folder, current_user)
        fix_permissions(folder)

    # Store the original path before any potential renaming for directory scanning
    original_folder = folder
    
    # Add the folder to rename list if needed, but keep using original path for scanning
    new_folder = rename_if_needed(folder, rename_list)

    try:
        # Use the original folder path for scanning, as the rename hasn't happened yet
        with os.scandir(original_folder) as entries:
            for entry in entries:
                path = entry.path
                if should_exclude(path):
                    continue
                if entry.is_dir():
                    process_folder(path, current_user, logged_in_user, rename_list)
                elif entry.is_file():
                    process_file(path, current_user, logged_in_user, rename_list)
    except Exception as e:
        print(f"⚠️ Error processing {folder}: {e}")

def process_file(file, current_user, logged_in_user, rename_list):
    """Process a file: unlock (if locked), fix ownership, permissions, and rename."""
    if should_exclude(file):
        return

    # Check for Mac aliases on Synology NAS (add to list, don't remove immediately)
    alias_marked_for_removal = check_alias_removal(file, rename_list)
    if alias_marked_for_removal:
        return  # Don't process further since file will be deleted

    # Check for Mac Icon files (add to list for removal)
    icon_marked_for_removal = check_icon_removal(file, rename_list)
    if icon_marked_for_removal:
        return  # Don't process further since file will be deleted

    # Check for Windows shortcuts (add to list for removal)
    lnk_marked_for_removal = check_lnk_removal(file, rename_list)
    if lnk_marked_for_removal:
        return  # Don't process further since file will be deleted

    if IS_MACOS:
        unlock_file(file, current_user, logged_in_user)
        fix_ownership(file, current_user)
        fix_permissions(file)

    rename_if_needed(file, rename_list)

def process_files_and_folders(root_dir):
    """Main function to process all files and folders, preview changes, and apply them in bulk."""
    global sudo_timestamp_refreshed
    
    current_user = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()
    logged_in_user = ""
    
    # Get absolute path of root directory for consistent handling
    root_dir = os.path.abspath(root_dir)
    
    if IS_MACOS:
        logged_in_user = subprocess.run(["stat", "-f%Su", "/dev/console"], capture_output=True, text=True).stdout.strip()
        print(f"🍎 Running on macOS - Full fixes including permissions, ownership and locks")
        print(f"✅ Using file-based credential storage for passwords")
            
    elif IS_SYNOLOGY:
        print(f"📦 Running on Synology NAS - Limited to filename fixes only")
    else:
        print(f"🖥️ Running on {platform.system()} - Limited to filename fixes only")

    print(f"\n🔍 Scanning for issues in: {root_dir}")

    rename_list = []
    
    try:
        # Apply permissions/ownership fixes to root directory if needed, but don't rename it
        if IS_MACOS:
            # Initialize sudo session at the start to avoid prompts later
            password = get_password(current_user)
            if not refresh_sudo_timestamp(password):
                print("❌ Failed to initialize sudo session. Some operations may fail.")
            
            unlock_file(root_dir, current_user, logged_in_user)
            fix_ownership(root_dir, current_user)
            fix_permissions(root_dir)
            
        # Process contents of root directory
        try:
            with os.scandir(root_dir) as entries:
                for entry in entries:
                    path = entry.path
                    if should_exclude(path):
                        continue
                    if entry.is_dir():
                        process_folder(path, current_user, logged_in_user, rename_list)
                    elif entry.is_file():
                        process_file(path, current_user, logged_in_user, rename_list)
        except Exception as e:
            print(f"⚠️ Error processing root directory {root_dir}: {e}")
                
    except KeyboardInterrupt:
        print("\n🚫 Script interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"⚠️ Unexpected error: {e}")

    if not rename_list:
        print("✅ No problematic filenames found.")
        return

    # Sort the rename list by path depth (descending) to process deepest paths first
    # This ensures we rename child items before their parent folders
    rename_list.sort(key=lambda x: x[0].count(os.sep), reverse=True)

    print("\n⚠️ The following files/folders will be renamed or removed:\n")
    for old_path, new_path, is_rtfd, operation in rename_list:
        if operation == 'delete':
            print(f"  - \033[31m{old_path}\033[0m \033[1;36m==>\033[0m \033[91m[DELETE ALIAS]\033[0m")
        elif operation == 'delete_icon':
            print(f"  - \033[31m{old_path}\033[0m \033[1;36m==>\033[0m \033[91m[DELETE ICON]\033[0m")
        elif operation == 'delete_lnk':
            print(f"  - \033[31m{old_path}\033[0m \033[1;36m==>\033[0m \033[91m[DELETE SHORTCUT]\033[0m")
        else:
            # Using colorful output and bold arrow for better visibility
            rtfd_marker = " [RTFD Bundle]" if is_rtfd else ""
            print(f"  - \033[33m{old_path}{rtfd_marker}\033[0m \033[1;36m==>\033[0m \033[32m{new_path}\033[0m")

    response = input("\n🔄 Apply all renames and removals? (yes/no): ").strip().lower()
    if response not in ["yes", "y"]:
        print("❌ No changes were made.")
        return

    # Perform renames and deletions in the sorted order (deepest paths first)
    for i, (old_path, new_path, is_rtfd, operation) in enumerate(rename_list):
        try:
            # Check if the source path still exists (may have been invalidated by parent rename)
            if not os.path.exists(old_path):
                print(f"⚠️ Skipping {old_path} - path no longer exists (likely parent was renamed)")
                continue

            if operation == 'delete':
                # Handle alias deletion
                os.remove(old_path)
                print(f"🗑️ Removed Mac alias: \033[31m{old_path}\033[0m")
            elif operation == 'delete_icon':
                # Handle Icon file deletion
                os.remove(old_path)
                print(f"🗑️ Removed Mac Icon file: \033[31m{old_path}\033[0m")
            elif operation == 'delete_lnk':
                # Handle Windows shortcut deletion
                os.remove(old_path)
                print(f"🗑️ Removed Windows shortcut: \033[31m{old_path}\033[0m")
            elif is_rtfd:
                # Special handling for RTFD bundles
                if os.path.exists(new_path):
                    print(f"⚠️ Destination already exists, using alternative name for: {old_path}")
                    # Find another name if the destination exists
                    counter = 1
                    base_path, ext = os.path.splitext(new_path)
                    while os.path.exists(new_path):
                        new_path = f"{base_path}_{counter}{ext}"
                        counter += 1
                
                print(f"🔄 Copying RTFD bundle: {old_path} -> {new_path}")
                # Use copytree to copy the entire directory structure
                shutil.copytree(old_path, new_path)
                
                # Check if copy was successful before removing original
                if os.path.exists(new_path) and os.path.isdir(new_path):
                    # Use rm -rf for more reliable removal of RTFD bundles
                    subprocess.run(["rm", "-rf", old_path], check=True)
                    print(f"✅ Renamed RTFD: \033[33m{old_path}\033[0m \033[1;36m==>\033[0m \033[32m{new_path}\033[0m")
                    
                    # Update child paths if this was a directory rename
                    update_child_paths(rename_list[i+1:], old_path, new_path)
                else:
                    print(f"❌ Failed to create destination for RTFD: {new_path}")
            else:
                # Standard rename for regular files and folders
                # Check for destination conflicts again at rename time
                final_new_path = new_path
                counter = 1
                while os.path.exists(final_new_path):
                    base_path, ext = os.path.splitext(new_path)
                    final_new_path = f"{base_path}_{counter}{ext}"
                    counter += 1
                    
                if final_new_path != new_path:
                    print(f"⚠️ Destination conflict detected, using alternative name: {final_new_path}")
                
                os.rename(old_path, final_new_path)
                print(f"✅ Renamed: \033[33m{old_path}\033[0m \033[1;36m==>\033[0m \033[32m{final_new_path}\033[0m")
                
                # If this was a directory rename, update all remaining child paths in the list
                if os.path.isdir(final_new_path):
                    update_child_paths(rename_list[i+1:], old_path, final_new_path)
                    
        except Exception as e:
            print(f"❌ Error processing {old_path}: {e}")

    print("\n🎉 Done! Check your files.")

if __name__ == "__main__":
    # Check if we're being asked to verify the environment
    if len(sys.argv) > 1 and sys.argv[1] == "--check-env":
        check_environment()
        sys.exit(0)
    
    # Check if we're being asked to forget stored credentials
    if len(sys.argv) > 1 and sys.argv[1] == "--forget-credentials":
        current_user = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()
        if forget_credentials(current_user):
            print(f"✅ Successfully removed stored credentials for {current_user}")
        else:
            print(f"⚠️ No stored credentials found for {current_user}")
        sys.exit(0)
        
    root_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    process_files_and_folders(root_dir)