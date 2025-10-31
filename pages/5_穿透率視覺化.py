import io
import os
from typing import List, Tuple, Optional

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio


def clean_sample_name(name: str) -> str:
    if not isinstance(name, str):
        return str(name)
    cleaned = name.strip()
    for suffix in (" RawData", " raw", " data", "_raw", "-raw"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    return cleaned


def detect_columns(df: pd.DataFrame) -> Tuple[str, List[str]]:
    if df.shape[1] < 2:
        raise ValueError("CSV 至少需要 2 欄：波長 + 至少一個樣品欄位")
    wavelength_col = df.columns[0]
    sample_cols = list(df.columns[1:])
    return wavelength_col, sample_cols


def to_numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


@st.cache_data(show_spinner=False)
def try_read_csv_path(file_path: str) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "cp950"):
        try:
            return pd.read_csv(file_path, sep=None, engine="python", encoding=encoding)
        except Exception:
            continue
    return pd.read_csv(file_path)


@st.cache_data(show_spinner=False)
def try_read_csv_bytes(content: bytes, filename: str) -> pd.DataFrame:
    buffer = io.BytesIO(content)
    for encoding in ("utf-8-sig", "utf-8", "cp950"):
        try:
            buffer.seek(0)
            return pd.read_csv(buffer, sep=None, engine="python", encoding=encoding)
        except Exception:
            continue
    buffer.seek(0)
    return pd.read_csv(buffer)


def generate_demo_dataframe() -> pd.DataFrame:
    wavelengths = np.linspace(400, 800, 251)
    s1 = np.exp(-((wavelengths - 500) ** 2) / (2 * 25 ** 2))
    s2 = 0.6 * np.exp(-((wavelengths - 600) ** 2) / (2 * 35 ** 2))
    s3 = 0.4 + 0.1 * np.sin((wavelengths - 400) / 400 * 8 * np.pi)
    df = pd.DataFrame({
        "Wavelength(nm)": wavelengths,
        "Material A": s1,
        "Material B": s2,
        "Material C": s3,
    })
    return df


def build_3d_stacked_figure(
    df: pd.DataFrame,
    wavelength_col: str,
    sample_cols: List[str],
    title: str,
    x_label: str,
    y_label: str,
    z_label: str,
    palette_name: str,
    line_width: float,
    opacity: float,
    elev_default_camera: bool = True,
) -> go.Figure:
    wavelengths = to_numeric_series(df[wavelength_col]).to_numpy()
    valid_mask = np.isfinite(wavelengths)
    wavelengths = wavelengths[valid_mask]

    cleaned_names = [clean_sample_name(c) for c in sample_cols]
    y_positions = np.arange(len(sample_cols))

    qualitative_palettes = {
        "Plotly": px.colors.qualitative.Plotly,
        "D3": px.colors.qualitative.D3,
        "G10": px.colors.qualitative.G10,
        "T10": px.colors.qualitative.T10,
        "Alphabet": px.colors.qualitative.Alphabet,
        "Dark24": px.colors.qualitative.Dark24,
        "Light24": px.colors.qualitative.Light24,
        "Set3": px.colors.qualitative.Set3,
    }
    colors = qualitative_palettes.get(palette_name, px.colors.qualitative.Plotly)

    fig = go.Figure()
    for idx, (col, y_pos, label) in enumerate(zip(sample_cols, y_positions, cleaned_names)):
        values = to_numeric_series(df[col]).to_numpy()
        values = values[valid_mask]
        color = colors[idx % len(colors)]
        fig.add_trace(
            go.Scatter3d(
                x=wavelengths,
                y=np.full_like(wavelengths, fill_value=float(y_pos)),
                z=values,
                mode="lines",
                line=dict(color=color, width=line_width),
                opacity=opacity,
                name=label,
            )
        )

    fig.update_layout(
        title=title,
        scene=dict(
            xaxis_title=x_label,
            yaxis_title=y_label,
            zaxis_title=z_label,
            yaxis=dict(
                tickmode="array",
                tickvals=y_positions.tolist(),
                ticktext=cleaned_names,
            ),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=0, r=0, t=60, b=0),
    )

    if elev_default_camera:
        fig.update_scenes(camera=dict(eye=dict(x=-1.6, y=-1.6, z=1.0)))

    return fig


def filter_df_by_range(df: pd.DataFrame, wavelength_col: str, min_w: float, max_w: float) -> pd.DataFrame:
    w = to_numeric_series(df[wavelength_col])
    mask = (w >= min_w) & (w <= max_w)
    return df.loc[mask].reset_index(drop=True)


st.header("穿透率 3D 視覺化")

# 檔案上傳
uploaded_file = st.file_uploader("上傳 CSV 檔案", type=["csv"]) 

df: Optional[pd.DataFrame] = None
if uploaded_file is not None:
    try:
        df = try_read_csv_bytes(uploaded_file.read(), uploaded_file.name)
    except Exception as e:
        st.error(f"讀取 CSV 檔案時發生錯誤: {e}")
        st.stop()

if df is None:
    st.info("請上傳 CSV 檔案開始。格式：第 1 欄為波長 (nm)，其後每欄為樣品的穿透率。")
    st.caption("提示：支援自動偵測分隔符與常見編碼 (UTF-8/UTF-8-SIG/CP950)")
    st.stop()

# 基本清理
df = df.dropna(how="all")

# 欄位設定
st.subheader("欄位設定")
try:
    default_wave_col, default_samples = detect_columns(df)
except Exception:
    default_wave_col, default_samples = df.columns[0], list(df.columns[1:])

# 自動使用第一欄為波長欄（不提供選擇）
wavelength_col = default_wave_col
all_sample_candidates = [c for c in df.columns if c != wavelength_col]
default_selected_samples = [c for c in all_sample_candidates if c in default_samples] or all_sample_candidates
sample_cols = st.multiselect("樣品欄（可多選）", options=all_sample_candidates, default=default_selected_samples)

# 指標樣品（與圖表多選分離）
stat_sample = st.selectbox("指標樣品（用於下方統計）", options=all_sample_candidates, index=0, format_func=clean_sample_name)

if not sample_cols:
    st.error("請至少選擇一個樣品欄位")
    st.stop()

# 預設視覺化參數（移除互動設定）
w_numeric = to_numeric_series(df[wavelength_col])
w_min, w_max = float(np.nanmin(w_numeric)), float(np.nanmax(w_numeric))
min_w, max_w = w_min, w_max

palette_name = "Plotly"
line_width = 2
opacity = 1.0

title = "Spectra - 3D Stacked Lines"
x_label = "Wavelength (nm)"
y_label = "Sample"
z_label = "Transmittance"

reset_view = True

# 範圍過濾（包含指標樣品，避免未勾選仍需計算時缺欄位）
columns_for_filter = [wavelength_col] + sample_cols
if stat_sample not in columns_for_filter:
    columns_for_filter = [wavelength_col] + list(dict.fromkeys(sample_cols + [stat_sample]))
df_filtered = filter_df_by_range(df[columns_for_filter], wavelength_col, min_w, max_w)

# 統計設定與單一樣品統計卡片（移到上方顯示）
st.subheader("規格設定 (CPK 計算)")
col_cfg1, col_cfg2 = st.columns(2)
with col_cfg1:
    usl = st.number_input("規格上限 (USL):", value=1.0000, step=0.0001, format="%.4f")
with col_cfg2:
    lsl = st.number_input("規格下限 (LSL):", value=0.0000, step=0.0001, format="%.4f")

st.subheader("統計分析")

series = to_numeric_series(df_filtered[stat_sample])
series = series[np.isfinite(series)]
if series.empty:
    st.warning(f"樣品 {stat_sample} 無有效數據")
else:
    s_mean = float(series.mean())
    s_std = float(series.std(ddof=1)) if len(series) > 1 else 0.0
    s_min = float(series.min())
    s_max = float(series.max())
    s_range = s_max - s_min
    snr = (s_mean / s_std) if s_std > 0 else float("inf")

    within_1 = int(((series >= s_mean - s_std) & (series <= s_mean + s_std)).sum()) if s_std > 0 else len(series)
    within_2 = int(((series >= s_mean - 2*s_std) & (series <= s_mean + 2*s_std)).sum()) if s_std > 0 else len(series)
    within_3 = int(((series >= s_mean - 3*s_std) & (series <= s_mean + 3*s_std)).sum()) if s_std > 0 else len(series)
    total_n = int(len(series))
    pct_1 = within_1 / total_n * 100.0
    pct_2 = within_2 / total_n * 100.0
    pct_3 = within_3 / total_n * 100.0

    # CPK 計算（條件：std>0 且 USL>LSL）
    cpk = None
    cpk_upper = None
    cpk_lower = None
    cpk_status = "無法計算"
    if s_std > 0 and (usl > lsl):
        cpk_upper = (usl - s_mean) / (3 * s_std)
        cpk_lower = (s_mean - lsl) / (3 * s_std)
        cpk = min(cpk_upper, cpk_lower)
        if cpk >= 1.67:
            cpk_status = "🟢 優秀 (Cpk ≥ 1.67)"
        elif cpk >= 1.33:
            cpk_status = "🟡 良好 (1.33 ≤ Cpk < 1.67)"
        elif cpk >= 1.0:
            cpk_status = "🟠 可接受 (1.0 ≤ Cpk < 1.33)"
        else:
            cpk_status = "🔴 需改善 (Cpk < 1.0)"
    elif s_std == 0:
        cpk_status = "資料標準差為 0，無法計算 Cpk"
    else:
        cpk_status = "USL 必須大於 LSL"

    st.markdown(f"**樣品：{clean_sample_name(stat_sample)}**")
    col_a, col_b, col_c, col_d, col_e, col_f = st.columns(6)
    with col_a:
        st.metric("平均值", f"{s_mean:.4f}")
        st.metric("標準差", f"{s_std:.4f}")
    with col_b:
        st.metric("最小值", f"{s_min:.4f}")
        st.metric("最大值", f"{s_max:.4f}")
    with col_c:
        st.metric("±1σ 範圍內", f"{within_1}/{total_n}", f"{pct_1:.1f}%")
    with col_d:
        st.metric("±2σ 範圍內", f"{within_2}/{total_n}", f"{pct_2:.1f}%")
    with col_e:
        st.metric("±3σ 範圍內", f"{within_3}/{total_n}", f"{pct_3:.1f}%")
    with col_f:
        if cpk is not None:
            st.metric("CPK 指標", f"{cpk:.3f}")
        else:
            st.metric("CPK 指標", "—")

    # 移除卡片下方輔助資訊（範圍、樣本數、CPK 上/下限 caption）

    st.subheader("CPK 製程能力分析")
    col_cpk_l, col_cpk_r = st.columns(2)
    with col_cpk_l:
        st.write(f"規格範圍: {lsl:.4f} ~ {usl:.4f}")
        st.write(f"規格公差: {usl - lsl:.4f}")
        if cpk is not None:
            st.write(f"CPK 值: {cpk:.3f}")
        else:
            st.write("CPK 值: —")
    with col_cpk_r:
        st.write(f"製程能力: {cpk_status}")
        if (cpk_upper is not None) and (cpk_lower is not None):
            st.write(f"CPK 上限: {cpk_upper:.3f}")
            st.write(f"CPK 下限: {cpk_lower:.3f}")
        else:
            st.write("CPK 上限: —")
            st.write("CPK 下限: —")

    st.subheader("標準差範圍分析")
    st.write(f"±1σ 範圍: {s_mean - s_std:.4f} ~ {s_mean + s_std:.4f}")
    st.write(f"±2σ 範圍: {s_mean - 2*s_std:.4f} ~ {s_mean + 2*s_std:.4f}")
    st.write(f"±3σ 範圍: {s_mean - 3*s_std:.4f} ~ {s_mean + 3*s_std:.4f}")

# 繪圖（位置移到統計卡片之後）
fig = build_3d_stacked_figure(
    df=df_filtered,
    wavelength_col=wavelength_col,
    sample_cols=sample_cols,
    title=title,
    x_label=x_label,
    y_label=y_label,
    z_label=z_label,
    palette_name=palette_name,
    line_width=float(line_width),
    opacity=float(opacity),
    elev_default_camera=reset_view or True,
)

st.plotly_chart(fig, use_container_width=True)



