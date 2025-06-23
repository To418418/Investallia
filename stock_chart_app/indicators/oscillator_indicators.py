# stock_chart_app/indicators/oscillator_indicators.py
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from stock_chart_app.plot_utils import add_line_trace # 修正: stock_chart_app からインポート

# --- RSI (既存 + 統合) ---
def calculate_rsi(df_orig, window=14):
    df = df_orig.copy()
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(com=window - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=window - 1, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    df[f'RSI_{window}'] = rsi.replace([np.inf, -np.inf], 100).fillna(50)
    return df

def add_rsi_trace(fig, df, window=14, row=2, col=1, **params):
    add_line_trace(fig, df, f'RSI_{window}', f'RSI({window})', color='purple', row=row, col=col)
    fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.4, row=row, col=col, line_width=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.4, row=row, col=col, line_width=1)
    fig.update_yaxes(range=[0, 100], row=row, col=col)

# --- Stochastics (既存 + 統合) ---
def calculate_stochastics(df_orig, k_window=14, d_window=3, smooth_k=3):
    df = df_orig.copy()
    high_k = df['High'].rolling(window=k_window).max()
    low_k = df['Low'].rolling(window=k_window).min()
    fast_k = 100 * ((df['Close'] - low_k) / (high_k - low_k).replace(0, np.nan))
    slow_k = fast_k.rolling(window=smooth_k).mean()
    slow_d = slow_k.rolling(window=d_window).mean()
    df[f'%K_{k_window}'] = slow_k.fillna(50)
    df[f'%D_{d_window}'] = slow_d.fillna(50)
    return df

def add_stochastics_traces(fig, df, k_window=14, d_window=3, row=2, col=1, **params):
    add_line_trace(fig, df, f'%K_{k_window}', f'%K({k_window})', color='blue', row=row, col=col)
    add_line_trace(fig, df, f'%D_{d_window}', f'%D({d_window})', color='red', dash='dash', row=row, col=col)
    fig.add_hline(y=80, line_dash="dash", line_color="red", opacity=0.4, row=row, col=col, line_width=1)
    fig.add_hline(y=20, line_dash="dash", line_color="green", opacity=0.4, row=row, col=col, line_width=1)
    fig.update_yaxes(range=[0, 100], row=row, col=col)

# --- RCI ---
def calculate_rci(df_orig, window=9):
    df = df_orig.copy()
    date_ranks = pd.Series(np.arange(1, window + 1))
    rci_values = pd.Series(index=df.index, dtype=float)
    for i in range(window - 1, len(df)):
        window_close = df['Close'].iloc[i - window + 1 : i + 1]
        price_ranks = window_close.rank(method='average')
        d_sq_sum = ((date_ranks.values - price_ranks.values)**2).sum()
        rho = 1 - (6 * d_sq_sum) / (window * (window**2 - 1))
        rci_values.iloc[i] = rho * 100
    df[f'RCI_{window}'] = rci_values.fillna(method='bfill').fillna(0)
    return df

def add_rci_trace(fig, df, window=9, row=2, col=1, **params):
    add_line_trace(fig, df, f'RCI_{window}', f'RCI({window})', color='darkorange', row=row, col=col)
    fig.add_hline(y=80, line_dash="dash", line_color="red", opacity=0.4, row=row, col=col, line_width=1)
    fig.add_hline(y=-80, line_dash="dash", line_color="green", opacity=0.4, row=row, col=col, line_width=1)
    fig.update_yaxes(range=[-100, 100], row=row, col=col)

# --- DMI / ADX Helpers & Main ---
def _wilders_smoothing(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1/period, adjust=False).mean()

def _calculate_atr_for_dmi(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
    return _wilders_smoothing(tr, window)

def calculate_dmi_adx(df_orig, window=14):
    df = df_orig.copy()
    move_up, move_down = df['High'].diff(), -df['Low'].diff()
    plus_dm = pd.Series(np.where((move_up > move_down) & (move_up > 0), move_up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((move_down > move_up) & (move_down > 0), move_down, 0.0), index=df.index)
    atr = _calculate_atr_for_dmi(df['High'], df['Low'], df['Close'], window)
    plus_di = 100 * (_wilders_smoothing(plus_dm, window) / atr.replace(0, np.nan))
    minus_di = 100 * (_wilders_smoothing(minus_dm, window) / atr.replace(0, np.nan))
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan))
    df[f'plus_di_{window}'] = plus_di.fillna(0)
    df[f'minus_di_{window}'] = minus_di.fillna(0)
    df[f'adx_{window}'] = _wilders_smoothing(dx.fillna(0), window).fillna(0)
    return df

def add_dmi_adx_traces(fig, df, window=14, row=2, col=1, **params):
    add_line_trace(fig, df, f'plus_di_{window}', f'+DI({window})', color='green', row=row, col=col)
    add_line_trace(fig, df, f'minus_di_{window}', f'-DI({window})', color='red', row=row, col=col)
    add_line_trace(fig, df, f'adx_{window}', f'ADX({window})', color='blue', width=2, row=row, col=col)
    fig.update_yaxes(range=[0, 100], row=row, col=col)

# --- Williams %R ---
def calculate_williams_r(df_orig, window=14):
    df = df_orig.copy()
    highest_high = df['High'].rolling(window=window).max()
    lowest_low = df['Low'].rolling(window=window).min()
    df[f'williams_r_{window}'] = ((highest_high - df['Close']) / (highest_high - lowest_low).replace(0, np.nan)) * -100
    df[f'williams_r_{window}'] = df[f'williams_r_{window}'].fillna(-50)
    return df

def add_williams_r_trace(fig, df, window=14, row=2, col=1, **params):
    add_line_trace(fig, df, f'williams_r_{window}', f"Williams %R({window})", color='cyan', row=row, col=col)
    fig.add_hline(y=-20, line_dash="dash", line_color="red", opacity=0.4, row=row, col=col, line_width=1)
    fig.add_hline(y=-80, line_dash="dash", line_color="green", opacity=0.4, row=row, col=col, line_width=1)
    fig.update_yaxes(range=[-100, 0], row=row, col=col)

# --- Aroon & Aroon Oscillator ---
def calculate_aroon(df_orig, window=25):
    df = df_orig.copy()
    # 修正: x.to_numpy() を x に変更
    days_since_high = df['High'].rolling(window=window).apply(lambda x: window - 1 - np.argmax(x), raw=True)
    days_since_low = df['Low'].rolling(window=window).apply(lambda x: window - 1 - np.argmin(x), raw=True)
    df[f'aroon_up_{window}'] = ((window - days_since_high) / window) * 100
    df[f'aroon_down_{window}'] = ((window - days_since_low) / window) * 100
    df[f'aroon_osc_{window}'] = df[f'aroon_up_{window}'] - df[f'aroon_down_{window}']
    return df

def add_aroon_traces(fig, df, window=25, row=2, col=1, **params):
    add_line_trace(fig, df, f'aroon_up_{window}', f'Aroon Up({window})', color='green', row=row, col=col)
    add_line_trace(fig, df, f'aroon_down_{window}', f'Aroon Down({window})', color='red', row=row, col=col)
    # add_line_trace(fig, df, f'aroon_osc_{window}', f'Aroon Osc({window})', color='blue', dash='dash', row=row, col=col) # オシレーターは別指標として追加
    fig.update_yaxes(range=[0, 100], row=row, col=col)

# --- Coppock Curve Helpers & Main ---
def _calculate_roc(close_series: pd.Series, window: int) -> pd.Series:
    return ((close_series - close_series.shift(window)) / close_series.shift(window).replace(0, np.nan)) * 100

def _calculate_wma(series: pd.Series, window: int) -> pd.Series:
    weights = np.arange(1, window + 1)
    return series.rolling(window=window).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def calculate_coppock_curve(df_orig, roc1_period=14, roc2_period=11, wma_period=10):
    df = df_orig.copy()
    roc_sum = _calculate_roc(df['Close'], roc1_period) + _calculate_roc(df['Close'], roc2_period)
    df['coppock'] = _calculate_wma(roc_sum, wma_period).fillna(0)
    return df

def add_coppock_curve_trace(fig, df, row=2, col=1, **params):
    add_line_trace(fig, df, 'coppock', 'Coppock Curve', color='sienna', row=row, col=col)
    fig.add_hline(y=0, line_dash="dash", line_color="grey", opacity=0.5, row=row, col=col, line_width=1)

# --- Force Index ---
def calculate_force_index(df_orig, window=13):
    df = df_orig.copy()
    one_period_fi = df['Close'].diff(1) * df['Volume']
    df[f'force_index_{window}'] = one_period_fi.ewm(span=window, adjust=False).mean().fillna(0)
    return df

def add_force_index_trace(fig, df, window=13, row=2, col=1, **params):
    add_line_trace(fig, df, f'force_index_{window}', f'Force Index({window})', color='darkviolet', row=row, col=col)
    fig.add_hline(y=0, line_dash="dash", line_color="grey", opacity=0.5, row=row, col=col, line_width=1)

# --- Mass Index ---
def calculate_mass_index(df_orig, ema_period=9, sum_period=25):
    df = df_orig.copy()
    price_range = df['High'] - df['Low']
    ema1 = price_range.ewm(span=ema_period, adjust=False).mean()
    ema2 = ema1.ewm(span=ema_period, adjust=False).mean()
    ratio = ema1 / ema2.replace(0, np.nan)
    df[f'mass_index_{sum_period}'] = ratio.rolling(window=sum_period).sum().fillna(0)
    return df

def add_mass_index_trace(fig, df, sum_period=25, row=2, col=1, **params):
    add_line_trace(fig, df, f'mass_index_{sum_period}', f'Mass Index({sum_period})', color='teal', row=row, col=col)
    fig.add_hline(y=27, line_dash="dash", line_color="red", opacity=0.5, row=row, col=col, line_width=1, name="Reversal Line") # Reversal Bulge
    fig.add_hline(y=26.5, line_dash="dot", line_color="grey", opacity=0.5, row=row, col=col, line_width=1, name="Setup Line")

# --- Psychological Line ---
def calculate_psychological_line(df_orig, window=12):
    df = df_orig.copy()
    price_up_days = (df['Close'].diff() > 0).astype(int)
    rolling_up_days = price_up_days.rolling(window=window).sum()
    df[f'psy_line_{window}'] = (rolling_up_days / window) * 100
    df[f'psy_line_{window}'] = df[f'psy_line_{window}'].fillna(50)
    return df

def add_psychological_line_trace(fig, df, window=12, row=2, col=1, **params):
    add_line_trace(fig, df, f'psy_line_{window}', f'Psychological Line({window})', color='hotpink', row=row, col=col)
    fig.add_hline(y=75, line_dash="dash", line_color="red", opacity=0.4, row=row, col=col, line_width=1)
    fig.add_hline(y=25, line_dash="dash", line_color="green", opacity=0.4, row=row, col=col, line_width=1)
    fig.update_yaxes(range=[0, 100], row=row, col=col)

# --- MA Deviation Rate ---
def calculate_ma_deviation_rate(df_orig, window=20, ma_type='sma'):
    df = df_orig.copy()
    if ma_type.lower() == 'sma': ma_series = df['Close'].rolling(window=window).mean()
    else: ma_series = df['Close'].ewm(span=window, adjust=False).mean()
    deviation_rate = ((df['Close'] - ma_series) / ma_series.replace(0, np.nan)) * 100
    df[f'ma_dev_rate_{window}'] = deviation_rate.fillna(0)
    return df

def add_ma_deviation_rate_trace(fig, df, window=20, row=2, col=1, **params):
    add_line_trace(fig, df, f'ma_dev_rate_{window}', f'MA Dev Rate({window})', color='slategray', row=row, col=col)
    fig.add_hline(y=0, line_dash="dash", line_color="grey", opacity=0.5, row=row, col=col, line_width=1)

