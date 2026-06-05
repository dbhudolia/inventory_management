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


def stock_position_summary():
    st.title("📦 Stock Position Summary")
    st.info(
        "Consolidated overview: Rows are compressed by item specifications to show packet counts and rack distribution.")

    conn = get_db_connection()

    # --- FETCH DYNAMIC DROPDOWN FILTER OPTIONS ---
    filter_data = pd.read_sql(
        'SELECT mica_type, material, "type" AS type, finish FROM stock WHERE status = \'Available\' AND weight > 0',
        conn
    )

    with st.expander("🛠️ Filter Stock Position (Click to Expand)", expanded=True):
        f1, f2, f3 = st.columns(3)
        mica_filter = f1.multiselect("Mica Type", options=filter_data['mica_type'].unique(), placeholder="All Mica")
        mat_filter = f2.multiselect("Material", options=filter_data['material'].unique(), placeholder="All Materials")
        type_filter = f3.multiselect("Stock Type", options=filter_data['type'].unique(), placeholder="All Types")

        f4, f5 = st.columns(2)
        finish_filter = f4.multiselect("Finish", options=filter_data['finish'].unique(), placeholder="All Finishes")
        text_search = st.text_input("Search by Invoice # or Rack name")

        st.divider()
        # --- NEW: THICKNESS SIZE FILTER CONTROLS ---
        st.markdown("##### 📏 Filter by Sheet Thickness (Value before the first '*')")
        t_col1, t_col2 = st.columns(2)
        min_thick = t_col1.number_input("Minimum Thickness (mm)", min_value=0.0, value=0.0, step=0.1,
                                        help="Show sizes where the first number is >= this value")
        max_thick = t_col2.number_input("Maximum Thickness (mm) [Leave 0.0 for No Upper Limit]", min_value=0.0,
                                        value=0.0, step=0.1, help="Show sizes where the first number is <= this value")

    # --- CONSOLIDATED PACKET QUERY (COMPRESSED REMOVING UNIT WEIGHT) ---
    base_query = """
    SELECT 
        main.invoice_no AS "Invoice #",
        main.size AS "Size", 
        main.finish AS "Finish", 
        main.material AS "Material", 
        main.type AS "Type",
        main.mica_type AS "Mica Type", 
        (SELECT COUNT(id) FROM stock 
         WHERE invoice_no = main.invoice_no AND size = main.size AND finish = main.finish 
           AND material = main.material AND "type" = main.type AND mica_type = main.mica_type 
           AND status = 'Available' AND weight > 0) AS "Total Packets",
        (SELECT SUM(weight) FROM stock 
         WHERE invoice_no = main.invoice_no AND size = main.size AND finish = main.finish 
           AND material = main.material AND "type" = main.type AND mica_type = main.mica_type 
           AND status = 'Available' AND weight > 0) AS "Total Weight (KG)",
        string_agg(main.rack_summary, ', ') AS "Rack Distribution"
    FROM (
        SELECT 
            invoice_no, size, finish, material, "type" AS type, mica_type,
            (godown || ' ' || rack || '(' || COUNT(id) || ' packets)') AS rack_summary
        FROM stock
        WHERE status = 'Available' AND weight > 0
        GROUP BY invoice_no, size, finish, material, "type", mica_type, godown, rack
    ) AS main
    GROUP BY main.invoice_no, main.size, main.finish, main.material, main.type, main.mica_type
    ORDER BY "Total Weight (KG)" DESC
    """

    df_position = pd.read_sql(base_query, conn)
    conn.close()

    if df_position.empty:
        st.warning("No active inventory stock to display.")
        return

    # --- APPLY DROP-DOWN FILTERS ---
    if mica_filter:
        df_position = df_position[df_position['Mica Type'].isin(mica_filter)]
    if mat_filter:
        df_position = df_position[df_position['Material'].isin(mat_filter)]
    if type_filter:
        df_position = df_position[df_position['Type'].isin(type_filter)]
    if finish_filter:
        df_position = df_position[df_position['Finish'].isin(finish_filter)]

    # --- NEW: APPLY THICKNESS FILTERING LOGIC ---
    def extract_thickness(size_str):
        try:
            # Splits string at the first '*' and grabs the first element
            if size_str and '*' in str(size_str):
                return float(str(size_str).split('*')[0].strip())
            return float(size_str)
        except ValueError:
            return 0.0  # Return 0 if the format is a plain string instead of numbers

    # Apply extractor to the Size column to run data range evaluations
    df_position['extracted_thickness'] = df_position['Size'].apply(extract_thickness)

    # Filter for minimum thickness boundary
    if min_thick > 0.0:
        df_position = df_position[df_position['extracted_thickness'] >= min_thick]

    # Filter for maximum thickness boundary (if specified)
    if max_thick > 0.0:
        df_position = df_position[df_position['extracted_thickness'] <= max_thick]

    # --- APPLY TEXT FILTERS ---
    if text_search:
        df_position = df_position[
            df_position['Invoice #'].str.contains(text_search, case=False, regex=False) |
            df_position['Size'].str.contains(text_search, case=False, regex=False) |
            df_position['Rack Distribution'].str.contains(text_search, case=False, regex=False)
            ]

    # --- DISPLAY CONSOLIDATED POSITION ---
    st.divider()
    st.subheader(f"Summary View: {len(df_position)} Unique Attribute Groups")

    # Drop the temporary extracted column before presenting the clean UI table to users
    final_display_df = df_position.drop(columns=['extracted_thickness'])
    st.dataframe(final_display_df, use_container_width=True, hide_index=True)