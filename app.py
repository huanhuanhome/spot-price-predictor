import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import Pipeline
from sklearn.metrics import r2_score
import warnings
import io
import pwlf  # 需要先安装: pip install pwlf

warnings.filterwarnings('ignore')

# ========== 新增：异常值处理函数 ==========
def remove_outliers_by_timepoint(df, columns, factor=2.5, fill_method='median'):
    """
    对DataFrame的每一列（每个时点）进行异常值检测和修正。
    df: index=日期, columns=时点索引(0-95)
    columns: 要处理的列范围（通常为 list(range(96))）
    factor: IQR倍数，默认2.5
    fill_method: 'median' 或 'neighbor'（此处先用中位数）
    返回修正后的df, 修正统计字典
    """
    df_fixed = df.copy()
    stats = {'total_outliers': 0, 'points_fixed': 0}
    for col in columns:
        series = df[col]
        valid_mask = series.notna()
        if valid_mask.sum() == 0:
            continue
        values = series[valid_mask].values
        q1, q3 = np.percentile(values, [25, 75])
        iqr = q3 - q1
        lower = q1 - factor * iqr
        upper = q3 + factor * iqr
        outlier_mask = (values < lower) | (values > upper)
        if outlier_mask.sum() > 0:
            stats['total_outliers'] += outlier_mask.sum()
            fill_val = series.median() if fill_method == 'median' else series.mean()
            outlier_idx = series[valid_mask].index[outlier_mask]
            df_fixed.loc[outlier_idx, col] = fill_val
            stats['points_fixed'] += len(outlier_idx)
    return df_fixed, stats
# ========================================

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
    **数据对齐**：系统会根据 `日期` + `时点` 作为唯一键，将上传的“实际电价”与当前模型生成的“预测电价”进行精准匹配。
- **完整性检查**：
    - ✅ **有效回测**：目标日期的 96 个时点必须**全部有值**。若存在缺失值 (NaN) 或空行，该日期将被跳过或导致回测失败。
    - ❌ **非预测模式**：此功能专用于**事后验证**。请勿上传“待预测”的空值表格（那是用于“基础数据上传”的功能）。
- **误差计算**：
    - 系统仅对**两者均存在数据**的时点计算误差。
    - 若发现某时点实际电价为异常值（如负电价或极大值），建议在上传前清洗数据，以免拉高 **RMSE** 指标影响评估结果。
    """)


actual_file = st.sidebar.file_uploader(
    "上传实际电价文件 (用于深度回测)",
    type=["xlsx"],
    help="格式需包含 '日期', '时点' 和 '价格' 列。系统将自动将其与当前预测结果对齐。"
)

# ---------- 新增：异常值处理选项 ----------
st.sidebar.subheader("🔧 数据清洗选项")
enable_outlier_removal = st.sidebar.checkbox("启用异常值自动修正 (IQR方法)", value=True)
outlier_factor = st.sidebar.slider(
    "异常检测严格度 (IQR倍数)", 
    min_value=1.5, max_value=4.0, value=2.5, step=0.1,
    help="数值越小越敏感（剔除更多点），越大越宽松。默认2.5适用于大多数电力数据。"
)
# ----------------------------------------

alpha = st.sidebar.slider(
    "负荷敏感系数 (α)",
    min_value=0.0, max_value=2.0, value=0.0, step=0.1,
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

        # ========== 新增：异常值处理（根据用户选择） ==========
        if enable_outlier_removal:
            with st.spinner("正在检测并修正历史数据中的异常值..."):
                # 处理竞价空间
                space_pivot, space_stats = remove_outliers_by_timepoint(space_pivot, required_cols_idx, factor=outlier_factor)
                # 处理电价（仅对历史数据非空值进行修正）
                price_pivot, price_stats = remove_outliers_by_timepoint(price_pivot, required_cols_idx, factor=outlier_factor)
                
                total_fixed = space_stats['points_fixed'] + price_stats['points_fixed']
                if total_fixed > 0:
                    st.sidebar.success(f"✅ 异常值修正完成：共修正 {total_fixed} 个数据点（竞价空间 {space_stats['points_fixed']}，电价 {price_stats['points_fixed']}）")
                else:
                    st.sidebar.info("未检测到明显异常值")
        # ===================================================

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

        # 插入电价水平相似性计算

        # ========== 新增：电价水平相似性修正 ==========
        # 计算每个历史日的平均电价
        hist_avg_prices = np.mean(hist_price_mat, axis=1)

        # 估算目标日的平均电价：用竞价空间与历史电价的关系做快速线性回归
        from sklearn.linear_model import LinearRegression
        _temp_reg = LinearRegression()
        # 将所有历史数据摊平（n_dates*96, 1）
        _flat_space = hist_space_mat.reshape(-1, 1)
        _flat_price = hist_price_mat.reshape(-1, 1)
        _temp_reg.fit(_flat_space, _flat_price)
        _target_avg_price_est = _temp_reg.predict([[np.mean(target_space_vec)]])[0][0]

        # 计算电价水平相似度（高斯核，带宽=50元，可根据数据范围调整）
        level_similarities = np.exp(-((hist_avg_prices - _target_avg_price_est)**2) / (2 * 50**2))

        # 最终相似度 = 形状相似度 × 水平相似度
        similarities = similarities * level_similarities

        # 可选：将相似度归一化到[0,1]区间（仅用于展示，不影响加权排序）
        similarities = similarities / (similarities.max() + 1e-9)
        # =============================================

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

        # --- 6. 竞价空间-电价散点图与拐点检测 ---
        st.header("📈 第二步：竞价空间-电价关系分析与拐点检测")

        # 收集所有相似日的竞价空间和电价数据
        all_spaces = []
        all_prices = []
        for i, date in enumerate(top_k_dates):
            spaces = hist_space_mat[i]
            prices = hist_price_mat[i]
            all_spaces.extend(spaces)
            all_prices.extend(prices)

        # 创建DataFrame用于可视化
        scatter_df = pd.DataFrame({
            '竞价空间': all_spaces,
            '电价': all_prices
        })

        # 绘制散点图
        fig_scatter = px.scatter(scatter_df, x='竞价空间', y='电价',
                                title='竞价空间 vs 电价 散点图',
                                labels={'竞价空间': '竞价空间 (MW)', '电价': '电价 (元/MWh)'},
                                opacity=0.6)

        # 使用Piecewise Linear Fit寻找4段的拐点
        try:
            # 创建PWLF对象
            pwlf_model = pwlf.PiecewiseLinFit(np.array(all_spaces), np.array(all_prices))
            
            # 拟合4段（需要3个拐点）
            breaks = pwlf_model.fit(4)
            
            # 生成预测值用于绘图
            x_sorted = np.sort(all_spaces)
            y_pred = pwlf_model.predict(x_sorted)
            
            # 添加分段线到散点图
            fig_scatter.add_trace(go.Scatter(
                x=x_sorted,
                y=y_pred,
                mode='lines',
                name='分段线性拟合',
                line=dict(color='red', width=2)
            ))
            
            # 添加拐点到散点图
            break_points_x = breaks[1:-1]
            break_points_y = pwlf_model.predict(break_points_x)
            
            fig_scatter.add_trace(go.Scatter(
                x=break_points_x,
                y=break_points_y,
                mode='markers',
                name='拐点',
                marker=dict(color='yellow', size=10, symbol='x', line=dict(color='black', width=2))
            ))
            
            st.success(f"✅ 成功找到3个拐点，将数据分为4段")
            st.write(f"拐点位置: {[round(x, 2) for x in break_points_x]} MW")
            
            # 准备存储每个区间的回归模型
            segments = []
            for i in range(len(breaks)-1):
                # 历史数据落在当前区间的掩码
                if i == len(breaks)-2:  # 最后一段包含右边界
                    mask = (np.array(all_spaces) >= breaks[i]) & (np.array(all_spaces) <= breaks[i+1])
                else:
                    mask = (np.array(all_spaces) >= breaks[i]) & (np.array(all_spaces) < breaks[i+1])
                
                seg_spaces = np.array(all_spaces)[mask]
                seg_prices = np.array(all_prices)[mask]
                
                if len(seg_spaces) > 0:
                    # 对每段进行线性回归
                    if len(seg_spaces) > 1:
                        reg = LinearRegression()
                        reg.fit(seg_spaces.reshape(-1, 1), seg_prices)
                    else:
                        reg = None
                    
                    segments.append({
                        'segment_id': i+1,
                        'range': (breaks[i], breaks[i+1]),
                        'regressor': reg,
                        'spaces': seg_spaces,
                        'prices': seg_prices
                    })
            
            # 显示各段统计信息
            st.subheader("📊 各段数据分析")
            seg_info_df = pd.DataFrame([
                {
                    '段ID': seg['segment_id'],
                    '范围(MW)': f"[{seg['range'][0]:.2f}, {seg['range'][1]:.2f}]",
                    '数据点数': len(seg['spaces']),
                    '回归模型': 'Yes' if seg['regressor'] is not None else 'No'
                } for seg in segments
            ])
            st.dataframe(seg_info_df, use_container_width=True)
            
        except Exception as e:
            st.warning(f"分段线性拟合失败: {e}")
            st.info("使用简单的散点图进行分析")

        st.plotly_chart(fig_scatter, use_container_width=True)

        # # --- 7. 基于分段回归的最终预测 ---
        # st.header("🚀 第三步：基于分段回归的最终预测")

        # # 为每个时点进行预测
        # final_predictions = np.full(96, np.nan)
        # target_space_arr = target_space_vec[0]  # 长度96

        # for i, space_val in enumerate(target_space_arr):
        #     # 确定当前竞价空间属于哪个段
        #     for seg in segments:
        #         low, high = seg['range']
        #         if low <= space_val <= high:
        #             if seg['regressor'] is not None:
        #                 pred_val = seg['regressor'].predict([[space_val]])[0]
        #                 final_predictions[i] = pred_val
        #             else:
        #                 # 如果该段只有一个点，直接用它的价格作为预测
        #                 final_predictions[i] = seg['prices'][0]
        #             break  # 找到对应段后跳出循环

        # # 如果有未预测的点（理论上不会发生），使用全局平均
        # if np.isnan(final_predictions).any():
        #     global_avg_price = np.mean(all_prices)
        #     final_predictions = np.where(np.isnan(final_predictions), global_avg_price, final_predictions)

        # # 应用动态幅度修正
        # s_target = target_space_vec.flatten()


        # --- 7. 基于每个时点独立加权回归的最终预测 ---
        st.header("🚀 第三步：加权预测 (每个时点独立建模)")

        # 准备历史数据矩阵（已是按日期行、时点列）
        # hist_space_mat: (n_dates, 96)
        # hist_price_mat: (n_dates, 96)
        # similarities: (n_dates, ) 每个历史日的相似度（已按与目标日竞价空间形状计算）

        # 归一化相似度作为权重（确保非负）
        weights = similarities.copy()
        weights = np.maximum(weights, 0)  # 余弦相似度可能为负，取max(0, sim)
        if weights.sum() == 0:
            weights = np.ones(len(weights)) / len(weights)
        else:
            weights = weights / weights.sum()   # 和为1

        # 对每个时点独立进行加权线性回归
        pred_by_timepoint = np.full(96, np.nan)
        target_space_arr = target_space_vec[0]  # 长度96

        for t in range(96):
            # 提取历史第t时点的竞价空间和电价
            X_t = hist_space_mat[:, t].reshape(-1, 1)   # (n_dates,1)
            y_t = hist_price_mat[:, t]                  # (n_dates,)
            
            # 去除NaN值（某些历史日该时点可能缺失）
            valid_mask = ~np.isnan(y_t) & ~np.isnan(X_t.flatten())
            if valid_mask.sum() < 2:
                # 数据不足，使用该时点的历史中位数替代
                pred_by_timepoint[t] = np.nanmedian(hist_price_mat[:, t])
                continue
            
            X_t_valid = X_t[valid_mask]
            y_t_valid = y_t[valid_mask]
            w_t_valid = weights[valid_mask]
            
            # 加权线性回归 (权重为相似度)
            reg = LinearRegression()
            reg.fit(X_t_valid, y_t_valid, sample_weight=w_t_valid)
            
            # 预测目标日该时点
            pred_val = reg.predict([[target_space_arr[t]]])[0]
            pred_by_timepoint[t] = pred_val

        # 对可能出现的NaN（全历史缺失）用全局平均插补
        if np.isnan(pred_by_timepoint).any():
            global_avg = np.nanmedian(hist_price_mat)
            pred_by_timepoint = np.where(np.isnan(pred_by_timepoint), global_avg, pred_by_timepoint)

        # 应用动态幅度修正 (与原来逻辑相同)
        s_target = target_space_vec.flatten()
        epsilon = 10.0
        global_avg_space = np.mean(hist_space_mat)  # 所有历史日所有时点的平均竞价空间
        global_avg_price = np.mean(hist_price_mat)  # 所有历史日所有时点的平均电价

        safe_s_base = np.where(global_avg_space < epsilon, epsilon, global_avg_space)
        space_diff_ratio = (s_target - global_avg_space) / safe_s_base
        space_diff_ratio = np.clip(space_diff_ratio, -2.0, 2.0)

        correction_factor = 1 + (alpha * space_diff_ratio)
        correction_factor = np.maximum(correction_factor, 0.1)

        p_final = pred_by_timepoint * correction_factor

        st.markdown(f"**修正系数 α**: {alpha} | **最大修正幅度**: {np.max(np.abs(correction_factor - 1))*100:.1f}%")
        st.info(f"💡 预测方法：每个时点独立预测(权重来自竞价空间形状相似度)，共 {len(weights)} 个历史日参与建模。")

        final_predictions = pred_by_timepoint   # 兼容原有导出代码

        # 7结束

        epsilon = 10.0
        # 使用全局历史平均作为基准
        global_avg_space = np.mean(all_spaces)
        global_avg_price = np.mean(all_prices)
        
        safe_s_base = np.where(global_avg_space < epsilon, epsilon, global_avg_space)
        space_diff_ratio = (s_target - global_avg_space) / safe_s_base
        space_diff_ratio = np.clip(space_diff_ratio, -2.0, 2.0)
        
        correction_factor = 1 + (alpha * space_diff_ratio)
        correction_factor = np.maximum(correction_factor, 0.1)
        
        # 将修正应用于分段回归结果
        p_final = final_predictions * correction_factor
        
        st.markdown(f"**修正系数 α**: {alpha} | **最大修正幅度**: {np.max(np.abs(correction_factor - 1))*100:.1f}%")

        # ========== 自动偏置修正（留一法系统性误差评估） ==========
        # 原理：对每个历史日，用其余历史日做加权回归预测，计算平均预测误差，作为系统偏差补偿到当前预测。
        try:
            n_hist = len(hist_price_mat)
            if n_hist >= 5:   # 至少需要5个历史日才能稳健评估
                errors = []
                # 为避免计算过慢，最多取最近30个历史日（或全部）
                eval_indices = list(range(min(n_hist, 30)))
                
                for idx in eval_indices:
                    # 构建训练集：排除第 idx 天
                    train_idx = [i for i in range(n_hist) if i != idx]
                    X_train = hist_space_mat[train_idx]
                    y_train = hist_price_mat[train_idx]
                    # 计算训练集的相似度（用于加权回归）
                    sim_train = similarities[train_idx] if 'similarities' in dir() else np.ones(len(train_idx))
                    w_train = np.maximum(sim_train, 0)
                    if w_train.sum() == 0:
                        w_train = np.ones(len(train_idx)) / len(train_idx)
                    else:
                        w_train = w_train / w_train.sum()
                    
                    # 对每个时点做加权回归预测第 idx 天的电价
                    pred_idx = np.zeros(96)
                    for t in range(96):
                        X_t = X_train[:, t].reshape(-1, 1)
                        y_t = y_train[:, t]
                        # 过滤有效数据
                        valid = ~np.isnan(y_t) & ~np.isnan(X_t.flatten())
                        if valid.sum() < 2:
                            pred_idx[t] = np.nanmedian(y_train[:, t])
                            continue
                        reg = LinearRegression()
                        reg.fit(X_t[valid], y_t[valid], sample_weight=w_train[valid])
                        pred_idx[t] = reg.predict([[hist_space_mat[idx, t]]])[0]
                    
                    # 计算该日的平均预测误差（预测 - 实际）
                    actual_idx = hist_price_mat[idx]
                    valid_compare = ~np.isnan(actual_idx) & ~np.isnan(pred_idx)
                    if valid_compare.sum() > 0:
                        err = np.mean(pred_idx[valid_compare] - actual_idx[valid_compare])
                        errors.append(err)
                
                if errors:
                    systematic_bias = np.mean(errors)   # 正值表示模型整体偏高
                    # 应用偏置修正（减去偏差）
                    p_final = p_final - systematic_bias
                    # 也对 final_predictions（修正前）进行记录（可选）
                    final_predictions = final_predictions - systematic_bias
                    st.success(f"🔧 自动偏置修正：基于 {len(errors)} 个历史日留一验证，检测到模型平均偏差 {systematic_bias:.2f} 元/MWh，已自动扣除。")
                else:
                    st.info("自动偏置修正：有效对比点不足，跳过。")
            else:
                st.info(f"自动偏置修正：历史样本数({n_hist}) < 5，跳过。")
        except Exception as e:
            st.warning(f"自动偏置修正计算失败（不影响主结果）：{e}")
        # =======================================================
        
        # --- 8. 最终预测结果可视化 ---
        fig = go.Figure()

        # 添加历史相似日作为背景
        for i, date in enumerate(top_k_dates):
            fig.add_trace(go.Scatter(
                y=top_k_prices[i],
                mode='lines',
                name=f'相似日：{date.strftime("%m-%d")}',
                line=dict(color='lightgray', width=1, dash='dot'),
                opacity=0.4, showlegend=False
            ))

        # 添加最终预测结果
        fig.add_trace(go.Scatter(
            y=p_final,
            mode='lines',
            name='🔴 最终预测 (分段回归+修正)',
            line=dict(color='red', width=3)
        ))

        # 添加真实价格 (如果有)
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

        # 添加独立回测数据 (如果有)
        true_price_independent = None
        if actual_file:
            try:
                df_act = pd.read_excel(actual_file)
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
            except Exception as e:
                st.error(f"读取独立回测文件失败：{e}")

        # 添加竞价空间 (右轴)
        fig.add_trace(go.Scatter(
            y=s_target,
            mode='lines',
            name='⚡ 目标日竞价空间',
            line=dict(color='orange', width=2, dash='dot'),
            yaxis='y2',
            opacity=0.6
        ))

        # 布局设置
        tick_positions = list(range(0, 96, 4))
        tick_labels = [str(x // 4) for x in tick_positions]

        fig.update_layout(
            title=f"{target_date.strftime('%Y-%m-%d')} 现货价格最终预测对比",
            xaxis=dict(title="时点 (0-95)", range=[0, 95], tickmode='array', tickvals=tick_positions, ticktext=tick_labels, tickfont=dict(size=12)),
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
            legend=dict(orientation="h", y=1.05, font=dict(size=10))
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
            "分段回归预测价格": np.round(final_predictions, 2),
            "修正后预测价格": np.round(p_final, 2),
            "目标日竞价空间": np.round(s_target, 2),
            "全局平均空间": round(np.mean(all_spaces), 2),
            "全局平均价格": round(np.mean(all_prices), 2),
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
    *

    *   **上传真实电价的独立文件回测模式**：用户可上传独立的实际电价报表（如 `REPORT0.xlsx`），系统会自动根据“日期”和“时点”将真实数据与当前的预测结果进行精准对齐。

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