import streamlit as st
import psycopg2
import pandas as pd
import warnings

# Suppress the pandas DBAPI2 connection warning
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")


def get_db_connection():
    """Establishes a password-safe connection to Supabase using separate parameters."""
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        database=st.secrets["postgres"]["database"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        port=st.secrets["postgres"]["port"]
    )


def inventory_management():
    st.title("📊 Mica Warehouse Dashboard")

    # --- DATA FETCHING (CLOUD POSTGRESQL) ---
    conn = get_db_connection()

    # "type" is wrapped in double quotes because it is a reserved SQL keyword in PostgreSQL
    # Fetching finish, godown, and rack columns into memory so python can execute string splits
    metrics_query = """
    SELECT size, finish, material, mica_type, "type", weight, godown, rack, id
    FROM stock 
    WHERE status = 'Available' AND weight > 0
    """
    df_raw = pd.read_sql(metrics_query, conn)
    conn.close()

    if df_raw.empty:
        st.warning("No active stock found in the database. Log some items in 'Inward Entry' first.")
        return

    # --- TOP LEVEL METRICS (WIDE MODE) ---
    total_weight = df_raw['weight'].sum()
    unique_sizes = df_raw['size'].nunique()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Weight (KG)", f"{total_weight:,.2f}")
    m2.metric("Unique Sizes", unique_sizes)
    m3.metric("Mica Types", df_raw['mica_type'].nunique())
    m4.metric("Materials", df_raw['material'].nunique())

    st.divider()

    # --- ROW 1: COMPOSITION ANALYSIS ---
    st.subheader("🧱 Stock Composition")
    c1, c2 = st.columns(2)

    with c1:
        st.write("**Weight by Mica Type**")
        mica_dist = df_raw.groupby('mica_type')['weight'].sum().reset_index()
        st.bar_chart(data=mica_dist, x='mica_type', y='weight', color="#FF4B4B")

    with c2:
        st.write("**Weight by Material Type**")
        mat_dist = df_raw.groupby('material')['weight'].sum().reset_index()
        st.bar_chart(data=mat_dist, x='material', y='weight', color="#0068C9")

    st.divider()

    # --- TABLE 1: INVENTORY BREAKDOWN BY EXACT SIZE ---
    st.subheader("📏 Table 1: Inventory Breakdown by Size & Finish")

    # Rebuilding your original structured subquery summary inside python for maximum calculation safety
    df_raw['location_summary'] = df_raw['godown'] + ' ' + df_raw['rack']

    # 1. Group to count packets per location variant block
    loc_counts = df_raw.groupby(
        ['size', 'finish', 'mica_type', 'material', 'type', 'location_summary']).size().reset_index(name='p_count')
    loc_counts['loc_str'] = loc_counts['location_summary'] + ':' + loc_counts['p_count'].astype(str) + ' packets'

    # 2. String aggregate location lists together
    loc_aggs = loc_counts.groupby(['size', 'finish', 'mica_type', 'material', 'type'])['loc_str'].apply(
        lambda x: ', '.join(x)).reset_index(name='Locations & Packets')

    # 3. Aggregate mass totals across configurations
    weights_agg = df_raw.groupby(['size', 'finish', 'mica_type', 'material', 'type'])['weight'].sum().reset_index(
        name='Total Weight (KG)')

    # Merge matching properties together
    summary_df = pd.merge(weights_agg, loc_aggs, on=['size', 'finish', 'mica_type', 'material', 'type'])
    summary_df.columns = ["Size", "Finish", "Mica", "Material", "Type", "Total Weight (KG)", "Locations & Packets"]
    summary_df = summary_df.sort_values(by="Total Weight (KG)", ascending=False)

    # Render Table 1
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.divider()

    # --- TABLE 2: INVENTORY BREAKDOWN BY THICKNESS (MM ONLY) ---
    st.subheader("🔬 Table 2: Inventory Breakdown by Thickness (MM)")
    st.write("Consolidated physical weight totals grouping all variations sharing the same gauge thickness.")

    df_thickness = df_raw.copy()

    # Safely extract the leading digits before the first * sign (e.g., '0.4*1000*600' -> '0.4')
    df_thickness['Thickness (MM)'] = df_thickness['size'].astype(str).apply(
        lambda x: x.split('*')[0].strip() if '*' in x else x
    )

    # Re-run aggregation pipelines over the isolated MM parameter
    thick_counts = df_thickness.groupby(
        ['Thickness (MM)', 'finish', 'mica_type', 'material', 'type', 'location_summary']).size().reset_index(
        name='p_count')
    thick_counts['loc_str'] = thick_counts['location_summary'] + ':' + thick_counts['p_count'].astype(str) + ' packets'

    thick_loc_aggs = thick_counts.groupby(['Thickness (MM)', 'finish', 'mica_type', 'material', 'type'])[
        'loc_str'].apply(lambda x: ', '.join(x)).reset_index(name='Locations & Packets')
    thick_weights_agg = df_thickness.groupby(['Thickness (MM)', 'finish', 'mica_type', 'material', 'type'])[
        'weight'].sum().reset_index(name='Total Weight (KG)')

    thickness_df = pd.merge(thick_weights_agg, thick_loc_aggs,
                            on=['Thickness (MM)', 'finish', 'mica_type', 'material', 'type'])
    thickness_df.columns = ["Thickness (MM)", "Finish", "Mica", "Material", "Type", "Total Weight (KG)",
                            "Locations & Packets"]
    thickness_df = thickness_df.sort_values(by="Total Weight (KG)", ascending=False)

    # Render Table 2
    st.dataframe(thickness_df, use_container_width=True, hide_index=True)

    # --- LOW STOCK WARNINGS ---
    st.divider()
    low_stock_limit = 20.0
    low_stock = summary_df[summary_df['Total Weight (KG)'] < low_stock_limit]

    if not low_stock.empty:
        with st.expander("⚠️ Low Stock Alerts (Below 20 KG)", expanded=False):
            st.write("Consider reordering the following specific variations:")
            st.dataframe(low_stock, use_container_width=True, hide_index=True)