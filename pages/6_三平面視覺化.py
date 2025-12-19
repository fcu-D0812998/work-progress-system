import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.interpolate import griddata
from typing import Optional


PLANE_MARKER_SIZE = 3
PLANE_MARKER_COLOR = "rgb(255,255,255)"
PLANE_MARKER_OPACITY = 0.25


def non_linear_scale_z(
    z: np.ndarray,
    threshold1: float = 0.6,
    threshold2: float = 0.8,
    scale_factor: float = 2.0,
) -> np.ndarray:
    """
    非線性縮放 Z 軸值（僅用於視覺化，數據本身不變）
    - 0 到 threshold1: 維持原比例
    - threshold1 到 threshold2: 放大顯示（scale_factor 倍）
    - threshold2 以上: 線性延續
    """
    z_scaled = z.copy()
    mask1 = (z >= 0) & (z <= threshold1)
    mask2 = (z > threshold1) & (z <= threshold2)
    mask3 = z > threshold2

    z_scaled[mask1] = z[mask1]
    z_scaled[mask2] = threshold1 + scale_factor * (z[mask2] - threshold1)

    if np.any(mask3):
        z_scaled[mask3] = (
            threshold1
            + scale_factor * (threshold2 - threshold1)
            + (z[mask3] - threshold2)
        )

    return z_scaled


def griddata_with_fallback(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    xi_grid: np.ndarray,
    yi_grid: np.ndarray,
    fill_value: float = np.nan,
) -> np.ndarray:
    """
    先嘗試 cubic，失敗則 fallback 到 linear，再到 nearest。
    """
    for method in ("cubic", "linear", "nearest"):
        try:
            return griddata(
                (x, y),
                z,
                (xi_grid, yi_grid),
                method=method,
                fill_value=fill_value,
            )
        except Exception:
            continue
    raise ValueError("griddata 插值失敗：cubic/linear/nearest 都無法完成，請檢查資料點分佈與數量。")


def create_offset_surface(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    name: str,
    colorscale: str,
    z_title: str = "差異 (mm)",
    apply_nonlinear_scale: bool = False,
    coloraxis: Optional[str] = None,
    show_colorbar: bool = True,
) -> go.Surface:
    """建立差異值曲面圖（Z 可視覺化縮放；顏色仍對應原始 z）"""
    z_display = non_linear_scale_z(z) if apply_nonlinear_scale else z

    x_min, x_max = float(np.nanmin(x)), float(np.nanmax(x))
    y_min, y_max = float(np.nanmin(y)), float(np.nanmax(y))

    x_range = x_max - x_min
    y_range = y_max - y_min
    x_min -= x_range * 0.05
    x_max += x_range * 0.05
    y_min -= y_range * 0.05
    y_max += y_range * 0.05

    grid_resolution = 50
    xi = np.linspace(x_min, x_max, grid_resolution)
    yi = np.linspace(y_min, y_max, grid_resolution)
    xi_grid, yi_grid = np.meshgrid(xi, yi)

    zi_grid = griddata_with_fallback(x, y, z_display, xi_grid, yi_grid, fill_value=np.nan)
    zi_grid_original = griddata_with_fallback(x, y, z, xi_grid, yi_grid, fill_value=np.nan)

    return go.Surface(
        x=xi_grid,
        y=yi_grid,
        z=zi_grid,
        surfacecolor=zi_grid_original,
        name=name,
        colorscale=colorscale,
        coloraxis=coloraxis,
        showscale=show_colorbar,
        colorbar=dict(title=z_title) if show_colorbar else None,
        opacity=0.9,
    )


def calc_cmin_cmax(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, 1.0
    cmin = float(np.nanmin(finite))
    cmax = float(np.nanmax(finite))
    if cmin == cmax:
        # 避免色階範圍為 0 導致顯示怪異
        eps = 1e-9 if cmin == 0 else abs(cmin) * 1e-6
        return cmin - eps, cmax + eps
    return cmin, cmax


def require_columns(df: pd.DataFrame, required: list[str], label: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{label} 缺少必要欄位：{missing}")


def clean_common_excel(df: pd.DataFrame) -> pd.DataFrame:
    if "項目" not in df.columns:
        return df
    df = df[df["項目"].notna()].copy()
    df = df[df["項目"] != "數據"].copy()
    df["項目"] = df["項目"].astype(str).str.strip()
    return df


st.header("三平面視覺化（座標 / 孔徑 / 真圓度）")
st.caption("請依序上傳 3 份 Excel")

col_u1, col_u2, col_u3 = st.columns(3)
with col_u1:
    coord_file = st.file_uploader("上傳座標比較資料（Excel）", type=["xlsx"])
with col_u2:
    diameter_file = st.file_uploader("上傳孔徑比較資料（Excel）", type=["xlsx"])
with col_u3:
    roundness_file = st.file_uploader("上傳真圓度比較資料（Excel）", type=["xlsx"])

if not (coord_file and diameter_file and roundness_file):
    st.info("請先完成三個檔案上傳。")
    st.stop()

try:
    coord_df = pd.read_excel(coord_file)
    diameter_df = pd.read_excel(diameter_file)
    roundness_df = pd.read_excel(roundness_file)

    coord_df = clean_common_excel(coord_df)
    diameter_df = clean_common_excel(diameter_df)
    roundness_df = clean_common_excel(roundness_df)

    # === 座標檔：拆 X/Y ===
    require_columns(coord_df, ["項目", "類別", "CAD\nSpec.", "原廠", "德烜"], "座標檔")
    x_coords = coord_df[coord_df["類別"] == " X 中心座標"].copy()
    y_coords = coord_df[coord_df["類別"] == " Y 中心座標"].copy()

    cad_col = "CAD\nSpec."
    x_coords = x_coords.rename(columns={cad_col: "CAD_X", "原廠": "原廠_X", "德烜": "德烜_X"})
    y_coords = y_coords.rename(columns={cad_col: "CAD_Y", "原廠": "原廠_Y", "德烜": "德烜_Y"})

    merged_df = pd.merge(
        x_coords[["項目", "CAD_X", "原廠_X", "德烜_X"]],
        y_coords[["項目", "CAD_Y", "原廠_Y", "德烜_Y"]],
        on="項目",
        how="inner",
    )

    # === 孔徑檔 ===
    require_columns(diameter_df, ["項目", "CAD\nSpec.", "原廠", "德烜"], "孔徑檔")
    diameter_df = diameter_df.rename(columns={cad_col: "CAD_D", "原廠": "原廠_D", "德烜": "德烜_D"})

    # === 真圓度檔 ===
    require_columns(roundness_df, ["項目", "CAD\nSpec.", "原廠", "德烜"], "真圓度檔")
    roundness_df = roundness_df.rename(
        columns={cad_col: "CAD_Roundness", "原廠": "原廠_Roundness", "德烜": "德烜_Roundness"}
    )

    # 轉數值 + dropna（完全比照原腳本）
    numeric_cols = ["CAD_X", "原廠_X", "德烜_X", "CAD_Y", "原廠_Y", "德烜_Y"]
    for col in numeric_cols:
        merged_df[col] = pd.to_numeric(merged_df[col], errors="coerce")
    merged_df = merged_df.dropna(subset=numeric_cols)

    for col in ["CAD_D", "原廠_D", "德烜_D"]:
        diameter_df[col] = pd.to_numeric(diameter_df[col], errors="coerce")
    diameter_df = diameter_df.dropna(subset=["CAD_D", "原廠_D", "德烜_D"])

    for col in ["CAD_Roundness", "原廠_Roundness", "德烜_Roundness"]:
        roundness_df[col] = pd.to_numeric(roundness_df[col], errors="coerce")
    roundness_df = roundness_df.dropna(subset=["CAD_Roundness", "原廠_Roundness", "德烜_Roundness"])

    # 合併三份資料
    df = pd.merge(merged_df, diameter_df[["項目", "CAD_D", "原廠_D", "德烜_D"]], on="項目", how="inner")
    df = pd.merge(
        df,
        roundness_df[["項目", "CAD_Roundness", "原廠_Roundness", "德烜_Roundness"]],
        on="項目",
        how="inner",
    )

    if df.empty:
        raise ValueError("三份資料合併後為空（可能是『項目』對不起來或有大量缺值）。")

    st.success(f"合併完成：有效資料筆數 {len(df)}")

    # ====== 1) 孔徑差異曲面（相對 CAD，絕對值）======
    st.subheader("1) 孔徑差異曲面圖（相對 CAD，絕對值）")

    fig_diam = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "scene"}, {"type": "scene"}]],
        subplot_titles=("原廠座標平面（孔徑差異曲面，相對 CAD）", "德烜座標平面（孔徑差異曲面，相對 CAD）"),
        horizontal_spacing=0.1,
    )

    x_oem = df["原廠_X"].to_numpy(dtype=float)
    y_oem = df["原廠_Y"].to_numpy(dtype=float)
    z_oem = np.abs((df["原廠_D"] - df["CAD_D"]).to_numpy(dtype=float))
    cmin_diam, cmax_diam = calc_cmin_cmax(np.concatenate([z_oem, np.abs((df["德烜_D"] - df["CAD_D"]).to_numpy(dtype=float))]))
    fig_diam.add_trace(
        create_offset_surface(
            x_oem,
            y_oem,
            z_oem,
            "原廠孔徑差異",
            "Turbo",
            "孔徑差異 (mm)",
            apply_nonlinear_scale=True,
            coloraxis="coloraxis",
            show_colorbar=False,
        ),
        row=1,
        col=1,
    )
    fig_diam.add_trace(
        go.Scatter3d(
            x=x_oem,
            y=y_oem,
            z=np.zeros_like(x_oem),
            mode="markers",
            marker=dict(size=PLANE_MARKER_SIZE, color=PLANE_MARKER_COLOR),
            opacity=PLANE_MARKER_OPACITY,
            showlegend=False,
            text=df["項目"],
            hovertemplate="<b>%{text}</b><br>原廠 XY: (%{x:.2f}, %{y:.2f})<br>Z=0<extra></extra>",
        ),
        row=1,
        col=1,
    )

    x_dh = df["德烜_X"].to_numpy(dtype=float)
    y_dh = df["德烜_Y"].to_numpy(dtype=float)
    z_dh = np.abs((df["德烜_D"] - df["CAD_D"]).to_numpy(dtype=float))
    fig_diam.add_trace(
        create_offset_surface(
            x_dh,
            y_dh,
            z_dh,
            "德烜孔徑差異",
            "Turbo",
            "孔徑差異 (mm)",
            apply_nonlinear_scale=True,
            coloraxis="coloraxis",
            show_colorbar=False,
        ),
        row=1,
        col=2,
    )
    fig_diam.add_trace(
        go.Scatter3d(
            x=x_dh,
            y=y_dh,
            z=np.zeros_like(x_dh),
            mode="markers",
            marker=dict(size=PLANE_MARKER_SIZE, color=PLANE_MARKER_COLOR),
            opacity=PLANE_MARKER_OPACITY,
            showlegend=False,
            text=df["項目"],
            hovertemplate="<b>%{text}</b><br>德烜 XY: (%{x:.2f}, %{y:.2f})<br>Z=0<extra></extra>",
        ),
        row=1,
        col=2,
    )

    fig_diam.update_scenes(
        xaxis_title="X (mm)",
        yaxis_title="Y (mm)",
        zaxis_title="孔徑差異 (mm)",
        aspectmode="manual",
        aspectratio={"x": 1, "y": 1, "z": 0.5},
        camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)),
        row=1,
        col=1,
    )
    fig_diam.update_scenes(
        xaxis_title="X (mm)",
        yaxis_title="Y (mm)",
        zaxis_title="孔徑差異 (mm)",
        aspectmode="manual",
        aspectratio={"x": 1, "y": 1, "z": 0.5},
        camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)),
        row=1,
        col=2,
    )
    fig_diam.update_layout(
        height=700,
        width=1400,
        showlegend=False,
        coloraxis=dict(
            colorscale="Turbo",
            cmin=cmin_diam,
            cmax=cmax_diam,
            colorbar=dict(title="孔徑差異 (mm)"),
        ),
        margin=dict(l=0, r=0, t=60, b=0),
    )
    st.plotly_chart(fig_diam, use_container_width=True)

    # ====== 2) 座標偏移量曲面（相對 CAD）======
    st.subheader("2) 座標偏移量曲面圖（相對 CAD）")

    df["原廠_座標偏移"] = np.sqrt((df["原廠_X"] - df["CAD_X"]) ** 2 + (df["原廠_Y"] - df["CAD_Y"]) ** 2)
    df["德烜_座標偏移"] = np.sqrt((df["德烜_X"] - df["CAD_X"]) ** 2 + (df["德烜_Y"] - df["CAD_Y"]) ** 2)

    fig_diff = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "scene"}, {"type": "scene"}]],
        subplot_titles=("原廠座標平面（Z=座標偏移量，相對 CAD）", "德烜座標平面（Z=座標偏移量，相對 CAD）"),
        horizontal_spacing=0.1,
    )

    z_oem_offset = df["原廠_座標偏移"].to_numpy(dtype=float)
    cmin_off, cmax_off = calc_cmin_cmax(np.concatenate([df["原廠_座標偏移"].to_numpy(dtype=float), df["德烜_座標偏移"].to_numpy(dtype=float)]))
    fig_diff.add_trace(
        create_offset_surface(
            x_oem,
            y_oem,
            z_oem_offset,
            "原廠座標偏移",
            "Turbo",
            "座標偏移量 (mm)",
            coloraxis="coloraxis",
            show_colorbar=False,
        ),
        row=1,
        col=1,
    )
    fig_diff.add_trace(
        go.Scatter3d(
            x=x_oem,
            y=y_oem,
            z=np.zeros_like(x_oem),
            mode="markers",
            marker=dict(size=PLANE_MARKER_SIZE, color=PLANE_MARKER_COLOR),
            opacity=PLANE_MARKER_OPACITY,
            showlegend=False,
            text=df["項目"],
            hovertemplate="<b>%{text}</b><br>原廠 XY: (%{x:.2f}, %{y:.2f})<br>Z=0<extra></extra>",
        ),
        row=1,
        col=1,
    )

    z_dh_offset = df["德烜_座標偏移"].to_numpy(dtype=float)
    fig_diff.add_trace(
        create_offset_surface(
            x_dh,
            y_dh,
            z_dh_offset,
            "德烜座標偏移",
            "Turbo",
            "座標偏移量 (mm)",
            coloraxis="coloraxis",
            show_colorbar=False,
        ),
        row=1,
        col=2,
    )
    fig_diff.add_trace(
        go.Scatter3d(
            x=x_dh,
            y=y_dh,
            z=np.zeros_like(x_dh),
            mode="markers",
            marker=dict(size=PLANE_MARKER_SIZE, color=PLANE_MARKER_COLOR),
            opacity=PLANE_MARKER_OPACITY,
            showlegend=False,
            text=df["項目"],
            hovertemplate="<b>%{text}</b><br>德烜 XY: (%{x:.2f}, %{y:.2f})<br>Z=0<extra></extra>",
        ),
        row=1,
        col=2,
    )

    fig_diff.update_scenes(
        xaxis_title="X (mm)",
        yaxis_title="Y (mm)",
        zaxis_title="座標偏移量 (mm)",
        aspectmode="manual",
        aspectratio={"x": 1, "y": 1, "z": 0.3},
        camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)),
        row=1,
        col=1,
    )
    fig_diff.update_scenes(
        xaxis_title="X (mm)",
        yaxis_title="Y (mm)",
        zaxis_title="座標偏移量 (mm)",
        aspectmode="manual",
        aspectratio={"x": 1, "y": 1, "z": 0.3},
        camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)),
        row=1,
        col=2,
    )
    fig_diff.update_layout(
        height=700,
        width=1400,
        showlegend=False,
        coloraxis=dict(
            colorscale="Turbo",
            cmin=cmin_off,
            cmax=cmax_off,
            colorbar=dict(title="座標偏移量 (mm)"),
        ),
        margin=dict(l=0, r=0, t=60, b=0),
    )
    st.plotly_chart(fig_diff, use_container_width=True)

    # ====== 3) 真圓度差異曲面（相對 CAD；保留正負，與原腳本一致）======
    st.subheader("3) 真圓度差異曲面圖（相對 CAD）")

    fig_round = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "scene"}, {"type": "scene"}]],
        subplot_titles=("原廠座標平面（真圓度差異曲面，相對 CAD）", "德烜座標平面（真圓度差異曲面，相對 CAD）"),
        horizontal_spacing=0.1,
    )

    z_oem_round = (df["原廠_Roundness"] - df["CAD_Roundness"]).to_numpy(dtype=float)
    z_dh_round = (df["德烜_Roundness"] - df["CAD_Roundness"]).to_numpy(dtype=float)
    cmin_round, cmax_round = calc_cmin_cmax(np.concatenate([z_oem_round, z_dh_round]))
    fig_round.add_trace(
        create_offset_surface(
            x_oem,
            y_oem,
            z_oem_round,
            "原廠真圓度差異",
            "Turbo",
            "真圓度差異 (mm)",
            coloraxis="coloraxis",
            show_colorbar=False,
        ),
        row=1,
        col=1,
    )
    fig_round.add_trace(
        go.Scatter3d(
            x=x_oem,
            y=y_oem,
            z=np.zeros_like(x_oem),
            mode="markers",
            marker=dict(size=PLANE_MARKER_SIZE, color=PLANE_MARKER_COLOR),
            opacity=PLANE_MARKER_OPACITY,
            showlegend=False,
            text=df["項目"],
            hovertemplate="<b>%{text}</b><br>原廠 XY: (%{x:.2f}, %{y:.2f})<br>Z=0<extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig_round.add_trace(
        create_offset_surface(
            x_dh,
            y_dh,
            z_dh_round,
            "德烜真圓度差異",
            "Turbo",
            "真圓度差異 (mm)",
            coloraxis="coloraxis",
            show_colorbar=False,
        ),
        row=1,
        col=2,
    )
    fig_round.add_trace(
        go.Scatter3d(
            x=x_dh,
            y=y_dh,
            z=np.zeros_like(x_dh),
            mode="markers",
            marker=dict(size=PLANE_MARKER_SIZE, color=PLANE_MARKER_COLOR),
            opacity=PLANE_MARKER_OPACITY,
            showlegend=False,
            text=df["項目"],
            hovertemplate="<b>%{text}</b><br>德烜 XY: (%{x:.2f}, %{y:.2f})<br>Z=0<extra></extra>",
        ),
        row=1,
        col=2,
    )

    fig_round.update_scenes(
        xaxis_title="X (mm)",
        yaxis_title="Y (mm)",
        zaxis_title="真圓度差異 (mm)",
        aspectmode="manual",
        aspectratio={"x": 1, "y": 1, "z": 0.3},
        camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)),
        row=1,
        col=1,
    )
    fig_round.update_scenes(
        xaxis_title="X (mm)",
        yaxis_title="Y (mm)",
        zaxis_title="真圓度差異 (mm)",
        aspectmode="manual",
        aspectratio={"x": 1, "y": 1, "z": 0.3},
        camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)),
        row=1,
        col=2,
    )
    fig_round.update_layout(
        height=700,
        width=1400,
        showlegend=False,
        coloraxis=dict(
            colorscale="Turbo",
            cmin=cmin_round,
            cmax=cmax_round,
            colorbar=dict(title="真圓度差異 (mm)"),
        ),
        margin=dict(l=0, r=0, t=60, b=0),
    )
    st.plotly_chart(fig_round, use_container_width=True)

except Exception as e:
    st.error(f"處理檔案時發生錯誤：{e}")
    st.stop()


