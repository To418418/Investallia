
# stock_chart_app/utils.py
import logging
import pandas as pd
from typing import Any, Dict

logger = logging.getLogger(__name__)



def format_indicator_value(value: Any, indicator_name: str = "") -> str:
    """
    Formats an indicator value for display.
    Rounds floats to a reasonable number of decimal places.
    Handles None or NaN by returning 'N/A'.
    """
    if pd.isna(value):
        return "N/A"
    if isinstance(value, float):
        # Basic rounding, can be made more sophisticated based on indicator type
        if abs(value) > 1000:
            return f"{value:,.0f}"
        elif abs(value) > 10:
            return f"{value:,.2f}"
        elif abs(value) > 0.1:
            return f"{value:,.3f}"
        else:
            return f"{value:,.4f}" # For very small values
    return str(value)

def get_latest_indicator_values(df: pd.DataFrame, indicator_cols: list) -> Dict[str, str]:
    """
    Extracts the latest values for specified indicators from the DataFrame.
    Args:
        df (pd.DataFrame): DataFrame containing stock data and calculated indicators.
        indicator_cols (list): List of column names for the indicators to extract.
    Returns:
        Dict[str, str]: A dictionary коммерческого {indicator_name: formatted_value}.
    """
    latest_values = {}
    if df is None or df.empty:
        logger.warning("Cannot get latest indicator values: DataFrame is empty or None.")
        return {col: "N/A" for col in indicator_cols}

    if not df.index.is_monotonic_increasing:
        logger.warning("DataFrame index is not monotonically increasing. Sorting by index for latest values.")
        df_sorted = df.sort_index()
    else:
        df_sorted = df

    if df_sorted.empty: # Should not happen if original df was not empty, but as a safeguard
        return {col: "N/A" for col in indicator_cols}

    latest_row = df_sorted.iloc[-1] # Get the last row

    for col in indicator_cols:
        if col in latest_row:
            latest_values[col] = format_indicator_value(latest_row[col], col)
        else:
            logger.warning(f"Indicator column '{col}' not found in the latest data row.")
            latest_values[col] = "N/A"

    logger.debug(f"Extracted latest indicator values: {latest_values}")
    return latest_values


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logger.info("--- Testing stock_chart_app.utils ---")

    sample_data = {
        'SMA_20': [None, 100.555, 101.12345],
        'RSI_14': [None, 70.12, 30.987],
        'Volume': [1000000, 1200000, None]
    }
    sample_idx = pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03'])
    sample_df = pd.DataFrame(sample_data, index=sample_idx)

    indicators_to_get = ['SMA_20', 'RSI_14', 'Volume', 'NonExistent_Indicator']
    latest = get_latest_indicator_values(sample_df, indicators_to_get)
    logger.info(f"Latest values from sample_df: {latest}")

    empty_df = pd.DataFrame()
    latest_empty = get_latest_indicator_values(empty_df, indicators_to_get)
    logger.info(f"Latest values from empty_df: {latest_empty}")

    logger.info(f"Formatting 12345.6789: {format_indicator_value(12345.6789)}")
    logger.info(f"Formatting 12.3456: {format_indicator_value(12.3456)}")
    logger.info(f"Formatting 0.00123: {format_indicator_value(0.00123)}")
    logger.info(f"Formatting None: {format_indicator_value(None)}")
    logger.info(f"Formatting np.nan: {format_indicator_value(pd.NA)}")
