"""
inspect_nmg.py - Quick look at what's in the NMG file
"""
import pandas as pd

# Load the Excel file
excel_file = 'boe-nmg-household-survey-data.xlsx'

# See what sheets are in it
xl = pd.ExcelFile(excel_file)
print("Sheets in the file:")
print(xl.sheet_names)
print()

# Look at the first sheet
first_sheet = xl.sheet_names[0]
print(f"Looking at sheet: {first_sheet}")
df = pd.read_excel(excel_file, sheet_name=first_sheet, nrows=5)

print("\nColumn names:")
print(df.columns.tolist())

print("\nFirst few rows:")
print(df.head())

print("\nData shape:")
print(f"Rows: {len(df)}, Columns: {len(df.columns)}")