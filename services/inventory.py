import streamlit as st
import psycopg2
import pandas as pd

def get_db_connection():
    """Establishes a password-safe connection to Supabase using separate parameters."""
    conn = psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        database=st.secrets["postgres"]["database"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        port=st.secrets["postgres"]["port"]
    )
    return conn

def inventory_management():
    st.title("📊 Mica Warehouse Dashboard")

    # --- DATA FETCHING (CLOUD POSTGRESQL) ---
    conn = get_db_connection()

    # "type" is wrapped in double quotes because it is a reserved SQL keyword in PostgreSQL
    metrics_query = """
    SELECT size, material, mica_type, "type", weight 
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

    # --- ROW 2: DETAILED BREAKDOWN (POSTGRESQL COMPATIBLE) ---
    st.subheader("📏 Inventory Breakdown by Size & Finish")

    # Fixed: group_concat replaced with string_agg, and "type" is double-quoted safely
    breakdown_query = """
        SELECT 
            main.size AS "Size", 
            main.finish AS "Finish", 
            main.mica_type AS "Mica", 
            main.material AS "Material", 
            main.type AS "Type",
            -- Core Subquery: Calculates absolute raw sum across matching groups
            (SELECT SUM(weight) FROM stock 
             WHERE size = main.size 
               AND finish = main.finish 
               AND mica_type = main.mica_type 
               AND material = main.material 
               AND "type" = main.type 
               AND status = 'Available' AND weight > 0) AS "Total Weight (KG)",
            string_agg(main.location_summary, ', ') AS "Locations & Packets"
        FROM (
            SELECT 
                size, 
                finish, 
                mica_type, 
                material,
                "type" AS type,
                (godown || ' ' || rack || ':' || COUNT(id) || ' packets') AS location_summary
            FROM stock
            WHERE status = 'Available' AND weight > 0
            GROUP BY size, finish, mica_type, material, "type", godown, rack
        ) AS main
        GROUP BY main.size, main.finish, main.mica_type, main.material, main.type
        ORDER BY "Total Weight (KG)" DESC
        """

    summary_df = pd.read_sql(breakdown_query, conn)
    conn.close()

    # Displaying the final table with the correct mathematical weights and hidden index column
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # --- LOW STOCK WARNINGS ---
    low_stock_limit = 20.0  # 20 KG threshold
    low_stock = summary_df[summary_df['Total Weight (KG)'] < low_stock_limit]

    if not low_stock.empty:
        with st.expander("⚠️ Low Stock Alerts (Below 20 KG)", expanded=False):
            st.write("Consider reordering the following specific variations:")
            st.table(low_stock)