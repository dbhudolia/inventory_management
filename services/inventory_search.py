import streamlit as st
import psycopg2
import pandas as pd


def get_db_connection():
    """Establishes a password-safe connection to Supabase using separate parameters."""
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        database=st.secrets["postgres"]["database"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        port=st.secrets["postgres"]["port"]
    )


def inventory_search_management():
    st.title("🔍 Advanced Inventory Search & Rack Breakdown")
    st.info("Select a Godown and Rack to see a compressed packet breakdown of weights, or use global filters.")

    conn = get_db_connection()

    # -------------------------------------------------------------
    # GODOWN & RACK PACKET BREAKDOWN
    # -------------------------------------------------------------
    st.subheader("📦 Rack-Wise Packet Breakdown")
    st.write("See a consolidated summary of items and packet counts for a specific location.")

    loc_df = pd.read_sql("SELECT DISTINCT godown, rack FROM stock WHERE status = 'Available' AND weight > 0", conn)

    b_col1, b_col2 = st.columns(2)
    selected_g = b_col1.selectbox("Choose Godown for Breakdown", options=[""] + list(loc_df['godown'].unique()))

    if selected_g:
        available_racks = loc_df[loc_df['godown'] == selected_g]['rack'].unique()
    else:
        available_racks = loc_df['rack'].unique()

    selected_r = b_col2.selectbox("Choose Rack for Breakdown", options=[""] + list(available_racks))

    if selected_g and selected_r:
        breakdown_query = """
        SELECT 
            invoice_no AS "Invoice #", 
            size AS "Size", 
            finish AS "Finish", 
            material AS "Material", 
            "type" AS "Type", 
            mica_type AS "Mica Type", 
            weight AS "Weight (KG)",
            COUNT(id) AS "Total Packets",
            SUM(weight) AS "Total Weight (KG)"
        FROM stock 
        WHERE godown = %s AND rack = %s AND status = 'Available' AND weight > 0
        GROUP BY invoice_no, size, finish, material, "type", mica_type, weight
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
    query = """
        SELECT id, invoice_no, size, finish, material, "type", mica_type, weight, godown, rack, status 
        FROM stock 
        WHERE weight > 0 AND status = 'Available'
        """
    df = pd.read_sql(query, conn)

    if df.empty:
        st.warning("No available stock records found.")
        conn.close()
        return

    with st.expander("🛠️ Search Filters (Click to Expand)", expanded=True):
        f1, f2, f3 = st.columns(3)
        mica_filter = f1.multiselect("Mica Type", options=df['mica_type'].unique(), placeholder="All Mica")
        mat_filter = f2.multiselect("Material", options=df['material'].unique(), placeholder="All Materials")
        type_filter = f3.multiselect("Stock Type", options=df['type'].unique(), placeholder="All Types")

        f4, f5, f6 = st.columns(3)
        finish_filter = f4.multiselect("Finish", options=df['finish'].unique(), placeholder="All Finishes")
        godown_filter = f5.multiselect("Godown Location", options=df['godown'].unique(), placeholder="All Godowns")
        rack_filter = f6.multiselect("Specific Rack / Row", options=df['rack'].unique(), placeholder="All Racks")

        st.divider()
        text_search = st.text_input("Global Text Search (Invoice #, Size like 5*1000)")

    if mica_filter: df = df[df['mica_type'].isin(mica_filter)]
    if mat_filter: df = df[df['material'].isin(mat_filter)]
    if type_filter: df = df[df['type'].isin(type_filter)]
    if finish_filter: df = df[df['finish'].isin(finish_filter)]
    if godown_filter: df = df[df['godown'].isin(godown_filter)]
    if rack_filter: df = df[df['rack'].isin(rack_filter)]

    if text_search:
        df = df[
            df['invoice_no'].str.contains(text_search, case=False, regex=False) |
            df['size'].str.contains(text_search, case=False, regex=False) |
            df['rack'].str.contains(text_search, case=False, regex=False)
            ]

    st.subheader(f"Found {len(df)} Matching Individual Batches")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------
    # MANAGEMENT PANEL: EDIT & REMOVAL CONTROLS
    # -------------------------------------------------------------
    st.markdown("---")
    st.subheader("🛠️ Inventory Management Panel")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "✏️ Bulk Edit Stock",
        "💰 Edit Sales Records",
        "❌ Cancel/Delete Sales Entry",
        "🗑️ Delete Stock Entry",
        "💥 Clear Entire Rack"
    ])

    df_all_sales = pd.read_sql("""
        SELECT id AS "Sales ID", sale_date AS "Date", company_name AS "Company", 
               invoice_no AS "Invoice No", size AS "Size", qty_sold AS "Qty Sold (KG)", 
               price_per_kg AS "Rate/KG", stock_id 
        FROM sales ORDER BY id DESC
    """, conn)

    # TAB 1: BULK SELECT AND EDIT STOCK ENTRIES
    with tab1:
        st.write(
            "Select one or multiple Item IDs from the filtered search results above to apply changes across all of them at once.")
        available_ids = sorted(list(df['id'].unique()))
        selected_ids = st.multiselect("Select Item IDs to Edit in Bulk", options=available_ids,
                                      placeholder="Choose one or multiple IDs")

        if selected_ids:
            st.warning(
                f"⚠️ You have selected **{len(selected_ids)}** items to edit at the same time. Any values modified below will overwrite old records for all selected entries.")
            reference_row = df[df['id'] == selected_ids[0]].iloc[0]

            with st.form("bulk_edit_values_form"):
                new_invoice = st.text_input("Invoice Number", value=str(reference_row['invoice_no']))

                e_col1, e_col2 = st.columns(2)
                with e_col1:
                    new_size = st.text_input("Size", value=str(reference_row['size']))
                    new_material = st.selectbox("Material", ["Rigid", "Flexible", "Epoxy"],
                                                index=["Rigid", "Flexible", "Epoxy"].index(reference_row['material']) if
                                                reference_row['material'] in ["Rigid", "Flexible", "Epoxy"] else 0)
                    is_epoxy_edit = (new_material == "Epoxy")
                    new_finish = st.selectbox("Finish", ["Glass Cloth", "Steel", "Plain", "Polished", "N/A"],
                                              index=["Glass Cloth", "Steel", "Plain", "Polished", "N/A"].index(
                                                  reference_row['finish']) if reference_row['finish'] in ["Glass Cloth",
                                                                                                          "Steel",
                                                                                                          "Plain",
                                                                                                          "Polished",
                                                                                                          "N/A"] else 0,
                                              disabled=is_epoxy_edit)

                with e_col2:
                    new_mica = st.selectbox("Mica Type", ["Muscovite", "Phlogopite", "Phlogopite(EV)", "N/A"],
                                            index=["Muscovite", "Phlogopite", "Phlogopite(EV)", "N/A"].index(
                                                reference_row['mica_type']) if reference_row['mica_type'] in [
                                                "Muscovite", "Phlogopite", "Phlogopite(EV)", "N/A"] else 0,
                                            disabled=is_epoxy_edit)
                    new_type = st.selectbox("Stock Type", ["Fresh", "Seconds", "Cut", "Open", "Joint", "Damage", "Seconds (Assorted)"],
                                            index=["Fresh", "Seconds", "Cut", "Open", "Joint", "Damage"].index(
                                                reference_row['type']) if reference_row['type'] in ["Fresh", "Seconds",
                                                                                                    "Cut", "Open",
                                                                                                    "Joint",
                                                                                                    "Damage"] else 0)
                    new_weight = st.number_input("Weight per Packet (KG)", min_value=0.0, step=0.1,
                                                 value=float(reference_row['weight']))

                st.markdown("**Location Details (Use this to mass-transfer items across racks/godowns)**")
                loc_col1, loc_col2 = st.columns(2)
                new_godown = loc_col1.selectbox("Godown", ["Godown 1", "Godown 2"],
                                                index=["Godown 1", "Godown 2"].index(reference_row['godown']) if
                                                reference_row['godown'] in ["Godown 1", "Godown 2"] else 0)
                new_rack = loc_col2.text_input("Rack / Row Location", value=str(reference_row['rack']))

                if st.form_submit_button("Apply Changes to All Selected Packets", type="primary"):
                    final_finish = "N/A" if is_epoxy_edit else new_finish
                    final_mica = "N/A" if is_epoxy_edit else new_mica

                    cursor_edit = conn.cursor()
                    for target_id in selected_ids:
                        cursor_edit.execute("""
                            UPDATE stock 
                            SET invoice_no = %s, size = %s, finish = %s, material = %s, "type" = %s, mica_type = %s, weight = %s, godown = %s, rack = %s 
                            WHERE id = %s
                        """, (new_invoice, new_size, final_finish, new_material, new_type, final_mica, new_weight,
                              new_godown, new_rack, int(target_id)))

                    conn.commit()
                    cursor_edit.close()
                    st.success(f"🎉 Bulk update complete!")
                    st.rerun()

    # TAB 2: EDIT RECENT SALES ENTRIES (WITH DROPDOWN FOR CLIENT NAMES)
    with tab2:
        if df_all_sales.empty:
            st.info("No transaction tracking history recorded to edit yet.")
        else:
            st.markdown("##### 🔍 Step 1: Filter Sales Logs")
            sf1, sf2 = st.columns(2)

            comp_opts = ["All Companies"] + list(df_all_sales['Company'].unique())
            selected_sales_comp = sf1.selectbox("Filter Sales by Company", comp_opts, key="sales_filter_comp")

            size_opts = ["All Sizes"] + list(df_all_sales['Size'].unique())
            selected_sales_size = sf2.selectbox("Filter Sales by Sheet Size", size_opts, key="sales_filter_size")

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
                sales_options = {
                    f"Sales ID: {row['Sales ID']} | Buyer: {row['Company']} | Size: {row['Size']} ({row['Qty Sold (KG)']} KG)":
                        row['Sales ID']
                    for _, row in df_filtered_sales.iterrows()
                }
                selected_sales_label = st.selectbox("Choose Target Sales ID", list(sales_options.keys()),
                                                    key="sales_id_picker_dropdown")
                sale_id_to_edit = sales_options[selected_sales_label]

                matched_sale = df_all_sales[df_all_sales['Sales ID'] == sale_id_to_edit].iloc[0]
                orig_stock_id = int(matched_sale['stock_id'])
                orig_qty_sold = float(matched_sale['Qty Sold (KG)'])

                cursor_stock = conn.cursor()
                cursor_stock.execute("SELECT weight, status FROM stock WHERE id = %s", (orig_stock_id,))
                stock_record = cursor_stock.fetchone()

                if stock_record:
                    warehouse_balance = float(stock_record[0])
                    max_allowable_qty = warehouse_balance + orig_qty_sold

                    with st.form("edit_sales_form"):
                        # UPGRADED: Pull full distinct client list for editing tab consistency
                        cursor_edit_sales = conn.cursor()
                        cursor_edit_sales.execute(
                            "SELECT DISTINCT company_name FROM sales WHERE company_name IS NOT NULL AND company_name != '' ORDER BY company_name ASC")
                        known_companies = [r[0] for r in cursor_edit_sales.fetchall()]
                        cursor_edit_sales.close()

                        current_buyer_name = str(matched_sale['Company'])
                        if current_buyer_name not in known_companies:
                            known_companies.append(current_buyer_name)

                        edit_dropdown_opts = ["[+ Register New Company]"] + sorted(known_companies)

                        selected_edit_comp_opt = st.selectbox(
                            "Company Name",
                            options=edit_dropdown_opts,
                            index=edit_dropdown_opts.index(
                                current_buyer_name) if current_buyer_name in edit_dropdown_opts else 0
                        )

                        if selected_edit_comp_opt == "[+ Register New Company]":
                            new_company = st.text_input("Type New Company Name String", value="")
                        else:
                            new_company = selected_edit_comp_opt

                        new_sales_invoice = st.text_input("Invoice Number", value=str(matched_sale['Invoice No']))

                        sc1, sc2 = st.columns(2)
                        new_rate = sc1.number_input("Price per KG (INR)", min_value=0.0, step=1.0,
                                                    value=float(matched_sale['Rate/KG']))
                        new_qty = sc2.number_input("Quantity Sold (KG)", min_value=0.1, max_value=max_allowable_qty,
                                                   step=0.1, value=orig_qty_sold)

                        if st.form_submit_button("Save Sales Changes", type="primary"):
                            calculated_amount = round(new_qty * new_rate, 2)
                            qty_diff = round(new_qty - orig_qty_sold, 2)
                            updated_warehouse_weight = round(warehouse_balance - qty_diff, 2)

                            cursor_sales = conn.cursor()
                            cursor_sales.execute("""
                                UPDATE sales 
                                SET company_name = %s, 
                                    invoice_no = %s,
                                    price_per_kg = %s, 
                                    qty_sold = %s, 
                                    total_amount = %s 
                                WHERE id = %s
                            """, (new_company.strip(), new_sales_invoice, new_rate, new_qty, calculated_amount,
                                  int(sale_id_to_edit)))

                            if updated_warehouse_weight <= 0:
                                cursor_sales.execute("UPDATE stock SET weight = 0, status = 'Sold' WHERE id = %s",
                                                     (orig_stock_id,))
                            else:
                                cursor_sales.execute("UPDATE stock SET weight = %s, status = 'Available' WHERE id = %s",
                                                     (updated_warehouse_weight, orig_stock_id))

                            conn.commit()
                            cursor_sales.close()
                            st.success(f"Sales ID {sale_id_to_edit} updated successfully!")
                            st.rerun()
                else:
                    st.error("The warehouse lot associated with this transaction row was permanently deleted.")

    # TAB 3: CANCEL/DELETE SALES ENTRY
    with tab3:
        st.write(
            "Delete a sales entry completely. This will **automatically return the sold weight** back to the warehouse sheet entry.")
        if not df_all_sales.empty:
            sales_delete_options = {
                f"Sales ID: {row['Sales ID']} | Buyer: {row['Company']} | Size: {row['Size']} | Returned: {row['Qty Sold (KG)']} KG":
                    row['Sales ID'] for _, row in df_all_sales.iterrows()}
            selected_del_label = st.selectbox("Select Sales Entry to Delete & Reverse",
                                              [""] + list(sales_delete_options.keys()))

            if selected_del_label:
                sale_id_to_delete = sales_delete_options[selected_del_label]
                matched_del_sale = df_all_sales[df_all_sales['Sales ID'] == sale_id_to_delete].iloc[0]
                target_stock_id = int(matched_del_sale['stock_id'])
                return_weight = float(matched_del_sale['Qty Sold (KG)'])

                confirm_sales_wipe = st.checkbox(
                    f"Confirm reversal: Delete Sales ID {sale_id_to_delete} and add back {return_weight} KG to Stock ID {target_stock_id}")

                if st.button("Execute Sales Deletion", type="primary", disabled=not confirm_sales_wipe):
                    cursor_wipe = conn.cursor()
                    cursor_wipe.execute("""
                        UPDATE stock 
                        SET weight = weight + %s, 
                            status = 'Available' 
                        WHERE id = %s
                    """, (return_weight, target_stock_id))

                    cursor_wipe.execute("DELETE FROM sales WHERE id = %s", (int(sale_id_to_delete),))
                    conn.commit()
                    cursor_wipe.close()
                    st.success(f"Transaction reversed!")
                    st.rerun()
        else:
            st.info("No transaction records available to reverse.")

    # TAB 4: DELETE ONE SPECIFIC ENTRY
    with tab4:
        delete_id = st.number_input("Enter Item ID to Delete", min_value=1, step=1, key="del_id_input")
        confirm_single = st.checkbox("I confirm I want to permanently delete Item ID")
        if st.button("Delete Single Entry", type="primary", disabled=not confirm_single):
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stock WHERE id = %s", (int(delete_id),))
            conn.commit()
            cursor.close()
            st.success(f"Successfully deleted Item ID {delete_id}!")
            st.rerun()

    # TAB 5: REMOVE ALL ENTRIES FROM ONE RACK
    with tab5:
        selected_rack_to_clear = st.selectbox("Select Rack to Empty Completely",
                                              options=[""] + list(df['rack'].unique()))
        if selected_rack_to_clear:
            items_on_rack = df[df['rack'] == selected_rack_to_clear]
            st.warning(
                f"This action will delete ALL **{len(items_on_rack)}** items linked to Rack: **{selected_rack_to_clear}**")
            confirm_rack = st.checkbox(f"I confirm I want to wipe out all items from {selected_rack_to_clear}")
            if st.button(f"Wipe Rack {selected_rack_to_clear}", type="primary", disabled=not confirm_rack):
                cursor = conn.cursor()
                cursor.execute("DELETE FROM stock WHERE rack = %s AND status = 'Available'", (selected_rack_to_clear,))
                conn.commit()
                cursor.close()
                st.success(f"All stock records on Rack '{selected_rack_to_clear}' have been removed!")
                st.rerun()

    # -------------------------------------------------------------
    # HISTORICAL SALES PERFORMANCE LOG
    # -------------------------------------------------------------
    st.markdown("---")
    st.subheader("📈 Sales Dispatch & Customer Tracking Analysis")

    try:
        sales_df = pd.read_sql("""
            SELECT 
                sale_date AS "Date/Time",
                company_name AS "Buyer Company",
                invoice_no AS "Orig. Inv",
                size AS "Size",
                mica_type AS "Mica",
                material AS "Material",
                "type" AS "Type",
                qty_sold AS "Qty Sold (KG)",
                price_per_kg AS "Rate/KG",
                total_amount AS "Total Value",
                notes AS "Special Notes"
            FROM sales 
            ORDER BY id DESC
        """, conn)

        if not sales_df.empty:
            s_col1, s_col2 = st.columns(2)
            s_col1.metric("Gross Revenue Tracked", f"₹ {sales_df['Total Value'].sum():,.2f}")
            s_col2.metric("Total Weight Dispatched", f"{sales_df['Qty Sold (KG)'].sum():,.2f} KG")
            st.dataframe(sales_df, use_container_width=True, hide_index=True)
        else:
            st.info("No transaction tracking history found for this business period.")
    except Exception as e:
        st.info("Sales tracking system ready.")

    conn.close()