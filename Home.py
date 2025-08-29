import streamlit as st
import base64

# 設定頁面配置
st.set_page_config(
    page_title="德烜科技半導體作業作業平台",
    page_icon="logoicon.ico",
    layout="wide"
)

# 載入並顯示公司 Logo
def get_logo_base64():
    """將 logo 轉換為 base64 格式"""
    try:
        with open("logoicon.ico", "rb") as f:
            logo_data = f.read()
        logo_base64 = base64.b64encode(logo_data).decode()
        return logo_base64
    except:
        return None

# 顯示 Logo 和標題並排
logo_base64 = get_logo_base64()
if logo_base64:
    col1, col2 = st.columns([1, 4])
    with col1:
        st.markdown(f"""
        <div style="text-align: center; margin: 0.5rem 0;">
            <img src="data:image/x-icon;base64,{logo_base64}" alt="德烜科技 Logo" style="max-width: 80px; height: auto; vertical-align: middle;">
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.title("德烜科技半導體工作平台")
else:
    # 如果沒有 Logo，只顯示標題
    st.title("德烜科技半導體工作平台")

st.markdown("---")

# 簡介
st.markdown("""
##  歡迎使用德烜科技半導體部門工作平台

###  目前功能：

1.  表面特徵分析：計算液滴潤濕角
2.  Dimple 3D 視覺化：3D 凹痕高度圖分析
3.  工作進度管理：專案進度追蹤與管理
4.  客品編號派工單：自動化派工單生成

###  使用方式：
請使用左側邊欄選擇您需要的功能，每個功能都是獨立的模組，可以單獨使用。

###  技術特色：
- 多頁面應用架構
- 即時資料處理
- 互動式視覺化
- 自動化檔案處理
""")
