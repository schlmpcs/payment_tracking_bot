import sys
print(f"Path: {sys.path}")
try:
    import pdfplumber
    print("pdfplumber: OK")
except ImportError as e:
    print(f"pdfplumber: FAIL - {e}")

try:
    import pandas
    print("pandas: OK")
except ImportError as e:
    print(f"pandas: FAIL - {e}")

try:
    # Adjust path if needed
    current_dir = 'd:\\Spotify\\spotify_family_automatization-fresh-start'
    if current_dir not in sys.path:
        sys.path.append(current_dir)
        
    from bot.utils.receipt_parser import parse_kaspi_receipt
    print("bot.utils.receipt_parser: OK")
except ImportError as e:
    print(f"bot.utils.receipt_parser: FAIL - {e}")
except Exception as e:
    print(f"bot.utils.receipt_parser: FAIL (Other) - {e}")
