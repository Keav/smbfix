import os
import sys
import re

# Define control characters (ASCII 0x00-0x1F and 0x7F)
CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x1F\x7F]")

# Get directory to scan (default: current directory)
search_path = sys.argv[1] if len(sys.argv) > 1 else "."

# Store problematic filenames
problem_files = []

# Scan recursively
for root, dirs, files in os.walk(search_path):
    for name in dirs + files:  # Check both files and folders
        if CONTROL_CHAR_REGEX.search(name):
            problem_files.append(os.path.join(root, name))

# If no issues, exit
if not problem_files:
    print(f"✅ No filenames with control characters found in '{search_path}'.")
    exit(0)

# Print detected issues
print("\n⚠️  Filenames containing control characters:\n")
for f in problem_files:
    print(f"  - {f}")

# Save detected issues to a log file
log_file = "problem_filenames.log"
with open(log_file, "w", encoding="utf-8") as log:
    for f in problem_files:
        log.write(f + "\n")

print(f"\n📄 Logged problematic filenames to: {log_file}")

# Prompt user for confirmation
response = input("\n🔄 Do you want to rename these files? (yes/no): ").strip().lower()

if response not in ["yes", "y"]:
    print("❌ No changes were made.")
    exit(0)

# Rename each problematic file
renamed_files = []
print("\n🔄 Renaming files...\n")
for old_path in problem_files:
    old_name = os.path.basename(old_path)
    new_name = CONTROL_CHAR_REGEX.sub("", old_name)  # Remove control characters
    new_path = os.path.join(os.path.dirname(old_path), new_name)

    try:
        os.rename(old_path, new_path)
        renamed_files.append(f"{old_path} → {new_path}")
        print(f"✅ Renamed: {old_path} → {new_path}")
    except Exception as e:
        print(f"❌ Error renaming {old_path}: {e}")

# Save renamed files to a log file
if renamed_files:
    renamed_log = "renamed_files.log"
    with open(renamed_log, "w", encoding="utf-8") as log:
        for entry in renamed_files:
            log.write(entry + "\n")
    print(f"\n📄 Logged renamed files to: {renamed_log}")

print("\n🎉 Done! Check your files.")