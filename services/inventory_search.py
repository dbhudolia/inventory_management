import streamlit as st
import sqlite3
import pandas as pd


def inventory_search_management():
    st.title("🔍 Advanced Inventory Search & Rack Breakdown")
    st.info("Select a Godown and Rack to see a compressed packet breakdown of weights, or use global filters.")

    conn = sqlite3.connect('inventory.db')

    # -------------------------------------------------------------
    # NEW FEATURE: GODOWN & RACK PACKET BREAKDOWN
    # -------------------------------------------------------------
    st.subheader("📦 Rack-Wise Packet Breakdown")
    st.write("See a consolidated summary of items and packet counts for a specific location.")

    # Quick database pull to get valid locations for the dropdowns
    loc_df = pd.read_sql("SELECT DISTINCT godown, rack FROM stock WHERE status = 'Available' AND weight > 0", conn)

    b_col1, b_col2 = st.columns(2)
    selected_g = b_col1.selectbox("Choose Godown for Breakdown", options=[""] + list(loc_df['godown'].unique()))

    # Filter rack choices based on selected godown
    if selected_g:
        available_racks = loc_df[loc_df['godown'] == selected_g]['rack'].unique()
    else:
        available_racks = loc_df['rack'].unique()

    selected_r = b_col2.selectbox("Choose Rack for Breakdown", options=[""] + list(available_racks))

    # If both are selected, generate the single-line packet summary
    if selected_g and selected_r:
        breakdown_query = """
        SELECT 
            invoice_no AS [Invoice #], 
            size AS [Size], 
            finish AS [Finish], 
            material AS [Material], 
            type AS [Type], 
            mica_type AS [Mica Type], 
            weight AS [Weight (KG)],
            COUNT(id) AS [Total Packets],
            SUM(weight) AS [Total Weight (KG)]
        FROM stock 
        WHERE godown = ? AND rack = ? AND status = 'Available' AND weight > 0
        GROUP BY invoice_no, size, finish, material, type, mica_type, weight
        """
        breakdown_df = pd.read_sql(breakdown_query, conn, params=(selected_g, selected_r))

        if not breakdown_df.empty:
            st.success(f"📍 Displaying items physically present in **{selected_g} -> {selected_r}**")
            st.dataframe(breakdown_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No active stock found at this specific coordinate.")

    st.divider()

    # -------------------------------------------------------------
    # MAIN ADVANCED GLOBAL SEARCH
    # -------------------------------------------------------------
    st.subheader("🕵️ Global Inventory Search Filters")
    # 1. FETCH ALL ACTIVE STOCK (Row-by-Row View with IDs)
    query = """
        SELECT id, invoice_no, size, finish, material, type, mica_type, weight, godown, rack, status 
        FROM stock 
        WHERE weight > 0 AND status = 'Available'
        """
    df = pd.read_sql(query, conn)

    if df.empty:
        st.warning("No available stock records found.")
        conn.close()
        return

    # --- FILTER SECTION ---
    with st.expander("🛠️ Search Filters (Click to Expand)", expanded=True):
        f1, f2, f3 = st.columns(3)
        mica_filter = f1.multiselect("Mica Type", options=df['mica_type'].unique(), placeholder="All Mica")
        mat_filter = f2.multiselect("Material", options=df['material'].unique(), placeholder="All Materials")
        type_filter = f3.multiselect("Stock Type", options=df['type'].unique(), placeholder="All Types")

        f4, f5, f6 = st.columns(3)
        finish_filter = f4.multiselect("Finish", options=df['finish'].unique(), placeholder="All Finishes")
        godown_filter = f5.multiselect("Godown Location", options=df['godown'].unique(), placeholder="All Godowns")
        # ADDED: Rack filter dropdown for the global row-by-row search
        rack_filter = f6.multiselect("Specific Rack / Row", options=df['rack'].unique(), placeholder="All Racks")

        st.divider()
        text_search = st.text_input("Global Text Search (Invoice #, Size like 5*1000)")

    # --- APPLY FILTERS TO DATAFRAME ---
    if mica_filter: df = df[df['mica_type'].isin(mica_filter)]
    if mat_filter: df = df[df['material'].isin(mat_filter)]
    if type_filter: df = df[df['type'].isin(type_filter)]
    if finish_filter: df = df[df['finish'].isin(finish_filter)]
    if godown_filter: df = df[df['godown'].isin(godown_filter)]
    if rack_filter: df = df[df['rack'].isin(rack_filter)]

    if text_search:
        # regex=False ensures sizes like 5*1000 don't cause crashes
        df = df[
            df['invoice_no'].str.contains(text_search, case=False, regex=False) |
            df['size'].str.contains(text_search, case=False, regex=False) |
            df['rack'].str.contains(text_search, case=False, regex=False)
            ]

    # --- DISPLAY RESULTS ---
    st.subheader(f"Found {len(df)} Matching Individual Batches")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------
    # MANAGEMENT PANEL: EDIT & REMOVAL CONTROLS
    # -------------------------------------------------------------
    st.markdown("---")
    st.subheader("🛠️ Inventory Management Panel")

    tab1, tab2, tab3, tab4 = st.tabs(["✏️ Edit Stock Entry", "💰 Update Sales Prices", "🗑️ Delete Single Entry", "💥 Clear Entire Rack"])

    # TAB 1: EDIT SINGLE ENTRY VALUES
    with tab1:
        st.write("Modify attributes or transfer locations using a record ID.")
        edit_id = st.number_input("Enter Item ID to Edit", min_value=1, step=1, key="edit_id_input")

        if edit_id in df['id'].values:
            current_row = df[df['id'] == edit_id].iloc[0]
            st.markdown(f"**Editing Record ID: {edit_id}** (Invoice: {current_row['invoice_no']})")

            with st.form("edit_values_form"):
                e_col1, e_col2 = st.columns(2)
                with e_col1:
                    new_size = st.text_input("Size", value=str(current_row['size']))
                    new_material = st.selectbox("Material", ["Rigid", "Flexible", "Epoxy"],
                                                index=["Rigid", "Flexible", "Epoxy"].index(current_row['material']) if
                                                current_row['material'] in ["Rigid", "Flexible", "Epoxy"] else 0)
                    is_epoxy_edit = (new_material == "Epoxy")
                    new_finish = st.selectbox("Finish", ["Glass Cloth", "Steel", "Plain", "Polished", "N/A"],
                                              index=["Glass Cloth", "Steel", "Plain", "Polished", "N/A"].index(
                                                  current_row['finish']) if current_row['finish'] in ["Glass Cloth",
                                                                                                      "Steel", "Plain",
                                                                                                      "Polished",
                                                                                                      "N/A"] else 0,
                                              disabled=is_epoxy_edit)

                with e_col2:
                    new_mica = st.selectbox("Mica Type", ["Muscovite", "Phlogopite", "Phlogopite(EV)", "N/A"],
                                            index=["Muscovite", "Phlogopite", "Phlogopite(EV)", "N/A"].index(current_row['mica_type']) if
                                            current_row['mica_type'] in ["Muscovite", "Phlogopite", "Phlogopite(EV)", "N/A"] else 0,
                                            disabled=is_epoxy_edit)
                    new_type = st.selectbox("Stock Type", ["Fresh", "Seconds", "Cut", "Open"],
                                            index=["Fresh", "Seconds", "Cut", "Open"].index(current_row['type']) if
                                            current_row['type'] in ["Fresh", "Seconds", "Cut", "Open"] else 0)
                    new_weight = st.number_input("Weight (KG)", min_value=0.0, step=0.1,
                                                 value=float(current_row['weight']))

                st.markdown("**Location Details (Use this to transfer items)**")
                loc_col1, loc_col2 = st.columns(2)
                new_godown = loc_col1.selectbox("Godown", ["Godown 1", "Godown 2"],
                                                index=["Godown 1", "Godown 2"].index(current_row['godown']) if
                                                current_row['godown'] in ["Godown 1", "Godown 2"] else 0)
                new_rack = loc_col2.text_input("Rack / Row Location", value=str(current_row['rack']))

                if st.form_submit_button("Save Changes", type="primary"):
                    final_finish = "N/A" if is_epoxy_edit else new_finish
                    final_mica = "N/A" if is_epoxy_edit else new_mica

                    cursor_edit = conn.cursor()
                    cursor_edit.execute("""
                        UPDATE stock 
                        SET size = ?, finish = ?, material = ?, type = ?, mica_type = ?, weight = ?, godown = ?, rack = ? 
                        WHERE id = ?
                    """, (new_size, final_finish, new_material, new_type, final_mica, new_weight, new_godown, new_rack,
                          edit_id))
                    conn.commit()
                    st.success(f"Item ID {edit_id} updated successfully!")
                    st.rerun()
        elif edit_id:
            st.warning(f"ID {edit_id} is not found or not available.")

    with tab2:
        st.write("Modify the Company, Price/KG, or Sold Quantity of an issued transaction.")

        conn_sales = sqlite3.connect('inventory.db')

        # Pull ALL historical sales data first so we can apply filters to it
        df_all_sales = pd.read_sql("""
            SELECT id AS [Sales ID], sale_date AS [Date], company_name AS [Company], 
                   size AS [Size], qty_sold AS [Qty Sold (KG)], price_per_kg AS [Rate/KG], stock_id
            FROM sales ORDER BY id DESC
        """, conn_sales)

        if df_all_sales.empty:
            st.info("No transaction tracking history recorded to edit yet.")
        else:
            # NEW: Filter block specifically for narrowing down sales records
            st.markdown("##### 🔍 Step 1: Filter Sales Logs")
            sf1, sf2 = st.columns(2)

            comp_opts = ["All Companies"] + list(df_all_sales['Company'].unique())
            selected_sales_comp = sf1.selectbox("Filter Sales by Company", comp_opts, key="sales_filter_comp")

            size_opts = ["All Sizes"] + list(df_all_sales['Size'].unique())
            selected_sales_size = sf2.selectbox("Filter Sales by Sheet Size", size_opts, key="sales_filter_size")

            # Apply the filter selections
            df_filtered_sales = df_all_sales.copy()
            if selected_sales_comp != "All Companies":
                df_filtered_sales = df_filtered_sales[df_filtered_sales['Company'] == selected_sales_comp]
            if selected_sales_size != "All Sizes":
                df_filtered_sales = df_filtered_sales[df_filtered_sales['Size'] == selected_sales_size]

            st.write(f"Matching Sales Entries Displayed: **{len(df_filtered_sales)}**")
            st.dataframe(df_filtered_sales.drop(columns=['stock_id']), use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("##### 💼 Step 2: Select Sales Record to Edit")

            if df_filtered_sales.empty:
                st.warning("No sales logs match the company and size selected above.")
            else:
                # NEW: Dropdown selector that contains ONLY the highly filtered choices
                sales_options = {
                    f"Sales ID: {row['Sales ID']} | Buyer: {row['Company']} | Size: {row['Size']} ({row['Qty Sold (KG)']} KG)":
                        row['Sales ID']
                    for _, row in df_filtered_sales.iterrows()
                }
                selected_sales_label = st.selectbox("Choose Target Sales ID", list(sales_options.keys()),
                                                    key="sales_id_picker_dropdown")
                sale_id_to_edit = sales_options[selected_sales_label]

                # Extract original parameters from historical row context
                matched_sale = df_all_sales[df_all_sales['Sales ID'] == sale_id_to_edit].iloc[0]
                orig_stock_id = int(matched_sale['stock_id'])
                orig_qty_sold = float(matched_sale['Qty Sold (KG)'])

                # Fetch live current weight balance remaining on the warehouse shelf
                cursor_stock = conn_sales.cursor()
                cursor_stock.execute("SELECT weight, status FROM stock WHERE id = ?", (orig_stock_id,))
                stock_record = cursor_stock.fetchone()

                if stock_record:
                    warehouse_balance = float(stock_record[0])
                    max_allowable_qty = warehouse_balance + orig_qty_sold

                    with st.form("edit_sales_form"):
                        new_company = st.text_input("Company Name", value=str(matched_sale['Company']))

                        sc1, sc2 = st.columns(2)
                        new_rate = sc1.number_input("Price per KG (INR)", min_value=0.0, step=1.0,
                                                    value=float(matched_sale['Rate/KG']))
                        new_qty = sc2.number_input("Quantity Sold (KG)", min_value=0.1, max_value=max_allowable_qty,
                                                   step=0.1, value=orig_qty_sold)

                        if st.form_submit_button("Save Sales Changes", type="primary"):
                            calculated_amount = round(new_qty * new_rate, 2)
                            qty_diff = round(new_qty - orig_qty_sold, 2)
                            updated_warehouse_weight = round(warehouse_balance - qty_diff, 2)

                            cursor_sales = conn_sales.cursor()
                            cursor_sales.execute("""
                                UPDATE sales 
                                SET company_name = ?, 
                                    price_per_kg = ?, 
                                    qty_sold = ?, 
                                    total_amount = ? 
                                WHERE id = ?
                            """, (new_company, new_rate, new_qty, calculated_amount, sale_id_to_edit))

                            if updated_warehouse_weight <= 0:
                                cursor_sales.execute("UPDATE stock SET weight = 0, status = 'Sold' WHERE id = ?",
                                                     (orig_stock_id,))
                            else:
                                cursor_sales.execute("UPDATE stock SET weight = ?, status = 'Available' WHERE id = ?",
                                                     (updated_warehouse_weight, orig_stock_id))

                            conn_sales.commit()
                            st.success(f"Sales ID {sale_id_to_edit} updated successfully!")
                            st.rerun()
                else:
                    st.error("The warehouse lot associated with this transaction row was permanently deleted.")
        conn_sales.close()

    # TAB 3: DELETE ONE SPECIFIC ENTRY
    with tab3:
        delete_id = st.number_input("Enter Item ID to Delete", min_value=1, step=1, key="del_id_input")
        confirm_single = st.checkbox(f"I confirm I want to permanently delete Item ID {delete_id}")
        if st.button("Delete Single Entry", type="primary", disabled=not confirm_single):
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stock WHERE id = ?", (delete_id,))
            conn.commit()
            st.success(f"Successfully deleted Item ID {delete_id}!")
            st.rerun()

    # TAB 4: REMOVE ALL ENTRIES FROM ONE RACK
    with tab4:
        selected_rack_to_clear = st.selectbox("Select Rack to Empty Completely",
                                              options=[""] + list(df['rack'].unique()))
        if selected_rack_to_clear:
            items_on_rack = df[df['rack'] == selected_rack_to_clear]
            st.warning(
                f"This action will delete ALL **{len(items_on_rack)}** items linked to Rack: **{selected_rack_to_clear}**")
            confirm_rack = st.checkbox(f"I confirm I want to wipe out all items from {selected_rack_to_clear}")
            if st.button(f"Wipe Rack {selected_rack_to_clear}", type="primary", disabled=not confirm_rack):
                cursor = conn.cursor()
                cursor.execute("DELETE FROM stock WHERE rack = ? AND status = 'Available'", (selected_rack_to_clear,))
                conn.commit()
                st.success(f"All stock records on Rack '{selected_rack_to_clear}' have been removed!")
                st.rerun()

    # -------------------------------------------------------------
    # NEW COMPONENT: HISTORICAL SALES PERFORMANCE LOG
    # -------------------------------------------------------------
    st.markdown("---")
    st.subheader("📈 Sales Dispatch & Customer Tracking Analysis")

    conn_sales = sqlite3.connect('inventory.db')
    try:
        sales_df = pd.read_sql("""
            SELECT 
                sale_date AS [Date/Time],
                company_name AS [Buyer Company],
                invoice_no AS [Orig. Inv],
                size AS [Size],
                mica_type AS [Mica],
                material AS [Material],
                type AS [Type],
                qty_sold AS [Qty Sold (KG)],
                price_per_kg AS [Rate/KG],
                total_amount AS [Total Value],
                notes AS [Special Notes]
            FROM sales 
            ORDER BY id DESC
        """, conn_sales)

        if not sales_df.empty:
            # High level monetization tracking metrics
            s_col1, s_col2 = st.columns(2)
            s_col1.metric("Gross Revenue Tracked", f"₹ {sales_df['Total Value'].sum():,.2f}")
            s_col2.metric("Total Weight Dispatched", f"{sales_df['Qty Sold (KG)'].sum():,.2f} KG")

            st.dataframe(sales_df, use_container_width=True, hide_index=True)
        else:
            st.info("No transaction tracking history found for this business period.")
    except Exception as e:
        st.info(
            "Sales tracking system ready. Execute your first order transaction to compile the ledger data view.")
    conn_sales.close()
    conn.close()