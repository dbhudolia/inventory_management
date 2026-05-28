import streamlit as st
import sqlite3
import pandas as pd


def inventory_management():
    st.title("📊 Mica Warehouse Dashboard")

    # --- DATA FETCHING ---
    conn = sqlite3.connect('inventory.db')

    # Fetching the core metrics
    metrics_query = """
    SELECT size, material, mica_type, type, weight 
    FROM stock 
    WHERE status = 'Available' AND weight > 0
    """
    df_metrics = pd.read_sql(metrics_query, conn)

    if df_metrics.empty:
        st.warning("No active stock found in the database. Log some items in 'Inward Entry' first.")
        conn.close()
        return

    # --- TOP LEVEL METRICS (WIDE MODE) ---
    total_weight = df_metrics['weight'].sum()
    unique_sizes = df_metrics['size'].nunique()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Weight (KG)", f"{total_weight:,.2f}")
    m2.metric("Unique Sizes", unique_sizes)
    m3.metric("Mica Types", df_metrics['mica_type'].nunique())
    m4.metric("Materials", df_metrics['material'].nunique())

    st.divider()

    # --- ROW 1: COMPOSITION ANALYSIS ---
    st.subheader("🧱 Stock Composition")
    c1, c2 = st.columns(2)

    with c1:
        st.write("**Weight by Mica Type**")
        mica_dist = df_metrics.groupby('mica_type')['weight'].sum().reset_index()
        st.bar_chart(data=mica_dist, x='mica_type', y='weight', color="#FF4B4B")

    with c2:
        st.write("**Weight by Material Type**")
        mat_dist = df_metrics.groupby('material')['weight'].sum().reset_index()
        st.bar_chart(data=mat_dist, x='material', y='weight', color="#0068C9")

    st.divider()

    # --- ROW 2: DETAILED BREAKDOWN (FIXED WEIGHT SUM LOGIC) ---
    st.subheader("📏 Inventory Breakdown by Size & Finish")

    # This query calculates the absolute raw SUM(weight) while cleanly grouping location text
    breakdown_query = """
        SELECT 
            main.size AS [Size], 
            main.finish AS [Finish], 
            main.mica_type AS [Mica], 
            main.material AS [Material], 
            main.type AS [Type],
            -- Core Fix: We calculate the true sum of weights from the raw rows matching these groups
            (SELECT SUM(weight) FROM stock 
             WHERE size = main.size 
               AND finish = main.finish 
               AND mica_type = main.mica_type 
               AND material = main.material 
               AND type = main.type 
               AND status = 'Available' AND weight > 0) AS [Total Weight (KG)],
            group_concat(main.location_summary, ', ') AS [Locations & Packets]
        FROM (
            SELECT 
                size, 
                finish, 
                mica_type, 
                material,
                type,
                (godown || ' ' || rack || ':' || COUNT(id) || ' packets') AS location_summary
            FROM stock
            WHERE status = 'Available' AND weight > 0
            GROUP BY size, finish, mica_type, material, type, godown, rack
        ) AS main
        GROUP BY main.size, main.finish, main.mica_type, main.material, main.type
        ORDER BY [Total Weight (KG)] DESC
        """

    summary_df = pd.read_sql(breakdown_query, conn)
    conn.close()

    # Displaying the final table with the correct mathematical weights
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # --- LOW STOCK WARNINGS ---
    low_stock_limit = 20.0  # 20 KG threshold
    low_stock = summary_df[summary_df['Total Weight (KG)'] < low_stock_limit]

    if not low_stock.empty:
        with st.expander("⚠️ Low Stock Alerts (Below 20 KG)", expanded=False):
            st.write("Consider reordering the following specific variations:")
            st.table(low_stock, hide_index=True)