# stock_chart_app/indicators/volume_indicators.py
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from stock_chart_app.plot_utils import add_line_trace # 修正: stock_chart_app からインポート

# --- Volume (既存) ---
def add_volume_trace(fig, df, row=2, col=1, **params):
    if 'Volume' in df.columns and not df['Volume'].isnull().all():
        colors = ['green' if df['Close'].iloc[i] >= df['Open'].iloc[i] else 'red' for i in range(len(df))]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='出来高', marker_color=colors, opacity=0.5), row=row, col=col)

# --- Volume SMA (既存) ---
def calculate_volume_sma(df_orig, window=20):
    df = df_orig.copy()
    if 'Volume' in df.columns:
        df[f'Volume_SMA_{window}'] = df['Volume'].rolling(window=window, min_periods=1).mean()
    return df

def add_volume_sma_trace(fig, df, window=20, color='blue', row=2, col=1, **params):
    if f'Volume_SMA_{window}' in df.columns:
        add_line_trace(fig, df, f'Volume_SMA_{window}', f'出来高SMA({window})', color=color, width=1.5, row=row, col=col, opacity=0.8)

# --- On-Balance Volume (OBV) ---
def calculate_obv(df_orig):
    df = df_orig.copy()
    price_change_sign = np.sign(df['Close'].diff()).fillna(0)
    df['obv'] = (price_change_sign * df['Volume']).cumsum()
    return df

def add_obv_trace(fig, df, row=2, col=1, **params):
    add_line_trace(fig, df, 'obv', 'OBV', color='blue', row=row, col=col)

# --- Money Flow Index (MFI) ---
def calculate_mfi(df_orig, window=14):
    df = df_orig.copy()
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    raw_money_flow = typical_price * df['Volume']
    money_flow_direction = typical_price.diff()
    positive_money_flow = raw_money_flow.where(money_flow_direction > 0, 0).rolling(window=window).sum()
    negative_money_flow = raw_money_flow.where(money_flow_direction < 0, 0).rolling(window=window).sum()
    money_flow_ratio = positive_money_flow / negative_money_flow.replace(0, np.nan)
    mfi = 100 - (100 / (1 + money_flow_ratio))
    df[f'mfi_{window}'] = mfi.replace([np.inf, -np.inf], 100).fillna(50)
    return df

def add_mfi_trace(fig, df, window=14, row=2, col=1, **params):
    add_line_trace(fig, df, f'mfi_{window}', f'MFI({window})', color='green', row=row, col=col)
    fig.add_hline(y=80, line_dash="dash", line_color="red", opacity=0.4, row=row, col=col, line_width=1)
    fig.add_hline(y=20, line_dash="dash", line_color="green", opacity=0.4, row=row, col=col, line_width=1)
    fig.update_yaxes(range=[0, 100], row=row, col=col)

# --- Volume Weighted Average Price (VWAP) ---
def calculate_vwap(df_orig, reset_daily=True):
    df = df_orig.copy()
    tp_vol = ((df['High'] + df['Low'] + df['Close']) / 3) * df['Volume']
    vol = df['Volume']
    if reset_daily and isinstance(df.index, pd.DatetimeIndex):
        cum_tp_vol = tp_vol.groupby(df.index.date).cumsum()
        cum_vol = vol.groupby(df.index.date).cumsum()
    else:
        cum_tp_vol = tp_vol.cumsum()
        cum_vol = vol.cumsum()
    df['vwap'] = (cum_tp_vol / cum_vol.replace(0, np.nan)).fillna(method='ffill')
    return df

def add_vwap_trace(fig, df, row=1, col=1, **params):
    add_line_trace(fig, df, 'vwap', 'VWAP', color='magenta', width=1.5, dash='longdash', row=row, col=col)

# --- Chaikin Money Flow (CMF) ---
def calculate_cmf(df_orig, window=20):
    df = df_orig.copy()
    mf_multiplier = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low']).replace(0, np.nan)
    mf_volume = mf_multiplier.fillna(0) * df['Volume']
    cmf = mf_volume.rolling(window=window).sum() / df['Volume'].rolling(window=window).sum().replace(0, np.nan)
    df[f'cmf_{window}'] = cmf.fillna(0)
    return df

def add_cmf_trace(fig, df, window=20, row=2, col=1, **params):
    add_line_trace(fig, df, f'cmf_{window}', f'CMF({window})', color='blueviolet', row=row, col=col)
    fig.add_hline(y=0, line_dash="dash", line_color="grey", opacity=0.5, row=row, col=col, line_width=1)
    fig.update_yaxes(range=[-1, 1], row=row, col=col)

# --- Ease of Movement (EOM) ---
def calculate_eom(df_orig, window=14, divisor=100000000.0):
    df = df_orig.copy()
    mid_point_move = ((df['High'] + df['Low']) / 2).diff(1)
    box_ratio = (df['Volume'] / divisor) / (df['High'] - df['Low']).replace(0, np.nan)
    one_period_eom = mid_point_move / box_ratio.replace(0, np.nan)
    df[f'eom_{window}'] = one_period_eom.rolling(window=window).mean().fillna(0)
    return df

def add_eom_trace(fig, df, window=14, row=2, col=1, **params):
    add_line_trace(fig, df, f'eom_{window}', f'EOM({window})', color='brown', row=row, col=col)
    fig.add_hline(y=0, line_dash="dash", line_color="grey", opacity=0.5, row=row, col=col, line_width=1)
