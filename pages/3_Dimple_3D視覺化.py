import streamlit as st
import pandas as pd
import show
import chardet
import re

# 主標題
st.header("📊 AMAT Heater Dimple 3D Viewer")

def parse_chinese_format(content):
    """解析中文格式的檔案"""
    data = []
    lines = content.strip().split('\n')
    
    for line in lines:
        if line.strip():
            # 使用正則表達式提取點名稱和座標值
            # 格式: 點 Z1: X 座標   7.9578  點 Z1: Y 座標   -0.0517 點 Z1: Z 座標   0.0427
            pattern = r'點\s*([^:]+):\s*X\s*座標\s*([-\d.]+)\s*點\s*\1:\s*Y\s*座標\s*([-\d.]+)\s*點\s*\1:\s*Z\s*座標\s*([-\d.]+)'
            match = re.search(pattern, line)
            
            if match:
                point_name = match.group(1)
                x_value = float(match.group(2))
                y_value = float(match.group(3))
                z_value = float(match.group(4))
                
                # 轉換為程式期望的格式: [Z1, X, Z1, Y, Z1, Z]
                data.append([point_name, x_value, point_name, y_value, point_name, z_value])
    
    return data

# 檔案上傳
uploaded_file = st.file_uploader("上傳 CSV 檔案", type=['csv', 'xlsx'])

if uploaded_file is not None:
    try:
        # 判斷格式
        if uploaded_file.name.endswith('.csv'):
            # 先讀取檔案內容來檢測編碼
            raw_content = uploaded_file.read()
            uploaded_file.seek(0)  # 重置檔案指標
            
            # 使用 chardet 自動檢測編碼
            detected_encoding = chardet.detect(raw_content)
            st.info(f"檢測到的編碼: {detected_encoding['encoding']} (信心度: {detected_encoding['confidence']:.2f})")
            
            # 嘗試不同的編碼
            encodings_to_try = [
                detected_encoding['encoding'] if detected_encoding['confidence'] > 0.7 else None,
                'utf-8',
                'big5',
                'gbk',
                'gb2312',
                'latin1',
                'cp950',
                'utf-8-sig'
            ]
            
            content = None
            used_encoding = None
            
            for encoding in encodings_to_try:
                if encoding:
                    try:
                        content = raw_content.decode(encoding)
                        used_encoding = encoding
                        st.success(f"成功使用編碼: {encoding}")
                        break
                    except (UnicodeDecodeError, LookupError):
                        continue
            
            if content is None:
                st.error("無法解碼檔案，請檢查檔案編碼")
                st.stop()
            
            # 檢查檔案格式
            lines = content.strip().split('\n')
            if len(lines) > 0:
                first_line = lines[0]
                
                # 檢查是否為中文格式
                if '點' in first_line and '座標' in first_line:
                    st.info("檢測到中文格式檔案")
                    data = parse_chinese_format(content)
                    if data:
                        df = pd.DataFrame(data)
                    else:
                        st.error("無法解析中文格式檔案")
                        st.stop()
                        
                # 檢查是否為標準 CSV 格式
                elif ',' in first_line:
                    st.info("檢測到標準 CSV 格式")
                    try:
                        df = pd.read_csv(uploaded_file, encoding=used_encoding, header=None)
                    except Exception as e:
                        st.error(f"讀取 CSV 檔案時發生錯誤: {str(e)}")
                        st.stop()
                        
                # 檢查是否為特殊格式（每行一個資料點）
                else:
                    st.info("檢測到特殊格式檔案")
                    data = []
                    for line in lines:
                        if line.strip():  # 跳過空行
                            parts = line.strip().split(',')
                            if len(parts) >= 6:  # 確保有足夠的欄位
                                data.append(parts)
                    
                    if data:
                        df = pd.DataFrame(data)
                    else:
                        st.error("檔案格式不正確或檔案為空")
                        st.stop()
            else:
                st.error("檔案為空")
                st.stop()
                    
        elif uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file, header=None)
        else:
            st.error("不支援的檔案格式")
            st.stop()

        # 檢查資料是否為空
        if df.empty:
            st.error("檔案沒有資料或格式不正確")
            st.stop()
        
        # 直接使用 show.py 的 create_visualization 函數
        fig = show.create_visualization(df)
        
        # 使用全寬顯示圖表，並設定高度
        st.plotly_chart(fig, use_container_width=True, height=800)
        
    except Exception as e:
        st.error(f"處理檔案時發生錯誤: {str(e)}")
        st.write("請確保上傳的檔案包含有效的資料")
        st.write("如果問題持續，請嘗試將檔案另存為 UTF-8 編碼")
        st.stop()
else:
    st.info("請上傳 CSV 或 Excel 檔案來開始 3D 視覺化。")
