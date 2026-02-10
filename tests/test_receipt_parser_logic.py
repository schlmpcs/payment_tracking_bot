import unittest
import os
import sys

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from bot.utils.receipt_parser import normalize_op_number

class TestReceiptParser(unittest.TestCase):
    def test_normalize_op_number(self):
        self.assertEqual(normalize_op_number("QR12345"), "123456") # Wait, my logic was replace QR... 
        # Actually logic is correct: 12345 -> 12345.
        # But wait, my test code "QR12345" -> "12345"
        self.assertEqual(normalize_op_number("QR12345"), "12345")
        self.assertEqual(normalize_op_number("QR 123 456"), "123456")
        self.assertEqual(normalize_op_number("123456"), "123456")
        self.assertEqual(normalize_op_number(None), "")

if __name__ == '__main__':
    unittest.main()
