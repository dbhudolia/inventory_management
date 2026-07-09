import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime


def get_db_connection():
    """Establishes a password-safe connection to Supabase using separate parameters."""
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        database=st.secrets["postgres"]["database"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        port=st.secrets["postgres"]["port"]
    )


def rack_liquidation_management():
    st.title("📤 Outward Order (Bulk Rack Sales Clearout)")
    st.info("Filter your warehouse stock, choose a specific rack, and sell every matching batch in a single go.")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Ensure table blueprint tracking schemas remain safe
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id SERIAL PRIMARY KEY,
        stock_id INTEGER,
        invoice_no TEXT,
        size TEXT,
        finish TEXT,
        material TEXT,
        "type" TEXT,
        mica_type TEXT,
        company_name TEXT,
        qty_sold REAL,
        price_per_kg REAL,
        total_amount REAL,
        notes TEXT,
        sale_date TIMESTAMP
    )
    """)
    conn.commit()

    query = """
    SELECT id, invoice_no, size, finish, material, "type", mica_type, weight, godown, rack 
    FROM stock 
    WHERE status = 'Available' AND weight > 0
    """
    df_raw = pd.read_sql(query, conn)

    if df_raw.empty:
        st.warning("No active stock currently available in the warehouse.")
        cursor.close()
        conn.close()
        return

    # STEP 1: DYNAMIC FILTER BAR
    st.subheader("🛠️ Step 1: Filter Stock Matrix")
    with st.container(border=True):
        f_col1, f_col2, f_col3 = st.columns(3)
        selected_size = f_col1.selectbox("Filter by Size", ["All Sizes"] + list(df_raw['size'].unique()))
        selected_mica = f_col2.selectbox("Filter by Mica Type", ["All Mica"] + list(df_raw['mica_type'].unique()))
        selected_material = f_col3.selectbox("Filter by Material",
                                             ["All Materials"] + list(df_raw['material'].unique()))

        f_col4, f_col5 = st.columns(2)
        selected_finish = f_col4.selectbox("Filter by Finish", ["All Finishes"] + list(df_raw['finish'].unique()))
        selected_type = f_col5.selectbox("Filter by Stock Type", ["All Types"] + list(df_raw['type'].unique()))

    # Apply structural variant filters to the local memory dataframe
    df_filtered = df_raw.copy()
    if selected_size != "All Sizes": df_filtered = df_filtered[df_filtered['size'] == selected_size]
    if selected_mica != "All Mica": df_filtered = df_filtered[df_filtered['mica_type'] == selected_mica]
    if selected_material != "All Materials": df_filtered = df_filtered[df_filtered['material'] == selected_material]
    if selected_finish != "All Finishes": df_filtered = df_filtered[df_filtered['finish'] == selected_finish]
    if selected_type != "All Types": df_filtered = df_filtered[df_filtered['type'] == selected_type]

    # Dynamically extract only racks containing active items matching the applied attribute filters
    available_racks = sorted(list(df_filtered['rack'].dropna().unique()))

    st.divider()

    # STEP 2: CHOOSE TARGET RACK AND TRANSACTION DETAILS
    st.subheader("💼 Step 2: Process Rack Liquidation Dispatch")

    col_rack, col_cust, col_date = st.columns([2.5, 2, 1.5])

    with col_rack:
        selected_rack = st.selectbox("🎯 Target Rack to Liquidate", options=["-- Select a Rack --"] + available_racks)

    with col_cust:
        cursor.execute(
            "SELECT DISTINCT company_name FROM sales WHERE company_name IS NOT NULL AND company_name != '' ORDER BY company_name ASC")
        known_companies = [row[0] for row in cursor.fetchall()]

        company_dropdown_options = ["[+ Register New Company]"] + known_companies
        selected_company_option = st.selectbox("Select Customer / Company", options=company_dropdown_options)

        if selected_company_option == "[+ Register New Company]":
            company_name = st.text_input("Type New Company Name String", value="")
        else:
            company_name = selected_company_option

    with col_date:
        sales_manual_date = st.date_input("Sales Date", value=datetime.today())

    if selected_rack == "-- Select a Rack --":
        st.info("Choose a targeted rack above to view and calculate your liquidating batch summaries.")
        cursor.close()
        conn.close()
        return

    # Isolate the exact matching rows resting on that target rack coordinate
    df_rack_pool = df_filtered[df_filtered['rack'] == selected_rack]
    total_pool_weight = round(df_rack_pool['weight'].sum(), 2)
    total_pool_packets = len(df_rack_pool)

    if total_pool_packets == 0:
        st.error(f"❌ No matching batches found on Rack '{selected_rack}' under current specifications.")
        cursor.close()
        conn.close()
        return

    # Render a clear preview dataframe showing what will leave the warehouse gates
    st.write(f"**Found {total_pool_packets} packets on Rack '{selected_rack}' matching your specifications:**")
    st.dataframe(df_rack_pool, use_container_width=True, hide_index=True)

    st.divider()
    col_p, col_n = st.columns([1, 2])
    with col_p:
        # Allows entering 0.0 cleanly without falling below min_value constraints
        price_per_kg = st.number_input("Flat Price per KG", min_value=0.0, step=5.0, value=0.0)
    with col_n:
        notes = st.text_input("Transaction Notes", value=f"Bulk liquidation clearout of Rack {selected_rack}.")

    total_value = round(total_pool_weight * price_per_kg, 2)

    # Display warnings if the price parameter is deliberately zeroed out
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("Total Weight Dispatched", f"{total_pool_weight:,.2f} KG", delta=f"{total_pool_packets} packets")

    if price_per_kg > 0:
        m_col2.metric("Total Deal Value", f"₹ {total_value:,.2f}")
    else:
        st.warning("⚠️ Price is set to 0.0 (Pending Later Update)")

    if st.button("Confirm and Dispatch Complete Rack Stock", type="primary", use_container_width=True):
        if not company_name or company_name.strip() == "":
            st.error("❌ Customer Company Name choice or raw string entry is required.")
        else:
            try:
                sales_date_str = sales_manual_date.strftime("%Y-%m-%d 00:00:00")

                # Iterate through all isolated rack entries to clean balances and map sales tracking data safely
                for _, row in df_rack_pool.iterrows():
                    p_id = int(row['id'])
                    p_weight = float(row['weight'])
                    packet_value = round(p_weight * price_per_kg, 2)

                    # Update individual stock record to zero balance/sold
                    cursor.execute("UPDATE stock SET weight = 0, status = 'Sold' WHERE id = %s", (p_id,))

                    # Generate mirrored line items inside your sales matrix logs
                    cursor.execute("""
                        INSERT INTO sales (
                            stock_id, invoice_no, size, finish, material, "type", mica_type, 
                            company_name, qty_sold, price_per_kg, total_amount, notes, sale_date
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (p_id, row['invoice_no'], row['size'], row['finish'], row['material'],
                          row['type'], row['mica_type'], company_name.strip(), p_weight, price_per_kg,
                          packet_value, notes, sales_date_str))

                conn.commit()
                st.success(
                    f"🎉 Successfully cleared Rack '{selected_rack}'! Dispatched {total_pool_packets} packets ({total_pool_weight} KG) to {company_name}.")

                cursor.close()
                conn.close()
                st.rerun()

            except Exception as e:
                conn.rollback()
                st.error(f"Critical transaction rollback triggered by database error: {e}")

    try:
        cursor.close()
        conn.close()
    except:
        pass