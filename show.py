import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.interpolate import griddata
from plotly.colors import sample_colorscale


def validate_every_cell(df):
    """
    檢查每一列的每一欄是否符合格式
    - 第 1,3,5 欄：點名稱（Z開頭）且不為空
    - 第 2,4,6 欄：數值且不為空
    """
    if df.shape[1] != 6:
        raise ValueError(
            f"請按照範例格式上傳：['Z1', 'X_Value', 'Z1', 'Y_Value', 'Z1', 'Z_Value']，目前檔案有 {df.shape[1]} 欄"
        )

    for idx, row in df.iterrows():
        for col in range(6):
            val = row[col]

            if pd.isna(val) or str(val).strip() == "":
                raise ValueError(
                    f"第 {idx+1} 列，第 {col+1} 欄為空，請按照範例格式：['Z1', 'X_Value', 'Z1', 'Y_Value', 'Z1', 'Z_Value']"
                )

            if col in [0, 2, 4]:  # 檢查點名稱
                val_str = str(val).strip()
                # 支援Z開頭或其他字母開頭的點名稱
                if not (val_str.startswith("Z") or (len(val_str) > 0 and val_str[0].isalpha())):
                    raise ValueError(
                        f"第 {idx+1} 列，第 {col+1} 欄應為點名稱（如Z1、Z2等），實際為：{val}"
                    )
            if col in [1, 3, 5]:  # 檢查數值
                try:
                    float(val)
                except Exception:
                    raise ValueError(
                        f"第 {idx+1} 列，第 {col+1} 欄應為數值，實際為：{val}"
                    )


def create_visualization(df=None):
    """創建 3D Dimple 視覺化，含格式檢查"""
    if df is None:
        df_raw = pd.read_csv("B01_to_B50_output.csv", header=None)
    else:
        df_raw = df.copy()

    # 檢查格式
    validate_every_cell(df_raw)

    # 重命名欄位
    df_raw.columns = ['Dimple_X', 'X_Value', 'Dimple_Y', 'Y_Value', 'Dimple_Z', 'Z_Value']

    # 轉換成標準格式
    df = pd.DataFrame({
        'Dimple': df_raw['Dimple_X'],
        'X': df_raw['X_Value'],
        'Y': df_raw['Y_Value'],
        'Z': df_raw['Z_Value']
    })

    # 不使用極端值過濾，直接使用原始資料
    df_filtered = df.copy()

    # 畫圓
    x, y, z = df_filtered['X'], df_filtered['Y'], df_filtered['Z']
    r = np.max(np.sqrt(x**2 + y**2)) * 1.08
    mask = np.sqrt(x**2 + y**2) <= r
    df_in = df_filtered[mask].copy()
    x_in, y_in, z_in = df_in['X'], df_in['Y'], df_in['Z']

    # 內插格點
    xi = np.linspace(x_in.min(), x_in.max(), 50)
    yi = np.linspace(y_in.min(), y_in.max(), 50)
    xi_grid, yi_grid = np.meshgrid(xi, yi)
    zi_grid = griddata((x_in, y_in), z_in, (xi_grid, yi_grid), method='linear')

    # 圓座標
    theta = np.linspace(0, 2*np.pi, 200)
    circle_x = r * np.cos(theta)
    circle_y = r * np.sin(theta)
    circle_z = np.zeros_like(theta)

    # 畫圖
    fig = go.Figure()
    fig.add_trace(go.Scatter3d(x=circle_x, y=circle_y, z=circle_z, mode='lines',
                               line=dict(color='lightblue', width=4), showlegend=False))
    # 畫圓盤表面
    fig.add_trace(go.Surface(x=xi_grid, y=yi_grid, z=zi_grid,
                              colorscale='Jet', opacity=1, showscale=False, showlegend=False))
    # 畫點
    fig.add_trace(go.Scatter3d(x=x_in, y=y_in, z=z_in, mode='markers',
                               marker=dict(size=5, color=z_in, colorscale='Jet', opacity=0.6,
                                           colorbar=dict(title='Z (mm)', x=0.02)),
                               text=[f"Dimple: {list(df_in['Dimple'])[i]}<br>X: {list(df_in['X'])[i]:.2f} mm<br>Y: {list(df_in['Y'])[i]:.2f} mm<br>Z: {list(df_in['Z'])[i]:.4f} mm"
                                     for i in range(len(df_in))],
                               hoverinfo='text', showlegend=False))
    # 底部文字    
    fig.add_trace(go.Scatter3d(x=x_in, y=y_in, z=np.zeros_like(z_in), mode='markers+text',
                               marker=dict(size=10, color=z_in, colorscale='Jet', opacity=1, symbol='circle'),
                               text=df_in['Dimple'], textposition="middle center",
                               textfont=dict(size=11, color='white'),
                               hoverinfo='text', hovertext=[
                                   f"Dimple: {list(df_in['Dimple'])[i]}<br>X: {list(df_in['X'])[i]:.2f} mm<br>Y: {list(df_in['Y'])[i]:.2f} mm<br>Z: {list(df_in['Z'])[i]:.4f} mm"
                                   for i in range(len(df_in))],
                               showlegend=False))

    # 柱狀圖
    zmin, zmax = df_in['Z'].min(), df_in['Z'].max()
    colorscale = 'Jet'

    for i in range(len(x_in)):
        t = (list(z_in)[i] - zmin) / (zmax - zmin) if zmax > zmin else 0.5
        color = sample_colorscale(colorscale, [t])[0]
        fig.add_trace(go.Scatter3d(
            x=[list(x_in)[i], list(x_in)[i]], y=[list(y_in)[i], list(y_in)[i]], z=[0, list(z_in)[i]],
            mode='lines', line=dict(color=color, width=3), showlegend=False, hoverinfo='skip'))

    fig.update_layout(
        scene=dict(
            xaxis_title='X (mm)', yaxis_title='Y (mm)', zaxis_title='Z (mm)',
            aspectmode='manual', aspectratio=dict(x=1, y=1, z=0.4),
            camera=dict(eye=dict(x=-1.25, y=1.25, z=0.75), up=dict(x=0, y=1, z=1)),
            xaxis=dict(showgrid=True, zeroline=True, showbackground=False),
            yaxis=dict(showgrid=True, zeroline=True, showbackground=False),
            zaxis=dict(showgrid=True, zeroline=True, showbackground=False)
        ),
        title='3D Dimple Height Map', margin=dict(l=0, r=0, b=0, t=40),
        height=800, width=1200
    )

    return fig


if __name__ == "__main__":
    fig = create_visualization()
    fig.show()
