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

# Save to a log file
log_file = "problem_filenames.log"
with open(log_file, "w", encoding="utf-8") as log:
    for f in problem_files:
        log.write(f + "\n")

print(f"\n📄 Logged problematic filenames to: {log_file}")
print("✅ No files were changed. Review the log and rename manually if needed.")
