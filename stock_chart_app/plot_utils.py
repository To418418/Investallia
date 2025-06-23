

# stock_chart_app/plot_utils.py
import plotly.graph_objects as go


def add_candlestick_trace(fig, df, row=1, col=1):
    """
    指定されたFigureにローソク足トレースを追加します。
    """
    if df is not None and not df.empty and all(c in df.columns for c in ['Open', 'High', 'Low', 'Close']):
        fig.add_trace(go.Candlestick(x=df.index,
                                     open=df['Open'],
                                     high=df['High'],
                                     low=df['Low'],
                                     close=df['Close'],
                                     name='ローソク足'),
                      row=row, col=col)
    # fig.update_layout(xaxis_rangeslider_visible=False) # これは呼び出し元で全体に設定する方が良い

def add_line_trace(fig, df, column_name, trace_name, color='blue', width=1, dash='solid', row=1, col=1, opacity=1.0):
    """
    指定されたFigureにラインチャートトレースを追加します。
    """
    if column_name in df.columns and not df[column_name].isnull().all(): # データが存在し、全てNaNではない
        fig.add_trace(go.Scatter(x=df.index,
                                 y=df[column_name],
                                 name=trace_name,
                                 line=dict(color=color, width=width, dash=dash),
                                 opacity=opacity),
                      row=row, col=col)

