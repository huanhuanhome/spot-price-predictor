import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="现货价格智能预测系统 (v3.1 - 最终修复版)", layout="wide")

st.title("⚡ 现货价格智能预测系统 (v3.1)")
st.markdown("""
**更新说明**：
- 修复缩进错误，确保所有逻辑在 try-except 块内正常运行。
- 支持预测**未来日期**（仅有竞价空间，无现货价格）。
- 自动区分**历史样本库**和**待预测目标**。
""")

# --- 侧边栏 ---
st.sidebar.header("⚙️ 模型设置")
uploaded_file = st.sidebar.file_uploader("上传 基础数据.xlsx", type=["xlsx"])

alpha = st.sidebar.slider(
    "负荷敏感系数 (α)", 
    min_value=0.0, max_value=2.0, value=1.0, step=0.1,
    help="控制竞价空间变化对价格的影响程度。"
)

if uploaded_file:
    try:
        # --- 1. 数据读取与预处理 ---
        df_raw = pd.read_excel(uploaded_file)
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

        space_pivot = df_raw.pivot_table(index='日期', columns='idx', values='竞价空间', aggfunc='first')
        price_pivot = df_raw.pivot_table(index='日期', columns='idx', values='现货出清电价', aggfunc='first')

        required_cols = list(range(96))
        space_pivot = space_pivot.reindex(columns=required_cols)
        price_pivot = price_pivot.reindex(columns=required_cols)

        # --- 2. 智能日期分类 ---
        all_dates = sorted(list(space_pivot.index))
        
        if not all_dates:
            st.error("未找到任何日期数据。")
            st.stop()

        valid_history_mask = (space_pivot.notna().all(axis=1) & price_pivot.notna().all(axis=1))
        history_dates = [d for d in all_dates if valid_history_mask.loc[d]]

        valid_target_mask = space_pivot.notna().all(axis=1)
        target_candidates = [d for d in all_dates if valid_target_mask.loc[d]]

        st.sidebar.success(f"数据解析成功！\n- 历史样本: {len(history_dates)} 天\n- 可预测日期: {len(target_candidates)} 天")

        if len(history_dates) < 3:
            st.error(f"错误：有效历史样本不足 3 天 (当前 {len(history_dates)} 天)。")
            st.stop()

        default_idx = len(target_candidates) - 1
        target_date = st.sidebar.selectbox(
            "选择要预测的日期",
            options=target_candidates,
            index=default_idx,
            format_func=lambda x: x.strftime("%Y-%m-%d")
        )

        # --- 3. 准备数据矩阵 ---
        target_space_series = space_pivot.loc[target_date]
        target_space_vec = target_space_series.values.reshape(1, -1)
        
        has_price_target = target_date in price_pivot.index and price_pivot.loc[target_date].notna().all()
        current_hist_dates = [d for d in history_dates if d != target_date]
        
        if len(current_hist_dates) < 3:
            st.error(f"错误：排除目标日后，剩余有效历史样本不足 3 天。")
            st.stop()

        hist_space_mat = space_pivot.loc[current_hist_dates].values
        hist_price_mat = price_pivot.loc[current_hist_dates].values

        mode_text = '✅ 回测验证' if has_price_target else '🔮 未来预测'
        st.info(f"当前模式：{mode_text} | 参与计算的历史天数：{len(current_hist_dates)}")

        # --- 4. 核心算法：相似度计算 ---
        st.header("📊 第一步：形状提取")
        
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
        
        # --- 5. 基准曲线与趋势分析 ---
        st.header("📈 第二步：趋势分析")
        
        weights = top_k_sims / np.sum(top_k_sims)
        p_base = np.sum(top_k_prices * weights.reshape(-1, 1), axis=0)
        s_base = np.sum(top_k_spaces * weights.reshape(-1, 1), axis=0)
        
        x_axis = np.arange(96).reshape(-1, 1)
        lr_model = LinearRegression()
        lr_model.fit(x_axis, p_base)
        trend_slope = lr_model.coef_[0]
        
        trend_status = "平稳"
        if trend_slope > 0.5: trend_status = "↗️ 走高"
        elif trend_slope < -0.5: trend_status = "↘️ 走低"
        
        col_t1, col_t2, col_t3 = st.columns(3)
        col_t1.metric("基础均价", f"{np.mean(p_base):.2f}")
        col_t2.metric("趋势斜率", f"{trend_slope:.4f}", delta=trend_status)
        col_t3.metric("峰值时段", f"{np.argmax(p_base)//4}:00")

        # --- 6. 动态幅度修正 ---
        st.header("🚀 第三步：动态修正")
        
        s_target = target_space_vec.flatten()
        epsilon = 10.0 
        safe_s_base = np.where(s_base < epsilon, epsilon, s_base)
        
        space_diff_ratio = (s_target - s_base) / safe_s_base
        space_diff_ratio = np.clip(space_diff_ratio, -2.0, 2.0)
        
        correction_factor = 1 + (alpha * space_diff_ratio)
        correction_factor = np.maximum(correction_factor, 0.1)
        
        p_final = p_base * correction_factor
        
        st.markdown(f"**修正系数 α**: {alpha} | **最大修正**: {np.max(np.abs(correction_factor - 1))*100:.1f}%")

        # --- 7. 可视化 ---
        fig = go.Figure()
        
        for i, date in enumerate(top_k_dates):
            fig.add_trace(go.Scatter(
                y=top_k_prices[i],
                mode='lines',
                name=f'相似日: {date.strftime("%m-%d")}',
                line=dict(color='lightgray', width=1, dash='dot'),
                opacity=0.4, showlegend=False
            ))
        
        fig.add_trace(go.Scatter(
            y=p_base, mode='lines', name='🔵 基础形状',
            line=dict(color='blue', width=2, dash='dash'), opacity=0.7
        ))
        
        fig.add_trace(go.Scatter(
            y=p_final, mode='lines', name='🔴 最终预测',
            line=dict(color='red', width=3)
        ))
        
        if has_price_target:
            true_price = price_pivot.loc[target_date].values
            fig.add_trace(go.Scatter(
                y=true_price, mode='lines', name='🟢 真实价格',
                line=dict(color='green', width=2, dash='dot'), opacity=0.8
            ))
        
        fig.add_trace(go.Scatter(
            y=s_target, mode='lines', name='⚡ 竞价空间',
            line=dict(color='orange', width=2, dash='dot'),
            yaxis='y2', opacity=0.6
        ))

        fig.update_layout(
            title=f"{target_date.strftime('%Y-%m-%d')} 现货价格预测",
            xaxis=dict(title="时点 (0-95)", range=[0, 95]),
            yaxis=dict(
                title=dict(text="电价 (元/MWh)", font=dict(color="red")),
                tickfont=dict(color="red"), side='left'
            ),
            yaxis2=dict(
                title=dict(text="竞价空间 (MW)", font=dict(color="orange")),
                tickfont=dict(color="orange"),
                overlaying='y', side='right', showgrid=False
            ),
            hovermode="x unified", template="plotly_white",
            height=600, legend=dict(orientation="h", y=1.05)
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # --- 8. 结果导出 (修复缩进问题) ---
        st.header("📥 结果导出：目标日完整数据")
        
        # 【修复】使用标准的多行循环，避免单行 if 导致的缩进解析错误
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
        
        if has_price_target:
            export_data["真实价格"] = np.round(price_pivot.loc[target_date].values, 2)
            export_data["预测误差"] = np.round(p_final - price_pivot.loc[target_date].values, 2)
        
        export_df = pd.DataFrame(export_data)
        
        st.dataframe(export_df, use_container_width=True, height=600, hide_index=True)
        
        # 【关键修复】确保下载按钮逻辑严格在 try 块内，且缩进与 st.dataframe 一致
        csv_content = export_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 下载完整数据 (CSV)",
            data=csv_content,
            file_name=f"forecast_{target_date.strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

    except Exception as e:
        # 只有当 try 块正确结束时，这里才会被执行
        st.error(f"发生错误：{e}")
        import traceback
        st.code(traceback.format_exc())
else:
    st.info("👈 请上传 基础数据.xlsx")