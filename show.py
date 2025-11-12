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


def _build_stepped_bowl_surface(steps, outer_radius, resolution=600, z_scale=0.05):
    """根據階梯設定生成碗狀表面網格（參考 test.py）
    
    參數:
        steps: List[Tuple[直徑(mm), 深度(mm)]] - 階梯設定
        outer_radius: 外圈半徑
        resolution: 網格解析度
        z_scale: 底盤 Z 軸縮放比例（預設 0.05，讓底盤極扁）
    
    返回:
        (X, Y, Z) 網格座標
    """
    x = np.linspace(-outer_radius, outer_radius, resolution)
    y = np.linspace(-outer_radius, outer_radius, resolution)
    X, Y = np.meshgrid(x, y)
    R = np.sqrt(X**2 + Y**2)
    
    # 初始化 Z 值
    Z = np.zeros_like(R, dtype=float)
    Z[R > outer_radius] = np.nan  # 超出外徑區域不顯示
    
    scaled_steps = []

    # 由外向內覆蓋各階高度
    for dia, depth in sorted(steps, key=lambda t: t[0], reverse=True):
        r_th = dia / 2.0
        mask = (R <= r_th)
        depth_clipped = max(depth, -0.1)
        scaled_depth = depth_clipped * z_scale
        scaled_steps.append((dia, scaled_depth))
        Z[mask] = scaled_depth

    # 將頂部對齊 z = 0
    finite_mask = np.isfinite(Z)
    if finite_mask.any():
        top_value = np.max(Z[finite_mask])
        Z[finite_mask] -= top_value
        scaled_steps = [(dia, depth - top_value) for dia, depth in scaled_steps]
    
    return X, Y, Z, scaled_steps


def create_visualization(df=None, show_shield=False, base_profile=None):
    """創建 3D Dimple 視覺化，含格式檢查
    
    參數:
        df: 資料框
        show_shield: 是否顯示 z=0.001 的遮擋圓盤（從底部往上看時阻擋3D點）
        base_profile: Optional[List[Tuple[直徑(mm), 高度(mm)]]] - AMAT Heater 階梯設定
    """
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

    # 計算標準差統計資訊
    z_mean = df['Z'].mean()
    z_std = df['Z'].std()
    z_min = df['Z'].min()
    z_max = df['Z'].max()
    
    # 計算各標準差範圍內的資料點數量
    within_1std = len(df[(df['Z'] >= z_mean - z_std) & (df['Z'] <= z_mean + z_std)])
    within_2std = len(df[(df['Z'] >= z_mean - 2*z_std) & (df['Z'] <= z_mean + 2*z_std)])
    within_3std = len(df[(df['Z'] >= z_mean - 3*z_std) & (df['Z'] <= z_mean + 3*z_std)])
    
    # 計算百分比
    total_points = len(df)
    pct_1std = (within_1std / total_points) * 100
    pct_2std = (within_2std / total_points) * 100
    pct_3std = (within_3std / total_points) * 100

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
    
    # 1. 碗狀底面（如果有提供階梯設定）
    if base_profile and len(base_profile) >= 2:
        # 使用最大直徑作為外圈半徑
        outer_dia = max([dia for dia, _ in base_profile])
        outer_r = outer_dia / 2.0
        
        # 底盤 Z 軸縮放比例（大幅縮小讓底盤扁平）
        bowl_z_scale = 0.035
        
        # 生成碗狀表面
        bowl_X, bowl_Y, bowl_Z, scaled_steps = _build_stepped_bowl_surface(
            base_profile, outer_r, resolution=400, z_scale=bowl_z_scale
        )
        scaled_dict = {dia: depth for dia, depth in scaled_steps}
        
        fig.add_trace(go.Surface(
            x=bowl_X, 
            y=bowl_Y, 
            z=bowl_Z,
            showscale=False,
            colorscale='Viridis',
            opacity=0.95,
            hoverinfo='skip'
        ))

        # 外圈邊界線（Top = 0）
        theta_boundary = np.linspace(0, 2*np.pi, 361)
        
        # 各階層邊界線
        for dia, depth in base_profile:
            if dia <= outer_dia:
                depth_clipped = scaled_dict.get(dia, 0.0)
                r_layer = dia / 2.0
                fig.add_trace(go.Scatter3d(
                    x=r_layer * np.cos(theta_boundary),
                    y=r_layer * np.sin(theta_boundary),
                    z=np.full_like(theta_boundary, depth_clipped),
                    mode='lines',
                    line=dict(color='lightgray', width=2),
                    showlegend=False
                ))
        
        # 底部投影點落在碗狀表面上
        def get_step_height(x_val, y_val):
            r_val = np.sqrt(x_val**2 + y_val**2)
            for dia, depth in sorted(scaled_steps, key=lambda t: t[0], reverse=True):
                if r_val <= dia / 2.0:
                    return depth
            return 0.0
        
        bowl_heights = np.array([get_step_height(xi, yi) for xi, yi in zip(x_in, y_in)])
        
        fig.add_trace(go.Scatter3d(
            x=x_in, y=y_in, z=bowl_heights,
            mode='markers',
            marker=dict(size=9, color=z_in, colorscale='Jet', opacity=1, symbol='circle'),
            hoverinfo='text',
            hovertext=[
                f"Dimple: {list(df_in['Dimple'])[i]}<br>X: {list(df_in['X'])[i]:.2f} mm<br>Y: {list(df_in['Y'])[i]:.2f} mm<br>Z: {list(df_in['Z'])[i]:.4f} mm"
                for i in range(len(df_in))
            ],
            showlegend=False
        ))
    else:
        # 原本的平面圓圈線
        fig.add_trace(go.Scatter3d(x=circle_x, y=circle_y, z=circle_z, mode='lines',
                                   line=dict(color='lightblue', width=4), showlegend=False))
        
        # 原本的底部投影點（z=0）
        fig.add_trace(go.Scatter3d(x=x_in, y=y_in, z=np.zeros_like(z_in), mode='markers',
                                   marker=dict(size=10, color=z_in, colorscale='Jet', opacity=1, symbol='circle'),
                                   hoverinfo='text', hovertext=[
                                       f"Dimple: {list(df_in['Dimple'])[i]}<br>X: {list(df_in['X'])[i]:.2f} mm<br>Y: {list(df_in['Y'])[i]:.2f} mm<br>Z: {list(df_in['Z'])[i]:.4f} mm"
                                       for i in range(len(df_in))],
                                   showlegend=False))
    
    # 3. 不透明圓盤（z=0.001）- 可選的遮擋層，從底部往上看時阻擋上方的3D點
    if show_shield:
        n_r = 30  # 徑向分辨率
        n_theta = 100  # 角度分辨率
        r_grid = np.linspace(0, r, n_r)
        theta_grid = np.linspace(0, 2*np.pi, n_theta)
        r_mesh, theta_mesh = np.meshgrid(r_grid, theta_grid)
        
        # 轉換成笛卡爾坐標
        shield_disk_x = r_mesh * np.cos(theta_mesh)
        shield_disk_y = r_mesh * np.sin(theta_mesh)
        shield_disk_z = np.ones_like(shield_disk_x) * 0.001  # 在 z=0.001
        
        # 畫不透明遮擋圓盤
        fig.add_trace(go.Surface(
            x=shield_disk_x, 
            y=shield_disk_y, 
            z=shield_disk_z,
            colorscale=[[0, 'white'], [1, 'white']],  # 純白色
            showscale=False,
            opacity=1,
            showlegend=False,
            hoverinfo='skip'
        ))
    
    # 4. 移除圓盤表面（改用柱狀圖）
    # fig.add_trace(go.Surface(x=xi_grid, y=yi_grid, z=zi_grid,
    #                           colorscale='Jet', opacity=1, showscale=False, showlegend=False))
    
    # 5. 為每個 dimple 點畫一根柱子（從 z=0 到測量點）
    # 計算顏色映射
    z_min_val = z_in.min()
    z_max_val = z_in.max()
    
    # 使用 Jet colorscale
    from plotly.colors import sample_colorscale
    
    for i in range(len(x_in)):
        x_val = x_in.iloc[i]
        y_val = y_in.iloc[i]
        z_val = z_in.iloc[i]
        dimple_name = df_in['Dimple'].iloc[i]
        
        # 計算顏色（根據 Z 值）
        if z_max_val > z_min_val:
            normalized_z = (z_val - z_min_val) / (z_max_val - z_min_val)
        else:
            normalized_z = 0.5
        color = sample_colorscale('Jet', [normalized_z])[0]
        
        # 畫柱子（從 z=0 到測量點）
        fig.add_trace(go.Scatter3d(
            x=[x_val, x_val],
            y=[y_val, y_val],
            z=[0, z_val],
            mode='lines',
            line=dict(color=color, width=4),
            showlegend=False,
            hoverinfo='text',
            hovertext=f"Dimple: {dimple_name}<br>X: {x_val:.2f} mm<br>Y: {y_val:.2f} mm<br>Z: {z_val:.4f} mm"
        ))
        
        # 在柱子頂端加一個點
        fig.add_trace(go.Scatter3d(
            x=[x_val],
            y=[y_val],
            z=[z_val],
            mode='markers',
            marker=dict(size=4, color=color),
            showlegend=False,
            hoverinfo='skip'
        ))
    
    # 加入 colorbar（使用一個隱藏的 scatter 來顯示色階）
    fig.add_trace(go.Scatter3d(
        x=[x_in.iloc[0]],
        y=[y_in.iloc[0]],
        z=[z_in.iloc[0]],
        mode='markers',
        marker=dict(
            size=0.1,
            color=[z_min_val],
            colorscale='Jet',
            cmin=z_min_val,
            cmax=z_max_val,
            colorbar=dict(title='Z (mm)', x=1.02),
            showscale=True
        ),
        showlegend=False,
        hoverinfo='skip'
    ))

    fig.update_layout(
        scene=dict(
            xaxis_title='X (mm)', yaxis_title='Y (mm)', zaxis_title='Z (mm)',
            aspectmode='manual', aspectratio=dict(x=1, y=1, z=0.5),
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
