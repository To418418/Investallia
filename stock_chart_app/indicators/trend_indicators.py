# stock_chart_app/indicators/trend_indicators.py

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from stock_chart_app.plot_utils import add_line_trace # 修正: stock_chart_app からインポート

# --- SMA / EMA (既存 + 統合) ---
def calculate_sma(df_orig, window=20):
    df = df_orig.copy()
    df[f'SMA_{window}'] = df['Close'].rolling(window=window, min_periods=1).mean()
    return df

def add_sma_trace(fig, df, window=20, color='orange', row=1, col=1):
    add_line_trace(fig, df, f'SMA_{window}', f'SMA({window})', color=color, row=row, col=col)

def calculate_ema(df_orig, window=20):
    df = df_orig.copy()
    df[f'EMA_{window}'] = df['Close'].ewm(span=window, adjust=False, min_periods=1).mean()
    return df

def add_ema_trace(fig, df, window=20, color='purple', row=1, col=1):
    add_line_trace(fig, df, f'EMA_{window}', f'EMA({window})', color=color, row=row, col=col)

# --- Bollinger Bands (既存 + 統合) ---
def calculate_bollinger_bands(df_orig, window=20, nbdev=2):
    df = df_orig.copy()
    # ユーザー提供コードのnbdevは一旦無視し、2σと3σを両方計算する仕様に統一
    mid_band_col = f'BB_Mid_{window}'
    df[mid_band_col] = df['Close'].rolling(window=window).mean()
    std_dev = df['Close'].rolling(window=window).std(ddof=0)
    df[f'BB_Upper_2std_{window}'] = df[mid_band_col] + (std_dev * 2)
    df[f'BB_Lower_2std_{window}'] = df[mid_band_col] - (std_dev * 2)
    df[f'BB_Upper_3std_{window}'] = df[mid_band_col] + (std_dev * 3) # 3σも追加
    df[f'BB_Lower_3std_{window}'] = df[mid_band_col] - (std_dev * 3) # 3σも追加
    return df

def add_bollinger_bands_traces(fig, df, window=20, row=1, col=1):
    add_line_trace(fig, df, f'BB_Mid_{window}', f'BB Mid({window})', color='cyan', width=1, row=row, col=col)
    add_line_trace(fig, df, f'BB_Upper_2std_{window}', f'+2σ', color='skyblue', width=1, dash='dash', row=row, col=col, opacity=0.8)
    add_line_trace(fig, df, f'BB_Lower_2std_{window}', f'-2σ', color='skyblue', width=1, dash='dash', row=row, col=col, opacity=0.8)
    add_line_trace(fig, df, f'BB_Upper_3std_{window}', f'+3σ', color='lightsteelblue', width=1, dash='dot', row=row, col=col, opacity=0.7)
    add_line_trace(fig, df, f'BB_Lower_3std_{window}', f'-3σ', color='lightsteelblue', width=1, dash='dot', row=row, col=col, opacity=0.7)

# --- Ichimoku Kinko Hyo (既存 + 統合) ---
# def calculate_ichimoku(df_orig, tenkan_period=9, kijun_period=26, senkou_b_period=52, chikou_period=26, senkou_shift=26):
#     df = df_orig.copy()
#     high, low, close = df['High'], df['Low'], df['Close']
#     tenkan_sen = (high.rolling(window=tenkan_period).max() + low.rolling(window=tenkan_period).min()) / 2
#     kijun_sen = (high.rolling(window=kijun_period).max() + low.rolling(window=kijun_period).min()) / 2
#     senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(senkou_shift -1) # Plotly用にシフトを調整
#     senkou_span_b = ((high.rolling(window=senkou_b_period).max() + low.rolling(window=senkou_b_period).min()) / 2).shift(senkou_shift -1) # Plotly用にシフトを調整
#     chikou_span = close.shift(-(chikou_period -1)) # Plotly用にシフトを調整
#     df['tenkan_sen'], df['kijun_sen'], df['senkou_span_a'], df['senkou_span_b'], df['chikou_span'] = tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span
#     return df

def calculate_ichimoku(df_orig, tenkan_period=9, kijun_period=26, senkou_b_period=52, chikou_period=26, senkou_shift=26):
    df = df_orig.copy()
    high, low, close = df['High'], df['Low'], df['Close']

    tenkan_sen = (high.rolling(window=tenkan_period).max() + low.rolling(window=tenkan_period).min()) / 2
    kijun_sen = (high.rolling(window=kijun_period).max() + low.rolling(window=kijun_period).min()) / 2

    # 先行スパンA: 26期間未来へシフト
    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(senkou_shift)
    # 先行スパンB: 26期間未来へシフト
    senkou_span_b = ((high.rolling(window=senkou_b_period).max() + low.rolling(window=senkou_b_period).min()) / 2).shift(senkou_shift)
    # 遅行スパン: 26期間過去へシフト
    chikou_span = close.shift(-chikou_period)

    df['tenkan_sen'], df['kijun_sen'], df['senkou_span_a'], df['senkou_span_b'], df['chikou_span'] = tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span
    return df

def add_ichimoku_traces(fig, df, row=1, col=1):
    add_line_trace(fig, df, 'tenkan_sen', '転換線', color='blue', width=1, row=row, col=col)
    add_line_trace(fig, df, 'kijun_sen', '基準線', color='red', width=1.2, row=row, col=col)
    add_line_trace(fig, df, 'chikou_span', '遅行スパン', color='green', width=1.5, dash='dashdot', row=row, col=col)
    fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_a'], line_color='rgba(0,0,0,0)', showlegend=False, hoverinfo='skip'), row=row, col=col)
    fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_b'], line_color='rgba(0,0,0,0)', name='雲 (Kumo)', fill='tonexty', fillcolor='rgba(230, 230, 250, 0.4)', showlegend=True, hoverinfo='skip'), row=row, col=col)

# --- MACD (既存 + 統合) ---
def calculate_macd(df_orig, fast_period=12, slow_period=26, signal_period=9):
    df = df_orig.copy()
    ema_fast = df['Close'].ewm(span=fast_period, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=slow_period, adjust=False).mean()
    df['MACD_Line'] = ema_fast - ema_slow
    df['MACD_Signal'] = df['MACD_Line'].ewm(span=signal_period, adjust=False).mean()
    df['MACD_Hist'] = df['MACD_Line'] - df['MACD_Signal']
    return df

def add_macd_traces(fig, df, row=2, col=1, **params):
    add_line_trace(fig, df, 'MACD_Line', 'MACD', color='blue', row=row, col=col)
    add_line_trace(fig, df, 'MACD_Signal', 'Signal', color='red', dash='dash', row=row, col=col)
    colors = ['green' if val >= 0 else 'red' for val in df['MACD_Hist']]
    fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], name='Histogram', marker_color=colors, opacity=0.6), row=row, col=col)

# --- Parabolic SAR ---
def calculate_parabolic_sar(df_orig, initial_af=0.02, af_increment=0.02, max_af=0.2):
    df = df_orig.copy()
    high, low = df['High'], df['Low']
    length = len(df)
    sar = pd.Series([np.nan] * length, index=df.index)
    if length < 2: return df.assign(psar=sar)
    trend = 1 # 1 for uptrend, -1 for downtrend
    ep = high.iloc[0]
    af = initial_af
    sar.iloc[0] = low.iloc[0]

    for i in range(1, length):
        prev_sar, prev_ep, prev_af, prev_trend = sar.iloc[i-1], ep, af, trend
        if prev_trend == 1:
            current_sar = prev_sar + prev_af * (prev_ep - prev_sar)
            if high.iloc[i] > prev_ep:
                ep = high.iloc[i]
                af = min(prev_af + af_increment, max_af)
            if current_sar > low.iloc[i]: # Trend reversal
                trend = -1; ep = low.iloc[i]; af = initial_af
                sar.iloc[i] = max(prev_ep, high.iloc[i])
            else: sar.iloc[i] = current_sar
        else: # Downtrend
            current_sar = prev_sar + prev_af * (prev_ep - prev_sar)
            if low.iloc[i] < prev_ep:
                ep = low.iloc[i]
                af = min(prev_af + af_increment, max_af)
            if current_sar < high.iloc[i]: # Trend reversal
                trend = 1; ep = high.iloc[i]; af = initial_af
                sar.iloc[i] = min(prev_ep, low.iloc[i])
            else: sar.iloc[i] = current_sar
    df['psar'] = sar
    return df

def add_parabolic_sar_trace(fig, df, row=1, col=1, **params):
    fig.add_trace(go.Scatter(x=df.index, y=df['psar'], name='Parabolic SAR', mode='markers', marker=dict(color='black', size=3)), row=row, col=col)

# --- Moving Average Envelope ---
def calculate_ma_envelope(df_orig, window=20, percentage=0.025, ma_type='sma'):
    df = df_orig.copy()
    if ma_type.lower() == 'sma': middle_band = df['Close'].rolling(window=window).mean()
    else: middle_band = df['Close'].ewm(span=window, adjust=False).mean()
    df[f'envelope_upper_{window}'] = middle_band * (1 + percentage)
    df[f'envelope_lower_{window}'] = middle_band * (1 - percentage)
    df[f'envelope_mid_{window}'] = middle_band
    return df

def add_ma_envelope_traces(fig, df, window=20, row=1, col=1, **params):
    add_line_trace(fig, df, f'envelope_upper_{window}', f'Env Up({window}d, {params.get("percentage", 0.025):.1%})', color='fuchsia', width=1, dash='dot', row=row, col=col)
    add_line_trace(fig, df, f'envelope_lower_{window}', f'Env Low({window}d, {params.get("percentage", 0.025):.1%})', color='fuchsia', width=1, dash='dot', row=row, col=col)

# --- Donchian Channel ---
def calculate_donchian_channel(df_orig, window=20):
    df = df_orig.copy()
    df[f'donchian_upper_{window}'] = df['High'].rolling(window=window).max()
    df[f'donchian_lower_{window}'] = df['Low'].rolling(window=window).min()
    df[f'donchian_mid_{window}'] = (df[f'donchian_upper_{window}'] + df[f'donchian_lower_{window}']) / 2
    return df

def add_donchian_channel_traces(fig, df, window=20, row=1, col=1, **params):
    add_line_trace(fig, df, f'donchian_upper_{window}', f'Donchian Up({window})', color='darkturquoise', width=1, row=row, col=col)
    add_line_trace(fig, df, f'donchian_lower_{window}', f'Donchian Low({window})', color='darkturquoise', width=1, row=row, col=col)
    add_line_trace(fig, df, f'donchian_mid_{window}', f'Donchian Mid({window})', color='powderblue', width=1, dash='dash', row=row, col=col)

# --- Keltner Channel ---
def calculate_atr(df_orig, window=14):
    df = df_orig.copy()
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df[f'atr_{window}'] = tr.ewm(alpha=1/window, adjust=False).mean()
    return df

def calculate_keltner_channels(df_orig, ema_window=20, atr_window=10, atr_multiplier=2.0):
    df = df_orig.copy()
    if f'atr_{atr_window}' not in df.columns: df = calculate_atr(df, window=atr_window)
    df[f'kc_mid_{ema_window}'] = df['Close'].ewm(span=ema_window, adjust=False).mean()
    df[f'kc_upper_{ema_window}'] = df[f'kc_mid_{ema_window}'] + (df[f'atr_{atr_window}'] * atr_multiplier)
    df[f'kc_lower_{ema_window}'] = df[f'kc_mid_{ema_window}'] - (df[f'atr_{atr_window}'] * atr_multiplier)
    return df

def add_keltner_channels_traces(fig, df, ema_window=20, row=1, col=1, **params):
    add_line_trace(fig, df, f'kc_upper_{ema_window}', f'KC Up({ema_window})', color='goldenrod', width=1, row=row, col=col)
    add_line_trace(fig, df, f'kc_lower_{ema_window}', f'KC Low({ema_window})', color='goldenrod', width=1, row=row, col=col)
    add_line_trace(fig, df, f'kc_mid_{ema_window}', f'KC Mid({ema_window})', color='gold', width=1, dash='dash', row=row, col=col)



