import streamlit as st
import psycopg2
import pandas as pd
import datetime

# Set to True whenever you want to include AAA Balance +- in calculations & display
INCLUDE_AAA_BALANCE = False


@st.cache_data(ttl=30)
def fetch_tally_stock_data():
    try:
        conn = psycopg2.connect(
            host=st.secrets["postgres"]["host"],
            database=st.secrets["postgres"]["database"],
            user=st.secrets["postgres"]["user"],
            password=st.secrets["postgres"]["password"],
            port=st.secrets["postgres"]["port"]
        )
        query = """
            SELECT 
                item_display_name AS "Item Name",
                closing_qty_numeric AS "Stock Qty",
                unit_of_measure AS "Unit",
                closing_qty_raw AS "Raw Balance",
                last_synced_at AS "Last Synced"
            FROM tally_stock_summary
            ORDER BY item_display_name ASC;
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)


def render_tally_stock_page():
    # --- HEADER SECTION ---
    header_col, refresh_col = st.columns([5, 1])
    with header_col:
        st.title("📦 Tally Live Stock Inventory")
        st.caption("Direct synchronization view of all Tally 9 stock items and closing balances.")

    with refresh_col:
        st.write("")
        if st.button("🔄 Refresh Data", key="refresh_tally_btn", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    df, error = fetch_tally_stock_data()

    if error:
        st.error(f"❌ Failed to connect to Supabase: {error}")
        return

    if df.empty:
        st.warning("⚠️ No stock items found in the database. Run `sync_tally.bat` on your PC to populate records.")
        return

    # --- DATA NORMALIZATION ---
    df["Unit"] = df["Unit"].fillna("").str.strip().str.upper()
    df["Stock Qty"] = pd.to_numeric(df["Stock Qty"], errors="coerce").fillna(0.0)

    # --- EXCLUDE AAA BALANCE IF TOGGLED OFF ---
    if not INCLUDE_AAA_BALANCE:
        df = df[~df["Item Name"].str.upper().str.contains("AAA BALANCE", na=False)]

    last_sync_time = df["Last Synced"].dropna().max()
    formatted_time = last_sync_time.strftime("%d %b %Y, %I:%M %p") if pd.notnull(last_sync_time) else "N/A"

    # --- KPI METRICS ---
    kg_stock = df[df["Unit"] == "KG"]["Stock Qty"].sum()
    roll_stock = df[df["Unit"] == "ROLL"]["Stock Qty"].sum()
    pcs_stock = df[df["Unit"] == "PCS"]["Stock Qty"].sum()
    negative_items = df[df["Stock Qty"] < 0]

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Items", f"{len(df):,}")
    m2.metric("Total Stock (KG)", f"{kg_stock:,.2f} KG")
    m3.metric("Total Rolls", f"{roll_stock:,.0f} ROLL")
    m4.metric("Total Pieces", f"{pcs_stock:,.0f} PCS")
    m5.metric(
        "Negative Stock Items",
        f"{len(negative_items)}",
        delta=f"{len(negative_items)} anomalies" if len(negative_items) > 0 else "Clean",
        delta_color="inverse"
    )

    st.divider()

    # --- FILTERS ---
    f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
    search_query = f_col1.text_input("🔍 Search Item Name", placeholder="e.g. 0.5, GCF, PB, CUT, STEEL")
    available_units = ["All Units"] + sorted([u for u in df["Unit"].unique() if u])
    selected_unit = f_col2.selectbox("Unit of Measure", available_units)
    balance_type = f_col3.selectbox(
        "Stock Status",
        ["All Stock", "In-Stock (> 0)", "Negative Stock (< 0)", "Zero Balance (= 0)"]
    )

    filtered_df = df.copy()

    if search_query:
        filtered_df = filtered_df[filtered_df["Item Name"].str.contains(search_query, case=False, na=False)]

    if selected_unit != "All Units":
        filtered_df = filtered_df[filtered_df["Unit"] == selected_unit]

    if balance_type == "In-Stock (> 0)":
        filtered_df = filtered_df[filtered_df["Stock Qty"] > 0]
    elif balance_type == "Negative Stock (< 0)":
        filtered_df = filtered_df[filtered_df["Stock Qty"] < 0]
    elif balance_type == "Zero Balance (= 0)":
        filtered_df = filtered_df[filtered_df["Stock Qty"] == 0]

    # --- TABLE & CSV EXPORT ---
    table_info_col, export_col = st.columns([4, 1])
    with table_info_col:
        st.subheader(f"Inventory List ({len(filtered_df)} items matching)")
        st.caption(f"Last synced from Tally: **{formatted_time}**")

    with export_col:
        csv_data = filtered_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"tally_stock_{datetime.date.today().isoformat()}.csv",
            mime="text/csv",
            use_container_width=True
        )

    display_df = filtered_df[["Item Name", "Stock Qty", "Unit", "Raw Balance"]].copy()

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Item Name": st.column_config.TextColumn("Stock Item Description", width="large"),
            "Stock Qty": st.column_config.NumberColumn("Closing Qty", format="%.3f"),
            "Unit": st.column_config.TextColumn("UOM", width="small"),
            "Raw Balance": st.column_config.TextColumn("Tally Ledger String", width="medium"),
        }
    )