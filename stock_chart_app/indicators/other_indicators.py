# stock_chart_app/indicators/other_indicators.py
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from stock_chart_app.plot_utils import add_line_trace # 修正: stock_chart_app からインポート

# --- Average True Range (ATR) ---
def calculate_atr(df_orig, window=14):
    """ATRを計算し、DataFrameに'atr_WINDOW'列として追加します。"""
    df = df_orig.copy()
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1, skipna=False)
    # Wilder's smoothing
    df[f'atr_{window}'] = tr.ewm(com=window - 1, adjust=False).mean()
    return df

def add_atr_trace(fig, df, window=14, row=2, col=1, **params):
    """ATRをサブプロットに描画します。"""
    add_line_trace(fig, df, f'atr_{window}', f'ATR({window})', color='chocolate', row=row, col=col)

# --- Standard Deviation (Volatility) ---
def calculate_std_dev(df_orig, window=20):
    """終値の標準偏差を計算します。"""
    df = df_orig.copy()
    df[f'std_dev_{window}'] = df['Close'].rolling(window=window).std(ddof=0)
    return df

def add_std_dev_trace(fig, df, window=20, row=2, col=1, **params):
    """標準偏差をサブプロットに描画します。"""
    add_line_trace(fig, df, f'std_dev_{window}', f'Std Dev({window})', color='olivedrab', row=row, col=col)

# --- Pivot Points ---
def calculate_pivot_points(df_orig):
    """
    前日のデータを使用して、各日のピボットポイントを計算します。
    日足データでの使用を想定しています。
    """
    df = df_orig.copy()
    prev_high = df['High'].shift(1)
    prev_low = df['Low'].shift(1)
    prev_close = df['Close'].shift(1)

    p = (prev_high + prev_low + prev_close) / 3
    r1 = (2 * p) - prev_low
    s1 = (2 * p) - prev_high
    r2 = p + (prev_high - prev_low)
    s2 = p - (prev_high - prev_low)
    r3 = prev_high + 2 * (p - prev_low)
    s3 = prev_low - 2 * (prev_high - p)

    df['pivot'] = p
    df['r1'], df['s1'] = r1, s1
    df['r2'], df['s2'] = r2, s2
    df['r3'], df['s3'] = r3, s3
    return df

def add_pivot_points_traces(fig, df, row=1, col=1, **params):
    """ピボットポイントをメインチャートに描画します。"""
    add_line_trace(fig, df, 'pivot', 'Pivot', color='gold', width=1, dash='dot', row=row, col=col)
    add_line_trace(fig, df, 'r1', 'R1', color='lightgreen', width=1, dash='dot', row=row, col=col)
    add_line_trace(fig, df, 's1', 'S1', color='lightcoral', width=1, dash='dot', row=row, col=col)
    add_line_trace(fig, df, 'r2', 'R2', color='limegreen', width=1, dash='dash', row=row, col=col)
    add_line_trace(fig, df, 's2', 'S2', color='red', width=1, dash='dash', row=row, col=col)
    add_line_trace(fig, df, 'r3', 'R3', color='darkgreen', width=1, dash='longdash', row=row, col=col)
    add_line_trace(fig, df, 's3', 'S3', color='darkred', width=1, dash='longdash', row=row, col=col)
