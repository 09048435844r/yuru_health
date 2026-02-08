import streamlit as st
import pandas as pd
import yaml
from datetime import datetime, timedelta
from src.database_manager import DatabaseManager
from src.withings_fetcher import WithingsFetcher
from src.fetchers.oura_fetcher import OuraFetcher
from auth.withings_oauth import WithingsOAuth


st.set_page_config(
    page_title="健康管理システム",
    page_icon="🏥",
    layout="wide"
)


@st.cache_resource
def get_database_manager():
    return DatabaseManager("config/secrets.yaml")


@st.cache_resource
def get_withings_oauth(_db_manager):
    return WithingsOAuth(_db_manager)


@st.cache_resource
def get_withings_config():
    with open("config/settings.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("withings", {})


def main():
    st.title("🏥 健康管理システム")
    st.markdown("---")
    
    db_manager = get_database_manager()
    
    st.sidebar.header("設定")
    st.sidebar.info(f"**環境:** {db_manager.env}")
    st.sidebar.info(f"**DB種別:** {db_manager.db_config['type']}")
    
    st.sidebar.markdown("---")
    st.sidebar.header("🔐 API連携")
    
    withings_oauth = get_withings_oauth(db_manager)
    if withings_oauth.is_authenticated():
        st.sidebar.success("✅ Withings: 認証済み")
        if st.sidebar.button("🔓 Withings認証解除"):
            withings_oauth.clear_tokens()
            st.rerun()
    else:
        st.sidebar.warning("⚠️ Withings: 未認証")
    
    st.sidebar.markdown("---")
    
    menu = st.sidebar.radio(
        "メニュー",
        ["データ表示", "API連携設定", "データ取得", "データベース管理"]
    )
    
    if menu == "データ表示":
        show_data_page(db_manager)
    elif menu == "API連携設定":
        api_connection_page(db_manager)
    elif menu == "データ取得":
        fetch_data_page(db_manager)
    elif menu == "データベース管理":
        database_management_page(db_manager)


def api_connection_page(db_manager: DatabaseManager):
    st.header("🔐 API連携設定")
    
    tab1, tab2 = st.tabs(["Withings", "Oura Ring"])
    
    with tab1:
        st.subheader("🏋️ Withings OAuth2 認証")
        
        withings_oauth = get_withings_oauth(db_manager)
        
        if withings_oauth.is_authenticated():
            st.success("✅ 認証済みです")
            
            user_id = withings_oauth.get_user_id()
            if user_id:
                st.info(f"**ユーザーID:** {user_id}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 トークン更新", type="secondary"):
                    try:
                        withings_oauth.refresh_access_token()
                        st.success("✅ トークンを更新しました")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ エラー: {str(e)}")
            
            with col2:
                if st.button("🔓 認証解除", type="secondary"):
                    withings_oauth.clear_tokens()
                    st.success("✅ 認証を解除しました")
                    st.rerun()
        else:
            st.warning("⚠️ 未認証です。以下の手順で認証してください。")
            
            st.markdown("### 認証手順")
            st.markdown("1. 下のボタンをクリックして認証URLを生成")
            st.markdown("2. 生成されたURLをブラウザで開く")
            st.markdown("3. Withingsにログインして承認")
            st.markdown("4. リダイレクト後のURLから `code=` の後の文字列をコピー")
            st.markdown("5. 下の入力欄にコードを貼り付けて「認証実行」をクリック")
            
            if st.button("🔗 認証URL生成", type="primary"):
                auth_url = withings_oauth.get_authorization_url()
                st.code(auth_url, language=None)
                st.info("👆 このURLをブラウザで開いてください")
            
            st.markdown("---")
            
            auth_code = st.text_input("認証コード", placeholder="リダイレクトURLの code= の後の文字列を入力")
            
            if st.button("✅ 認証実行", type="primary", disabled=not auth_code):
                try:
                    with st.spinner("認証中..."):
                        withings_oauth.exchange_code_for_token(auth_code)
                    st.success("✅ 認証に成功しました！")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 認証エラー: {str(e)}")
    
    with tab2:
        st.subheader("💍 Oura Ring Personal Token")
        
        st.info("Oura RingはPersonal Tokenを使用します。`config/secrets.yaml` に設定してください。")
        
        st.markdown("### 設定方法")
        st.markdown("1. [Oura Cloud](https://cloud.ouraring.com/personal-access-tokens) でPersonal Tokenを取得")
        st.markdown("2. `config/secrets.yaml` の `oura.personal_token` に設定")
        st.markdown("3. アプリを再起動")
        
        st.markdown("---")
        
        if st.button("🔍 接続テスト", type="primary"):
            try:
                oura_fetcher = OuraFetcher({}, db_manager=db_manager)
                if oura_fetcher.authenticate():
                    st.success("✅ Oura Ring APIに接続できました")
                else:
                    st.error("❌ Personal Tokenが設定されていません")
            except Exception as e:
                st.error(f"❌ エラー: {str(e)}")


def show_data_page(db_manager: DatabaseManager):
    st.header("📊 データ表示")
    
    data_type = st.radio("データ種別", ["体重データ (Withings)", "活動データ (Oura)"], horizontal=True)
    
    if data_type == "体重データ (Withings)":
        show_weight_data(db_manager)
    else:
        show_oura_data(db_manager)


def show_weight_data(db_manager: DatabaseManager):
    st.subheader("🏋️ 体重データ (Withings)")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        user_id_filter = st.text_input("ユーザーID", value="")
        limit = st.number_input("表示件数", min_value=10, max_value=1000, value=100, step=10)
    
    try:
        if user_id_filter:
            data = db_manager.get_weight_data(user_id=user_id_filter, limit=limit)
        else:
            data = db_manager.get_weight_data(limit=limit)
        
        if data:
            df = pd.DataFrame(data)
            
            with col1:
                st.subheader(f"📈 体重推移グラフ (直近{len(df)}件)")
                
                if 'measured_at' in df.columns:
                    df['measured_at'] = pd.to_datetime(df['measured_at'])
                    df_sorted = df.sort_values('measured_at')
                    
                    st.line_chart(
                        df_sorted.set_index('measured_at')['weight_kg'],
                        use_container_width=True
                    )
            
            st.subheader("📋 データテーブル")
            
            display_columns = ['id', 'user_id', 'measured_at', 'weight_kg', 'created_at']
            display_df = df[display_columns] if all(col in df.columns for col in display_columns) else df
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )
            
            st.success(f"✅ {len(data)}件のデータを表示中")
            
            with st.expander("📄 生データを表示"):
                if 'raw_data' in df.columns:
                    selected_row = st.selectbox(
                        "行を選択",
                        range(len(df)),
                        format_func=lambda x: f"ID: {df.iloc[x]['id']} - {df.iloc[x]['measured_at']}"
                    )
                    st.json(df.iloc[selected_row]['raw_data'])
                else:
                    st.info("raw_dataカラムが存在しません")
        else:
            st.warning("⚠️ データが見つかりません")
            st.info("「データ取得」メニューからダミーデータを取得してください")
    
    except Exception as e:
        st.error(f"❌ エラーが発生しました: {str(e)}")
        st.info("「データベース管理」メニューからテーブルを初期化してください")


def show_oura_data(db_manager: DatabaseManager):
    st.subheader("💍 活動データ (Oura Ring)")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        user_id_filter = st.text_input("ユーザーID", value="")
        limit = st.number_input("表示件数", min_value=10, max_value=1000, value=100, step=10)
    
    try:
        if user_id_filter:
            data = db_manager.get_oura_data(user_id=user_id_filter, limit=limit)
        else:
            data = db_manager.get_oura_data(limit=limit)
        
        if data:
            df = pd.DataFrame(data)
            
            with col1:
                st.subheader(f"📈 スコア推移グラフ (直近{len(df)}件)")
                
                if 'measured_at' in df.columns:
                    df['measured_at'] = pd.to_datetime(df['measured_at'])
                    df_sorted = df.sort_values('measured_at')
                    
                    chart_data = df_sorted.set_index('measured_at')[['activity_score', 'sleep_score', 'readiness_score']].dropna()
                    
                    if not chart_data.empty:
                        st.line_chart(chart_data, use_container_width=True)
            
            st.subheader("📋 データテーブル")
            
            display_columns = ['id', 'user_id', 'measured_at', 'activity_score', 'sleep_score', 'readiness_score', 'steps', 'created_at']
            display_df = df[display_columns] if all(col in df.columns for col in display_columns) else df
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )
            
            st.success(f"✅ {len(data)}件のデータを表示中")
            
            with st.expander("📄 生データを表示"):
                if 'raw_data' in df.columns:
                    selected_row = st.selectbox(
                        "行を選択",
                        range(len(df)),
                        format_func=lambda x: f"ID: {df.iloc[x]['id']} - {df.iloc[x]['measured_at']}"
                    )
                    st.json(df.iloc[selected_row]['raw_data'])
                else:
                    st.info("raw_dataカラムが存在しません")
        else:
            st.warning("⚠️ データが見つかりません")
            st.info("「データ取得」メニューからOuraデータを取得してください")
    
    except Exception as e:
        st.error(f"❌ エラーが発生しました: {str(e)}")
        st.info("「データベース管理」メニューからテーブルを初期化してください")


def fetch_data_page(db_manager: DatabaseManager):
    st.header("🔄 データ取得")
    
    data_source = st.radio("データソース", ["Withings (体重)", "Oura Ring (活動)"], horizontal=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        user_id = st.text_input("ユーザーID", value="user_001")
        days = st.number_input("取得日数", min_value=1, max_value=365, value=30)
    
    with col2:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        st.write("**取得期間**")
        st.write(f"開始: {start_date.strftime('%Y-%m-%d')}")
        st.write(f"終了: {end_date.strftime('%Y-%m-%d')}")
    
    if data_source == "Withings (体重)":
        withings_oauth = get_withings_oauth(db_manager)
        
        if not withings_oauth.is_authenticated():
            st.warning("⚠️ Withingsの認証が必要です。「API連携設定」メニューから認証してください。")
            return
        
        if st.button("📥 Withingsデータ取得", type="primary"):
            try:
                with st.spinner("Withings APIからデータを取得中..."):
                    withings_config = get_withings_config()
                    fetcher = WithingsFetcher(withings_config, withings_oauth)
                    
                    data = fetcher.fetch_data(
                        user_id=user_id,
                        start_date=start_date.strftime("%Y-%m-%d"),
                        end_date=end_date.strftime("%Y-%m-%d")
                    )
                    
                    if data:
                        progress_bar = st.progress(0)
                        for i, record in enumerate(data):
                            db_manager.insert_weight_data(
                                user_id=record["user_id"],
                                measured_at=record["measured_at"],
                                weight_kg=record["weight_kg"],
                                raw_data=record["raw_data"]
                            )
                            progress_bar.progress((i + 1) / len(data))
                        
                        st.success(f"✅ {len(data)}件のデータを取得・保存しました")
                        st.balloons()
                        st.info("「データ表示」メニューで確認できます")
                    else:
                        st.warning("⚠️ 指定期間のデータが見つかりませんでした")
            
            except Exception as e:
                st.error(f"❌ エラーが発生しました: {str(e)}")
                st.info("エラーの詳細を確認してください。認証が切れている場合は再認証してください。")
    
    else:
        try:
            oura_fetcher = OuraFetcher({}, db_manager=db_manager)
            if not oura_fetcher.authenticate():
                st.warning("⚠️ Oura Ring Personal Tokenが設定されていません。`config/secrets.yaml` に設定してください。")
                return
        except Exception as e:
            st.error(f"❌ Oura設定エラー: {str(e)}")
            return
        
        if st.button("📥 Ouraデータ取得", type="primary"):
            try:
                with st.spinner("Oura APIからデータを取得中..."):
                    oura_fetcher = OuraFetcher({}, db_manager=db_manager)
                    
                    data = oura_fetcher.fetch_data(
                        user_id=user_id,
                        start_date=start_date.strftime("%Y-%m-%d"),
                        end_date=end_date.strftime("%Y-%m-%d")
                    )
                    
                    if data:
                        progress_bar = st.progress(0)
                        for i, record in enumerate(data):
                            db_manager.insert_oura_data(
                                user_id=record["user_id"],
                                measured_at=record["measured_at"],
                                activity_score=record.get("activity_score"),
                                sleep_score=record.get("sleep_score"),
                                readiness_score=record.get("readiness_score"),
                                steps=record.get("steps"),
                                total_sleep_duration=record.get("total_sleep_duration"),
                                raw_data=record["raw_data"]
                            )
                            progress_bar.progress((i + 1) / len(data))
                        
                        st.success(f"✅ {len(data)}件のデータを取得・保存しました")
                        st.balloons()
                        st.info("「データ表示」メニューで確認できます")
                    else:
                        st.warning("⚠️ 指定期間のデータが見つかりませんでした")
            
            except Exception as e:
                st.error(f"❌ エラーが発生しました: {str(e)}")
                st.info("エラーの詳細を確認してください。Personal Tokenが正しいか確認してください。")


def database_management_page(db_manager: DatabaseManager):
    st.header("🗄️ データベース管理")
    
    st.subheader("データベース情報")
    col1, col2 = st.columns(2)
    
    with col1:
        st.info(f"**環境:** {db_manager.env}")
        st.info(f"**DB種別:** {db_manager.db_config['type']}")
    
    with col2:
        st.info(f"**接続先:** Supabase (PostgreSQL)")
    
    st.markdown("---")
    
    st.subheader("テーブル操作")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔧 テーブル初期化", type="primary"):
            try:
                db_manager.init_tables()
                st.success("✅ テーブルを初期化しました")
            except Exception as e:
                st.error(f"❌ エラー: {str(e)}")
    
    with col2:
        if st.button("🔍 接続テスト"):
            try:
                db_manager.get_weight_data(limit=1)
                st.success("✅ Supabaseに接続できました")
            except Exception as e:
                st.error(f"❌ 接続エラー: {str(e)}")
    
    st.markdown("---")
    
    st.subheader("⚠️ 危険な操作")
    
    with st.expander("データ削除"):
        st.warning("この操作は取り消せません")
        
        confirm = st.text_input("削除を実行するには「DELETE」と入力してください")
        
        if st.button("🗑️ 全データ削除", type="secondary"):
            if confirm == "DELETE":
                try:
                    db_manager.supabase.table("weight_data").delete().neq("id", 0).execute()
                    st.success("✅ 全データを削除しました")
                except Exception as e:
                    st.error(f"❌ エラー: {str(e)}")
            else:
                st.error("確認文字列が正しくありません")


if __name__ == "__main__":
    main()
