"""
Responsive layout components optimized for Galaxy Z Fold 7
カバーディスプレイ（狭い縦長）とメインディスプレイ（広い画面）の両方に対応
"""
import streamlit as st


def inject_responsive_css():
    """
    Galaxy Z Fold 7対応のレスポンシブCSSを注入
    
    - カバーディスプレイ（~280px幅）: 縦スクロール最適化、余白最小化
    - メインディスプレイ（~1768px幅）: 横並び最適化、情報密度向上
    """
    st.markdown("""
    <style>
    /* ========================================
       Galaxy Z Fold 7 Responsive Design
       ======================================== */
    
    /* Base: モバイル最適化（カバーディスプレイ想定） */
    .stApp {
        max-width: 100%;
    }
    
    /* メトリクスカードの最適化 */
    [data-testid="stMetricValue"] {
        font-size: 1.5rem;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem;
    }
    
    /* タブの最適化 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.25rem;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }
    
    .stTabs [data-baseweb="tab"] {
        white-space: nowrap;
        padding: 0.5rem 0.75rem;
        font-size: 0.9rem;
    }
    
    /* テーブルの横スクロール対応 */
    .dataframe-container {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }
    
    /* グラフの高さ調整（カバーディスプレイ） */
    .js-plotly-plot {
        min-height: 250px;
    }
    
    /* ========================================
       カバーディスプレイ（~280px幅）
       極端に狭い縦長画面での最適化
       ======================================== */
    @media (max-width: 320px) {
        /* 余白を最小化 */
        .block-container {
            padding: 1rem 0.5rem;
        }
        
        /* メトリクスを縦積み */
        [data-testid="column"] {
            min-width: 100% !important;
            flex: 1 1 100% !important;
        }
        
        /* タブのフォントサイズ縮小 */
        .stTabs [data-baseweb="tab"] {
            font-size: 0.75rem;
            padding: 0.4rem 0.5rem;
        }
        
        /* ボタンを全幅に */
        .stButton button {
            width: 100%;
        }
        
        /* グラフの高さを縮小 */
        .js-plotly-plot {
            min-height: 200px;
        }
    }
    
    /* ========================================
       タブレット・中間サイズ（321px～1024px）
       ======================================== */
    @media (min-width: 321px) and (max-width: 1024px) {
        .block-container {
            padding: 2rem 1rem;
        }
        
        /* 2カラムレイアウト */
        [data-testid="column"]:nth-child(odd) {
            padding-right: 0.5rem;
        }
        
        [data-testid="column"]:nth-child(even) {
            padding-left: 0.5rem;
        }
    }
    
    /* ========================================
       メインディスプレイ（1025px以上）
       Galaxy Z Fold 7 展開時の広大な画面を活用
       ======================================== */
    @media (min-width: 1025px) {
        .block-container {
            max-width: 1400px;
            padding: 2rem 2rem;
        }
        
        /* 3カラムレイアウト最適化 */
        [data-testid="column"] {
            padding: 0 0.75rem;
        }
        
        /* グラフを大きく表示 */
        .js-plotly-plot {
            min-height: 350px;
        }
        
        /* メトリクスカードを大きく */
        [data-testid="stMetricValue"] {
            font-size: 2rem;
        }
        
        [data-testid="stMetricLabel"] {
            font-size: 1rem;
        }
        
        /* タブを横並びで余裕を持たせる */
        .stTabs [data-baseweb="tab"] {
            padding: 0.75rem 1.5rem;
            font-size: 1rem;
        }
    }
    
    /* ========================================
       超広画面（1600px以上）
       デスクトップやFold展開時の最大活用
       ======================================== */
    @media (min-width: 1600px) {
        .block-container {
            max-width: 1600px;
        }
        
        /* 4カラムレイアウト対応 */
        .stColumns {
            gap: 1.5rem;
        }
        
        /* グラフをさらに大きく */
        .js-plotly-plot {
            min-height: 400px;
        }
    }
    
    /* ========================================
       共通スタイル改善
       ======================================== */
    
    /* Expanderの視認性向上 */
    .streamlit-expanderHeader {
        font-weight: 600;
        border-radius: 0.5rem;
        background-color: rgba(151, 166, 195, 0.1);
    }
    
    /* ボタンのホバー効果 */
    .stButton button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: all 0.2s ease;
    }
    
    /* メトリクスカードの視覚的改善 */
    [data-testid="stMetric"] {
        background-color: rgba(151, 166, 195, 0.05);
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid rgba(151, 166, 195, 0.2);
    }
    
    /* スクロールバーのスタイル改善 */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: rgba(151, 166, 195, 0.1);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: rgba(151, 166, 195, 0.3);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: rgba(151, 166, 195, 0.5);
    }
    </style>
    """, unsafe_allow_html=True)


def responsive_columns(num_columns: int, gap: str = "medium"):
    """
    レスポンシブなカラムを作成
    
    Args:
        num_columns: カラム数（デスクトップ時）
        gap: カラム間の間隔（"small", "medium", "large"）
    
    Returns:
        Streamlit columns
    """
    gap_map = {
        "small": "small",
        "medium": "medium",
        "large": "large"
    }
    return st.columns(num_columns, gap=gap_map.get(gap, "medium"))


def mobile_friendly_dataframe(df, **kwargs):
    """
    モバイルフレンドリーなDataFrame表示
    
    Args:
        df: pandas DataFrame
        **kwargs: st.dataframe に渡す追加引数
    """
    default_kwargs = {
        "use_container_width": True,
        "hide_index": True,
    }
    default_kwargs.update(kwargs)
    st.dataframe(df, **default_kwargs)
