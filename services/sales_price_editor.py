import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime
import warnings

# Suppress pandas DBAPI2 connection warning
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


def extract_thickness(size_str):
    """Extracts gauge/thickness parameter before the '*' symbol."""
    if size_str and '*' in str(size_str):
        return str(size_str).split('*')[0].strip()
    return str(size_str).strip() if size_str else "Unknown"


def sales_price_editor_management():
    st.title("🏷️ Smart Sales Price & Rate Editor")
    st.info(
        "Filter dispatches by Customer Name and Item Specifications. Update unit prices per KG across matching batches seamlessly."
    )

    conn = get_db_connection()

    # --- FETCH ALL HISTORICAL SALES LOGS FOR FILTERING ---
    query_sales = """
        SELECT id, stock_id, invoice_no, company_name, size, finish, material, "type", mica_type, 
               qty_sold, price_per_kg, total_amount, sale_date, notes
        FROM sales
        ORDER BY sale_date DESC, id DESC
    """
    df_sales_raw = pd.read_sql(query_sales, conn)

    if df_sales_raw.empty:
        st.warning("⚠️ No outward sales records found in the system registry.")
        conn.close()
        return

    # Extract Thickness MM helper column
    df_sales_raw['Thickness (MM)'] = df_sales_raw['size'].apply(extract_thickness)

    # -----------------------------------------------------------------
    # STEP 1: ADVANCED HIERARCHICAL FILTER BAR
    # -----------------------------------------------------------------
    st.subheader("🔍 Step 1: Filter Outward Dispatches")

    with st.container(border=True):
        # 1. Company Name Filter (Primary Anchor)
        known_companies = sorted(list(df_sales_raw['company_name'].dropna().unique()))
        selected_company = st.selectbox(
            "🏢 Select Customer / Company Name",
            options=["-- All Customers --"] + known_companies
        )

        # Filter dataframe by company first
        df_comp_filtered = df_sales_raw.copy()
        if selected_company != "-- All Customers --":
            df_comp_filtered = df_comp_filtered[df_comp_filtered['company_name'] == selected_company]

        st.divider()

        # 2. Material, Surface (Finish), Stock Type, Mica Filters
        f1, f2, f3, f4 = st.columns(4)

        avail_materials = sorted(list(df_comp_filtered['material'].dropna().unique()))
        selected_material = f1.selectbox("Material", ["All Materials"] + avail_materials)

        avail_finishes = sorted(list(df_comp_filtered['finish'].dropna().unique()))
        selected_finish = f2.selectbox("Surface / Finish", ["All Finishes"] + avail_finishes)

        avail_types = sorted(list(df_comp_filtered['type'].dropna().unique()))
        selected_type = f3.selectbox("Stock Type", ["All Types"] + avail_types)

        avail_micas = sorted(list(df_comp_filtered['mica_type'].dropna().unique()))
        selected_mica = f4.selectbox("Mica Type", ["All Mica"] + avail_micas)

        # 3. Dynamic Thickness and Size (Dimension) Filters
        f5, f6 = st.columns(2)

        avail_thicknesses = sorted(list(df_comp_filtered['Thickness (MM)'].dropna().unique()))
        selected_thickness = f5.selectbox("Thickness (MM)", ["All Thicknesses"] + avail_thicknesses)

        # Scope size choices based on preceding filters
        df_size_scope = df_comp_filtered.copy()
        if selected_material != "All Materials":
            df_size_scope = df_size_scope[df_size_scope['material'] == selected_material]
        if selected_finish != "All Finishes":
            df_size_scope = df_size_scope[df_size_scope['finish'] == selected_finish]
        if selected_type != "All Types":
            df_size_scope = df_size_scope[df_size_scope['type'] == selected_type]
        if selected_mica != "All Mica":
            df_size_scope = df_size_scope[df_size_scope['mica_type'] == selected_mica]
        if selected_thickness != "All Thicknesses":
            df_size_scope = df_size_scope[df_size_scope['Thickness (MM)'] == selected_thickness]

        avail_sizes = sorted(list(df_size_scope['size'].dropna().unique()))
        selected_size = f6.selectbox("Dimension / Size (Exact)", ["All Dimensions"] + avail_sizes)

    # -----------------------------------------------------------------
    # APPLY FILTERS TO ISOLATE TARGET BATCHES
    # -----------------------------------------------------------------
    df_matched = df_comp_filtered.copy()

    if selected_material != "All Materials":
        df_matched = df_matched[df_matched['material'] == selected_material]
    if selected_finish != "All Finishes":
        df_matched = df_matched[df_matched['finish'] == selected_finish]
    if selected_type != "All Types":
        df_matched = df_matched[df_matched['type'] == selected_type]
    if selected_mica != "All Mica":
        df_matched = df_matched[df_matched['mica_type'] == selected_mica]
    if selected_thickness != "All Thicknesses":
        df_matched = df_matched[df_matched['Thickness (MM)'] == selected_thickness]
    if selected_size != "All Dimensions":
        df_matched = df_matched[df_matched['size'] == selected_size]

    st.divider()

    if df_matched.empty:
        st.warning("⚠️ No sales records match your exact filter parameters.")
        conn.close()
        return

    # -----------------------------------------------------------------
    # STEP 2: DISPLAY MATCHING BATCHES PREVIEW
    # -----------------------------------------------------------------
    st.subheader("📋 Step 2: Preview Matching Dispatched Batches")

    total_matched_weight = round(df_matched['qty_sold'].sum(), 2)
    total_matched_revenue = round(df_matched['total_amount'].sum(), 2)

    m1, m2, m3 = st.columns(3)
    m1.metric("Matching Packets", f"{len(df_matched)} packets")
    m2.metric("Total Weight Sold", f"{total_matched_weight:,.2f} KG")
    m3.metric("Current Total Value", f"₹ {total_matched_revenue:,.2f}")

    # Format dataframe display
    display_cols = [
        'id', 'invoice_no', 'company_name', 'size', 'finish',
        'material', 'type', 'mica_type', 'qty_sold', 'price_per_kg', 'total_amount', 'sale_date'
    ]
    st.dataframe(
        df_matched[display_cols].rename(columns={
            'id': 'Sales ID',
            'invoice_no': 'Invoice #',
            'company_name': 'Customer',
            'size': 'Dimension',
            'finish': 'Surface/Finish',
            'material': 'Material',
            'type': 'Stock Type',
            'mica_type': 'Mica Type',
            'qty_sold': 'Qty Sold (KG)',
            'price_per_kg': 'Current Rate (₹/KG)',
            'total_amount': 'Total Value (₹)',
            'sale_date': 'Dispatch Date'
        }),
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # -----------------------------------------------------------------
    # STEP 3: SELECT SPECIFIC BATCHES & UPDATE PRICE
    # -----------------------------------------------------------------
    st.subheader("✏️ Step 3: Select Target Batches & Update Rate")

    # Map readable option strings to sales IDs
    batch_options = {
        f"Sales ID: {row['id']} | Inv: {row['invoice_no']} | Client: {row['company_name']} | Size: {row['size']} | {row['qty_sold']} KG (Current: ₹{row['price_per_kg']}/KG)":
            row['id']
        for _, row in df_matched.iterrows()
    }

    st.write("Choose whether to edit all filtered batches or pick specific ones:")

    select_all_toggle = st.checkbox("Select ALL matching batches shown above", value=True)

    if select_all_toggle:
        selected_batch_ids = list(df_matched['id'].unique())
        st.info(f"Selected all **{len(selected_batch_ids)}** matching batch records.")
    else:
        selected_batch_labels = st.multiselect(
            "Choose Target Sales Batches to Update",
            options=list(batch_options.keys()),
            placeholder="Select one or more sales entries"
        )
        selected_batch_ids = [batch_options[lbl] for lbl in selected_batch_labels]

    if not selected_batch_ids:
        st.warning("Please select at least one sales batch to update price parameters.")
        conn.close()
        return

    # Isolate selected target rows
    df_target_batches = df_matched[df_matched['id'].isin(selected_batch_ids)]
    target_weight = round(df_target_batches['qty_sold'].sum(), 2)

    col_p1, col_p2 = st.columns(2)

    with col_p1:
        new_rate = st.number_input(
            "New Price per KG (₹)",
            min_value=0.0,
            step=1.0,
            value=float(df_target_batches['price_per_kg'].iloc[0]) if not df_target_batches.empty else 0.0,
            help="Setting 0.0 keeps the status as pending update"
        )

    new_total_value = round(target_weight * new_rate, 2)

    with col_p2:
        st.metric("New Combined Total Value", f"₹ {new_total_value:,.2f}")

    if st.button("Apply New Rate to Selected Batches", type="primary", use_container_width=True):
        try:
            cursor = conn.cursor()

            # Execute batch update loop
            for _, row in df_target_batches.iterrows():
                s_id = int(row['id'])
                qty = float(row['qty_sold'])
                updated_amount = round(qty * new_rate, 2)

                cursor.execute("""
                    UPDATE sales
                    SET price_per_kg = %s,
                        total_amount = %s
                    WHERE id = %s
                """, (new_rate, updated_amount, s_id))

            conn.commit()
            cursor.close()

            st.success(
                f"🎉 Updated price to ₹ {new_rate}/KG for {len(selected_batch_ids)} sales entries ({target_weight} KG total).")
            st.rerun()

        except Exception as ex:
            conn.rollback()
            st.error(f"Critical error during database update operation: {ex}")

    conn.close()