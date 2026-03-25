import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression
import warnings
import io

warnings.filterwarnings('ignore')

st.set_page_config(page_title="现货价格智能预测与独立回测系统", layout="wide")

st.title("⚡ 现货价格智能预测与独立回测系统")
st.markdown("""
**系统说明**：
基于竞价空间形状相似度与动态幅度修正的现货电价预测模型。
支持两种模式：
1. **自动模式**：基础数据中目标日有价格则自动回测。
2. **独立回测模式**：上传独立实际电价文件，与预测结果进行深度对比分析。
""")
st.subheader(f"开发者：张欢欢 _  微信：shopify999  ")

# --- 侧边栏 ---
st.sidebar.header("⚙️ 操作指南")

# 1. 生成并下载模板功能 (保持不变)
def create_template():
    """生成标准的Excel模板"""
    dates = ['2026-01-23', '2026-01-24', '2026-01-25', '2026-01-26']
    times = []
    for i in range(96):
        if i == 95:
            times.append('24:00')
        else:
            h = (i + 1) // 4
            m = ((i + 1) % 4) * 15
            if m == 60:
                h += 1
                m = 0
            times.append(f"{h:02d}:{m:02d}")
    
    data = []
    for date in dates:
        for t in times:
            hour = int(t.split(':')[0])
            space = 500 + 300 * np.sin((hour - 6) * np.pi / 12) + np.random.randint(-50, 50)
            space = max(100, space)
            
            if date != '2026-01-26':
                price = 300 + 200 * np.sin((hour - 10) * np.pi / 12) + np.random.randint(-20, 20)
                price = max(50, price)
            else:
                price = None
            
            data.append({
                '日期': date,
                '时点': t,
                '竞价空间': round(space, 2),
                '现货出清电价': round(price, 2) if price is not None else ''
            })
    
    df_template = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_template.to_excel(writer, index=False, sheet_name='模板数据')
        df_info = pd.DataFrame({
            '字段名': ['日期', '时点', '竞价空间', '现货出清电价'],
            '必填': ['是', '是', '是', '否(预测日留空)'],
            '格式要求': ['YYYY-MM-DD', 'HH:MM 或 24:00', '数值 (MW)', '数值 (元/MWh)'],
            '说明': ['例如：2026-01-25', '每15分钟一个点，共96点', '必须大于0', '若无真实价格请留空']
        })
        df_info.to_excel(writer, index=False, sheet_name='填写说明')
        
    return output.getvalue()

template_data = create_template()
st.sidebar.download_button(
    label="📥 点击下载数据模板 (.xlsx)",
    data=template_data,
    file_name="现货预测_基础数据模板.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="包含示例数据和详细填写说明的Excel文件"
)

# 2. 数据格式说明 (保持不变)
with st.sidebar.expander("📖 数据格式要求说明", expanded=False):
    st.markdown("""
    **上传文件要求**：
    - **文件格式**：`.xlsx` (Excel)
    - **Sheet名称**：任意 (默认读取第一个Sheet)
    - **必需列名** (区分大小写)：
        1. `日期`: 格式如 `2026-01-25`
        2. `时点`: 格式如 `00:15`, `13:45`, `24:00` (每天必须有96个点)
        3. `竞价空间`: 数值型，单位 MW
        4. `现货出清电价`: 数值型，单位 元/MWh
    
    **预测逻辑说明**：
    - **历史数据**：日期对应的“现货出清电价”**必须有值**。
    - **待预测日期**：日期对应的“现货出清电价”**请留空** (或填NaN)。
    - 系统会自动识别有价格的日期作为“历史库”，无价格的日期作为“待预测目标”。
    """)

uploaded_file = st.sidebar.file_uploader("📂 上传您的基础数据.xlsx", type=["xlsx"])

# 🚀 新增：独立回测文件上传框
st.sidebar.subheader("🧪 独立回测工具 (可选)")

def generate_backtest_template():
    """生成标准的回测数据上传模板 (Excel)"""
    # 创建示例数据 (以2026-03-25为例，覆盖全天96个点)
    dates = ['2026-03-25'] * 96
    times = []
    
    # 生成 00:15 到 24:00 的96个时点
    for i in range(96):
        total_minutes = (i + 1) * 15
        h = total_minutes // 60
        m = total_minutes % 60
        if h == 24 and m == 0:
            time_str = "24:00"
        else:
            time_str = f"{h:02d}:{m:02d}"
        times.append(time_str)
    
    # 生成一些模拟的实际电价数据 (正弦波模拟早晚高峰)
    # 公式：基础价 + 高峰溢价 + 随机波动
    prices = []
    for i in range(96):
        hour = (i + 1) / 4.0
        if hour >= 24: hour = 23.75
        
        # 模拟双峰曲线 (中午和晚上)
        base_price = 350
        noon_peak = 100 * np.exp(-((hour - 12)**2) / 8)   # 中午峰
        night_peak = 150 * np.exp(-((hour - 19)**2) / 6)  # 晚上峰
        noise = np.random.randint(-20, 20)
        
        price = base_price + noon_peak + night_peak + noise
        prices.append(round(price, 2))
    
    # 创建 DataFrame
    df_template = pd.DataFrame({
        '日期': dates,
        '时点': times,
        '实际电价(元/MWh)': prices
    })
    
    # 转换为 Excel 二进制流
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_template.to_excel(writer, index=False, sheet_name='回测数据模板')
        
        # 自动调整列宽 (可选优化)
        worksheet = writer.sheets['回测数据模板']
        worksheet.column_dimensions['A'].width = 12
        worksheet.column_dimensions['B'].width = 10
        worksheet.column_dimensions['C'].width = 18
        
    output.seek(0)
    return output

# --- 在侧边栏显示下载按钮 ---

template_file = generate_backtest_template()

st.sidebar.download_button(
    label="📄 下载回测数据模板 (.xlsx)",
    data=template_file,
    file_name="回测数据上传模板_2026.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="点击下载标准Excel模板。只需填写'日期'、'时点'和'实际电价'三列，保存后上传即可进行回测。"
)



# 添加分割线，分隔下载和上传区域

# --- 接下来是您原有的上传代码 ---
# st.sidebar.subheader("🧪 第二步：上传数据")
# actual_file = st.sidebar.file_uploader(...) 

# 2. 数据格式说明 (保持不变)
with st.sidebar.expander("📖 数据格式要求说明", expanded=False):
    st.markdown("""
    **上传文件要求**：
    - **文件格式**：`.xlsx` (Excel)
    - **Sheet名称**：任意 (默认读取第一个Sheet)
    - **必需列名** (区分大小写)：
        1. `日期`: 格式如 `2026-01-25`
        2. `时点`: 格式如 `00:15`, `13:45`, `24:00` (每天必须有96个点)
        3. `实际电价`: 数值型，单位 元/MWh
    
    **数据回测说明**：
    - **历史数据**：日期对应的“现货出清电价”**必须有值**。
    - **待预测日期**：日期对应的“现货出清电价”**请留空** (或填NaN)。
    - 系统会自动识别有价格的日期作为“历史库”，无价格的日期作为“待预测目标”。
    """)


actual_file = st.sidebar.file_uploader(
    "上传实际电价文件 (用于深度回测)", 
    type=["xlsx"],
    help="格式需包含 '日期', '时点' 和 '价格' 列。系统将自动将其与当前预测结果对齐。"
)

alpha = st.sidebar.slider(
    "负荷敏感系数 (α)", 
    min_value=0.0, max_value=2.0, value=1.0, step=0.1,
    help="控制竞价空间变化对价格的影响程度。"
)

if uploaded_file:
    try:
        # --- 1. 数据读取与预处理 (保持原有逻辑不变) ---
        df_raw = pd.read_excel(uploaded_file)
        
        required_cols = ['日期', '时点', '竞价空间', '现货出清电价']
        missing_cols = [col for col in required_cols if col not in df_raw.columns]
        if missing_cols:
            st.error(f"❌ 错误：文件中缺少必需列：{missing_cols}。")
            st.stop()

        df_raw['日期'] = pd.to_datetime(df_raw['日期']).dt.date
        
        def parse_time_to_index(time_str):
            if pd.isna(time_str): return None
            time_str = str(time_str).strip()
            if time_str == '24:00': return 95
            try:
                t = pd.to_datetime(time_str, format='%H:%M')
                idx = int((t.hour * 60 + t.minute) / 15) - 1
                return max(0, min(95, idx))
            except: return None

        df_raw['idx'] = df_raw['时点'].apply(parse_time_to_index)
        df_raw = df_raw.dropna(subset=['idx'])
        df_raw = df_raw.sort_values(['日期', 'idx'])

        # 数据透视
        space_pivot = df_raw.pivot_table(index='日期', columns='idx', values='竞价空间', aggfunc='first')
        price_pivot = df_raw.pivot_table(index='日期', columns='idx', values='现货出清电价', aggfunc='first')

        required_cols_idx = list(range(96))
        space_pivot = space_pivot.reindex(columns=required_cols_idx)
        price_pivot = price_pivot.reindex(columns=required_cols_idx)

        # --- 2. 智能日期分类 (保持原有逻辑不变) ---
        all_dates = sorted(list(space_pivot.index))
        
        if not all_dates:
            st.error("未找到任何日期数据。")
            st.stop()

        valid_history_mask = (space_pivot.notna().all(axis=1) & price_pivot.notna().all(axis=1))
        history_dates = [d for d in all_dates if valid_history_mask.loc[d]]

        valid_target_mask = space_pivot.notna().all(axis=1)
        target_candidates = [d for d in all_dates if valid_target_mask.loc[d]]

        st.sidebar.success(f"✅ 数据解析成功！\n- 历史样本：{len(history_dates)} 天\n- 可预测日期：{len(target_candidates)} 天")

        if len(history_dates) < 3:
            st.error(f"❌ 错误：有效历史样本不足 3 天。")
            st.stop()

        # --- 3. 用户选择目标日 (保持原有逻辑不变) ---
        default_idx = len(target_candidates) - 1
        target_date = st.sidebar.selectbox(
            "选择要预测/回测的日期",
            options=target_candidates,
            index=default_idx,
            format_func=lambda x: x.strftime("%Y-%m-%d")
        )

        # --- 4. 准备数据矩阵 (保持原有逻辑不变) ---
        target_space_series = space_pivot.loc[target_date]
        target_space_vec = target_space_series.values.reshape(1, -1)
        
        has_price_target = target_date in price_pivot.index and price_pivot.loc[target_date].notna().all()
        
        current_hist_dates = [d for d in history_dates if d != target_date]
        
        if len(current_hist_dates) < 3:
            st.error(f"❌ 错误：排除目标日后，剩余有效历史样本不足 3 天。")
            st.stop()

        hist_space_mat = space_pivot.loc[current_hist_dates].values
        hist_price_mat = price_pivot.loc[current_hist_dates].values

        mode_text = '✅ 自动回测模式 (基础数据含真实价)' if has_price_target else '🔮 未来预测模式'
        if actual_file:
            mode_text += " + 🧪 独立回测增强"
            
        st.info(f"当前模式：**{mode_text}** | 参与计算的历史天数：{len(current_hist_dates)}")

        # --- 5. 核心算法：相似度计算 (保持原有逻辑不变) ---
        st.header("📊 第一步：形状提取 (相似日匹配)")
        
        tgt_norm = np.linalg.norm(target_space_vec)
        if tgt_norm == 0:
            st.error("目标日竞价空间向量为零。")
            st.stop()
            
        hist_norms = np.linalg.norm(hist_space_mat, axis=1)
        hist_norms[hist_norms==0] = 1e-9
        
        dots = np.dot(hist_space_mat, target_space_vec.T).flatten()
        similarities = dots / (hist_norms * tgt_norm)
        
        k = min(5, len(current_hist_dates))
        top_k_idx = np.argsort(similarities)[::-1][:k]
        top_k_dates = [current_hist_dates[i] for i in top_k_idx]
        top_k_sims = similarities[top_k_idx]
        top_k_spaces = hist_space_mat[top_k_idx]
        top_k_prices = hist_price_mat[top_k_idx]

        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader(f"Top {k} 相似日")
            sim_df = pd.DataFrame({
                "日期": [d.strftime("%Y-%m-%d") for d in top_k_dates],
                "相似度": np.round(top_k_sims, 4)
            })
            st.dataframe(sim_df, use_container_width=True)
        
        # --- 6. 基准曲线与趋势分析 (保持原有逻辑不变) ---
        st.header("📈 第二步：趋势分析与基准构建")
        
        weights = top_k_sims / np.sum(top_k_sims)
        p_base = np.sum(top_k_prices * weights.reshape(-1, 1), axis=0)
        s_base = np.sum(top_k_spaces * weights.reshape(-1, 1), axis=0)
        
        x_axis = np.arange(96).reshape(-1, 1)
        lr_model = LinearRegression()
        lr_model.fit(x_axis, p_base)
        trend_slope = lr_model.coef_[0]
        
        trend_status = "平稳"
        if trend_slope > 0.5: trend_status = "↗️ 全天走高"
        elif trend_slope < -0.5: trend_status = "↘️ 全天走低"
        
        col_t1, col_t2, col_t3 = st.columns(3)
        col_t1.metric("基础均价", f"{np.mean(p_base):.2f}")
        col_t2.metric("趋势斜率", f"{trend_slope:.4f}", delta=trend_status)
        col_t3.metric("峰值时段", f"{np.argmax(p_base)//4}:00")

        # --- 7. 动态幅度修正 (保持原有逻辑不变) ---
        st.header("🚀 第三步：动态幅度修正")
        
        s_target = target_space_vec.flatten()
        epsilon = 10.0 
        safe_s_base = np.where(s_base < epsilon, epsilon, s_base)
        
        space_diff_ratio = (s_target - s_base) / safe_s_base
        space_diff_ratio = np.clip(space_diff_ratio, -2.0, 2.0)
        
        correction_factor = 1 + (alpha * space_diff_ratio)
        correction_factor = np.maximum(correction_factor, 0.1)
        
        p_final = p_base * correction_factor
        
        st.markdown(f"**修正系数 α**: {alpha} | **最大修正幅度**: {np.max(np.abs(correction_factor - 1))*100:.1f}%")

        # --- 8. 可视化 (保持原有逻辑，增加独立回测数据的叠加) ---
        fig = go.Figure()
        
        for i, date in enumerate(top_k_dates):
            fig.add_trace(go.Scatter(
                y=top_k_prices[i],
                mode='lines',
                name=f'相似日：{date.strftime("%m-%d")}',
                line=dict(color='lightgray', width=1, dash='dot'),
                opacity=0.4, showlegend=False
            ))
        
        fig.add_trace(go.Scatter(
            y=p_base,
            mode='lines',
            name='🔵 基础形状 (加权平均)',
            line=dict(color='blue', width=2, dash='dash'),
            opacity=0.7
        ))
        
        fig.add_trace(go.Scatter(
            y=p_final,
            mode='lines',
            name='🔴 最终预测 (修正后)',
            line=dict(color='red', width=3)
        ))
        
        # 原始自动回测数据 (来自基础文件)
        true_price_auto = None
        if has_price_target:
            true_price_auto = price_pivot.loc[target_date].values
            fig.add_trace(go.Scatter(
                y=true_price_auto,
                mode='lines',
                name='🟢 真实价格 (基础文件)',
                line=dict(color='green', width=2, dash='dot'),
                opacity=0.6
            ))
        
        # 🚀 新增：处理独立回测文件
        true_price_independent = None
        backtest_metrics = {}
        
        if actual_file:
            try:
                df_act = pd.read_excel(actual_file)
                # 模糊匹配列名
                c_date = c_time = c_price = None
                for col in df_act.columns:
                    cl = str(col).lower()
                    if '日期' in cl or 'date' in cl: c_date = col
                    if '时点' in cl or '时间' in cl: c_time = col
                    if '价格' in cl or '出清' in cl or 'price' in cl: c_price = col
                
                if c_date and c_time and c_price:
                    df_act['日期'] = pd.to_datetime(df_act[c_date]).dt.date
                    df_act['idx'] = df_act[c_time].apply(parse_time_to_index)
                    df_act = df_act.dropna(subset=['idx'])
                    
                    # 筛选目标日
                    df_target = df_act[df_act['日期'] == target_date].sort_values('idx')
                    if len(df_target) > 10:
                        actual_series = df_target.set_index('idx')[c_price].reindex(range(96))
                        true_price_independent = actual_series.values
                        
                        fig.add_trace(go.Scatter(
                            y=true_price_independent,
                            mode='lines',
                            name='🟣 真实价格 (独立文件)',
                            line=dict(color='purple', width=3, dash='dot'),
                            opacity=0.9
                        ))
                        st.success("✅ 独立回测数据已加载并叠加到图表中 (紫色线)。")
                    else:
                        st.warning(f"独立文件中未找到 {target_date} 的足够数据。")
                else:
                    st.warning("无法识别独立文件中的列名，请确保包含'日期','时点','价格'。")
            except Exception as e:
                st.error(f"读取独立回测文件失败：{e}")

        fig.add_trace(go.Scatter(
            y=s_target,
            mode='lines',
            name='⚡ 目标日竞价空间',
            line=dict(color='orange', width=2, dash='dot'),
            yaxis='y2',
            opacity=0.6
        ))

        fig.update_layout(
            title=f"{target_date.strftime('%Y-%m-%d')} 现货价格预测与回测对比",
            xaxis=dict(title="时点 (0-95)", range=[0, 95]),
            yaxis=dict(
                title=dict(text="电价 (元/MWh)", font=dict(color="red")),
                tickfont=dict(color="red"),
                side='left'
            ),
            yaxis2=dict(
                title=dict(text="竞价空间 (MW)", font=dict(color="orange")),
                tickfont=dict(color="orange"),
                overlaying='y',
                side='right',
                showgrid=False
            ),
            hovermode="x unified",
            template="plotly_white",
            height=600,
            legend=dict(orientation="h", y=1.05)
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # ==========================================
        # 🚀 新增：独立回测详细分析模块
        # ==========================================
        # 优先使用独立文件的数据进行详细分析，如果没有则使用基础文件中的数据
        active_true_price = true_price_independent if true_price_independent is not None else true_price_auto
        
        if active_true_price is not None:
            st.divider()
            st.header("📊 详细回测分析报告")
            
            valid_mask = ~np.isnan(active_true_price)
            if np.sum(valid_mask) < 10:
                st.warning("有效数据点过少，无法计算详细指标。")
            else:
                pred_valid = p_final[valid_mask]
                actual_valid = active_true_price[valid_mask]
                
                # 计算误差
                abs_err = pred_valid - actual_valid
                abs_err_val = np.abs(abs_err)
                rel_err_val = abs_err_val / (np.abs(actual_valid) + 1e-9) * 100
                err_sq = abs_err ** 2
                
                # 核心指标
                mae = np.mean(abs_err_val)
                rmse = np.sqrt(np.mean(err_sq))
                mape = np.mean(rel_err_val)
                avg_actual = np.mean(actual_valid)
                
                # 平方和指标 (严格按照用户公式)
                sst = np.sum((actual_valid - avg_actual) ** 2)  # 实际电价总平方和 (SST)
                sse = np.sum(err_sq)                            # 残差平方和 (SSE)
                r_squared = 1 - (sse / sst) if sst > 0 else 0.0 # R²
                
                # 展示指标卡片
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("MAE (平均绝对误差)", f"{mae:.2f}")
                c2.metric("RMSE (均方根误差)", f"{rmse:.2f}")
                c3.metric("MAPE (平均绝对百分比误差)", f"{mape:.2f}%")
                c4.metric("R² (决定系数)", f"{r_squared:.4f}")
                
                c5, c6, c7 = st.columns(3)
                c5.metric("实际电价平均值", f"{avg_actual:.2f}")
                c6.metric("实际电价总平方和 (SST)", f"{sst:.2f}", help="SUMPRODUCT((实际值 - 平均值)^2)")
                c7.metric("残差平方和 (SSE)", f"{sse:.2f}", help="SUM((预测值 - 实际值)^2)")
                
                st.success(f"**模型评价**: R² = {r_squared:.4f}. " + 
                          ("拟合效果优秀!" if r_squared > 0.8 else "拟合效果良好." if r_squared > 0.5 else "拟合效果一般."))
                
                # 构建详细报表 DataFrame (模仿用户提供的格式)
                time_labels = []
                for i in range(96):
                    if i == 95: time_labels.append("24:00")
                    else:
                        h = (i + 1) // 4
                        m = ((i + 1) % 4) * 15
                        if m == 60: h += 1; m = 0
                        time_labels.append(f"{h:02d}:{m:02d}")
                
                # 初始化全量数据
                full_abs_err = np.full(96, np.nan)
                full_rel_err = np.full(96, np.nan)
                full_err_sq = np.full(96, np.nan)
                
                full_abs_err[valid_mask] = abs_err
                full_rel_err[valid_mask] = rel_err_val
                full_err_sq[valid_mask] = err_sq
                
                report_df = pd.DataFrame({
                    "时间点": time_labels,
                    "预测电价": np.round(p_final, 8),
                    "实际电价": np.round(active_true_price, 8),
                    "绝对误差": np.where(np.isnan(full_abs_err), "", np.round(full_abs_err, 8)),
                    "相对误差": np.where(np.isnan(full_rel_err), "", np.round(full_rel_err, 8)),
                    "误差平方": np.where(np.isnan(full_err_sq), "", np.round(full_err_sq, 8))
                })
                
                st.subheader("📋 逐时点误差明细表")
                st.dataframe(report_df, use_container_width=True, hide_index=True)
                
                # 导出按钮
                csv_buf = io.StringIO()
                report_df.to_csv(csv_buf, index=False)
                st.download_button(
                    label="📥 下载回测详细报表 (CSV)",
                    data=csv_buf.getvalue(),
                    file_name=f"backtest_detailed_{target_date.strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

        # --- 9. 结果导出 (保持原有逻辑，增加兼容性) ---
        st.header("📥 结果导出：目标日完整数据")
        
        time_labels = []
        for i in range(96):
            if i == 95:
                time_labels.append("24:00")
            else:
                h = (i + 1) // 4
                m = ((i + 1) % 4) * 15
                if m == 60:
                    h += 1
                    m = 0
                time_labels.append(f"{h:02d}:{m:02d}")
        
        export_data = {
            "时点索引": range(96),
            "时间": time_labels,
            "基础预测价格": np.round(p_base, 2),
            "修正后预测价格": np.round(p_final, 2),
            "目标日竞价空间": np.round(s_target, 2),
            "历史平均空间": np.round(s_base, 2),
            "空间偏差比率(%)": np.round(space_diff_ratio * 100, 1),
            "修正系数": np.round(correction_factor, 3)
        }
        
        # 如果有真实价格 (无论是来自基础文件还是独立文件)，都加入导出
        if active_true_price is not None:
            export_data["真实价格"] = np.round(active_true_price, 2)
            export_data["预测误差"] = np.round(p_final - active_true_price, 2)
        
        export_df = pd.DataFrame(export_data)
        
        st.dataframe(export_df, use_container_width=True, height=600, hide_index=True)
        
        csv_content = export_df.to_csv(index=False).encode('utf-8')
        file_suffix = "backtest" if active_true_price is not None else "forecast"
        st.download_button(
            label=f"📥 下载完整{'回测' if active_true_price is not None else '预测'}数据 (CSV)",
            data=csv_content,
            file_name=f"result_{file_suffix}_{target_date.strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"💥 发生错误：{e}")
        st.markdown("**建议**：请检查上传的文件格式及列名。")
        import traceback
        with st.expander("查看详细错误日志"):
            st.code(traceback.format_exc())
else:
    st.info("👈 请在左侧侧边栏上传 **基础数据.xlsx** 文件开始预测。")
# ==============================================================================
# 📚 底部帮助文档：回测功能说明与指标解读
# ==============================================================================
st.divider()
st.header("📖 回测功能说明与指标解读指南")

with st.expander("📊 点击查看：回测逻辑、指标含义及策略优化建议", expanded=False):
    st.markdown("""
    ### 1. 回测功能概述 (Backtesting Overview)
    本系统的回测模块旨在通过对比**“模型预测电价”**与**“实际出清电价”**，量化评估预测算法的准确性与稳定性。系统支持两种数据接入模式：
    *   **自动回测模式**：当基础数据文件中目标日期已包含真实电价时，系统自动触发比对。
    *   **独立文件回测模式**：用户可上传独立的实际电价报表（如 `REPORT0.xlsx`），系统会自动根据“日期”和“时点”将真实数据与当前的预测结果进行精准对齐。

    回测不仅生成直观的**双曲线对比图**（预测 vs 实际），还输出详细的**逐时点误差报表**及**核心统计指标**，帮助交易者识别模型在尖峰时刻（Peak Hours）和低谷时刻的捕捉能力。

    ---

    ### 2. 核心评价指标解读 (Key Metrics)

    | 指标名称 | 英文缩写 | **参考意义与业务价值** |
    | :--- | :---: | :--- |
    | **平均绝对误差** | **MAE** | **【直观偏差】**<br>反映预测值与实际值的平均偏离程度（单位：元/MWh）。<br>✅ **数值越小越好**。例如 MAE=20，意味着平均每个时点预测偏差约 20 元。它对异常值不敏感，最能代表日常预测水平。 |
    | **均方根误差** | **RMSE** | **【风险敏感度】**<br>对**大误差**（如尖峰时刻预测失误）给予更高惩罚。<br>✅ **若 RMSE 远大于 MAE**，说明模型在大部分时间准确，但在个别时刻（如突发高价）出现了严重偏差，需重点排查极端行情。 |
    | **平均绝对百分比误差** | **MAPE** | **【相对精度】**<br>消除量纲影响，反映误差占实际电价的比例。<br>✅ **参考标准**：<br>- < 10%：极高精度<br>- 10%~20%：良好，可用于指导交易<br>- > 30%：精度较低，需谨慎参考 |
    | **决定系数** | **$R^2$** | **【拟合优度】**<br>衡量模型解释电价波动的能力（0~1之间）。<br>✅ **参考标准**：<br>- 接近 1：模型完美捕捉了电价走势形状。<br>- > 0.8：优秀。<br>- < 0.5：模型未能有效捕捉市场变化规律。 |

    ---

    ### 3. 统计学深度参数 (Statistical Parameters)

    *   **实际电价平均值 (Mean Actual Price)**
        *   **含义**：目标日 96 个时点实际电价的算术平均数。
        *   **作用**：作为基准线，用于判断预测值是系统性偏高还是偏低。

    *   **实际电价总平方和 (SST, Total Sum of Squares)**
        *   **公式**：$\sum (实际电价_i - 实际平均值)^2$
        *   **含义**：反映了实际电价数据的**波动总量**（即市场本身的活跃程度）。
        *   **作用**：如果 SST 很小，说明当天电价平稳；如果 SST 很大，说明当天行情波动剧烈（如出现尖峰），对模型挑战大。

    *   **残差平方和 (SSE, Residual Sum of Squares)**
        *   **公式**：$\sum (实际电价_i - 预测电价_i)^2$
        *   **含义**：模型预测后**剩余的、未被解释的误差总量**。
        *   **作用**：这是我们要最小化的目标。SSE 越接近 0，说明预测曲线与实际曲线重合度越高。

    ---

    ### 4. 报表字段说明 (Report Columns)
    下载的详细回测报表（CSV/Excel）包含以下关键字段：
    1.  **时间点**：00:15 至 24:00 共 96 个时点。
    2.  **预测电价**：模型计算出的建议价格。
    3.  **实际电价**：市场真实的出清价格。
    4.  **绝对误差**：$预测 - 实际$。
        *   *正数* 表示预测偏高（可能导致少中标）；*负数* 表示预测偏低（可能导致高价中标亏损）。
    5.  **相对误差 (%)**：误差占实际价格的百分比，用于识别低价时段的相对偏差。
    6.  **误差平方**：用于定位造成 RMSE 升高的“罪魁祸首”时点。

    ---

    ### 5. 💡 策略优化建议
    *   **关注尖峰时刻**：检查图表中晚高峰（17:00-21:00）的曲线重合度。如果此时 **RMSE** 显著高于 **MAE**，建议调整侧边栏的**负荷敏感系数 ($\\alpha$)** 以增强响应。
    *   **观察 $R^2$ 趋势**：如果连续多日的 $R^2$ 低于 0.6，说明市场逻辑可能发生了变化，当前的历史相似日匹配逻辑可能需要更新样本库。
    *   **偏差方向分析**：如果“绝对误差”长期为正，说明模型系统性高估电价，可适当调低修正系数；反之则调高。
    """)
    
    st.caption("注：以上指标计算公式严格遵循统计学标准，旨在为电力现货交易提供量化决策支持。")