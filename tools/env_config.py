"""Read local credentials consistently for deployment and publishing.

Supports KEY=value, export KEY=value, and matching single/double quotes.
Values are literal (no shell expansion); the last duplicate wins, then the
process environment takes precedence. Never print the resulting dictionary.
"""

import os


def load_dotenv(path):
    values = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if separator and key and not key.startswith("#"):
                if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                    value = value[1:-1]
                values[key] = value
    values.update(os.environ)
    return values
