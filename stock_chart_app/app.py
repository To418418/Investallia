# stock_chart_app/app.py
import streamlit as st
import pandas as pd
import datetime
from plotly.subplots import make_subplots
from streamlit_js_eval import streamlit_js_eval # 画面幅取得のために再導入
import traceback
import json
import logging
import io
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import japanize_matplotlib  # 日本語表示のため

# --- Configuration and Utility Imports ---
try:
    from . import config_tech
    logger = config_tech.logger
    logger.info("stock_chart_app.app.py: Logger obtained from config_tech.")
except ImportError:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    logger.error("stock_chart_app.app.py: CRITICAL - config_tech.py failed to import or provide logger. Using fallback.")

try:
    from . import data_utils
    from . import plot_utils
    from .indicators import trend_indicators, oscillator_indicators, volume_indicators, other_indicators
    from . import chart_analyzer
    logger.info("stock_chart_app.app.py: Core utility modules imported successfully.")
except ImportError as e:
    logger.error(f"stock_chart_app.app.py: Failed to import one or more core utility modules: {e}", exc_info=True)
    raise

# --- Constants and Configuration ---
INDICATORS_CONFIG = {
    # --- トレンド系指標 ---
    'sma': {'label': '単純移動平均線 (SMA)', 'module': trend_indicators, 'calc_func': 'calculate_sma', 'plot_func': 'add_sma_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 20, 'min': 1, 'max': 200, 'step': 1}}, 'plot_on_price': True, 'data_cols': lambda p: [f"SMA_{p.get('window', 20)}"]},
    'ema': {'label': '指数平滑移動平均線 (EMA)', 'module': trend_indicators, 'calc_func': 'calculate_ema', 'plot_func': 'add_ema_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 20, 'min': 1, 'max': 200, 'step': 1}}, 'plot_on_price': True, 'data_cols': lambda p: [f"EMA_{p.get('window', 20)}"]},
    'bollinger': {'label': 'ボリンジャーバンド (2σ & 3σ)', 'module': trend_indicators, 'calc_func': 'calculate_bollinger_bands', 'plot_func': 'add_bollinger_bands_traces', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 20, 'min': 1, 'max': 200, 'step': 1}}, 'plot_on_price': True, 'data_cols': lambda p: [f"BB_Mid_{p.get('window', 20)}", f"BB_Upper_2std_{p.get('window', 20)}", f"BB_Lower_2std_{p.get('window', 20)}", f"BB_Upper_3std_{p.get('window', 20)}", f"BB_Lower_3std_{p.get('window', 20)}"]},
    'ichimoku': {'label': '一目均衡表', 'module': trend_indicators, 'calc_func': 'calculate_ichimoku', 'plot_func': 'add_ichimoku_traces', 'params': {}, 'plot_on_price': True, 'data_cols': lambda p: ['tenkan_sen', 'kijun_sen', 'senkou_span_a', 'senkou_span_b', 'chikou_span']},
    'psar': {'label': 'パラボリックSAR', 'module': trend_indicators, 'calc_func': 'calculate_parabolic_sar', 'plot_func': 'add_parabolic_sar_trace', 'params': {'initial_af': {'type': 'number_input', 'label': '初速AF', 'default': 0.02, 'min': 0.01, 'max': 0.2, 'step': 0.01}, 'af_increment': {'type': 'number_input', 'label': '加速AF', 'default': 0.02, 'min': 0.01, 'max': 0.2, 'step': 0.01}, 'max_af': {'type': 'number_input', 'label': '最大AF', 'default': 0.2, 'min': 0.1, 'max': 1.0, 'step': 0.05}}, 'plot_on_price': True, 'data_cols': lambda p: ['psar']},
    'ma_envelope': {'label': 'エンベロープ', 'module': trend_indicators, 'calc_func': 'calculate_ma_envelope', 'plot_func': 'add_ma_envelope_traces', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 20, 'min': 1, 'max': 200, 'step': 1}, 'percentage': {'type': 'number_input', 'label': '乖離率(%)', 'default': 2.5, 'min': 0.1, 'max': 50.0, 'step': 0.1}}, 'plot_on_price': True, 'data_cols': lambda p: [f"envelope_upper_{p.get('window', 20)}", f"envelope_lower_{p.get('window', 20)}"]},
    'donchian': {'label': 'ドンチアンチャネル', 'module': trend_indicators, 'calc_func': 'calculate_donchian_channel', 'plot_func': 'add_donchian_channel_traces', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 20, 'min': 1, 'max': 200, 'step': 1}}, 'plot_on_price': True, 'data_cols': lambda p: [f"donchian_upper_{p.get('window', 20)}", f"donchian_lower_{p.get('window', 20)}"]},
    'keltner': {'label': 'ケルトナーチャネル', 'module': trend_indicators, 'calc_func': 'calculate_keltner_channels', 'plot_func': 'add_keltner_channels_traces', 'params': {'ema_window': {'type': 'number_input', 'label': 'EMA期間', 'default': 20, 'min': 1, 'max': 100}, 'atr_window': {'type': 'number_input', 'label': 'ATR期間', 'default': 10, 'min': 1, 'max': 100}, 'atr_multiplier': {'type': 'number_input', 'label': 'ATR倍率', 'default': 2.0, 'min': 0.1, 'max': 10.0, 'step': 0.1}}, 'plot_on_price': True, 'data_cols': lambda p: [f"kc_upper_{p.get('ema_window', 20)}", f"kc_lower_{p.get('ema_window', 20)}"]},

    # --- オシレーター系指標 ---
    'macd': {'label': 'MACD', 'module': trend_indicators, 'calc_func': 'calculate_macd', 'plot_func': 'add_macd_traces', 'params': {'fast_period': {'type': 'number_input', 'label': '短期EMA', 'default': 12, 'min': 1}, 'slow_period': {'type': 'number_input', 'label': '長期EMA', 'default': 26, 'min': 1}, 'signal_period': {'type': 'number_input', 'label': 'シグナル', 'default': 9, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'MACD', 'data_cols': lambda p: ['MACD_Line', 'MACD_Signal', 'MACD_Hist']},
    'rsi': {'label': 'RSI', 'module': oscillator_indicators, 'calc_func': 'calculate_rsi', 'plot_func': 'add_rsi_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 14, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'RSI', 'data_cols': lambda p: [f"RSI_{p.get('window', 14)}"]},
    'stochastics': {'label': 'ストキャスティクス', 'module': oscillator_indicators, 'calc_func': 'calculate_stochastics', 'plot_func': 'add_stochastics_traces', 'params': {'k_window': {'type': 'number_input', 'label': '%K期間', 'default': 14, 'min': 1}, 'd_window': {'type': 'number_input', 'label': '%D期間', 'default': 3, 'min': 1}, 'smooth_k': {'type': 'number_input', 'label': '平滑化', 'default': 3, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'Stochastics', 'data_cols': lambda p: [f"%K_{p.get('k_window', 14)}", f"%D_{p.get('d_window', 3)}"]},
    'rci': {'label': 'RCI (順位相関指数)', 'module': oscillator_indicators, 'calc_func': 'calculate_rci', 'plot_func': 'add_rci_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 9, 'min': 2, 'max': 50}}, 'plot_on_price': False, 'subplot_name': 'RCI', 'data_cols': lambda p: [f"RCI_{p.get('window', 9)}"]},
    'dmi_adx': {'label': 'DMI/ADX', 'module': oscillator_indicators, 'calc_func': 'calculate_dmi_adx', 'plot_func': 'add_dmi_adx_traces', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 14, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'DMI/ADX', 'data_cols': lambda p: [f"plus_di_{p.get('window',14)}", f"minus_di_{p.get('window',14)}", f"adx_{p.get('window',14)}"]},
    'williams_r': {'label': 'ウィリアムズ %R', 'module': oscillator_indicators, 'calc_func': 'calculate_williams_r', 'plot_func': 'add_williams_r_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 14, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'Williams %R', 'data_cols': lambda p: [f"williams_r_{p.get('window',14)}"]},
    'aroon': {'label': 'アルーン', 'module': oscillator_indicators, 'calc_func': 'calculate_aroon', 'plot_func': 'add_aroon_traces', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 25, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'Aroon', 'data_cols': lambda p: [f"aroon_up_{p.get('window', 25)}", f"aroon_down_{p.get('window', 25)}"]},
    'coppock': {'label': 'コポックカーブ', 'module': oscillator_indicators, 'calc_func': 'calculate_coppock_curve', 'plot_func': 'add_coppock_curve_trace', 'params': {'roc1_period': {'type': 'number_input', 'label': 'ROC1期間', 'default': 14}, 'roc2_period': {'type': 'number_input', 'label': 'ROC2期間', 'default': 11}, 'wma_period': {'type': 'number_input', 'label': 'WMA期間', 'default': 10}}, 'plot_on_price': False, 'subplot_name': 'Coppock Curve', 'data_cols': lambda p: ['coppock']},
    'force_index': {'label': 'フォースインデックス', 'module': oscillator_indicators, 'calc_func': 'calculate_force_index', 'plot_func': 'add_force_index_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 13, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'Force Index', 'data_cols': lambda p: [f"force_index_{p.get('window',13)}"]},
    'mass_index': {'label': 'マスインデックス', 'module': oscillator_indicators, 'calc_func': 'calculate_mass_index', 'plot_func': 'add_mass_index_trace', 'params': {'sum_period': {'type': 'number_input', 'label': '合計期間', 'default': 25, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'Mass Index', 'data_cols': lambda p: [f"mass_index_{p.get('sum_period',25)}"]},
    'psy_line': {'label': 'サイコロジカルライン', 'module': oscillator_indicators, 'calc_func': 'calculate_psychological_line', 'plot_func': 'add_psychological_line_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 12, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'Psychological Line', 'data_cols': lambda p: [f"psy_line_{p.get('window',12)}"]},
    'ma_dev_rate': {'label': '移動平均乖離率', 'module': oscillator_indicators, 'calc_func': 'calculate_ma_deviation_rate', 'plot_func': 'add_ma_deviation_rate_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 20, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'MA Deviation Rate', 'data_cols': lambda p: [f"ma_dev_rate_{p.get('window',20)}"]},

    # --- 出来高系指標 ---
    'volume': {'label': '出来高', 'module': volume_indicators, 'calc_func': None, 'plot_func': 'add_volume_trace', 'params': {}, 'plot_on_price': False, 'subplot_name': '出来高', 'data_cols': lambda p: ['Volume']},
    'volume_sma': {'label': '出来高移動平均', 'module': volume_indicators, 'calc_func': 'calculate_volume_sma', 'plot_func': 'add_volume_sma_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 20, 'min': 1}}, 'plot_on_price': False, 'on_subplot_of': 'volume', 'data_cols': lambda p: [f"Volume_SMA_{p.get('window', 20)}"]},
    'obv': {'label': 'オンバランスボリューム (OBV)', 'module': volume_indicators, 'calc_func': 'calculate_obv', 'plot_func': 'add_obv_trace', 'params': {}, 'plot_on_price': False, 'subplot_name': 'OBV', 'data_cols': lambda p: ['obv']},
    'mfi': {'label': 'マネーフローインデックス (MFI)', 'module': volume_indicators, 'calc_func': 'calculate_mfi', 'plot_func': 'add_mfi_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 14, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'MFI', 'data_cols': lambda p: [f"mfi_{p.get('window',14)}"]},
    'vwap': {'label': 'VWAP (出来高加重平均価格)', 'module': volume_indicators, 'calc_func': 'calculate_vwap', 'plot_func': 'add_vwap_trace', 'params': {}, 'plot_on_price': True, 'data_cols': lambda p: ['vwap']},
    'cmf': {'label': 'チャイキンマネーフロー (CMF)', 'module': volume_indicators, 'calc_func': 'calculate_cmf', 'plot_func': 'add_cmf_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 20, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'CMF', 'data_cols': lambda p: [f"cmf_{p.get('window',20)}"]},
    'eom': {'label': 'イーズオブムーブメント (EOM)', 'module': volume_indicators, 'calc_func': 'calculate_eom', 'plot_func': 'add_eom_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 14, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'EOM', 'data_cols': lambda p: [f"eom_{p.get('window',14)}"]},

    # --- その他指標 ---
    'atr': {'label': 'ATR (平均実質変動幅)', 'module': other_indicators, 'calc_func': 'calculate_atr', 'plot_func': 'add_atr_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 14, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'ATR', 'data_cols': lambda p: [f"atr_{p.get('window',14)}"]},
    'std_dev': {'label': '標準偏差 (ボラティリティ)', 'module': other_indicators, 'calc_func': 'calculate_std_dev', 'plot_func': 'add_std_dev_trace', 'params': {'window': {'type': 'number_input', 'label': '期間', 'default': 20, 'min': 1}}, 'plot_on_price': False, 'subplot_name': 'Standard Deviation', 'data_cols': lambda p: [f"std_dev_{p.get('window',20)}"]},
    'pivot': {'label': 'ピボットポイント', 'module': other_indicators, 'calc_func': 'calculate_pivot_points', 'plot_func': 'add_pivot_points_traces', 'params': {}, 'plot_on_price': True, 'data_cols': lambda p: ['pivot', 'r1', 's1', 'r2', 's2', 'r3', 's3']},
}

DEFAULT_GEMINI_FLASH_MODEL_NAME = config_tech.DEFAULT_FLASH_MODEL_TECH
DEFAULT_GEMINI_PRO_MODEL_NAME = config_tech.DEFAULT_PRO_MODEL_TECH

def _create_matplotlib_technical_chart_image(
    df, ticker_symbol, selected_indicator_keys, indicator_params_values,
    additional_subplots_info, total_rows
):
    """Matplotlibを使用してテクニカルチャートの静的画像を生成する"""
    try:
        logger.info("Starting matplotlib static chart generation.")
        if df is None or df.empty:
            logger.warning("Matplotlib chart generation skipped: DataFrame is empty.")
            return None

        # メインチャートが16:9になるように全体のサイズと比率を計算
        num_subplots = total_rows - 1
        main_chart_width_inch = 12.8
        main_chart_height_inch = 7.2
        subplot_height_inch = 3.0

        total_height_inch = main_chart_height_inch + (num_subplots * subplot_height_inch)
        height_ratios = [main_chart_height_inch] + [subplot_height_inch] * num_subplots

        fig = plt.figure(figsize=(main_chart_width_inch, total_height_inch), dpi=100)
        gs = fig.add_gridspec(total_rows, 1, height_ratios=height_ratios)

        axes = [fig.add_subplot(gs[i, 0]) for i in range(total_rows)]
        main_ax = axes[0]
        for i in range(1, total_rows):
            axes[i].sharex(main_ax)

        # ローソク足の描画
        width = 0.8
        for i, (idx, row) in enumerate(df.iterrows()):
            num_date = mdates.date2num(idx)
            color = '#ff4b00' if row['Close'] >= row['Open'] else '#005aff'
            main_ax.add_patch(Rectangle((num_date - width/2, row['Open']), width, row['Close'] - row['Open'], facecolor=color, edgecolor='black', lw=0.5, zorder=3))
            main_ax.plot([num_date, num_date], [row['Low'], row['High']], color=color, lw=0.7, zorder=2)

        # メインチャートの指標
        for key in selected_indicator_keys:
            if key not in INDICATORS_CONFIG or not INDICATORS_CONFIG[key]['plot_on_price']: continue
            params = indicator_params_values.get(key, {})
            p_def = INDICATORS_CONFIG[key]['params']

            if key == 'sma':
                win = params.get('window', p_def['window']['default'])
                sma_col = f"SMA_{win}"
                if sma_col in df.columns: main_ax.plot(df.index, df[sma_col], label=sma_col, lw=1.0, zorder=4)
            if key == 'bollinger':
                win = params.get('window', p_def['window']['default'])
                u2_col, l2_col = f"BB_Upper_2std_{win}", f"BB_Lower_2std_{win}"
                if u2_col in df.columns and l2_col in df.columns:
                    main_ax.plot(df.index, df[u2_col], color='dimgray', lw=0.8, ls='--', zorder=1)
                    main_ax.plot(df.index, df[l2_col], color='dimgray', lw=0.8, ls='--', zorder=1)
                    main_ax.fill_between(df.index, df[l2_col], df[u2_col], facecolor='silver', alpha=0.2, zorder=0)

        # サブプロットの指標
        subplot_ax_idx = 1
        for subplot_name, subplot_info in additional_subplots_info.items():
            ax = axes[subplot_ax_idx]
            for key in subplot_info['keys']:
                params = indicator_params_values.get(key, {})
                p_def = INDICATORS_CONFIG[key]['params']

                if key == 'rsi':
                    win = params.get('window', p_def['window']['default'])
                    rsi_col = f"RSI_{win}"
                    if rsi_col in df.columns:
                        ax.plot(df.index, df[rsi_col], label=f'RSI({win})', lw=1.2)
                        ax.axhline(70, color='r', ls='--', lw=0.8)
                        ax.axhline(30, color='g', ls='--', lw=0.8)
                        ax.set_ylim(0, 100)
                if key == 'macd':
                    if 'MACD_Line' in df.columns and 'MACD_Signal' in df.columns:
                        ax.plot(df.index, df['MACD_Line'], label='MACD', lw=1.2)
                        ax.plot(df.index, df['MACD_Signal'], label='Signal', lw=1.0, ls='--')
                    if 'MACD_Hist' in df.columns:
                        colors = ['#ff4b00' if x >= 0 else '#005aff' for x in df['MACD_Hist']]
                        ax.bar(df.index, df['MACD_Hist'], width=width*1.2, color=colors, alpha=0.5)
                if key == 'volume':
                    colors = ['#ff4b00' if c >= o else '#005aff' for o, c in zip(df['Open'], df['Close'])]
                    ax.bar(df.index, df['Volume'], width=width*1.2, color=colors, alpha=0.7)
                if key == 'volume_sma':
                     win = params.get('window', p_def['window']['default'])
                     v_sma_col = f"Volume_SMA_{win}"
                     if v_sma_col in df.columns: ax.plot(df.index, df[v_sma_col], lw=1.0, ls='--', label=f'出来高SMA({win})')

            ax.set_title(subplot_name, fontsize=10)
            ax.legend(fontsize='small', loc='upper left')
            ax.grid(True, linestyle='--', alpha=0.6)
            ax.tick_params(axis='y', labelsize=8)
            ax.get_yaxis().get_major_formatter().set_scientific(False)
            subplot_ax_idx += 1

        main_ax.set_title(f"{ticker_symbol} 株価チャート", fontsize=14)
        main_ax.set_ylabel("価格", fontsize=10)
        main_ax.legend(fontsize='small', loc='upper left')
        main_ax.grid(True, linestyle='--', alpha=0.6)
        main_ax.tick_params(axis='y', labelsize=8)

        # ▼▼▼ X軸のフォーマットを修正 ▼▼▼
        # 最後の軸(一番下のチャートの軸)を取得
        bottom_ax = axes[-1]

        # 適切な数の目盛りを自動で設定 (最大12個)
        locator = mdates.AutoDateLocator(maxticks=12)
        bottom_ax.xaxis.set_major_locator(locator)

        # 日付のフォーマットを設定
        formatter = mdates.DateFormatter('%Y/%m/%d')
        bottom_ax.xaxis.set_major_formatter(formatter)

        # 上のチャートのX軸ラベルを非表示にする
        for ax in axes[:-1]:
            plt.setp(ax.get_xticklabels(), visible=False)

        # 最後の軸のラベルを回転させる
        plt.setp(bottom_ax.get_xticklabels(), rotation=-45, ha='left', fontsize=8)
        # ▲▲▲ X軸のフォーマットを修正 ▲▲▲

        fig.tight_layout(pad=1.5)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        logger.info("Matplotlib static chart generation successful.")
        return buf.getvalue()
    except Exception as e:
        logger.error(f"Error generating matplotlib chart: {e}", exc_info=True)
        st.error(f"Matplotlibでの静的チャート生成中にエラー: {e}")
        return None

def render_technical_analysis_content(
    sm_main_app, ticker_symbol: str, start_date: datetime.date, end_date: datetime.date,
    interval: str, selected_indicator_keys: list, indicator_params_values: dict,
    gemini_api_key: str, pro_model_password: str, active_gemini_model_name: str,
    use_static_image: bool = False
):
    logger.info(f"render_technical_analysis_content for {ticker_symbol} from {start_date} to {end_date}, interval {interval}.")
    if not ticker_symbol or not start_date or not end_date or not interval:
        st.warning("銘柄コード、期間、足種が正しく指定されていません。")
        return
    if start_date >= end_date:
        st.error("エラー: 開始日は終了日より前に設定してください。")
        return

    try:
        stock_data_master = data_utils.get_validated_data(ticker_symbol, start_date, end_date, interval=interval)
        if stock_data_master is None or stock_data_master.empty:
            st.warning(f"{ticker_symbol} の株価データを取得できませんでした。")
            sm_main_app.set_value("tech_analysis.current_chart_json", None)
            return

        logger.info(f"Stock data obtained for {ticker_symbol}. Calculating {len(selected_indicator_keys)} indicators.")
        stock_data_processed = stock_data_master.copy()
        ai_data_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        indicator_column_labels_for_ai = {}

        for key in selected_indicator_keys:
            if key not in INDICATORS_CONFIG: continue
            indicator_config = INDICATORS_CONFIG[key]
            params = indicator_params_values.get(key, {})
            default_params = {p_name: p_detail['default'] for p_name, p_detail in indicator_config.get('params', {}).items()}
            final_params = {**default_params, **params}

            if indicator_config.get('calc_func'):
                calc_func = getattr(indicator_config['module'], indicator_config['calc_func'])
                stock_data_processed = calc_func(stock_data_processed, **final_params)

            if 'data_cols' in indicator_config:
                cols_for_this_indicator = indicator_config['data_cols'](final_params)
                indicator_column_labels_for_ai[indicator_config['label']] = cols_for_this_indicator
                for col_name in cols_for_this_indicator:
                    if col_name in stock_data_processed.columns and col_name not in ai_data_columns:
                        ai_data_columns.append(col_name)

        logger.info(f"Indicator calculation complete. Preparing AI data.")
        valid_ai_columns = [col for col in ai_data_columns if col in stock_data_processed.columns]
        ai_df = stock_data_processed[valid_ai_columns].reset_index()
        if 'Date' in ai_df.columns:
            ai_df['Date'] = pd.to_datetime(ai_df['Date']).dt.strftime('%Y-%m-%d')

        max_rows_for_ai = 250
        ai_df_for_json = ai_df.tail(max_rows_for_ai)

        current_chart_json = ai_df_for_json.to_json(orient="records", date_format="iso", force_ascii=False)
        sm_main_app.set_value("tech_analysis.current_chart_json", current_chart_json)
        sm_main_app.set_value("tech_analysis.indicator_labels_for_ai", indicator_column_labels_for_ai)

        # --- プロット作成準備 ---
        additional_subplots_info = {}
        for ind_key in selected_indicator_keys:
            if ind_key not in INDICATORS_CONFIG: continue
            cfg = INDICATORS_CONFIG[ind_key]
            if not cfg['plot_on_price']:
                target_subplot_key = cfg.get('on_subplot_of')
                subplot_name = INDICATORS_CONFIG[target_subplot_key].get('subplot_name', INDICATORS_CONFIG[target_subplot_key]['label']) if target_subplot_key else cfg.get('subplot_name', cfg['label'])
                if subplot_name not in additional_subplots_info:
                    additional_subplots_info[subplot_name] = {'keys': []}
                additional_subplots_info[subplot_name]['keys'].append(ind_key)

        num_subplots = len(additional_subplots_info)
        total_rows = 1 + num_subplots

        # --- 描画方法の分岐 ---
        if use_static_image:
            with st.spinner("matplotlibで静的画像チャートを生成中です..."):
                final_params = {key: indicator_params_values.get(key, {p_name: p_detail['default'] for p_name, p_detail in cfg.get('params', {}).items()}) for key, cfg in INDICATORS_CONFIG.items()}
                img_bytes = _create_matplotlib_technical_chart_image(
                    stock_data_processed, ticker_symbol, selected_indicator_keys,
                    final_params, additional_subplots_info, total_rows
                )
            if img_bytes:
                st.image(img_bytes, caption="テクニカルチャートの静的画像", use_container_width=True)
            else:
                st.error("静的画像の生成に失敗しました。インタラクティブモードでお試しください。")
        else:
            # ▼▼▼ メインチャートを高くし、比率を維持するロジック ▼▼▼
            main_chart_base_height_px = 720  # メインチャートの基準の高さを設定 (px)
            subplot_height_px = 240          # サブチャート1つあたりの高さを設定 (px)

            total_chart_height = main_chart_base_height_px + (num_subplots * subplot_height_px)
            # make_subplotsは比率で解釈するため、絶対値のままで渡す
            row_heights = [main_chart_base_height_px] + [subplot_height_px] * num_subplots
            # ▲▲▲ 高さ計算ロジック ▲▲▲

            subplot_titles = [f"{ticker_symbol} 株価チャート"] + list(additional_subplots_info.keys())
            fig = make_subplots(rows=total_rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights, subplot_titles=subplot_titles)
            plot_utils.add_candlestick_trace(fig, stock_data_processed, row=1, col=1)

            for key in selected_indicator_keys:
                if key not in INDICATORS_CONFIG: continue
                cfg = INDICATORS_CONFIG[key]
                if cfg['plot_on_price']:
                    plot_func = getattr(cfg['module'], cfg['plot_func'])
                    plot_func(fig, stock_data_processed, **indicator_params_values.get(key, {}), row=1, col=1)

            current_subplot_idx = 2
            for subplot_name, subplot_info in additional_subplots_info.items():
                for key in subplot_info['keys']:
                    if key not in INDICATORS_CONFIG: continue
                    cfg = INDICATORS_CONFIG[key]
                    plot_func = getattr(cfg['module'], cfg['plot_func'])
                    plot_func(fig, stock_data_processed, **indicator_params_values.get(key, {}), row=current_subplot_idx, col=1)
                current_subplot_idx += 1

            fig.update_layout(height=total_chart_height, xaxis_rangeslider_visible=False, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

            # ▼▼▼ X軸のフォーマットを修正 ▼▼▼
            fig.update_xaxes(
                nticks=12,
                tickformat='%Y/%m/%d',
                tickangle=-45,
                row=total_rows,
                col=1
            )
            # ▲▲▲ X軸のフォーマットを修正 ▲▲▲

            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        logger.error(f"Error during render_technical_analysis_content: {e}", exc_info=True)
        st.error(f"チャート描画中にエラーが発生しました: {e}")
        st.text(traceback.format_exc())
        sm_main_app.set_value("tech_analysis.current_chart_json", None)
