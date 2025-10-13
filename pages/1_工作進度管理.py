import streamlit as st
import hashlib
import jwt
from datetime import datetime, timedelta, date
import psycopg2
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import base64
from PIL import Image
import os

# 資料庫連線設定 - Streamlit Cloud 專用
def get_database_config():
    """取得資料庫連線設定 - 從 Streamlit Cloud Secrets 讀取"""
    return {
        'host': st.secrets.get('DB_HOST'),
        'database': st.secrets.get('DB_NAME'),
        'user': st.secrets.get('DB_USER'),
        'password': st.secrets.get('DB_PASSWORD'),
        'port': st.secrets.get('DB_PORT'),
        'sslmode': st.secrets.get('DB_SSLMODE')
    }

# JWT 設定 - Streamlit Cloud 專用
def get_jwt_secret():
    """取得 JWT 密鑰 - 從 Streamlit Cloud Secrets 讀取"""
    return st.secrets.get('JWT_SECRET')

# 初始化設定
DATABASE_CONFIG = get_database_config()
JWT_SECRET = get_jwt_secret()
JWT_ALGORITHM = "HS256"

class DatabaseManager:
    """資料庫管理類別"""
    
    def __init__(self):
        self.conn = None
    
    def connect(self):
        """連線到資料庫"""
        try:
            self.conn = psycopg2.connect(**DATABASE_CONFIG)
            return True
        except Exception as e:
            st.error(f"資料庫連線失敗：{e}")
            return False
    
    def disconnect(self):
        """斷開資料庫連線"""
        if self.conn:
            self.conn.close()
    
    def execute_query(self, query, params=None, fetch=True):
        """執行查詢"""
        try:
            # 檢查連線狀態
            if not self.conn or self.conn.closed:
                if not self.connect():
                    st.error("無法重新連線到資料庫")
                    return None
            
            cur = self.conn.cursor()
            cur.execute(query, params)
            
            if fetch:
                result = cur.fetchall()
                # 對於 INSERT/UPDATE/DELETE 查詢，需要提交事務
                if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                    self.conn.commit()
                cur.close()
                return result
            else:
                self.conn.commit()
                cur.close()
                return True
                
        except Exception as e:
            st.error(f"查詢執行失敗：{e}")
            if self.conn and not self.conn.closed:
                self.conn.rollback()
            return None

def init_session_state():
    """初始化 session state"""
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None
    if 'db_manager' not in st.session_state:
        st.session_state.db_manager = None
    if 'current_week_start' not in st.session_state:
        st.session_state.current_week_start = get_week_start(datetime.now())
    if 'selected_user' not in st.session_state:
        st.session_state.selected_user = None
    
    # 初始化欄位順序設定（預設順序）
    if 'column_order' not in st.session_state:
        st.session_state.column_order = [
            '編號', '日期', '放行單', '使用狀況', '客戶', '廠區', 'User', '工作項目', 
            '目的', '問題', '狀態', '解決方案', '目前階段', '完成度', '預估營收', 
            '營收', '成本', '毛利率', '截止日期'
        ]
    if 'use_custom_order' not in st.session_state:
        st.session_state.use_custom_order = False
    
    # 🔍 新增：如果已登入且是 admin，確保 selected_user 有值
    if st.session_state.logged_in and st.session_state.current_user and st.session_state.current_user['role'] == 'admin':
        if st.session_state.db_manager and st.session_state.selected_user is None:
            users = get_users_list(st.session_state.db_manager)
            if users:
                st.session_state.selected_user = users[0]

def get_week_start(date):
    """取得週開始日期（週一）"""
    if hasattr(date, 'date'):
        date = date.date()
    days_since_monday = date.weekday()
    return date - timedelta(days=days_since_monday)

def verify_user(username, password, db_manager):
    """驗證使用者帳號密碼"""
    try:
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        query = """
        SELECT id, username, full_name, role, is_active 
        FROM users 
        WHERE username = %s AND password_hash = %s AND is_active = TRUE
        """
        
        result = db_manager.execute_query(query, (username, password_hash))
        
        if result and len(result) > 0:
            user_data = result[0]
            return {
                'id': user_data[0],
                'username': user_data[1],
                'full_name': user_data[2],
                'role': user_data[3],
                'is_active': user_data[4]
            }
        
        return None
        
    except Exception as e:
        st.error(f"驗證使用者時發生錯誤：{e}")
        return None

def login_page():
    """登入頁面"""
    st.header("工作進度管理系統")
    st.markdown("---")
    
    with st.form("login_form"):
        username = st.text_input("帳號", placeholder="請輸入帳號")
        password = st.text_input("密碼", type="password", placeholder="請輸入密碼")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            submit_button = st.form_submit_button("登入", use_container_width=True)
        
        if submit_button:
            if not username or not password:
                st.error("請輸入帳號和密碼！")
                return
            
            # 連線資料庫
            db_manager = DatabaseManager()
            if not db_manager.connect():
                st.error("無法連線到資料庫，請檢查網路連線和資料庫設定。")
                return
            
            # 驗證使用者
            user_info = verify_user(username, password, db_manager)
            if user_info:
                st.session_state.logged_in = True
                st.session_state.current_user = user_info
                st.session_state.db_manager = db_manager
                st.success(f"歡迎 {user_info['full_name']}！")
                st.rerun()
            else:
                st.error("帳號或密碼錯誤！")

def get_users_list(db_manager):
    """取得使用者列表"""
    try:
        # 檢查資料庫連線狀態
        if not db_manager.conn or db_manager.conn.closed:
            if not db_manager.connect():
                st.error("無法重新連線到資料庫")
                return []
        
        query = "SELECT full_name FROM users WHERE is_active = TRUE ORDER BY full_name"
        result = db_manager.execute_query(query)
        
        if result:
            return [row[0] for row in result]
        return []
    except Exception as e:
        st.error(f"載入使用者列表時發生錯誤：{e}")
        return []

def load_work_data(db_manager, current_user, week_start, selected_user=None):
    """載入工作資料"""
    try:
        # 檢查資料庫連線狀態
        if not db_manager.conn or db_manager.conn.closed:
            if not db_manager.connect():
                st.error("無法重新連線到資料庫")
                return pd.DataFrame()
        
        week_end = week_start + timedelta(days=6)
        
        if current_user['role'] == 'admin':
            if selected_user:
                query = """
                SELECT wp.id, wp.date, wp.usage_status, wp.release_form, wp.factory, wp.username, wp.item, wp.purpose, wp.problem, wp.status, wp.solution, wp.deadline,
                       wp.completion_rate, wp.estimate, wp.revenue, wp.cost, wp.gross_profit, wp.customer, wp.phase_code
                FROM work_progress wp 
                JOIN users u ON wp.user_id = u.id 
                WHERE u.full_name = %s
                  AND wp.date >= %s AND wp.date <= %s
                ORDER BY wp.date ASC
                """
                result = db_manager.execute_query(query, (selected_user, week_start, week_end))
            else:
                query = """
                SELECT wp.id, wp.date, wp.usage_status, wp.release_form, wp.factory, wp.username, wp.item, wp.purpose, wp.problem, wp.status, wp.solution, wp.deadline,
                       wp.completion_rate, wp.estimate, wp.revenue, wp.cost, wp.gross_profit, wp.customer, wp.phase_code
                FROM work_progress wp 
                JOIN users u ON wp.user_id = u.id 
                WHERE wp.date >= %s AND wp.date <= %s
                ORDER BY wp.date ASC
                """
                result = db_manager.execute_query(query, (week_start, week_end))
        else:
            query = """
            SELECT id, date, usage_status, release_form, factory, username, item, purpose, problem, status, solution, deadline, 
                   completion_rate, estimate, revenue, cost, gross_profit, customer, phase_code
            FROM work_progress 
            WHERE user_id = %s 
              AND date >= %s AND date <= %s
            ORDER BY date ASC
            """
            result = db_manager.execute_query(query, (current_user['id'], week_start, week_end))
        
        if result:
            df = pd.DataFrame(result, columns=[
                'id', 'date', 'usage_status', 'release_form', 'factory', 'username', 'item', 'purpose', 'problem', 'status', 'solution', 'deadline',
                'completion_rate', 'estimate', 'revenue', 'cost', 'gross_profit', 'customer', 'phase_code'
            ])
            
            # 確保日期欄位為 datetime 類型
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            if 'deadline' in df.columns:
                df['deadline'] = pd.to_datetime(df['deadline'])
            
            return df
        return pd.DataFrame()
        
    except Exception as e:
        st.error(f"載入資料時發生錯誤：{e}")
        return pd.DataFrame()

def check_table_structure(db_manager):
    """檢查表格結構"""
    try:
        query = """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'work_progress'
        ORDER BY ordinal_position
        """
        result = db_manager.execute_query(query)
        if result:
            st.info("work_progress 表格結構：")
            for col in result:
                st.write(f"- {col[0]}: {col[1]} ({'NULL' if col[2] == 'YES' else 'NOT NULL'})")
        return result
    except Exception as e:
        st.error(f"檢查表格結構時發生錯誤：{e}")
        return None

def get_user_id_by_name(db_manager, user_name):
    """根據使用者姓名取得使用者ID"""
    try:
        # 檢查資料庫連線狀態
        if not db_manager.conn or db_manager.conn.closed:
            if not db_manager.connect():
                st.error("無法重新連線到資料庫")
                return None
        
        query = "SELECT id FROM users WHERE full_name = %s"
        result = db_manager.execute_query(query, (user_name,))
        if result and len(result) > 0:
            return result[0][0]
        return None
    except Exception as e:
        st.error(f"取得使用者ID時發生錯誤：{e}")
        return None

def get_phase_list(db_manager):
    """取得階段列表"""
    try:
        # 檢查資料庫連線狀態
        if not db_manager.conn or db_manager.conn.closed:
            if not db_manager.connect():
                st.error("無法重新連線到資料庫")
                return []
        
        query = """
        SELECT code, name FROM phase_list 
        ORDER BY CASE code
            WHEN 'P1' THEN 1
            WHEN 'P2' THEN 2
            WHEN 'P3' THEN 3
            WHEN 'P4' THEN 4
            WHEN 'P5' THEN 5
            WHEN 'P6' THEN 6
            WHEN 'P7' THEN 7
            WHEN 'P8' THEN 8
            WHEN 'P9' THEN 9
            WHEN 'P10' THEN 10
            WHEN 'P11' THEN 11
            WHEN 'P12' THEN 12
            WHEN 'P13' THEN 13
            WHEN 'P14' THEN 14
            WHEN 'P15' THEN 15
            ELSE 999
        END
        """
        result = db_manager.execute_query(query)
        
        if result:
            return [(row[0], row[1]) for row in result]
        return []
    except Exception as e:
        st.error(f"載入階段列表時發生錯誤：{e}")
        return []

def get_phase_name_by_code(db_manager, phase_code):
    """根據階段代碼取得階段名稱"""
    try:
        if not phase_code or pd.isna(phase_code):
            return ""
        
        # 檢查資料庫連線狀態
        if not db_manager.conn or db_manager.conn.closed:
            if not db_manager.connect():
                return str(phase_code)  # 如果無法連線，返回原始代碼
        
        query = "SELECT name FROM phase_list WHERE code = %s"
        result = db_manager.execute_query(query, (phase_code,))
        
        if result and len(result) > 0:
            return result[0][0]
        return str(phase_code)  # 如果找不到對應名稱，返回原始代碼
    except Exception as e:
        return str(phase_code)  # 發生錯誤時返回原始代碼

def clean_empty_phase_codes(db_manager):
    """清理空的階段代碼，設定為預設階段P1"""
    try:
        # 檢查資料庫連線狀態
        if not db_manager.conn or db_manager.conn.closed:
            if not db_manager.connect():
                st.error("無法重新連線到資料庫")
                return False
        
        # 查詢有多少筆資料的 phase_code 是空的
        count_query = """
        SELECT COUNT(*) FROM work_progress 
        WHERE phase_code IS NULL OR phase_code = ''
        """
        result = db_manager.execute_query(count_query)
        
        if result and result[0][0] > 0:
            empty_count = result[0][0]
            st.info(f"發現 {empty_count} 筆資料的階段代碼為空，將設定為預設階段 P1")
            
            # 更新空的 phase_code 為 P1
            update_query = """
            UPDATE work_progress 
            SET phase_code = 'P1' 
            WHERE phase_code IS NULL OR phase_code = ''
            """
            
            if db_manager.execute_query(update_query, fetch=False):
                st.success(f"已成功將 {empty_count} 筆資料的階段代碼更新為 P1")
                return True
            else:
                st.error("更新階段代碼時發生錯誤")
                return False
        else:
            st.info("沒有發現空的階段代碼，資料庫狀態良好")
            return True
            
    except Exception as e:
        st.error(f"清理空的階段代碼時發生錯誤：{e}")
        return False

def calculate_cumulative_revenue(db_manager, current_user, selected_user=None):
    """計算累計營收統計（所有歷史資料，SQL 去重）"""
    try:
        
        # 檢查資料庫連線狀態
        if not db_manager.conn or db_manager.conn.closed:
            if not db_manager.connect():
                st.error("無法重新連線到資料庫")
                return {
                    'total_estimate': 0,
                    'total_revenue': 0,
                    'total_cost': 0
                }
        
        # 使用 SQL 去重查詢所有歷史營收資料
        if current_user['role'] == 'admin':
            if selected_user:
                query = """
                SELECT wp.estimate, wp.revenue, wp.cost
                FROM (
                    SELECT wp.estimate, wp.revenue, wp.cost,
                           ROW_NUMBER() OVER (PARTITION BY wp.item ORDER BY wp.date DESC) as rn
                    FROM work_progress wp 
                    JOIN users u ON wp.user_id = u.id 
                    WHERE u.full_name = %s
                ) wp
                WHERE wp.rn = 1
                """
                result = db_manager.execute_query(query, (selected_user,))
            else:
                query = """
                SELECT wp.estimate, wp.revenue, wp.cost
                FROM (
                    SELECT wp.estimate, wp.revenue, wp.cost,
                           ROW_NUMBER() OVER (PARTITION BY wp.item ORDER BY wp.date DESC) as rn
                    FROM work_progress wp 
                    JOIN users u ON wp.user_id = u.id 
                ) wp
                WHERE wp.rn = 1
                """
                result = db_manager.execute_query(query)
        else:
            query = """
            SELECT estimate, revenue, cost
            FROM (
                SELECT estimate, revenue, cost,
                       ROW_NUMBER() OVER (PARTITION BY item ORDER BY date DESC) as rn
                FROM work_progress 
                WHERE user_id = %s 
            ) wp
            WHERE rn = 1
            """
            result = db_manager.execute_query(query, (current_user['id'],))
        
        if result:
            # 計算統計數值
            total_estimate = sum(row[0] or 0 for row in result)
            total_revenue = sum(row[1] or 0 for row in result)
            total_cost = sum(row[2] or 0 for row in result)
            
            # 計算毛利率
            if total_revenue > 0:
                gross_profit_margin = ((total_revenue - total_cost) / total_revenue) * 100
            else:
                gross_profit_margin = 0.0
            
            return {
                'total_estimate': int(total_estimate),
                'total_revenue': int(total_revenue),
                'total_cost': int(total_cost),
                'gross_profit_margin': round(gross_profit_margin, 2)
            }
        else:
            return {
                'total_estimate': 0,
                'total_revenue': 0,
                'total_cost': 0,
                'gross_profit_margin': 0.0
            }
        
    except Exception as e:
        st.error(f"計算累計營收統計時發生錯誤：{e}")
        return {
            'total_estimate': 0,
            'total_revenue': 0,
            'total_cost': 0,
            'gross_profit_margin': 0.0
        }

def calculate_week_statistics(db_manager, current_user, week_start, selected_user=None):
    """計算該週的財務統計"""
    try:
        # 載入該週的工作資料
        df = load_work_data(db_manager, current_user, week_start, selected_user)
        
        if df.empty:
            return {
                'total_estimate': 0,
                'total_revenue': 0,
                'total_cost': 0
            }
        
        # 計算統計數值
        total_estimate = df['estimate'].fillna(0).sum()
        total_revenue = df['revenue'].fillna(0).sum()
        total_cost = df['cost'].fillna(0).sum()
        
        return {
            'total_estimate': int(total_estimate),
            'total_revenue': int(total_revenue),
            'total_cost': int(total_cost)
        }
        
    except Exception as e:
        st.error(f"計算週統計時發生錯誤：{e}")
        return {
            'total_estimate': 0,
            'total_revenue': 0,
            'total_cost': 0
        }

def add_work_item(db_manager, current_user, week_start, selected_user=None):
    """新增工作項目"""
    st.subheader("新增工作項目")
    
    with st.form("add_work_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            date = st.date_input("日期", value=week_start)
            usage_status = st.selectbox("使用狀況", ["", "下機品", "新品"], help="選擇使用狀況")
            release_form = st.text_input("放行單", placeholder="請輸入放行單")
            factory = st.text_input("廠區", placeholder="請輸入廠區")
            username = st.text_input("User", placeholder="請輸入User")
            customer = st.text_input("客戶", placeholder="請輸入客戶名稱")
            item = st.text_input("工作項目", placeholder="請輸入工作項目")
            purpose = st.text_input("目的", placeholder="請輸入目的")
            problem = st.text_input("問題", placeholder="請輸入問題")
            status = st.text_input("狀態", placeholder="請輸入狀態")
            deadline = st.date_input("截止日期", value=week_start)
        
        with col2:
            completion_rate = st.slider("完成度 (%)", 0, 100, 0)
            estimate = st.number_input("預估營收", min_value=0, value=0, step=1000, format="%d")
            revenue = st.number_input("營收", min_value=0, value=0, step=1000, format="%d")
            cost = st.number_input("成本", min_value=0, value=0, step=1000, format="%d")
        
        solution = st.text_area("解決方案", placeholder="請輸入解決方案", height=100)
        
        # 階段選擇（必填）
        phase_list = get_phase_list(db_manager)
        if phase_list:
            phase_options = {f"{code} - {name}": code for code, name in phase_list}
            selected_phase_display = st.selectbox("目前階段 *", list(phase_options.keys()), help="此欄位為必填")
            selected_phase_code = phase_options[selected_phase_display]
        else:
            st.warning("無法載入階段列表")
            selected_phase_code = None
        
        # 自動計算毛利率
        if revenue > 0:
            gross_profit = ((revenue - cost) / revenue) * 100
            st.info(f"毛利率: {gross_profit:.2f}%")
        else:
            gross_profit = 0.0
        
        # 圖片上傳
        uploaded_files = st.file_uploader(
            "上傳圖片", 
            type=['jpg', 'jpeg', 'png', 'gif', 'bmp'], 
            accept_multiple_files=True
        )
        
        submitted = st.form_submit_button("儲存")
        
        if submitted:
            if not item:
                st.error("工作項目不能為空。")
                return
            
            # 驗證階段選擇（必填）
            if not selected_phase_code:
                st.error("請選擇目前階段，此欄位為必填。")
                return
            
            # 檢查表格結構（除錯用）
            st.info("檢查表格結構...")
            check_table_structure(db_manager)
            
            # 取得使用者ID
            if current_user['role'] == 'admin':
                if not selected_user:
                    st.error("請先選擇使用者。")
                    return
                user_id = get_user_id_by_name(db_manager, selected_user)
                if not user_id:
                    st.error("無法取得使用者ID。")
                    return
            else:
                user_id = current_user['id']
            
            # 插入資料庫
            insert_query = """
            INSERT INTO work_progress (user_id, date, usage_status, release_form, factory, username, item, purpose, problem, status, solution, deadline, 
                                     completion_rate, estimate, revenue, cost, gross_profit, customer, phase_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """
            
            # 確保毛利率是正確的格式（小數，不是百分比）
            gross_profit_decimal = gross_profit / 100 if gross_profit > 0 else 0.0
            
            insert_data = (
                user_id, date, usage_status, release_form, factory, username, item, purpose, problem, status, solution,
                deadline, completion_rate, estimate, revenue, cost, gross_profit_decimal, customer, selected_phase_code
            )
            
            try:
                # 添加除錯資訊
                st.info(f"正在插入資料：user_id={user_id}, date={date}, item={item}")
                
                result = db_manager.execute_query(insert_query, insert_data, fetch=True)
                
                if result:
                    work_progress_id = result[0][0]
                    st.success(f"資料庫插入成功！記錄ID: {work_progress_id}")
                    
                    # 處理圖片上傳
                    if uploaded_files:
                        success_count = upload_images_to_database(db_manager, work_progress_id, uploaded_files)
                        if success_count > 0:
                            st.success(f"工作項目已成功新增！並上傳了 {success_count} 張圖片。")
                        else:
                            st.success("工作項目已成功新增！但圖片上傳失敗。")
                    else:
                        st.success("工作項目已成功新增！")
                    
                    st.rerun()
                else:
                    st.error("新增資料時發生錯誤：資料庫查詢返回空結果")
                    
            except Exception as e:
                st.error(f"新增資料時發生異常：{str(e)}")
                st.error(f"插入資料：{insert_data}")

def upload_images_to_database(db_manager, work_progress_id, uploaded_files):
    """上傳圖片到資料庫"""
    try:
        success_count = 0
        for uploaded_file in uploaded_files:
            try:
                # 讀取並壓縮圖片
                image = Image.open(uploaded_file)
                
                # 檢查圖片尺寸，如果太大則進行縮放
                max_size = (1920, 1080)  # 最大寬度和高度
                if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)
                    st.info(f"圖片 {uploaded_file.name} 已縮放至 {image.size[0]}x{image.size[1]}")
                
                # 轉換為 RGB 模式（如果是 RGBA，移除透明通道）
                if image.mode in ('RGBA', 'LA', 'P'):
                    # 創建白色背景
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    if image.mode == 'P':
                        image = image.convert('RGBA')
                    background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                    image = background
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # 壓縮圖片（品質設為 85%）
                output_buffer = io.BytesIO()
                image.save(output_buffer, format='JPEG', quality=85, optimize=True)
                compressed_image_data = output_buffer.getvalue()
                
                # 生成檔案名稱（改為 .jpg 格式）
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                base_name = os.path.splitext(uploaded_file.name)[0]
                new_filename = f"{timestamp}_{base_name}.jpg"
                
                # 顯示壓縮資訊
                # 重新讀取原始檔案大小
                uploaded_file.seek(0)
                original_size = len(uploaded_file.read())
                compressed_size = len(compressed_image_data)
                compression_ratio = (1 - compressed_size / original_size) * 100
                st.info(f"圖片 {uploaded_file.name} 壓縮完成：{original_size/1024:.1f}KB → {compressed_size/1024:.1f}KB (節省 {compression_ratio:.1f}%)")
                
                # 儲存到資料庫
                query = """
                INSERT INTO work_images (work_progress_id, image_name, image_data, image_path, uploaded_at, created_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                """
                if db_manager.execute_query(query, (work_progress_id, new_filename, compressed_image_data, new_filename), fetch=False):
                    success_count += 1
                    
            except Exception as e:
                st.error(f"處理圖片 {uploaded_file.name} 時發生錯誤：{str(e)}")
        
        return success_count
        
    except Exception as e:
        st.error(f"上傳圖片時發生錯誤：{str(e)}")
        return 0

def edit_work_item(db_manager, current_user, selected_user=None):
    """編輯工作項目"""
    st.subheader("編輯工作項目")
    
    # 載入當前週期資料
    week_start = st.session_state.current_week_start
    df = load_work_data(db_manager, current_user, week_start, selected_user)
    
    if df.empty:
        st.warning("目前沒有資料可以編輯。")
        return
    
    # 選擇要編輯的項目 - 改用 ID 和更多資訊來識別
    if 'id' in df.columns and 'item' in df.columns:
        # 創建顯示選項，包含 ID、日期和項目名稱
        df['display_option'] = df.apply(lambda row: f"ID:{row['id']} | {row['date'].strftime('%m/%d')} | {row['item']}", axis=1)
        
        selected_display = st.selectbox("選擇要編輯的項目", df['display_option'].tolist())
        
        if selected_display:
            # 根據顯示選項找到對應的資料
            selected_row = df[df['display_option'] == selected_display]
            if not selected_row.empty:
                item_data = selected_row.iloc[0]
                selected_id = item_data['id']  # 取得主鍵 ID
            
            with st.form("edit_work_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    # 安全地處理日期欄位
                    date_value = item_data['date']
                    if pd.api.types.is_datetime64_any_dtype(date_value):
                        date_value = date_value.date()
                    elif isinstance(date_value, str):
                        date_value = pd.to_datetime(date_value).date()
                    else:
                        date_value = date_value
                    
                    deadline_value = item_data['deadline']
                    if pd.api.types.is_datetime64_any_dtype(deadline_value):
                        deadline_value = deadline_value.date()
                    elif isinstance(deadline_value, str):
                        deadline_value = pd.to_datetime(deadline_value).date()
                    else:
                        deadline_value = deadline_value
                    
                    date = st.date_input("日期", value=date_value)
                    
                    # 安全地處理新欄位
                    usage_status_value = item_data['usage_status']
                    if pd.isna(usage_status_value):
                        usage_status_value = ""
                    else:
                        usage_status_value = str(usage_status_value)
                    
                    release_form_value = item_data['release_form']
                    if pd.isna(release_form_value):
                        release_form_value = ""
                    else:
                        release_form_value = str(release_form_value)
                    
                    factory_value = item_data['factory']
                    if pd.isna(factory_value):
                        factory_value = ""
                    else:
                        factory_value = str(factory_value)
                    
                    username_value = item_data['username']
                    if pd.isna(username_value):
                        username_value = ""
                    else:
                        username_value = str(username_value)
                    
                    # 安全地處理文字欄位
                    customer_value = item_data['customer']
                    if pd.isna(customer_value):
                        customer_value = ""
                    else:
                        customer_value = str(customer_value)
                    
                    item_value = item_data['item']
                    if pd.isna(item_value):
                        item_value = ""
                    else:
                        item_value = str(item_value)
                    
                    purpose_value = item_data['purpose']
                    if pd.isna(purpose_value):
                        purpose_value = ""
                    else:
                        purpose_value = str(purpose_value)
                    
                    problem_value = item_data['problem']
                    if pd.isna(problem_value):
                        problem_value = ""
                    else:
                        problem_value = str(problem_value)
                    
                    status_value = item_data['status']
                    if pd.isna(status_value):
                        status_value = ""
                    else:
                        status_value = str(status_value)
                    
                    usage_status = st.selectbox("使用狀況", ["", "下機品", "新品"], index=["", "下機品", "新品"].index(usage_status_value) if usage_status_value in ["", "下機品", "新品"] else 0, help="選擇使用狀況")
                    release_form = st.text_input("放行單", value=release_form_value)
                    factory = st.text_input("廠區", value=factory_value)
                    username = st.text_input("User", value=username_value)
                    customer = st.text_input("客戶", value=customer_value)
                    item = st.text_input("工作項目", value=item_value)
                    purpose = st.text_input("目的", value=purpose_value)
                    problem = st.text_input("問題", value=problem_value)
                    status = st.text_input("狀態", value=status_value)
                    deadline = st.date_input("截止日期", value=deadline_value)
                
                with col2:
                    # 安全地處理數值欄位
                    completion_value = item_data['completion_rate']
                    if pd.isna(completion_value):
                        completion_value = 0
                    else:
                        completion_value = int(float(completion_value))
                    
                    estimate_value = item_data['estimate']
                    if pd.isna(estimate_value):
                        estimate_value = 0
                    else:
                        estimate_value = int(float(estimate_value))
                    
                    revenue_value = item_data['revenue']
                    if pd.isna(revenue_value):
                        revenue_value = 0
                    else:
                        revenue_value = int(float(revenue_value))
                    
                    cost_value = item_data['cost']
                    if pd.isna(cost_value):
                        cost_value = 0
                    else:
                        cost_value = int(float(cost_value))
                    
                    completion_rate = st.slider("完成度 (%)", 0, 100, completion_value)
                    estimate = st.number_input("預估營收", min_value=0, value=estimate_value, step=1000, format="%d")
                    revenue = st.number_input("營收", min_value=0, value=revenue_value, step=1000, format="%d")
                    cost = st.number_input("成本", min_value=0, value=cost_value, step=1000, format="%d")
                
                # 安全地處理文字欄位
                solution_value = item_data['solution']
                if pd.isna(solution_value):
                    solution_value = ""
                else:
                    solution_value = str(solution_value)
                
                solution = st.text_area("解決方案", value=solution_value, height=100)
                
                # 階段選擇（必填）
                phase_list = get_phase_list(db_manager)
                if phase_list:
                    # 取得當前項目的階段代碼
                    current_phase_code = item_data.get('phase_code', '')
                    if pd.isna(current_phase_code) or current_phase_code == '':
                        # 如果原本是空的，設定為預設值 P1
                        current_phase_code = 'P1'
                        st.info("此項目的階段代碼原本為空，已設定為預設階段 P1")
                    else:
                        current_phase_code = str(current_phase_code)
                    
                    # 建立選項字典
                    phase_options = {f"{code} - {name}": code for code, name in phase_list}
                    
                    # 找到當前階段對應的顯示文字
                    current_phase_display = None
                    for display, code in phase_options.items():
                        if code == current_phase_code:
                            current_phase_display = display
                            break
                    
                    # 如果找不到對應的顯示文字，使用第一個選項
                    if current_phase_display is None and phase_options:
                        current_phase_display = list(phase_options.keys())[0]
                    
                    selected_phase_display = st.selectbox("目前階段 *", list(phase_options.keys()), 
                                                        index=list(phase_options.keys()).index(current_phase_display) if current_phase_display else 0,
                                                        help="此欄位為必填")
                    selected_phase_code = phase_options[selected_phase_display]
                else:
                    st.warning("無法載入階段列表")
                    selected_phase_code = None
                
                # 自動計算毛利率
                if revenue > 0:
                    gross_profit = ((revenue - cost) / revenue) * 100
                    st.info(f"毛利率: {gross_profit:.2f}%")
                else:
                    gross_profit = 0.0
                
                # 圖片上傳
                uploaded_files = st.file_uploader(
                    "上傳新圖片", 
                    type=['jpg', 'jpeg', 'png', 'gif', 'bmp'], 
                    accept_multiple_files=True
                )
                
                submitted = st.form_submit_button("更新")
                
                if submitted:
                    if not item:
                        st.error("工作項目不能為空。")
                        return
                    
                    # 驗證階段選擇（必填）
                    if not selected_phase_code:
                        st.error("請選擇目前階段，此欄位為必填。")
                        return
                    
                    # 取得使用者ID
                    if current_user['role'] == 'admin':
                        if not selected_user:
                            st.error("請先選擇使用者。")
                            return
                        user_id = get_user_id_by_name(db_manager, selected_user)
                        if not user_id:
                            st.error("無法取得使用者ID。")
                            return
                    else:
                        user_id = current_user['id']
                    
                    # 使用主鍵 ID 來更新記錄
                    update_query = """
                    UPDATE work_progress 
                    SET date = %s, usage_status = %s, release_form = %s, factory = %s, username = %s, item = %s, purpose = %s, problem = %s, status = %s, solution = %s, 
                        deadline = %s, completion_rate = %s, estimate = %s, revenue = %s, cost = %s, gross_profit = %s, customer = %s, phase_code = %s
                    WHERE id = %s
                    """
                    
                    update_data = (
                        date, usage_status, release_form, factory, username, item, purpose, problem, status, solution,
                        deadline, completion_rate, estimate, revenue, cost, gross_profit/100, customer, selected_phase_code,
                        int(selected_id)  # 確保是 Python 原生 int 類型
                    )
                    
                    if db_manager.execute_query(update_query, update_data, fetch=False):
                        # 處理圖片上傳
                        if uploaded_files:
                            # 直接使用 selected_id 作為 work_progress_id，確保是 int 類型
                            success_count = upload_images_to_database(db_manager, int(selected_id), uploaded_files)
                            if success_count > 0:
                                st.success(f"工作項目已成功更新！並新增了 {success_count} 張圖片。")
                            else:
                                st.success("工作項目已成功更新！但圖片上傳失敗。")
                        else:
                            st.success("工作項目已成功更新！")
                        
                        st.rerun()
                    else:
                        st.error("更新資料時發生錯誤。")

def find_work_progress_id(db_manager, user_id, date_str, item_name):
    """根據日期和工作項目找到記錄ID"""
    try:
        # 檢查資料庫連線狀態
        if not db_manager.conn or db_manager.conn.closed:
            if not db_manager.connect():
                st.error("無法重新連線到資料庫")
                return None
        
        # 將日期字串轉換為日期物件
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        query = """
        SELECT id FROM work_progress 
        WHERE user_id = %s AND date = %s AND item = %s
        """
        
        result = db_manager.execute_query(query, (user_id, date_obj, item_name))
        if result:
            return result[0][0]  # 返回記錄ID
        return None
        
    except Exception as e:
        st.error(f"查找工作記錄ID時發生錯誤：{str(e)}")
        return None

def delete_images_from_database(db_manager, work_progress_id):
    """從資料庫刪除圖片"""
    try:
        query = "DELETE FROM work_images WHERE work_progress_id = %s"
        return db_manager.execute_query(query, (work_progress_id,), fetch=False)
    except Exception as e:
        st.error(f"從資料庫刪除圖片時發生錯誤：{str(e)}")
        return False

def delete_work_item(db_manager, current_user, selected_user=None):
    """刪除工作項目"""
    st.subheader("刪除工作項目")
    
    # 載入當前週期資料
    week_start = st.session_state.current_week_start
    df = load_work_data(db_manager, current_user, week_start, selected_user)
    
    if df.empty:
        st.warning("目前沒有資料可以刪除。")
        return
    
    # 選擇要刪除的項目 - 改用 ID 和更多資訊來識別
    if 'id' in df.columns and 'item' in df.columns:
        # 創建顯示選項，包含 ID、日期和項目名稱
        df['display_option'] = df.apply(lambda row: f"ID:{row['id']} | {row['date'].strftime('%m/%d')} | {row['item']}", axis=1)
        
        selected_display = st.selectbox("選擇要刪除的項目", df['display_option'].tolist(), key="delete_select")
        
        if selected_display:
            # 根據顯示選項找到對應的資料
            selected_row = df[df['display_option'] == selected_display]
            if not selected_row.empty:
                item_data = selected_row.iloc[0]
                selected_id = item_data['id']  # 取得主鍵 ID
                selected_item = item_data['item']  # 取得項目名稱用於顯示
            
            st.warning(f"確定要刪除項目「{selected_item}」嗎？")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("確認刪除", type="primary"):
                    try:
                        # 使用主鍵 ID 來刪除記錄
                        delete_query = """
                        DELETE FROM work_progress 
                        WHERE id = %s
                        """
                        # 確保 selected_id 是 Python 原生 int 類型
                        delete_params = (int(selected_id),)
                        
                        # 先刪除相關圖片，確保是 int 類型
                        delete_images_from_database(db_manager, int(selected_id))
                        
                        # 執行刪除
                        result = db_manager.execute_query(delete_query, delete_params, fetch=False)
                        
                        if result:
                            st.success("已成功刪除該筆工作記錄及相關圖片。")
                            st.rerun()
                        else:
                            st.error("刪除操作失敗，請檢查資料庫連線。")
                            
                    except Exception as e:
                        st.error(f"刪除時發生錯誤：{str(e)}")
            
            with col2:
                if st.button("取消"):
                    st.rerun()

def show_revenue_trend(db_manager, item_name):
    """顯示營收趨勢圖"""
    try:
        # 檢查資料庫連線狀態
        if not db_manager.conn or db_manager.conn.closed:
            if not db_manager.connect():
                st.error("無法重新連線到資料庫")
                return
        
        # 查詢相同項目的所有營收和預估營收資料
        query = """
        SELECT date, item, revenue, estimate
        FROM work_progress
        WHERE item = %s AND (revenue IS NOT NULL OR estimate IS NOT NULL)
        ORDER BY date
        """
        
        result = db_manager.execute_query(query, (item_name,))
        
        if result:
            df = pd.DataFrame(result, columns=['date', 'item', 'revenue', 'estimate'])
            
            # 處理空值，將 None 轉換為 0
            df['revenue'] = df['revenue'].fillna(0)
            df['estimate'] = df['estimate'].fillna(0)
            
            # 無論幾筆資料，都從0開始顯示趨勢線
            # 取得最早日期的前3天作為起始點
            earliest_date = df['date'].min()
            start_date = earliest_date - timedelta(days=3)
            
            # 創建起始點（營收和預估營收都為0）
            start_point = pd.DataFrame({
                'date': [start_date],
                'item': [item_name],
                'revenue': [0],
                'estimate': [0]
            })
            
            # 合併起始點和實際資料
            trend_df = pd.concat([start_point, df], ignore_index=True)
            
            # 建立雙線趨勢圖
            fig = go.Figure()
            
            # 添加實際營收線
            fig.add_trace(go.Scatter(
                x=trend_df['date'],
                y=trend_df['revenue'],
                mode='lines+markers',
                name='實際營收',
                line=dict(color='blue', width=2),
                marker=dict(size=6)
            ))
            
            # 添加預估營收線
            fig.add_trace(go.Scatter(
                x=trend_df['date'],
                y=trend_df['estimate'],
                mode='lines+markers',
                name='預估營收',
                line=dict(color='red', width=2),
                marker=dict(size=6)
            ))
            
            # 更新圖表佈局
            fig.update_layout(
                title=f'項目: {item_name} - 營收趨勢圖',
                xaxis_title="日期",
                yaxis_title="營收 (元)",
                hovermode='x unified',
                legend=dict(
                    yanchor="top",
                    y=0.99,
                    xanchor="left",
                    x=0.01
                )
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"項目「{item_name}」沒有營收趨勢資料")
            
    except Exception as e:
        st.error(f"顯示營收趨勢圖時發生錯誤：{str(e)}")

def show_coa_images(db_manager, work_progress_id, item_name):
    """顯示COA圖片"""
    try:
        # 檢查資料庫連線狀態
        if not db_manager.conn or db_manager.conn.closed:
            if not db_manager.connect():
                st.error("無法重新連線到資料庫")
                return
        
        # 查詢圖片資料
        query = """
        SELECT image_name, image_data
        FROM work_images
        WHERE work_progress_id = %s
        ORDER BY image_name
        """
        
        result = db_manager.execute_query(query, (work_progress_id,))
        
        if result:
            st.subheader(f"工作圖片 - {item_name}")
            
            for i, (image_name, image_data) in enumerate(result):
                st.write(f"**圖片 {i+1}: {image_name}**")
                
                # 處理 memoryview 類型的圖片資料
                if hasattr(image_data, 'tobytes'):
                    # 如果是 memoryview，轉換為 bytes
                    image_bytes = image_data.tobytes()
                elif isinstance(image_data, bytes):
                    # 如果已經是 bytes，直接使用
                    image_bytes = image_data
                else:
                    # 其他情況，嘗試轉換為 bytes
                    image_bytes = bytes(image_data)
                
                # 顯示圖片
                try:
                    image = Image.open(io.BytesIO(image_bytes))
                    st.image(image, caption=image_name, use_container_width=True)
                    
                    # 下載按鈕
                    st.download_button(
                        label=f"下載 {image_name}",
                        data=image_bytes,
                        file_name=image_name,
                        mime="image/png"
                    )
                except Exception as img_error:
                    st.error(f"無法顯示圖片 {image_name}：{str(img_error)}")
                
                st.markdown("---")
        else:
            st.info(f"項目「{item_name}」目前沒有相關的工作圖片")
            
    except Exception as e:
        st.error(f"顯示工作圖片時發生錯誤：{str(e)}")
        st.error(f"錯誤詳情：{type(e).__name__}")

def copy_previous_week_data(db_manager, current_user, selected_user=None):
    """複製上週進度資料"""
    try:
        # 檢查資料庫連線狀態
        if not db_manager.conn or db_manager.conn.closed:
            if not db_manager.connect():
                st.error("無法重新連線到資料庫")
                return
        
        # 計算上週的日期範圍
        previous_week_start = st.session_state.current_week_start - timedelta(days=7)
        previous_week_end = previous_week_start + timedelta(days=6)
        
        st.info(f"正在查詢上週資料：{previous_week_start.strftime('%Y-%m-%d')} ~ {previous_week_end.strftime('%Y-%m-%d')}")
        
        # 查詢上週的資料
        if current_user['role'] == 'admin':
            if selected_user:
                query = """
                SELECT wp.id, wp.date, wp.usage_status, wp.release_form, wp.factory, wp.username, wp.item, wp.purpose, wp.problem, wp.status, wp.solution, wp.deadline,
                       wp.completion_rate, wp.estimate, wp.revenue, wp.cost, wp.gross_profit, wp.customer, wp.phase_code
                FROM work_progress wp 
                JOIN users u ON wp.user_id = u.id 
                WHERE u.full_name = %s
                  AND wp.date >= %s AND wp.date <= %s
                ORDER BY wp.date ASC
                """
                previous_data = db_manager.execute_query(query, (selected_user, previous_week_start, previous_week_end))
            else:
                st.error("請先選擇要複製的使用者。")
                return
        else:
            query = """
            SELECT id, date, usage_status, release_form, factory, username, item, purpose, problem, status, solution, deadline, 
                   completion_rate, estimate, revenue, cost, gross_profit, customer, phase_code
            FROM work_progress 
            WHERE user_id = %s 
              AND date >= %s AND date <= %s
            ORDER BY date ASC
            """
            previous_data = db_manager.execute_query(query, (current_user['id'], previous_week_start, previous_week_end))
        
        if previous_data:
            st.info(f"找到 {len(previous_data)} 筆上週資料，開始複製...")
            
            # 複製資料並修改日期為當前週期
            success_count = 0
            for i, row_data in enumerate(previous_data):
                try:
                    # 計算新的日期（保持星期幾不變，但改為當前週期）
                    original_date = row_data[1]  # date 欄位
                    if original_date:
                        # 確保 original_date 是 date 類型
                        if hasattr(original_date, 'date'):
                            original_date = original_date.date()
                        elif isinstance(original_date, str):
                            # 如果是字串，嘗試解析為日期
                            try:
                                original_date = datetime.strptime(original_date, '%Y-%m-%d').date()
                            except ValueError:
                                st.error(f"無法解析日期格式：{original_date}")
                                continue
                        elif not isinstance(original_date, date):
                            st.error(f"不支援的日期類型：{type(original_date)}")
                            continue
                        
                        # 計算原日期在上週的第幾天
                        days_diff = (original_date - previous_week_start).days
                        # 計算當前週期對應的日期
                        new_date = st.session_state.current_week_start + timedelta(days=days_diff)
                        
                        # 插入新資料
                        insert_query = """
                        INSERT INTO work_progress (user_id, date, usage_status, release_form, factory, username, item, purpose, problem, status, solution, deadline, 
                                                 completion_rate, estimate, revenue, cost, gross_profit, customer, phase_code)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        
                        # 取得使用者ID
                        if current_user['role'] == 'admin':
                            user_id = get_user_id_by_name(db_manager, selected_user)
                            if not user_id:
                                st.error(f"無法取得使用者 {selected_user} 的ID")
                                continue
                        else:
                            user_id = current_user['id']
                        
                        # 處理日期欄位
                        deadline_date = row_data[11]  # deadline 欄位 (索引11，因為前面有4個欄位)
                        if deadline_date:
                            # 確保 deadline_date 是 date 類型
                            if hasattr(deadline_date, 'date'):
                                deadline_date = deadline_date.date()
                            elif isinstance(deadline_date, str):
                                # 如果是字串，嘗試解析為日期
                                try:
                                    deadline_date = datetime.strptime(deadline_date, '%Y-%m-%d').date()
                                except ValueError:
                                    st.error(f"無法解析截止日期格式：{deadline_date}")
                                    deadline_date = new_date  # 使用新日期作為預設值
                            elif not isinstance(deadline_date, date):
                                st.error(f"不支援的截止日期類型：{type(deadline_date)}")
                                deadline_date = new_date  # 使用新日期作為預設值
                            
                            # 同樣調整截止日期
                            deadline_days_diff = (deadline_date - previous_week_start).days
                            new_deadline = st.session_state.current_week_start + timedelta(days=deadline_days_diff)
                        else:
                            new_deadline = new_date
                        
                        # 處理階段代碼，如果是空的則設定為 P1
                        phase_code = row_data[18] if row_data[18] and str(row_data[18]).strip() != '' else 'P1'
                        
                        insert_data = (
                            user_id, new_date, row_data[2], row_data[3], row_data[4], row_data[5], row_data[6], row_data[7], row_data[8], row_data[9], row_data[10], 
                            new_deadline, row_data[12], row_data[13], row_data[14], row_data[15], row_data[16], row_data[17], phase_code
                        )
                        
                        if db_manager.execute_query(insert_query, insert_data, fetch=False):
                            success_count += 1
                            st.info(f"已複製第 {i+1} 筆資料：{row_data[6]} ({new_date.strftime('%Y-%m-%d')})")
                        else:
                            st.error(f"複製第 {i+1} 筆資料失敗：{row_data[6]}")
                
                except Exception as row_error:
                    st.error(f"處理第 {i+1} 筆資料時發生錯誤：{str(row_error)}")
                    continue
            
            if success_count > 0:
                st.success(f"已成功複製 {success_count} 筆上週資料到本週！")
                st.rerun()
            else:
                st.error("複製過程中沒有成功插入任何資料。")
        else:
            st.warning("上週沒有資料可以複製。")
            
    except Exception as e:
        st.error(f"複製上週資料時發生錯誤：{str(e)}")
        st.error(f"錯誤詳情：{type(e).__name__}")

def main_dashboard():
    """主儀表板"""
    st.header("工作進度管理系統")
    
    # 頂部資訊
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.write(f"**歡迎，{st.session_state.current_user['full_name']}**")
    
    with col2:
        if st.button("🚪 登出"):
            st.session_state.logged_in = False
            st.session_state.current_user = None
            st.session_state.db_manager = None
            st.rerun()
    
    st.markdown("---")
    
    # 週期控制
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
    
    with col1:
        if st.button("◀ 上週"):
            st.session_state.current_week_start -= timedelta(days=7)
            st.rerun()
    
    with col2:
        if st.button("下週 ▶"):
            st.session_state.current_week_start += timedelta(days=7)
            st.rerun()
    
    with col3:
        if st.button("📋 複製上週", key="copy_previous_week_btn"):
            copy_previous_week_data(st.session_state.db_manager, st.session_state.current_user, st.session_state.selected_user)
    
    with col4:
        week_end = st.session_state.current_week_start + timedelta(days=6)
        st.write(f"**工作週期：{st.session_state.current_week_start.strftime('%m/%d')} ~ {week_end.strftime('%m/%d')}**")
    
    # 累計營收統計
    st.subheader("💰 累計營收統計")
    
    # 計算累計營收統計
    cumulative_revenue = calculate_cumulative_revenue(
        st.session_state.db_manager, 
        st.session_state.current_user, 
        st.session_state.selected_user
    )
    
    # 顯示累計營收統計指標
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="總預估營收",
            value=f"{cumulative_revenue['total_estimate']:,}",
            help="所有項目的預估營收總和（去重後）"
        )
    
    with col2:
        st.metric(
            label="總營收",
            value=f"{cumulative_revenue['total_revenue']:,}",
            help="所有項目的實際營收總和（去重後）"
        )
    
    with col3:
        st.metric(
            label="總成本",
            value=f"{cumulative_revenue['total_cost']:,}",
            help="所有項目的成本總和（去重後）"
        )
    
    with col4:
        st.metric(
            label="毛利率",
            value=f"{cumulative_revenue['gross_profit_margin']:.2f}%",
            help="整體毛利率（(總營收-總成本)/總營收*100）"
        )
    
    
    # Admin 模式的使用者選擇
    if st.session_state.current_user['role'] == 'admin':
        st.markdown("---")
        users = get_users_list(st.session_state.db_manager)
        if users:
            # 🔍 新增：保護 selected_user 不被意外重置
            if st.session_state.selected_user is None:
                st.session_state.selected_user = users[0]  # 預設選擇第一個使用者
            
            selected_user = st.selectbox("選擇使用者", users, key="admin_user_select", index=users.index(st.session_state.selected_user) if st.session_state.selected_user in users else 0)
            
            if selected_user != st.session_state.selected_user:
                st.session_state.selected_user = selected_user
                st.rerun()
    
    st.markdown("---")
    
    # 功能選單
    tab_names = ["📊 工作進度", "➕ 新增項目", "✏️ 編輯項目", "🗑️ 刪除項目", "📈 趨勢分析"]
    
    # Admin 用戶額外功能
    if st.session_state.current_user['role'] == 'admin':
        tab_names.append("🔧 系統管理")
    
    # 使用原本的分頁樣式
    tabs = st.tabs(tab_names)
    
    with tabs[0]:
        # 欄位順序自訂區域
        with st.expander("🔧 自訂欄位順序", expanded=False):
            st.info("💡 提示：選擇要顯示的欄位，然後使用上移/下移按鈕調整順序")
            
            # 預設所有欄位
            all_columns = [
                '編號', '日期', '放行單', '使用狀況', '客戶', '廠區', 'User', '工作項目', 
                '目的', '問題', '狀態', '解決方案', '目前階段', '完成度', '預估營收', 
                '營收', '成本', '毛利率', '截止日期'
            ]
            
            # 欄位選擇器
            selected_columns = st.multiselect(
                "選擇要顯示的欄位",
                options=all_columns,
                default=st.session_state.column_order if st.session_state.use_custom_order else all_columns,
                help="選擇要顯示的欄位，取消勾選可隱藏欄位"
            )
            
            # 如果有選擇欄位，顯示順序調整工具
            if selected_columns:
                st.write("**調整欄位順序：**")
                
                col_select, col_up, col_down = st.columns([3, 1, 1])
                
                with col_select:
                    if len(selected_columns) > 1:
                        selected_field = st.selectbox(
                            "選擇要調整的欄位",
                            options=selected_columns,
                            key="field_to_move"
                        )
                    else:
                        st.info("只有一個欄位，無需調整順序")
                        selected_field = None
                
                if len(selected_columns) > 1 and selected_field:
                    current_index = selected_columns.index(selected_field)
                    
                    with col_up:
                        if st.button("⬆️ 上移", use_container_width=True, disabled=(current_index == 0)):
                            # 交換位置
                            selected_columns[current_index], selected_columns[current_index - 1] = \
                                selected_columns[current_index - 1], selected_columns[current_index]
                            st.session_state.column_order = selected_columns
                            st.session_state.use_custom_order = True
                            st.rerun()
                    
                    with col_down:
                        if st.button("⬇️ 下移", use_container_width=True, disabled=(current_index == len(selected_columns) - 1)):
                            # 交換位置
                            selected_columns[current_index], selected_columns[current_index + 1] = \
                                selected_columns[current_index + 1], selected_columns[current_index]
                            st.session_state.column_order = selected_columns
                            st.session_state.use_custom_order = True
                            st.rerun()
                
                # 顯示目前順序
                st.write("**目前欄位順序：**")
                st.write(" → ".join(selected_columns))
            
            st.markdown("---")
            
            # 控制按鈕
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("✅ 套用", use_container_width=True):
                    if selected_columns:
                        st.session_state.column_order = selected_columns
                        st.session_state.use_custom_order = True
                        st.success("已套用自訂欄位順序！")
                        st.rerun()
                    else:
                        st.warning("請至少選擇一個欄位")
            
            with col2:
                if st.button("🔄 重置", use_container_width=True):
                    st.session_state.column_order = all_columns
                    st.session_state.use_custom_order = False
                    st.success("已重置為預設順序！")
                    st.rerun()
            
            with col3:
                if st.button("☑️ 全選", use_container_width=True):
                    st.session_state.column_order = all_columns
                    st.session_state.use_custom_order = True
                    st.rerun()
            
            with col4:
                if st.button("☐ 全不選", use_container_width=True):
                    st.session_state.column_order = []
                    st.session_state.use_custom_order = True
                    st.rerun()
            
            # 顯示目前狀態
            if st.session_state.use_custom_order:
                st.caption(f"✓ 目前使用自訂順序，顯示 {len(st.session_state.column_order)} 個欄位")
            else:
                st.caption(f"ℹ️ 目前使用預設順序，顯示 {len(all_columns)} 個欄位")
        
        st.markdown("---")
        
        # 載入並顯示工作資料
        df = load_work_data(st.session_state.db_manager, st.session_state.current_user, 
                           st.session_state.current_week_start, st.session_state.selected_user)
        
        if not df.empty:
            # 格式化顯示
            display_df = df.copy()
            
            # 安全地格式化日期欄位
            if pd.api.types.is_datetime64_any_dtype(display_df['date']):
                display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
            else:
                display_df['date'] = display_df['date'].fillna('').astype(str)
                
            if pd.api.types.is_datetime64_any_dtype(display_df['deadline']):
                display_df['deadline'] = display_df['deadline'].dt.strftime('%Y-%m-%d')
            else:
                display_df['deadline'] = display_df['deadline'].fillna('').astype(str)
            
            # 安全地格式化數值欄位
            display_df['completion_rate'] = display_df['completion_rate'].fillna(0).astype(str) + '%'
            display_df['estimate'] = display_df['estimate'].fillna(0).apply(lambda x: f"{int(x):,}")
            display_df['revenue'] = display_df['revenue'].fillna(0).apply(lambda x: f"{int(x):,}")
            display_df['cost'] = display_df['cost'].fillna(0).apply(lambda x: f"{int(x):,}")
            display_df['gross_profit'] = (display_df['gross_profit'].fillna(0) * 100).apply(lambda x: f"{x:.2f}%")
            
            # 安全地處理新欄位
            display_df['usage_status'] = display_df['usage_status'].fillna('').astype(str)
            display_df['release_form'] = display_df['release_form'].fillna('').astype(str)
            display_df['factory'] = display_df['factory'].fillna('').astype(str)
            display_df['username'] = display_df['username'].fillna('').astype(str)
            
            # 安全地處理文字欄位
            display_df['item'] = display_df['item'].fillna('').astype(str)
            display_df['purpose'] = display_df['purpose'].fillna('').astype(str)
            display_df['problem'] = display_df['problem'].fillna('').astype(str)
            display_df['status'] = display_df['status'].fillna('').astype(str)
            display_df['solution'] = display_df['solution'].fillna('').astype(str)
            display_df['customer'] = display_df['customer'].fillna('').astype(str)
            
            # 處理階段欄位，將代碼轉換為顯示名稱
            if 'phase_code' in display_df.columns:
                display_df['phase_display'] = display_df['phase_code'].apply(
                    lambda x: get_phase_name_by_code(st.session_state.db_manager, x)
                )
            else:
                display_df['phase_display'] = ''
            
            # 移除 id 欄位，只顯示需要的欄位
            display_df = display_df.drop(columns=['id'])
            
            # 添加編號欄位（從1開始）
            display_df.insert(0, '編號', range(1, len(display_df) + 1))
            
            # 重新命名欄位
            display_df = display_df.rename(columns={
                'date': '日期',
                'usage_status': '使用狀況',
                'release_form': '放行單',
                'factory': '廠區',
                'username': 'User',
                'item': '工作項目',
                'purpose': '目的',
                'problem': '問題',
                'status': '狀態',
                'solution': '解決方案',
                'phase_display': '目前階段',
                'deadline': '截止日期',
                'completion_rate': '完成度',
                'estimate': '預估營收',
                'revenue': '營收',
                'cost': '成本',
                'gross_profit': '毛利率',
                'customer': '客戶'
            })
            
            # 重新排列欄位順序，根據使用者設定或預設順序
            # 只保留實際存在的欄位（避免錯誤）
            available_columns = [col for col in st.session_state.column_order if col in display_df.columns]
            
            if available_columns:
                display_df = display_df.reindex(columns=available_columns)
            else:
                # 如果沒有可用欄位，使用預設順序
                default_order = [
                    '編號', '日期', '放行單', '使用狀況', '客戶', '廠區', 'User', '工作項目', '目的', '問題', '狀態', '解決方案', '目前階段',
                    '完成度', '預估營收', '營收', '成本', '毛利率', '截止日期'
                ]
                available_columns = [col for col in default_order if col in display_df.columns]
                display_df = display_df.reindex(columns=available_columns)
            
            # 顯示表格
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # 互動功能
            st.subheader("互動功能")
            col1, col2 = st.columns(2)
            
            with col1:
                # 趨勢圖
                selected_item_trend = st.selectbox("選擇項目查看營收趨勢", df['item'].tolist(), key="trend_select")
                if selected_item_trend:
                    show_revenue_trend(st.session_state.db_manager, selected_item_trend)
            
            with col2:
                 # COA圖片
                 selected_item_coa = st.selectbox("選擇項目查看工作圖片", df['item'].tolist(), key="coa_select")
                 if selected_item_coa:
                     item_data = df[df['item'] == selected_item_coa].iloc[0]
                     # 使用 find_work_progress_id 函數來取得正確的 ID
                     date_str = item_data['date'].strftime('%Y-%m-%d') if hasattr(item_data['date'], 'strftime') else str(item_data['date'])
                     item_str = str(item_data['item'])
                     
                     if st.session_state.current_user['role'] == 'admin':
                         if st.session_state.selected_user:
                             user_id = get_user_id_by_name(st.session_state.db_manager, st.session_state.selected_user)
                         else:
                             user_id = None
                     else:
                         user_id = st.session_state.current_user['id']
                     
                     if user_id:
                         work_progress_id = find_work_progress_id(st.session_state.db_manager, user_id, date_str, item_str)
                         if work_progress_id:
                             show_coa_images(st.session_state.db_manager, work_progress_id, selected_item_coa)
                         else:
                             st.warning("無法找到對應的工作記錄ID")
                     else:
                         st.warning("無法取得使用者ID")
        else:
            st.info("目前沒有工作資料。")
    
    with tabs[1]:
        add_work_item(st.session_state.db_manager, st.session_state.current_user, 
                     st.session_state.current_week_start, st.session_state.selected_user)
    
    with tabs[2]:
        edit_work_item(st.session_state.db_manager, st.session_state.current_user, st.session_state.selected_user)
    
    with tabs[3]:
        delete_work_item(st.session_state.db_manager, st.session_state.current_user, st.session_state.selected_user)
    
    with tabs[4]:
        st.subheader("趨勢分析")
        
        # 載入所有資料進行分析
        all_data = load_work_data(st.session_state.db_manager, st.session_state.current_user, 
                                 st.session_state.current_week_start, st.session_state.selected_user)
        
        if not all_data.empty:
            # 完成度分析
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**完成度分析**")
                completion_fig = px.bar(all_data, x='item', y='completion_rate',
                                      title='各項目完成度')
                st.plotly_chart(completion_fig, use_container_width=True)
            
            with col2:
                st.write("**營收分析**")
                revenue_fig = px.bar(all_data, x='item', y='revenue',
                                   title='各項目營收')
                st.plotly_chart(revenue_fig, use_container_width=True)
            
            # 毛利率分析
            st.write("**毛利率分析**")
            gross_profit_fig = px.bar(all_data, x='item', y='gross_profit',
                                    title='各項目毛利率')
            st.plotly_chart(gross_profit_fig, use_container_width=True)
        else:
            st.info("沒有資料可以進行趨勢分析。")
    
    # 系統管理分頁（僅限 Admin）
    if st.session_state.current_user['role'] == 'admin':
        with tabs[-1]:  # 最後一個分頁是系統管理
            st.subheader("系統管理")
            
            # 資料庫清理功能
            st.write("**資料庫維護**")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("清理空的階段代碼", help="將所有空的階段代碼設定為預設階段 P1"):
                    clean_empty_phase_codes(st.session_state.db_manager)
            
            with col2:
                if st.button("檢查資料庫狀態", help="檢查資料庫連線和基本狀態"):
                    try:
                        # 檢查連線
                        if st.session_state.db_manager.connect():
                            st.success("✅ 資料庫連線正常")
                            
                            # 檢查空的階段代碼數量
                            count_query = """
                            SELECT COUNT(*) FROM work_progress 
                            WHERE phase_code IS NULL OR phase_code = ''
                            """
                            result = st.session_state.db_manager.execute_query(count_query)
                            if result:
                                empty_count = result[0][0]
                                if empty_count > 0:
                                    st.warning(f"⚠️ 發現 {empty_count} 筆資料的階段代碼為空")
                                else:
                                    st.success("✅ 所有資料都有階段代碼")
                        else:
                            st.error("❌ 資料庫連線失敗")
                    except Exception as e:
                        st.error(f"❌ 檢查資料庫狀態時發生錯誤：{e}")
            
            st.markdown("---")
            
            # 資料統計
            st.write("**資料統計**")
            try:
                # 總工作記錄數
                total_query = "SELECT COUNT(*) FROM work_progress"
                total_result = st.session_state.db_manager.execute_query(total_query)
                if total_result:
                    st.metric("總工作記錄數", f"{total_result[0][0]:,}")
                
                # 按階段統計
                phase_stats_query = """
                SELECT pl.name, COUNT(wp.id) as count
                FROM phase_list pl
                LEFT JOIN work_progress wp ON pl.code = wp.phase_code
                GROUP BY pl.code, pl.name
                ORDER BY pl.code
                """
                phase_result = st.session_state.db_manager.execute_query(phase_stats_query)
                if phase_result:
                    st.write("**各階段工作記錄統計**")
                    phase_df = pd.DataFrame(phase_result, columns=['階段名稱', '記錄數'])
                    st.dataframe(phase_df, use_container_width=True, hide_index=True)
                
            except Exception as e:
                st.error(f"載入資料統計時發生錯誤：{e}")

# 初始化 session state
init_session_state()

# 檢查登入狀態
if not st.session_state.logged_in:
    login_page()
else:
    main_dashboard()