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

# 使用 Streamlit 原生元件顯示 Logo 和標題
logo_base64 = get_logo_base64()
if logo_base64:
    # 使用 columns 來並排顯示
    col1, col2 = st.columns([1, 8])
    with col1:
        st.image(f"data:image/x-icon;base64,{logo_base64}", width=60)
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

1.  工作進度管理：專案進度追蹤與管理
2.  表面特徵分析：計算液滴潤濕角
3.  Dimple 3D 視覺化：3D 凹痕高度圖分析

###  使用方式：
請使用左側邊欄選擇您需要的功能，每個功能都是獨立的模組，可以單獨使用。

""")
