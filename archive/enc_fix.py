import os
import sys
import re
import unicodedata

# Define problematic character ranges:
# - ASCII control characters (0x00-0x1F, 0x7F)
# - Private Use Area Unicode (U+E000–U+F8FF)
# - Unicode combining diacritics (U+0300–U+036F) to fix `cc 81`
PROBLEM_CHAR_REGEX = re.compile(r"[\x00-\x1F\x7F\uE000-\uF8FF\u0300-\u036F]")

# Function to replace problematic characters with `-`
def clean_filename(name):
    normalized_name = unicodedata.normalize("NFC", name)  # Normalize to NFC
    cleaned_name = PROBLEM_CHAR_REGEX.sub("-", normalized_name)  # Replace problem characters with '-'
    return cleaned_name

# Function to ensure uniqueness (only if needed)
def ensure_unique_filename(directory, filename):
    """Check for conflicts **after** the user confirms renaming."""
    new_path = os.path.join(directory, filename)

    # If no conflict, return the original cleaned name
    if not os.path.exists(new_path):
        return filename

    # If conflict exists, append `_1`, `_2`, etc.
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(os.path.join(directory, f"{base}_{counter}{ext}")):
        counter += 1

    return f"{base}_{counter}{ext}"

# Function to rename files and folders (stores changes for confirmation)
def rename_entry(entry_path):
    dirpath, name = os.path.split(entry_path)
    new_name = clean_filename(name)

    # If the name didn't change, return None (no need to rename)
    if new_name == name:
        return None

    return (entry_path, os.path.join(dirpath, new_name))  # Store rename operation

# Recursive function to process directories and files
def process_directory(directory):
    entries_to_rename = []

    try:
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda e: e.is_file(), reverse=True):  # Process files before folders
                if entry.is_dir(follow_symlinks=False):
                    process_directory(entry.path)  # Recurse into subdirectories
                
                rename_result = rename_entry(entry.path)
                if rename_result:
                    entries_to_rename.append(rename_result)

    except PermissionError:
        print(f"⚠️ Permission denied: {directory} - Skipping")
    except FileNotFoundError:
        print(f"⚠️ File not found: {directory} - Skipping")
    except Exception as e:
        print(f"⚠️ Unexpected error processing {directory}: {e}")

    return entries_to_rename

# Main function to start processing
def main(root_directory):
    print(f"\n🔍 Scanning for problematic filenames in: {root_directory}\n")

    rename_list = process_directory(root_directory)

    if not rename_list:
        print("✅ No problematic filenames found.")
        return

    # Display detected issues BEFORE confirming changes
    print("\n⚠️ The following files/folders will be renamed:\n")
    for old, new in rename_list:
        print(f"  - {old} → {new}")

    response = input("\n🔄 Do you want to apply these renames? (yes/no): ").strip().lower()
    if response not in ["yes", "y"]:
        print("❌ No changes were made.")
        return

    print("\n🔄 Applying renames...\n")
    for old, new in rename_list:
        # Ensure final name is unique **only if necessary**
        dirpath, new_name = os.path.split(new)
        unique_name = ensure_unique_filename(dirpath, new_name)
        final_path = os.path.join(dirpath, unique_name)

        try:
            os.rename(old, final_path)
            print(f"✅ Renamed: {old} → {final_path}")
        except Exception as e:
            print(f"❌ Error renaming {old}: {e}")

    print("\n🎉 Done! Check your files.")

# Entry point
if __name__ == "__main__":
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = '.'

    main(root_dir)