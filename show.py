import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.interpolate import griddata
from plotly.colors import sample_colorscale


def validate_every_cell(df):
    """檢查資料格式"""
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

            if col in [0, 2, 4]:
                val_str = str(val).strip()
                if not (val_str.startswith("Z") or (len(val_str) > 0 and val_str[0].isalpha())):
                    raise ValueError(
                        f"第 {idx+1} 列，第 {col+1} 欄應為點名稱（如Z1、Z2等），實際為：{val}"
                    )
            if col in [1, 3, 5]:
                try:
                    float(val)
                except Exception:
                    raise ValueError(
                        f"第 {idx+1} 列，第 {col+1} 欄應為數值，實際為：{val}"
                    )


def _prepare_data(df):
    """準備資料：驗證、轉換格式、計算圓圈範圍"""
    if df is None:
        df_raw = pd.read_csv("B01_to_B50_output.csv", header=None)
    else:
        df_raw = df.copy()

    validate_every_cell(df_raw)

    df_raw.columns = ['Dimple_X', 'X_Value', 'Dimple_Y', 'Y_Value', 'Dimple_Z', 'Z_Value']

    df = pd.DataFrame({
        'Dimple': df_raw['Dimple_X'],
        'X': df_raw['X_Value'],
        'Y': df_raw['Y_Value'],
        'Z': df_raw['Z_Value']
    })

    x, y, z = df['X'], df['Y'], df['Z']
    r = np.max(np.sqrt(x**2 + y**2)) * 1.08
    mask = np.sqrt(x**2 + y**2) <= r
    df_in = df[mask].copy()
    
    return df_in, r


def _get_color_for_z(z_val, z_min, z_max):
    """根據 Z 值計算顏色"""
    if z_max > z_min:
        normalized_z = (z_val - z_min) / (z_max - z_min)
    else:
        normalized_z = 0.5
    return sample_colorscale('Jet', [normalized_z])[0]


def _add_colorbar(fig, x_in, y_in, z_in):
    """加入顏色條"""
    z_min_val = z_in.min()
    z_max_val = z_in.max()
    
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


def _build_stepped_bowl_surface(steps, outer_radius, resolution=400, z_scale=1.0):
    """生成階梯碗狀表面"""
    x = np.linspace(-outer_radius, outer_radius, resolution)
    y = np.linspace(-outer_radius, outer_radius, resolution)
    X, Y = np.meshgrid(x, y)
    R = np.sqrt(X**2 + Y**2)
    
    Z = np.zeros_like(R, dtype=float)
    Z[R > outer_radius] = np.nan
    
    scaled_steps = []
    for dia, depth in sorted(steps, key=lambda t: t[0], reverse=True):
        r_th = dia / 2.0
        mask = (R <= r_th)
        scaled_depth = depth * z_scale
        scaled_steps.append((dia, scaled_depth))
        Z[mask] = scaled_depth

    finite_mask = np.isfinite(Z)
    if finite_mask.any():
        top_value = np.max(Z[finite_mask])
        Z[finite_mask] -= top_value
        scaled_steps = [(dia, depth - top_value) for dia, depth in scaled_steps]
    
    return X, Y, Z, scaled_steps


def create_dimple_3d_visualization(df=None, base_profile=None, show_vertical_lines=True, z_aspect_ratio=1, marker_size=4):
    """3D Dimple 視覺化（帶階梯底面）"""
    df_in, r = _prepare_data(df)
    x_in, y_in, z_in = df_in['X'], df_in['Y'], df_in['Z']

    fig = go.Figure()
    bowl_heights = None  # 初始化，用於儲存每個測量點對應的階層高度
    
    # 階梯底面
    if base_profile and len(base_profile) >= 2:
        outer_dia = max([dia for dia, _ in base_profile])
        outer_r = outer_dia / 2.0
        
        bowl_X, bowl_Y, bowl_Z, scaled_steps = _build_stepped_bowl_surface(
            base_profile, outer_r, resolution=400, z_scale=1.0
        )
        scaled_dict = {dia: depth for dia, depth in scaled_steps}
        
        fig.add_trace(go.Surface(
            x=bowl_X, y=bowl_Y, z=bowl_Z,
            showscale=False, colorscale='Viridis', opacity=0.95, hoverinfo='skip'
        ))

        theta_boundary = np.linspace(0, 2*np.pi, 361)
        for dia, depth in base_profile:
            if dia <= outer_dia:
                depth_clipped = scaled_dict.get(dia, 0.0)
                r_layer = dia / 2.0
                fig.add_trace(go.Scatter3d(
                    x=r_layer * np.cos(theta_boundary),
                    y=r_layer * np.sin(theta_boundary),
                    z=np.full_like(theta_boundary, depth_clipped),
                    mode='lines', line=dict(color='lightgray', width=2), showlegend=False
                ))
        
        def get_step_height(x_val, y_val):
            """使用 scaled_steps（調整後的值）計算階層高度，用於階梯底面顯示"""
            r_val = np.sqrt(x_val**2 + y_val**2)
            for dia, depth in sorted(scaled_steps, key=lambda t: t[0], reverse=True):
                if r_val <= dia / 2.0:
                    return depth
            return 0.0
        
        def get_original_step_height(x_val, y_val):
            """使用 base_profile（原始值）計算階層高度，用於測量點定位"""
            r_val = np.sqrt(x_val**2 + y_val**2)
            # 從大到小排序（外層到內層）
            sorted_profile = sorted(base_profile, key=lambda t: t[0], reverse=True)
            # 從外層開始檢查，找到第一個 r_val > dia/2 的階層
            # 點應該落在前一個階層（更內層的階層）
            prev_dia, prev_depth = None, None
            for dia, depth in sorted_profile:
                if r_val > dia / 2.0:
                    # 點超出當前階層，應該落在前一個階層
                    if prev_depth is not None:
                        return prev_depth
                    # 如果點超出最外層，返回最外層的高度
                    return depth
                prev_dia, prev_depth = dia, depth
            # 如果點在所有階層內（包括最內層），返回最內層的高度
            if sorted_profile:
                return sorted_profile[-1][1]  # 返回最內層（最小直徑）的高度
            return 0.0
        
        # 計算每個測量點對應的原始階層高度（用於測量點定位）
        bowl_heights = np.array([get_original_step_height(xi, yi) for xi, yi in zip(x_in, y_in)])
        
    # 垂直線和測量點
    z_min_val = z_in.min()
    z_max_val = z_in.max()
    
    for i in range(len(x_in)):
        x_val = x_in.iloc[i]
        y_val = y_in.iloc[i]
        z_val = z_in.iloc[i]  # Z_Value（相對於階層高度的偏移量）
        dimple_name = df_in['Dimple'].iloc[i]
        color = _get_color_for_z(z_val, z_min_val, z_max_val)
        
        # 計算階層高度（如果沒有 base_profile，則階層高度為 0）
        if base_profile and len(base_profile) >= 2 and bowl_heights is not None:
            step_height = float(bowl_heights[i])
        else:
            step_height = 0.0
        
        # 平面投影點：z = 階層高度
        plane_z = step_height
        # 空間中的點：z = 階層高度 + Z_Value * 10（僅視覺化放大）
        space_z = step_height + z_val * 100
        
        if show_vertical_lines:
            # 垂直線：從平面投影點到空間中的點
            fig.add_trace(go.Scatter3d(
                x=[x_val, x_val], y=[y_val, y_val], z=[plane_z, space_z],
                mode='lines', line=dict(color=color, width=4),
                showlegend=False, hoverinfo='text',
                hovertext=f"Dimple: {dimple_name}<br>X: {x_val:.2f} mm<br>Y: {y_val:.2f} mm<br>Z: {z_val:.4f} mm<br>階層高度: {step_height:.4f} mm"
            ))
        
        # 平面投影點
        fig.add_trace(go.Scatter3d(
            x=[x_val], y=[y_val], z=[plane_z],
            mode='markers', marker=dict(size=marker_size, color=color, symbol='circle', opacity=0.6),
            showlegend=False, hoverinfo='text',
            hovertext=f"Dimple: {dimple_name}<br>X: {x_val:.2f} mm<br>Y: {y_val:.2f} mm<br>階層高度: {step_height:.4f} mm"
        ))
        
        # 空間中的點
        fig.add_trace(go.Scatter3d(
            x=[x_val], y=[y_val], z=[space_z],
            mode='markers', marker=dict(size=marker_size, color=color),
            showlegend=False, hoverinfo='text',
            hovertext=f"Dimple: {dimple_name}<br>X: {x_val:.2f} mm<br>Y: {y_val:.2f} mm<br>Z: {z_val:.4f} mm<br>階層高度: {step_height:.4f} mm<br>空間位置: {space_z:.4f} mm"
        ))
    
    _add_colorbar(fig, x_in, y_in, z_in)
    
    fig.update_layout(
        scene=dict(
            xaxis_title='X (mm)', yaxis_title='Y (mm)', zaxis_title='Z (mm)',
            aspectmode='manual', aspectratio=dict(x=1, y=1, z=z_aspect_ratio),
            camera=dict(eye=dict(x=-1.25, y=1.25, z=0.75), up=dict(x=0, y=1, z=1)),
            xaxis=dict(showgrid=True, zeroline=True, showbackground=False),
            yaxis=dict(showgrid=True, zeroline=True, showbackground=False),
            zaxis=dict(showgrid=True, zeroline=True, showbackground=False, range=[-0.75, 0.75])
        ),
        title='3D Dimple Height Map', margin=dict(l=0, r=0, b=0, t=40),
        height=800, width=1200
    )
    
    return fig


def create_roundness_visualization(df=None, z_aspect_ratio=0.65, marker_size=6):
    """真圓度視覺化（平面）"""
    df_in, r = _prepare_data(df)
    x_in, y_in, z_in = df_in['X'], df_in['Y'], df_in['Z']
    
    fig = go.Figure()
    
    # 平面圓圈線
    theta = np.linspace(0, 2*np.pi, 200)
    circle_x = r * np.cos(theta)
    circle_y = r * np.sin(theta)
    circle_z = np.zeros_like(theta)
    
    fig.add_trace(go.Scatter3d(
        x=circle_x, y=circle_y, z=circle_z,
        mode='lines', line=dict(color='lightblue', width=4), showlegend=False
    ))
    
    # 底部投影點（z=0）
    fig.add_trace(go.Scatter3d(
        x=x_in, y=y_in, z=np.zeros_like(z_in),
        mode='markers',
        marker=dict(size=10, color=z_in, colorscale='Jet', opacity=1, symbol='circle'),
        hoverinfo='text',
        hovertext=[
            f"Dimple: {list(df_in['Dimple'])[i]}<br>X: {list(df_in['X'])[i]:.2f} mm<br>Y: {list(df_in['Y'])[i]:.2f} mm<br>Z: {list(df_in['Z'])[i]:.4f} mm"
            for i in range(len(df_in))
        ],
        showlegend=False
    ))
    
    # 測量點（空間中）
    z_min_val = z_in.min()
    z_max_val = z_in.max()
    
    for i in range(len(x_in)):
        x_val = x_in.iloc[i]
        y_val = y_in.iloc[i]
        z_val = z_in.iloc[i]
        dimple_name = df_in['Dimple'].iloc[i]
        color = _get_color_for_z(z_val, z_min_val, z_max_val)
        
        fig.add_trace(go.Scatter3d(
            x=[x_val], y=[y_val], z=[z_val],
            mode='markers', marker=dict(size=marker_size, color=color),
            showlegend=False, hoverinfo='text',
            hovertext=f"Dimple: {dimple_name}<br>X: {x_val:.2f} mm<br>Y: {y_val:.2f} mm<br>Z: {z_val:.4f} mm"
        ))
        
    _add_colorbar(fig, x_in, y_in, z_in)

    fig.update_layout(
        scene=dict(
            xaxis_title='X (mm)', yaxis_title='Y (mm)', zaxis_title='Z (mm)',
            aspectmode='manual', aspectratio=dict(x=1, y=1, z=z_aspect_ratio),
            camera=dict(eye=dict(x=-1.25, y=1.25, z=0.75), up=dict(x=0, y=1, z=1)),
            xaxis=dict(showgrid=True, zeroline=True, showbackground=False),
            yaxis=dict(showgrid=True, zeroline=True, showbackground=False),
            zaxis=dict(showgrid=True, zeroline=True, showbackground=False)
        ),
        title='3D Dimple Height Map', margin=dict(l=0, r=0, b=0, t=40),
        height=800, width=1200
    )

    return fig


def create_visualization(df=None, show_shield=False, show_vertical_lines=True, z_aspect_ratio=0.5, marker_size=4, base_profile=None):
    """向後相容的包裝函數"""
    if base_profile:
        return create_dimple_3d_visualization(df, base_profile, show_vertical_lines, z_aspect_ratio, marker_size)
    else:
        return create_roundness_visualization(df, z_aspect_ratio, marker_size)


if __name__ == "__main__":
    fig = create_visualization()
    fig.show()
