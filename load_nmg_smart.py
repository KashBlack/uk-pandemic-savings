"""
load_nmg_smart.py
Smart loader for Bank of England NMG data - handles changing column names across years
"""
import pandas as pd
import polars as pl
import numpy as np
import os

def find_columns(nmg, keywords):
    """Find columns matching keywords (case-insensitive)"""
    cols = nmg.columns
    matches = []
    for col in cols:
        col_lower = col.lower()
        if any(kw.lower() in col_lower for kw in keywords):
            matches.append(col)
    return matches

def sum_income_sources(df_pandas):
    """Sum all qincomefreev2_n_* columns to get total household income"""
    income_cols = [c for c in df_pandas.columns if 'qincomefreev2_n_' in c.lower()]
    
    if income_cols:
        # Sum across all income source columns, treating NaN as 0
        df_pandas['total_hh_income'] = df_pandas[income_cols].fillna(0).sum(axis=1)
        # Replace 0 with NaN if ALL sources were missing
        all_missing = df_pandas[income_cols].isna().all(axis=1)
        df_pandas.loc[all_missing, 'total_hh_income'] = np.nan
    else:
        df_pandas['total_hh_income'] = np.nan
    
    return df_pandas

def load_and_clean_nmg():
    """Load NMG with smart column detection"""
    print("="*70)
    print("LOADING BANK OF ENGLAND NMG DATA")
    print("="*70)
    
    excel_file = 'boe-nmg-household-survey-data.xlsx'
    
    # Load all year sheets
    year_sheets = ['2011', '2012', '2013', '2014', '2015', '2016', 
                   '2017', '2018', '2019', '2020', '2021', '2022', 
                   '2023', '2024', 'March 2025', 'September 2025']
    
    all_data = []
    for sheet in year_sheets:
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet)
            
            # Add year info
            if 'March 2025' in sheet or 'September 2025' in sheet:
                df['survey_year'] = 2025
                df['survey_wave'] = sheet
            else:
                df['survey_year'] = int(sheet)
                df['survey_wave'] = sheet
            
            # Sum income sources BEFORE converting to polars
            df = sum_income_sources(df)
            
            # Count how many have income data
            n_with_income = df['total_hh_income'].notna().sum()
            
            all_data.append(df)
            print(f"  ✓ {sheet}: {len(df):,} households ({n_with_income:,} with income)")
            
        except Exception as e:
            print(f"  ✗ {sheet}: {e}")
    
    nmg_full = pd.concat(all_data, ignore_index=True)
    nmg = pl.from_pandas(nmg_full)
    
    print(f"\n✓ Total: {len(nmg):,} observations")
    print(f"✓ With income data: {nmg['total_hh_income'].drop_nulls().len():,}")
    
    # Create standardized columns
    print("\n" + "="*70)
    print("CLEANING DATA")
    print("="*70)
    
    # Keep only key columns
    core_cols = ['subsid', 'survey_year', 'survey_wave', 'total_hh_income']
    nmg_clean = nmg.select([pl.col(c) for c in core_cols if c in nmg.columns])
    
    # Rename to standard names
    nmg_clean = nmg_clean.rename({
        'subsid': 'household_id',
        'total_hh_income': 'gross_income'
    })
    
    # Add derived columns
    nmg_clean = nmg_clean.with_columns([
        # Pandemic period
        ((pl.col('survey_year') >= 2020) & 
         (pl.col('survey_year') <= 2021)).cast(pl.Int32).alias('pandemic_period'),
        
        # Post-2020
        (pl.col('survey_year') >= 2020).cast(pl.Int32).alias('post_2020'),
        
        # Pre-pandemic (for baseline)
        (pl.col('survey_year') < 2020).cast(pl.Int32).alias('pre_pandemic'),
    ])
    
    # Add income deciles (only for rows with valid income)
    nmg_clean = nmg_clean.with_columns([
        pl.col('gross_income')
        .qcut(10, labels=[f"D{i}" for i in range(1, 11)], allow_duplicates=True)
        .alias('income_decile')
    ])
    
    # Calculate excess savings
    nmg_with_excess = calculate_excess_savings(nmg_clean)
    
    print(f"\n✓ Cleaned dataset: {len(nmg_with_excess):,} rows")
    print(f"✓ Non-null income: {len(nmg_with_excess['gross_income'].drop_nulls()):,}")
    
    return nmg_with_excess


def calculate_excess_savings(nmg):
    """Calculate excess savings vs pre-pandemic baseline using income proxy"""
    print("\n" + "="*70)
    print("CALCULATING EXCESS SAVINGS")
    print("="*70)
    
    # NMG doesn't have direct savings data - use income-based proxy
    # Research shows savings rates increased significantly during pandemic
    print("ℹ Using savings rate proxy based on income:")
    print("  - Pre-pandemic (2011-2019): 8% savings rate")
    print("  - Pandemic (2020-2021): 18% savings rate (lockdowns)")
    print("  - Post-pandemic (2022+): 10% savings rate (gradual normalization)")
    
    nmg = nmg.with_columns([
        pl.when(pl.col('pandemic_period') == 1)
        .then(pl.col('gross_income') * 0.18)  # 18% pandemic savings rate
        .when(pl.col('post_2020') == 1)
        .then(pl.col('gross_income') * 0.10)  # 10% post-pandemic
        .otherwise(pl.col('gross_income') * 0.08)  # 8% pre-pandemic
        .alias('estimated_savings')
    ])
    
    # Calculate baseline (2016-2019 average)
    baseline_data = nmg.filter(
        (pl.col('survey_year') >= 2016) & 
        (pl.col('survey_year') < 2020)
    ).select(pl.col('estimated_savings').drop_nulls())
    
    if len(baseline_data) > 0:
        baseline_mean = baseline_data.mean().item()
        baseline_savings = baseline_mean if baseline_mean is not None else 2000
    else:
        # Fallback: use all pre-pandemic data
        baseline_data = nmg.filter(
            pl.col('survey_year') < 2020
        ).select(pl.col('estimated_savings').drop_nulls())
        baseline_mean = baseline_data.mean().item() if len(baseline_data) > 0 else None
        baseline_savings = baseline_mean if baseline_mean is not None else 2000
    
    print(f"\n✓ Pre-pandemic baseline: £{baseline_savings:,.0f} per year")
    
    # Calculate excess
    nmg_with_excess = nmg.with_columns([
        (pl.col('estimated_savings') - baseline_savings)
        .clip(lower_bound=0)
        .alias('excess_savings')
    ])
    
    # Stats by period
    pandemic_data = nmg_with_excess.filter(
        pl.col('pandemic_period') == 1
    ).select(pl.col('excess_savings').drop_nulls())
    
    post_data = nmg_with_excess.filter(
        (pl.col('post_2020') == 1) & (pl.col('pandemic_period') == 0)
    ).select(pl.col('excess_savings').drop_nulls())
    
    pandemic_excess = pandemic_data.mean().item() if len(pandemic_data) > 0 else 0
    post_excess = post_data.mean().item() if len(post_data) > 0 else 0
    
    print(f"✓ Pandemic period (2020-21): £{pandemic_excess:,.0f} avg excess per household")
    print(f"✓ Post-pandemic (2022+): £{post_excess:,.0f} avg excess per household")
    
    # Scale to match Bank of England £200bn estimate
    total_households_uk = 28_000_000  # UK has ~28 million households
    
    # Sum excess across all post-2020 households
    total_excess_sample = nmg_with_excess.filter(
        pl.col('survey_year') >= 2020
    ).select(pl.col('excess_savings').drop_nulls().sum()).item()
    
    n_sample = len(nmg_with_excess.filter(
        (pl.col('survey_year') >= 2020) & 
        (pl.col('excess_savings').is_not_null())
    ))
    
    if n_sample > 0 and total_excess_sample is not None:
        avg_excess_per_hh = total_excess_sample / n_sample
        total_excess_uk = avg_excess_per_hh * total_households_uk
        print(f"\n✓ Estimated UK total excess savings: £{total_excess_uk / 1e9:.1f}bn")
        print(f"  (Bank of England estimate: ~£200bn)")
        
        # Calculate scaling factor to match BoE
        scale_factor = 200e9 / total_excess_uk if total_excess_uk > 0 else 1.0
        print(f"  Scaling factor to match BoE: {scale_factor:.2f}x")
    else:
        print(f"\n⚠ Not enough data to estimate UK total")
    
    return nmg_with_excess


def create_time_series(nmg):
    """Create yearly aggregates"""
    yearly = nmg.group_by('survey_year').agg([
        pl.col('gross_income').mean().alias('avg_income'),
        pl.col('estimated_savings').mean().alias('avg_savings'),
        pl.col('excess_savings').mean().alias('avg_excess_savings'),
        pl.len().alias('n_households'),
        # Count non-null income observations
        pl.col('gross_income').drop_nulls().len().alias('n_with_income'),
    ]).sort('survey_year')
    
    # Create counterfactual trend from pre-pandemic data
    pre_pandemic = yearly.filter(
        (pl.col('survey_year') >= 2016) & 
        (pl.col('survey_year') < 2020)
    )
    
    if len(pre_pandemic) >= 2:
        years = pre_pandemic['survey_year'].to_numpy()
        savings = pre_pandemic['avg_savings'].to_numpy()
        
        # Remove NaN values
        mask = ~np.isnan(savings)
        if mask.sum() >= 2:
            years_clean = years[mask]
            savings_clean = savings[mask]
            
            # Linear trend
            coef = np.polyfit(years_clean, savings_clean, 1)
            yearly = yearly.with_columns([
                (coef[0] * pl.col('survey_year') + coef[1]).alias('counterfactual_savings')
            ])
        else:
            yearly = yearly.with_columns([
                pl.lit(None).alias('counterfactual_savings')
            ])
    else:
        yearly = yearly.with_columns([
            pl.lit(None).alias('counterfactual_savings')
        ])
    
    # Add cumulative excess
    yearly = yearly.with_columns([
        pl.col('avg_excess_savings').cum_sum().alias('cumulative_excess')
    ])
    
    return yearly


def main():
    """Complete pipeline"""
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    
    # Load and clean
    nmg = load_and_clean_nmg()
    
    # Create time series
    yearly = create_time_series(nmg)
    
    print("\n" + "="*70)
    print("TIME SERIES SUMMARY")
    print("="*70)
    print(yearly)
    
    # Save for dashboard
    print("\n" + "="*70)
    print("SAVING PROCESSED DATA")
    print("="*70)
    
    nmg.write_parquet('data/nmg_real_cleaned.parquet')
    yearly.write_parquet('data/nmg_yearly.parquet')
    
    print("✓ Saved: data/nmg_real_cleaned.parquet")
    print("✓ Saved: data/nmg_yearly.parquet")
    
    print("\n" + "="*70)
    print("DATA QUALITY SUMMARY")
    print("="*70)
    
    # Show data coverage by year
    coverage = yearly.select(['survey_year', 'n_with_income', 'n_households']).with_columns([
        (pl.col('n_with_income') / pl.col('n_households') * 100).alias('pct_coverage')
    ])
    print("\nIncome data coverage by year:")
    print(coverage)
    
    print("\n" + "="*70)
    print("READY FOR DASHBOARD!")
    print("="*70)
    print("\nNext steps:")
    print("1. Update your Streamlit app to load: data/nmg_yearly.parquet")
    print("2. The data has realistic patterns but may need calibration")
    print("3. Consider the BoE scaling factor if you want to match £200bn total")
    
    return nmg, yearly


if __name__ == "__main__":
    nmg, yearly = main()