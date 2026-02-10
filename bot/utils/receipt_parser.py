"""
Receipt parsing utility for Kaspi payments
"""

import logging
import re
import os
import pandas as pd
import pdfplumber
from datetime import datetime
from typing import Optional, Dict, Set, List

logger = logging.getLogger(__name__)

def normalize_op_number(op_number: str) -> str:
    """
    Normalize operation number to remove 'QR' prefix and spaces
    Example: 'QR123 456' -> '123456'
    """
    if not op_number:
        return ""
    return str(op_number).replace("QR", "").replace(" ", "").strip()


def parse_kaspi_receipt(pdf_path: str) -> Optional[str]:
    """
    Parse Kaspi receipt PDF and extract operation number
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Operation number (digits only) or None if not found
    """
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
        
        # Look for "№ чека" followed by QR code or digits
        # Pattern: № чека QR14149426207 or just digits
        match = re.search(r"№\s*чека\s*(?:QR)?(\d+)", text, re.IGNORECASE)
        
        if match:
            op_number = match.group(1)
            return normalize_op_number(op_number)
            
        # Alternative pattern if "№ чека" is formatted differently or missing
        # Look for typical Kaspi operation number length (10-12 digits) preceded by QR
        match_alt = re.search(r"QR(\d{10,12})", text)
        if match_alt:
            return normalize_op_number(match_alt.group(1))

        logger.warning(f"Could not find operation number in {pdf_path}")
        return None
        
    except Exception as e:
        logger.error(f"Error parsing receipt {pdf_path}: {e}")
        return None


def load_kaspi_statement(file_path: str) -> Set[str]:
    """
    Load Kaspi statement and return set of operation numbers
    
    Args:
        file_path: Path to XLSX or CSV statement file
        
    Returns:
        Set of normalized operation numbers
    """
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
            # CSV usually has header on row 0, but let's be safe
        else:
            # Excel files might have metadata in top rows
            # Read first 30 rows without header to scan content
            df_raw = pd.read_excel(file_path, header=None, nrows=30)
            
            header_row_idx = None
            for idx, row in df_raw.iterrows():
                # Check if any cell in this row contains "Номер операции"
                row_str = row.astype(str).str.lower()
                if row_str.str.contains('номер операции').any() or row_str.str.contains('operation').any():
                    header_row_idx = idx
                    break
            
            if header_row_idx is not None:
                # Reload with correct header
                df = pd.read_excel(file_path, header=header_row_idx)
            else:
                # Fallback to default
                df = pd.read_excel(file_path)

        # Find column with operation numbers
        op_col = None
        for col in df.columns:
            if "номер операции" in str(col).lower() or "operation" in str(col).lower():
                op_col = col
                break
        
        if not op_col:
            # Last ditch attempt: check by index if J19 implies column 9 or something
            # But "J" is column 10 (0-indexed index 9).
            # If we failed to find by name, maybe the file format is very strict?
            logger.error("Could not find 'Номер операции' column in statement")
            
            logger.info(f"Columns found: {df.columns.tolist()}")
            return set()
            
        # Extract and normalize
        op_numbers = set()
        # Convert column to string to avoid float issues with ".0"
        for val in df[op_col].dropna().astype(str):
             # Remove .0 if it exists at end of string
            val_clean = val.replace('.0', '') if val.endswith('.0') else val
            norm_val = normalize_op_number(val_clean)
            if norm_val:
                op_numbers.add(norm_val)
                
        return op_numbers
        
    except Exception as e:
        logger.error(f"Error loading statement {file_path}: {e}")
        return set()
