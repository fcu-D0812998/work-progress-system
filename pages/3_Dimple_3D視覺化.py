import streamlit as st
import pandas as pd
import show
import chardet
import re

# 主標題
st.header(" AMAT Heater Dimple 3D Viewer")

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
        
        # 計算標準差統計資訊
        z_values = df.iloc[:, 5].astype(float)  # 假設 Z 值在第6欄（索引5）
        z_mean = z_values.mean()
        z_std = z_values.std()
        z_min = z_values.min()
        z_max = z_values.max()
        
        # 計算各標準差範圍內的資料點數量
        within_1std = len(z_values[(z_values >= z_mean - z_std) & (z_values <= z_mean + z_std)])
        within_2std = len(z_values[(z_values >= z_mean - 2*z_std) & (z_values <= z_mean + 2*z_std)])
        within_3std = len(z_values[(z_values >= z_mean - 3*z_std) & (z_values <= z_mean + 3*z_std)])
        
        # 計算百分比
        total_points = len(z_values)
        pct_1std = (within_1std / total_points) * 100
        pct_2std = (within_2std / total_points) * 100
        pct_3std = (within_3std / total_points) * 100
        
        # 顯示統計資訊
        st.subheader("📊 統計分析")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("平均值 (mm)", f"{z_mean:.4f}")
            st.metric("標準差 (mm)", f"{z_std:.4f}")
        
        with col2:
            st.metric("最小值 (mm)", f"{z_min:.4f}")
            st.metric("最大值 (mm)", f"{z_max:.4f}")
        
        with col3:
            st.metric("±1σ 範圍內", f"{within_1std}/{total_points}", f"{pct_1std:.1f}%")
            st.metric("±2σ 範圍內", f"{within_2std}/{total_points}", f"{pct_2std:.1f}%")
        
        with col4:
            st.metric("±3σ 範圍內", f"{within_3std}/{total_points}", f"{pct_3std:.1f}%")
            st.metric("變異係數", f"{(z_std/z_mean)*100:.2f}%")
        
        # 標準差範圍顯示
        st.subheader("📈 標準差範圍分析")
        st.write(f"**±1σ 範圍**: {z_mean - z_std:.4f} ~ {z_mean + z_std:.4f} mm")
        st.write(f"**±2σ 範圍**: {z_mean - 2*z_std:.4f} ~ {z_mean + 2*z_std:.4f} mm")
        st.write(f"**±3σ 範圍**: {z_mean - 3*z_std:.4f} ~ {z_mean + 3*z_std:.4f} mm")
        
        # 閾值分析
        st.subheader("🎯 閾值分析")
        col1, col2 = st.columns(2)
        
        with col1:
            threshold_value = st.number_input(
                "輸入閾值 (mm):",
                value=0.77,
                step=0.01,
                format="%.4f",
                help="輸入一個數值來分析有多少測量值在這個閾值之上或之下"
            )
        
        with col2:
            threshold_direction = st.selectbox(
                "分析方向:",
                ["小於等於閾值", "大於等於閾值", "等於閾值 (±0.001)"]
            )
        
        # 計算閾值分析結果
        if threshold_direction == "小於等於閾值":
            threshold_count = len(z_values[z_values <= threshold_value])
            threshold_pct = (threshold_count / total_points) * 100
            st.success(f"📊 **小於等於 {threshold_value:.4f} mm 的資料點**: {threshold_count}/{total_points} 個 ({threshold_pct:.1f}%)")
        elif threshold_direction == "大於等於閾值":
            threshold_count = len(z_values[z_values >= threshold_value])
            threshold_pct = (threshold_count / total_points) * 100
            st.success(f"📊 **大於等於 {threshold_value:.4f} mm 的資料點**: {threshold_count}/{total_points} 個 ({threshold_pct:.1f}%)")
        else:  # 等於閾值
            threshold_count = len(z_values[abs(z_values - threshold_value) <= 0.001])
            threshold_pct = (threshold_count / total_points) * 100
            st.success(f"📊 **等於 {threshold_value:.4f} mm (±0.001) 的資料點**: {threshold_count}/{total_points} 個 ({threshold_pct:.1f}%)")
        
        # 顯示閾值範圍內的資料
        if threshold_direction == "小於等於閾值":
            df_threshold = df[z_values <= threshold_value]
        elif threshold_direction == "大於等於閾值":
            df_threshold = df[z_values >= threshold_value]
        else:
            df_threshold = df[abs(z_values - threshold_value) <= 0.001]
        
        if len(df_threshold) > 0:
            st.write(f"**閾值範圍內的資料點**: {list(df_threshold.iloc[:, 0])}")  # 顯示點名稱
        
        # 標準差過濾選項
        st.subheader("🔍 資料過濾選項")
        filter_option = st.selectbox(
            "選擇要顯示的資料範圍：",
            ["顯示所有資料", "±1σ 範圍內", "±2σ 範圍內", "±3σ 範圍內", "自定義標準差倍數", f"閾值分析: {threshold_direction} {threshold_value:.4f}mm"]
        )
        
        # 根據選擇過濾資料
        if filter_option == "±1σ 範圍內":
            df_filtered = df[(z_values >= z_mean - z_std) & (z_values <= z_mean + z_std)]
            st.info(f"顯示 ±1σ 範圍內的資料：{len(df_filtered)}/{total_points} 個點 ({pct_1std:.1f}%)")
        elif filter_option == "±2σ 範圍內":
            df_filtered = df[(z_values >= z_mean - 2*z_std) & (z_values <= z_mean + 2*z_std)]
            st.info(f"顯示 ±2σ 範圍內的資料：{len(df_filtered)}/{total_points} 個點 ({pct_2std:.1f}%)")
        elif filter_option == "±3σ 範圍內":
            df_filtered = df[(z_values >= z_mean - 3*z_std) & (z_values <= z_mean + 3*z_std)]
            st.info(f"顯示 ±3σ 範圍內的資料：{len(df_filtered)}/{total_points} 個點 ({pct_3std:.1f}%)")
        elif filter_option == "自定義標準差倍數":
            std_multiplier = st.slider("標準差倍數", 0.1, 5.0, 2.0, 0.1)
            df_filtered = df[(z_values >= z_mean - std_multiplier*z_std) & (z_values <= z_mean + std_multiplier*z_std)]
            filtered_count = len(df_filtered)
            filtered_pct = (filtered_count / total_points) * 100
            st.info(f"顯示 ±{std_multiplier}σ 範圍內的資料：{filtered_count}/{total_points} 個點 ({filtered_pct:.1f}%)")
        elif filter_option.startswith("閾值分析"):
            # 使用之前計算的閾值過濾結果
            df_filtered = df_threshold
            filtered_count = len(df_filtered)
            filtered_pct = (filtered_count / total_points) * 100
            st.info(f"顯示閾值分析結果：{filtered_count}/{total_points} 個點 ({filtered_pct:.1f}%)")
        else:
            df_filtered = df
            st.info(f"顯示所有資料：{total_points} 個點")
        
        # 直接使用 show.py 的 create_visualization 函數
        fig = show.create_visualization(df_filtered)
        
        # 使用全寬顯示圖表，並設定高度
        st.plotly_chart(fig, use_container_width=True, height=800)
        
    except Exception as e:
        st.error(f"處理檔案時發生錯誤: {str(e)}")
        st.write("請確保上傳的檔案包含有效的資料")
        st.write("如果問題持續，請嘗試將檔案另存為 UTF-8 編碼")
        st.stop()
else:
    st.info("請上傳 CSV 或 Excel 檔案來開始 3D 視覺化。")
