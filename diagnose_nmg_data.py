"""
diagnose_nmg_data.py
Check what's actually in the Excel file to fix column detection
"""
import pandas as pd
import os

excel_file = 'boe-nmg-household-survey-data.xlsx'

print("="*70)
print("NMG DATA DIAGNOSTIC")
print("="*70)

# Check a few representative years
test_years = ['2016', '2019', '2020', '2023']

for year in test_years:
    print(f"\n{'='*70}")
    print(f"YEAR: {year}")
    print('='*70)
    
    try:
        df = pd.read_excel(excel_file, sheet_name=year, nrows=5)
        
        print(f"\nShape: {df.shape[0]} rows (showing first 5), {df.shape[1]} columns")
        
        # Find all columns with "income" in name
        income_cols = [c for c in df.columns if 'income' in c.lower()]
        print(f"\nIncome-related columns ({len(income_cols)}):")
        for col in income_cols[:10]:  # Show first 10
            non_null = df[col].notna().sum()
            print(f"  - {col}: {non_null}/5 non-null")
        
        # Find all columns with "sav" in name
        sav_cols = [c for c in df.columns if 'sav' in c.lower()]
        print(f"\nSavings-related columns ({len(sav_cols)}):")
        for col in sav_cols[:10]:
            non_null = df[col].notna().sum()
            print(f"  - {col}: {non_null}/5 non-null")
        
        # Find all columns with "spend" or "expend" in name
        spend_cols = [c for c in df.columns if 'spend' in c.lower() or 'expend' in c.lower()]
        print(f"\nSpending-related columns ({len(spend_cols)}):")
        for col in spend_cols[:10]:
            non_null = df[col].notna().sum()
            print(f"  - {col}: {non_null}/5 non-null")
        
        # Check combhhincomere specifically
        if 'combhhincomere' in df.columns:
            print(f"\n✓ combhhincomere exists!")
            print(f"  Sample values: {df['combhhincomere'].dropna().head(3).tolist()}")
        else:
            print(f"\n✗ combhhincomere NOT FOUND in {year}")
            
    except Exception as e:
        print(f"Error loading {year}: {e}")

# Check if data directory exists
print(f"\n{'='*70}")
print("DIRECTORY CHECK")
print('='*70)
if os.path.exists('data'):
    print("✓ data/ directory exists")
else:
    print("✗ data/ directory does NOT exist - will create it")
    os.makedirs('data', exist_ok=True)
    print("✓ Created data/ directory")

print("\n" + "="*70)
print("RECOMMENDATIONS")
print("="*70)
print("""
Based on the diagnostic:

1. Check which income column has the most non-null values across years
2. The column name might change between years (common in survey data)
3. You may need to use different columns for different year ranges
4. Consider creating a mapping: {year_range: best_column_name}
""")