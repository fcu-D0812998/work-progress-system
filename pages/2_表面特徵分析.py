import streamlit as st
import pandas as pd
from PIL import Image
import io
from wetting_angle import calculate_wetting_angles, draw_lines_on_image

# 主標題
st.header("📐 潤濕角度量測工具")

st.markdown("""
**Step 1：前往標註平台**

請先點選下方按鈕，先使用 [makesense.ai](https://www.makesense.ai/) 標註你要量測角度的圖片。完成後請匯出成含有「兩條線段」資訊的 `.csv`。

> 格式：每兩列為一組，欄位為 x1, y1, x2, y2, image_name
""")

col1, _ = st.columns([1, 3])
with col1:
    st.link_button(" 前往 makesense.ai", url="https://www.makesense.ai/", use_container_width=True)

st.markdown("---")
st.markdown("**Step 2：上傳標註後的 CSV 與圖片**")

# 上傳欄位
csv_file = st.file_uploader("上傳標註 CSV", type=["csv"])
image_file = st.file_uploader("上傳對應圖片", type=["jpg", "jpeg", "png"])

if csv_file and image_file:
    try:
        # 計算角度
        csv_text = csv_file.read().decode("utf-8")
        results = calculate_wetting_angles(io.StringIO(csv_text))

        # 讀入圖片
        image_bytes = image_file.read()
        input_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # 執行畫圖（使用 BytesIO 當作 output）
        output_buffer = io.BytesIO()
        draw_lines_on_image(input_image, results, output_buffer)
        output_buffer.seek(0)

        # 顯示圖片
        st.success(" 計算完成，以下為標註圖與角度資訊：")
        st.image(output_buffer, caption="角度標註圖", use_container_width=True)

        # 提供下載按鈕
        st.download_button(
            label=" 下載標註圖片",
            data=output_buffer,
            file_name="wetting_angle_output.jpg",
            mime="image/jpeg"
        )

        # 顯示角度資訊表格
        df = pd.DataFrame([{
            "編號": r["drop_id"],
            "角度": f"{r['angle']:.2f}°",
            "圖片": r["image_name"]
        } for r in results])
        st.table(df)

    except Exception as e:
        st.error(f" 發生錯誤：{e}")
else:
    st.info("請上傳標註 CSV 與對應圖片。")
