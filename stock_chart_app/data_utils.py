
# stock_chart_app/data_utils.py
import yfinance as yf
import pandas as pd
import streamlit as st
import traceback


def download_stock_data(ticker_symbol, start_date, end_date, interval="1d"):
    """
    yfinanceを使用して株価データをダウンロードし、基本的な前処理を行います。
    auto_adjust=True を使用して、分割や配当を自動調整した価格を取得します。
    """
    # st.write(f"データ取得試行中: {ticker_symbol}, 開始: {start_date}, 終了: {end_date}, 足種: {interval}")
    try:
        data = yf.download(
            ticker_symbol,
            start=start_date,
            end=end_date,
            auto_adjust=True,  # 分割や配当を自動調整し、'Adj Close' は不要になる
            progress=False,
            interval=interval
        )

        if data.empty:
            st.warning(f"yfinanceから取得したデータが空です: {ticker_symbol} ({interval}足), 期間: {start_date} - {end_date}")
            return None

        # auto_adjust=True の場合、通常カラム名は 'Open', 'High', 'Low', 'Close', 'Volume'
        # MultiIndex になるのは複数のティッカーを一度に取得した場合など。
        # 単一ティッカーなら通常は発生しないが、念のためチェック。
        if isinstance(data.columns, pd.MultiIndex):
            # st.info(f"yfinanceからMultiIndexのカラムが返されました（ティッカー: {ticker_symbol}）。最初のレベルを使用します。カラム: {data.columns}") # この情報メッセージを削除
            data.columns = data.columns.get_level_values(0)

        # カラム名を標準形 (先頭大文字) に統一
        data.columns = [str(col).capitalize() for col in data.columns]
        # yfinance v0.2.1以降、auto_adjust=Trueの場合、'Adj Close'は通常なく、'Close'が調整済み終値
        # 'Adj close' のような小文字カラムが存在する場合に備えて 'Adj Close' にリネーム
        if 'Adj close' in data.columns:
            data.rename(columns={'Adj close': 'Adj Close'}, inplace=True)

        # auto_adjust=True を使っている場合、'Close' が調整済み終値のはず。
        # もし 'Adj Close' が別途存在し、それが 'Close' と異なる場合、どちらを正とするか。
        # yfinance の auto_adjust=True は 'Close' を調整済みにするので、通常 'Adj Close' は不要。
        if 'Adj Close' in data.columns and 'Close' in data.columns and not data['Adj Close'].equals(data['Close']):
            # st.info(f"'{ticker_symbol}': 'Close' と 'Adj Close' の両方が存在し値が異なります。" # 詳細情報なので削除またはデバッグレベルへ
            #         "auto_adjust=True のため 'Close' が調整済み価格のはずですが、念のため確認してください。'Close' を使用します。")
            pass # Closeを優先する
        elif 'Adj Close' in data.columns and 'Close' not in data.columns:
            # auto_adjust=True で 'Close' がなく 'Adj Close' だけの場合 (通常は考えにくい)
            # st.info(f"'{ticker_symbol}': 'Adj Close' のみ存在するため、これを 'Close' として使用します。") # 詳細情報なので削除またはデバッグレベルへ
            data.rename(columns={'Adj Close': 'Close'}, inplace=True)


        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            st.error(f"{ticker_symbol} のデータに必要なカラム {missing_cols} が不足しています。現在のカラム: {data.columns.tolist()}")
            return None

        # 主要な価格データがない行を削除 (VolumeのNaNは許容する場合があるため、OHLCのみ対象)
        data.dropna(subset=['Open', 'High', 'Low', 'Close'], inplace=True)
        if data.empty:
            st.warning(f"{ticker_symbol} のデータはOHLCのNaN値を除去後、空になりました。")
            return None

        # st.write(f"データ取得・加工成功: {ticker_symbol}, {len(data)}行")
        return data

    except Exception as e:
        st.error(f"データダウンロードまたは加工中に例外が発生しました ({ticker_symbol}, {interval}足):")
        st.error(f"例外の型: {type(e)}")
        st.error(f"例外メッセージ: {str(e)}")
        st.text("詳細なスタックトレース:")
        st.text(traceback.format_exc())
        return None

def get_validated_data(ticker_symbol, start_date, end_date, interval="1d"):
    if not ticker_symbol:
        st.warning("銘柄コードを入力してください。")
        return None
    if not start_date or not end_date:
        st.warning("開始日と終了日を選択してください。")
        return None
    if start_date >= end_date:
        st.error("開始日は終了日より前に設定してください。")
        return None

    # yfinanceはdatetimeオブジェクトも受け付けるが、strftimeで文字列に統一
    str_start_date = start_date.strftime("%Y-%m-%d")
    # yfinanceのendは指定日を含まないため、1日加算するか、そのまま渡すか仕様による。
    # 通常は指定日まで含めることが多いので、そのまま渡す。
    str_end_date = end_date.strftime("%Y-%m-%d")

    data = download_stock_data(ticker_symbol, str_start_date, str_end_date, interval=interval)

    if data is None or data.empty:
        # download_stock_data内で警告が出るので、ここでは追加のメッセージは不要な場合も
        return None

    return data
