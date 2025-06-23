# state_manager.py
import streamlit as st
import pandas as pd
from typing import Any, Dict, List


class StateManager:
    """
    Streamlitのセッション状態 (st.session_state) を一元管理するクラス。
    キーの命名規則の強制や、状態の初期化、取得、設定を容易にする。
    """
    def __init__(self, initial_states: Dict[str, Any] = None):
        """
        StateManagerを初期化します。

        Args:
            initial_states (Dict[str, Any], optional): 初期化時に設定する状態の辞書。
                                                      キーはドット区切り (例: "page.variable") を推奨。
                                                      値は任意。
        """
        if initial_states:
            for key, value in initial_states.items():
                self.initialize_state(key, value)

    def _validate_key(self, key: str):
        """キーが文字列であり、空でないことを検証する。"""
        if not isinstance(key, str) or not key:
            raise ValueError("状態キーは空でない文字列である必要があります。")

    def initialize_state(self, key: str, default_value: Any):
        """
        指定されたキーのセッション状態を初期化します。キーが既に存在する場合は何もしません。

        Args:
            key (str): 状態のキー。
            default_value (Any): 状態のデフォルト値。
        """
        self._validate_key(key)
        if key not in st.session_state:
            st.session_state[key] = default_value

    def get_value(self, key: str, default: Any = None) -> Any:
        """
        指定されたキーのセッション状態の値を取得します。
        キーが存在しない場合は、指定されたデフォルト値を返します。

        Args:
            key (str): 取得する状態のキー。
            default (Any, optional): キーが存在しない場合に返す値。デフォルトは None。

        Returns:
            Any: 状態の値。
        """
        self._validate_key(key)
        return st.session_state.get(key, default)

    def set_value(self, key: str, value: Any):
        """
        指定されたキーのセッション状態に値を設定します。

        Args:
            key (str): 設定する状態のキー。
            value (Any): 設定する値。
        """
        self._validate_key(key)
        st.session_state[key] = value

    def update_values(self, updates: Dict[str, Any]):
        """
        複数のセッション状態を一度に更新します。

        Args:
            updates (Dict[str, Any]): 更新するキーと値の辞書。
        """
        for key, value in updates.items():
            self.set_value(key, value) # _validate_key は set_value 内で行われる

    def delete_value(self, key: str):
        """
        指定されたキーのセッション状態を削除します。

        Args:
            key (str): 削除する状態のキー。
        """
        self._validate_key(key)
        if key in st.session_state:
            del st.session_state[key]

    def ensure_df_state(self, key: str, default_data: List[Dict] = None, columns: List[str] = None):
        """
        指定されたキーのセッション状態がPandas DataFrameであることを保証します。
        存在しない場合やDataFrameでない場合は、新しいDataFrameで初期化します。

        Args:
            key (str): DataFrame状態のキー。
            default_data (List[Dict], optional): 初期化用のデータリスト。デフォルトは空のリスト。
            columns (List[str], optional): DataFrameのカラム。default_dataがない場合に空のDFを作る際に使用。
        """
        self._validate_key(key)
        current_value = self.get_value(key)
        if not isinstance(current_value, pd.DataFrame):
            if default_data is not None:
                df = pd.DataFrame(default_data)
            elif columns is not None:
                df = pd.DataFrame(columns=columns)
            else:
                df = pd.DataFrame()
            self.set_value(key, df)

    def get_all_states(self) -> Dict[str, Any]:
        """
        現在のすべてのセッション状態を辞書として取得します。
        注意: st.session_state には Streamlit 内部のキーも含まれる可能性があります。

        Returns:
            Dict[str, Any]: セッション状態の辞書。
        """
        return dict(st.session_state)

# --- StateManagerで使用するキーの例 (各ページや機能で定義) ---
# 例:
# portfolio_page_keys = {
#     "balance_df": "portfolio.balance_df",
#     "stock_df": "portfolio.stock_df",
#     "consult_stock_name": "portfolio.consult_stock_name",
#     # ...
# }

# chat_page_keys = {
#     "generated_html": "chat.generated_html",
#     "error_message": "chat.error_message",
#     # ...
# }

# main_app_keys = {
#     "current_step": "app.current_step",
#     "selected_model": "app.selected_model",
#     # ...
# }
