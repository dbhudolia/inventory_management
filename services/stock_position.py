import streamlit as st
import sqlite3
import pandas as pd


def stock_position_summary():
    st.title("📦 Stock Position Summary")
    st.info(
        "Consolidated overview: Rows are compressed by item specifications to show packet counts and rack distribution.")

    conn = sqlite3.connect('inventory.db')

    # --- FETCH DYNAMIC DROPDOWN FILTER OPTIONS ---
    filter_data = pd.read_sql(
        "SELECT mica_type, material, type, finish FROM stock WHERE status = 'Available' AND weight > 0", conn)

    with st.expander("🛠️ Filter Stock Position (Click to Expand)", expanded=True):
        f1, f2, f3 = st.columns(3)
        mica_filter = f1.multiselect("Mica Type", options=filter_data['mica_type'].unique(), placeholder="All Mica")
        mat_filter = f2.multiselect("Material", options=filter_data['material'].unique(), placeholder="All Materials")
        type_filter = f3.multiselect("Stock Type", options=filter_data['type'].unique(), placeholder="All Types")

        f4, f5 = st.columns(2)
        finish_filter = f4.multiselect("Finish", options=filter_data['finish'].unique(), placeholder="All Finishes")
        text_search = st.text_input("Search by Invoice #, Size (e.g., 5*1000), or Rack name")

    # --- CONSOLIDATED PACKET QUERY (GROUPED BY SPEC + WEIGHT) ---
    # This compresses exact matches and sums their packet counts and weights
    base_query = """
    SELECT 
        main.invoice_no AS [Invoice #],
        main.size AS [Size], 
        main.finish AS [Finish], 
        main.material AS [Material], 
        main.type AS [Type],
        main.mica_type AS [Mica Type], 
        main.weight AS [Unit Weight (KG)],
        (SELECT COUNT(id) FROM stock 
         WHERE invoice_no = main.invoice_no AND size = main.size AND finish = main.finish 
           AND material = main.material AND type = main.type AND mica_type = main.mica_type 
           AND weight = main.weight AND status = 'Available') AS [Total Packets],
        (SELECT SUM(weight) FROM stock 
         WHERE invoice_no = main.invoice_no AND size = main.size AND finish = main.finish 
           AND material = main.material AND type = main.type AND mica_type = main.mica_type 
           AND weight = main.weight AND status = 'Available') AS [Total Weight (KG)],
        group_concat(main.rack_summary, ', ') AS [Rack Distribution]
    FROM (
        SELECT 
            invoice_no, size, finish, material, type, mica_type, weight,
            -- Formats strings like "1A1(5 packets)"
            (godown || rack || '(' || COUNT(id) || ' packets)') AS rack_summary
        FROM stock
        WHERE status = 'Available' AND weight > 0
        GROUP BY invoice_no, size, finish, material, type, mica_type, weight, godown, rack
    ) AS main
    GROUP BY main.invoice_no, main.size, main.finish, main.material, main.type, main.mica_type, main.weight
    ORDER BY [Total Weight (KG)] DESC
    """

    df_position = pd.read_sql(base_query, conn)
    conn.close()

    if df_position.empty:
        st.warning("No active inventory stock to display.")
        return

    # --- APPLY FILTER LOGIC ---
    if mica_filter:
        df_position = df_position[df_position['Mica Type'].isin(mica_filter)]
    if mat_filter:
        df_position = df_position[df_position['Material'].isin(mat_filter)]
    if type_filter:
        df_position = df_position[df_position['Type'].isin(type_filter)]
    if finish_filter:
        df_position = df_position[df_position['Finish'].isin(finish_filter)]

    if text_search:
        # regex=False ensures sizes like '5*1000' work perfectly
        df_position = df_position[
            df_position['Invoice #'].str.contains(text_search, case=False, regex=False) |
            df_position['Size'].str.contains(text_search, case=False, regex=False) |
            df_position['Rack Distribution'].str.contains(text_search, case=False, regex=False)
            ]

    # --- DISPLAY CONSOLIDATED POSITION ---
    st.divider()
    st.subheader(f"Summary View: {len(df_position)} Unique Weight Groups")
    st.dataframe(df_position, use_container_width=True, hide_index=True)